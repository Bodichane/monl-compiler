"""Lire la réponse du modèle, et l'écrire sur le disque."""

import json
import os
import re
from xml.etree import ElementTree

from ..design_system import ASSET_MANIFEST_FILENAME, DESIGN_SPEC_FILENAME, DESIGN_SYSTEM_FILENAME
from . import fondations

# ------------------------------------------------------- parsing + gardes --
# Tabulation, saut de ligne et retour chariot sont les seuls caractères de
# contrôle légitimes dans un fichier texte livré.
_CONTROLES_AUTORISES = {"\t", "\n", "\r"}

def _refuser_caracteres_de_controle(path, content):
    """Refuse un fichier porteur de caractères de contrôle, NUL en tête.

    Un modèle qui écrit ses accents en échappement Unicode peut produire
    `\\u0000` là où il visait `\\u00e8` : `json.loads` rend alors un octet NUL,
    le fichier reste de l'UTF-8 PARFAITEMENT VALIDE, et plus rien en aval ne
    s'en aperçoit. Mesuré sur un site réellement construit — « Animalière »
    livré en « Animali\x00re », trente et un octets NUL dans un index.html
    déclaré réussi. Refuser ici plutôt que plus loin donne au modèle sa reprise
    ciblée, au lieu de publier un texte français mutilé.
    """
    fautifs = {
        caractere for caractere in content
        if ord(caractere) < 32 and caractere not in _CONTROLES_AUTORISES
    }
    if not fautifs:
        return
    nombre = sum(content.count(caractere) for caractere in fautifs)
    noms = ", ".join(f"U+{ord(c):04X}" for c in sorted(fautifs))
    raise fondations.FrontendAIError(
        f"caractère de contrôle interdit dans {path} : {noms} "
        f"({nombre} occurrence(s)) — un accent mal échappé produit ce défaut, "
        "et le fichier reste de l'UTF-8 valide.")

def _validate_files(files, require_index=True):
    """Valide une map de fichiers sans imposer son format de transport."""
    if not isinstance(files, dict) or not files:
        raise fondations.FrontendAIError("réponse du modèle sans clé 'files' exploitable")
    if require_index and "index.html" not in files:
        raise fondations.FrontendAIError("'index.html' absent de la réponse (obligatoire)")

    total = 0
    for path, content in files.items():
        norm = path.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            raise fondations.FrontendAIError(f"chemin refusé (doit rester dans frontend/) : {path}")
        if not norm.endswith(fondations.ALLOWED_EXTENSIONS):
            raise fondations.FrontendAIError(f"extension refusée : {path}")
        if not isinstance(content, str):
            raise fondations.FrontendAIError(f"contenu non textuel pour : {path}")
        _refuser_caracteres_de_controle(path, content)
        if norm.lower().endswith(".svg"):
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError as exc:
                raise fondations.FrontendAIError(f"SVG invalide ou incomplet : {path}") from exc
            if root.tag.rsplit("}", 1)[-1].lower() != "svg":
                raise fondations.FrontendAIError(f"SVG invalide ou incomplet : {path}")
            # Le namespace XML standard `xmlns="http://www.w3.org/2000/svg"`
            # est obligatoire et ne télécharge rien. Ne pas le confondre avec
            # une vraie ressource distante dans href/src/url().
            if re.search(
                    r"(?:\b(?:href|src|xlink:href)\s*=\s*['\"]"
                    r"(?:https?:|//)|\burl\(\s*['\"]?(?:https?:|//))",
                    content, re.IGNORECASE):
                raise fondations.FrontendAIError(
                    f"SVG non autonome (ressource externe) : {path}")
        total += len(content.encode("utf-8"))
    if total > fondations.MAX_TOTAL_BYTES:
        raise fondations.FrontendAIError(f"réponse trop volumineuse ({total} octets)")
    return files

def _json_payload(raw_text):
    """Décode une réponse JSON, avec tolérance aux clôtures Markdown."""
    text = raw_text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise fondations.FrontendAIError(f"réponse du modèle illisible (JSON attendu) : {e}") from e

def parse_files_payload(raw_text):
    """Extrait {chemin: contenu} de la réponse du modèle, avec les mêmes
    garde-fous que pour toute entrée non fiable."""
    payload = _json_payload(raw_text)
    return _validate_files(payload.get("files"), require_index=True)

