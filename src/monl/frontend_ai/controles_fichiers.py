"""Ce que le site livré RÉCLAME, et qui doit être servi."""

import json
import os
import posixpath
import re
from html import unescape

# Une référence construite à l'exécution (gabarit JS, moteur de template)
# n'est pas un chemin de fichier : `src="${esc(p.imageUrl)}"` désigne une
# image que l'API renverra, pas un fichier à trouver sur le disque.
_REFERENCE_DYNAMIQUE = re.compile(r"\$\{|\{\{|<%")

_BALISE_RESSOURCE = re.compile(
    r"<(?:img|script|link|source|video|audio|object)\b[^>]*?"
    r"\b(?:src|href|data)=['\"]([^'\"]+)['\"]",
    re.IGNORECASE | re.DOTALL,
)

# Seulement les affectations de ressource explicites. Ne pas confondre un
# fetch('/booking') ou un lien de navigation avec un fichier statique.
_RESSOURCE_JS = re.compile(
    r"\.(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]|"
    r"setAttribute\(\s*['\"](?:src|href)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_URL_CSS = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.IGNORECASE)

def _sans_corps_de_script(html):
    """Retire le CORPS des <script>, en gardant les balises elles-mêmes.

    Le contenu d'un <script> n'est pas du balisage : le lire comme tel fait
    prendre le gabarit `<img src="${...}">` d'une fonction de rendu pour une
    vraie balise. La balise ouvrante est conservée, sans quoi le
    `<script src="app.js">` légitime disparaîtrait du contrôle.
    """
    return re.sub(r"(<script\b[^>]*>)(.*?)(</script\s*>)",
                  lambda m: m.group(1) + m.group(3), html,
                  flags=re.IGNORECASE | re.DOTALL)

def _declared_link_errors(project_dir, rendered_source):
    """Un lien déclaré dans la spec doit se retrouver dans le site livré.

    C'est le pendant exact du contrôle des assets (point 83) : monl ne
    vérifie pas qu'une adresse RÉPOND — il ne fait aucun appel réseau — mais
    il vérifie qu'elle est bien PRÉSENTE. Sans ça, l'auteur déclare son
    Instagram, l'IA l'oublie, et personne ne s'en aperçoit avant de chercher
    le lien sur le site en ligne.

    La comparaison porte sur l'adresse et non sur le libellé : un libellé peut
    légitimement être reformulé par l'interface, une adresse jamais.
    """
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if not os.path.exists(contract_path):
        return []
    try:
        with open(contract_path, encoding="utf-8") as fh:
            liens = json.load(fh).get("links") or []
    except (OSError, json.JSONDecodeError):
        return []
    source = unescape(rendered_source)
    return [
        f"lien déclaré absent du site : « {lien['label']} » → {lien['url']}"
        for lien in liens if lien["url"] not in source
    ]

def _frontend_local_reference_errors(project_dir):
    """Vérifie les ressources locales réellement référencées par le site.

    Le smoke test exécute le JavaScript et les routes API, mais ne télécharge
    pas les images et ne charge pas les feuilles CSS comme un navigateur. Ce
    contrôle complète donc le smoke test : il refuse les CDN, les chemins qui
    ne sont servis par aucun montage, et chaque fichier local absent. Les
    liens externes de navigation restent légitimes.

    La résolution suit la carte RÉELLE de ``serve.py`` (voir serving.py), pas
    une intuition sur ``frontend/`` : ``frontend/`` est monté sur ``/site`` et
    le dossier d'assets déclaré par la spec sur ``/site/<assets_dir>``. Chaque
    référence est donc calculée en URL comme le ferait le navigateur, puis
    ramenée au disque par ces deux montages. Un chemin absolu n'est pas fautif
    en soi — ``/site/assets/photo.png`` est exactement ce que sert le wrapper ;
    c'est ``/assets/photo.png``, servi par personne, qui l'est.
    """
    frontend_dir = os.path.join(project_dir, "frontend")
    errors = []
    assets_dir = None
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if os.path.exists(contract_path):
        try:
            with open(contract_path, encoding="utf-8") as fh:
                assets_dir = (json.load(fh).get("assets") or {}).get("dir")
        except (OSError, json.JSONDecodeError):
            assets_dir = None
    prefixe_assets = (assets_dir or "").strip("/")
    # Le wrapper ne monte le dossier d'assets que `if os.path.isdir(...)` :
    # déclaré dans la spec ne veut pas dire présent sur le disque. Quand il
    # est absent, aucune route n'est enregistrée et Starlette laisse la
    # requête retomber sur /site, donc `assets/x.webp` est servi depuis
    # `frontend/assets/x.webp`. Vérifié contre un vrai serveur : croire le
    # contrat sur parole faisait refuser trois images de KoraMaison qui
    # répondent 200.
    monte_assets = bool(prefixe_assets) and os.path.isdir(
        os.path.join(project_dir, prefixe_assets))

    def fichier_servi(url):
        """Le fichier disque servi pour une URL, ou None si rien ne la sert."""
        if url != "/site" and not url.startswith("/site/"):
            return None
        reste = url[len("/site"):].lstrip("/")
        if monte_assets and (reste == prefixe_assets
                             or reste.startswith(prefixe_assets + "/")):
            # Monté AVANT /site par le wrapper : ce dossier vit hors de
            # frontend/, à la racine du projet (brique 13, point 83).
            chemin = os.path.join(project_dir, reste)
        else:
            chemin = os.path.join(frontend_dir, reste)
        # StaticFiles(html=True) sert l'index d'un dossier.
        if os.path.isdir(chemin):
            chemin = os.path.join(chemin, "index.html")
        return chemin

    def check(origin, reference):
        ref = reference.strip()
        if not ref or ref.startswith(("#", "data:", "blob:", "mailto:", "tel:")):
            return
        if re.match(r"^(?:https?:)?//", ref, re.IGNORECASE):
            errors.append(f"ressource externe interdite (CDN ou URL distante) : {origin} → {ref}")
            return
        # monl ne peut rien affirmer d'une référence construite à l'exécution :
        # il se tait plutôt que de deviner un fichier (même arbitrage que le
        # contrôle d'existence des assets, point 83).
        if _REFERENCE_DYNAMIQUE.search(ref):
            return
        clean = ref.split("#", 1)[0].split("?", 1)[0].strip()
        if not clean:
            return
        if clean.startswith("/"):
            url = posixpath.normpath(clean)
        else:
            url = posixpath.normpath(
                posixpath.join("/site", posixpath.dirname(origin), clean))
        candidat = fichier_servi(url)
        if candidat is None:
            errors.append(
                f"ressource jamais servie (hors de /site) : {origin} → {ref}")
            return
        if not os.path.isfile(candidat):
            relatif = os.path.relpath(candidat, project_dir).replace(os.sep, "/")
            errors.append(f"ressource locale absente : {relatif} (référencée par {origin})")

    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith((".html", ".css", ".js")):
                continue
            path = os.path.join(root, name)
            try:
                content = open(path, encoding="utf-8", errors="ignore").read()
            except OSError as exc:
                errors.append(f"frontend illisible : {path} — {exc}")
                continue
            origin = os.path.relpath(path, frontend_dir).replace(os.sep, "/")
            if name.endswith(".html"):
                for ref in _BALISE_RESSOURCE.findall(_sans_corps_de_script(content)):
                    check(origin, ref)
            elif name.endswith(".js"):
                for match in _RESSOURCE_JS.finditer(content):
                    check(origin, match.group(1) or match.group(2))
            elif name.endswith(".css"):
                for ref in _URL_CSS.findall(content):
                    check(origin, ref)
    return list(dict.fromkeys(errors))

def _frontend_behavioral_quality_errors(project_dir):
    """Repère un piège fréquent des interfaces générées : les IDs DOM.

    ``dataset`` fournit toujours des chaînes alors que les IDs JSON sont
    généralement numériques. Une recherche stricte non normalisée rend les
    actions Modifier/Supprimer visuellement présentes mais inopérantes.
    Ce contrôle reste volontairement étroit pour ne pas prétendre parser le
    JavaScript ; il bloque uniquement le motif prouvé et corrigeable.
    """
    frontend_dir = os.path.join(project_dir, "frontend")
    errors = []
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith(".js"):
                continue
            path = os.path.join(root, name)
            try:
                content = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for match in re.finditer(
                    r"\b(?:const|let|var)\s+(\w+)\s*=\s*[^;\n]*\.dataset\.\w+",
                    content):
                variable = match.group(1)
                suffix = content[match.start():match.end()]
                if re.search(r"\b(?:Number|parseInt|parseFloat)\s*\(", suffix):
                    continue
                if re.search(rf"\.id\s*===\s*{re.escape(variable)}\b", content):
                    origin = os.path.relpath(path, frontend_dir).replace(os.sep, "/")
                    errors.append(
                        f"identifiant DOM non normalisé dans frontend/{origin} : "
                        f"{variable} vient de dataset et est comparé à un ID API ; "
                        "convertir avec Number() ou parseInt() avant Modifier/Supprimer.")
    return list(dict.fromkeys(errors))