#: Un bloc clôturé Markdown, avec ou sans nom de langage. Le contenu est
#: capturé tel quel : c'est un FICHIER, pas du JSON.
_BLOC_CLOTURE = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?```", re.DOTALL)

def _fichier_depuis_un_bloc(raw_text, expected_path):
    """Repli : le modèle a rendu le FICHIER, pas un JSON qui le contient.

    Une étape séquentielle doit emballer tout un fichier JavaScript dans une
    chaîne JSON — chaque saut de ligne échappé, chaque guillemet doublé. C'est
    là que les modèles bon marché cassent, et le prix est lourd : mesuré sur
    une construction réelle, `app.js` a échoué deux fois puis rendu 834 jetons
    — un fichier minuscule mais ANALYSABLE. La boucle de reprise optimise la
    lisibilité, jamais la complétude, et un quart du budget est parti là.

    L'enveloppe JSON n'apporte d'ailleurs rien ici : l'étape SAIT quel fichier
    elle attend. Le contrat JSON reste la voie normale — ceci n'est qu'un
    filet, et il passe par les MÊMES garde-fous (`_validate_files`) : extension,
    confinement, taille, caractères de contrôle. Aucune voie ne les contourne.
    """
    # Une réponse TRONQUÉE ne doit jamais passer par ici. Un nombre IMPAIR de
    # clôtures dit qu'un bloc est resté ouvert : la réponse a été coupée. Sans
    # ce contrôle, un modèle qui illustre par un petit extrait fermé puis se
    # fait couper au milieu du vrai fichier verrait son EXTRAIT écrit dans
    # app.js — et l'échelle d'agrandissement du plafond, qui existe justement
    # pour ce cas, ne serait jamais atteinte.
    if raw_text.count("```") % 2:
        return None
    blocs = [bloc for bloc in _BLOC_CLOTURE.findall(raw_text) if bloc.strip()]
    if not blocs:
        return None
    # Le PLUS GROS bloc : un modèle bavard commente sa réponse par de petits
    # extraits avant de rendre le fichier.
    contenu = max(blocs, key=len)
    # Un bloc qui EST le JSON attendu n'est pas un fichier : l'écrire tel quel
    # déposerait `{"files": …}` dans app.js, ce qui parse et ne marche pas.
    if contenu.lstrip().startswith("{"):
        return None
    # La clôture avale le dernier saut de ligne : un fichier source se termine
    # par un saut de ligne, on le rétablit plutôt que de livrer une dernière
    # ligne collée à rien.
    contenu = contenu.rstrip("\n") + "\n"
    return _validate_files({expected_path: contenu}, require_index=False)

def parse_single_file_payload(raw_text, expected_path):
    """Décode la réponse d'une étape de génération séquentielle.

    Le transport normal reste ``{"files": {…}}`` — même contrat JSON que la
    voie monolithique. Quand il est illisible, on retombe sur le fichier rendu
    en bloc clôturé plutôt que de brûler une reprise (voir
    ``_fichier_depuis_un_bloc``).
    """
    try:
        payload = _json_payload(raw_text)
        files = _validate_files(payload.get("files"), require_index=False)
    except fondations.FrontendAIError:
        secours = _fichier_depuis_un_bloc(raw_text, expected_path)
        if secours is None:
            raise
        return secours
    if set(files) != {expected_path}:
        rendus = ", ".join(sorted(files))
        raise fondations.FrontendAIError(
            f"l'étape devait rendre uniquement {expected_path}, reçu : {rendus}")
    return files

def _write_files(project_dir, files):
    frontend_dir = os.path.join(project_dir, "frontend")
    os.makedirs(frontend_dir, exist_ok=True)
    for path, content in files.items():
        dest = os.path.join(frontend_dir, path.replace("\\", "/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
    return frontend_dir

def _restaurer_frontend(project_dir, instantane):
    """Remet le frontend dans l'état exact d'un instantané.

    Ciblée à dessein : seuls les fichiers de la LISTE BLANCHE sont touchés.
    Effacer le dossier emporterait les images générées, qui n'y sont pas
    soumises et que personne ne rejouerait sans repayer.
    """
    frontend_dir = os.path.join(project_dir, "frontend")
    for rel in set(_read_existing_frontend(project_dir)) - set(instantane):
        os.remove(os.path.join(frontend_dir, rel))
    return _write_files(project_dir, instantane)

def _read_existing_frontend(project_dir):
    frontend_dir = os.path.join(project_dir, "frontend")
    snapshot = {}
    if not os.path.isdir(frontend_dir):
        return snapshot
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, frontend_dir)
            if name.endswith(fondations.ALLOWED_EXTENSIONS):
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    snapshot[rel] = fh.read()
    return snapshot

def _project_guidance(project_dir):
    """Ajoute les artefacts de direction préparés par l'auteur au brief IA."""
    blocks = []
    for name in (DESIGN_SYSTEM_FILENAME, DESIGN_SPEC_FILENAME,
                 ASSET_MANIFEST_FILENAME):
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                blocks.append(f"\n\n## {name} — source de vérité\n{fh.read()}")
    return "".join(blocks)
