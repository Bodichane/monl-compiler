"""Invariants transverses de la documentation du dépôt."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

from monl.cli.dispatch import build_parser as build_monl_parser
from monl_platform.__main__ import VERBES as VERBES_PLATEFORME

RACINE = Path(__file__).resolve().parents[1]

# Ces documents racontent un état passé : leurs références sont des preuves,
# pas des instructions à appliquer à l'arbre courant.
DOCUMENTS_HISTORIQUES = {
    "CHANGELOG.md": "journal des versions passées",
    "CLAUDE.md": "journal de travail conservé par le mainteneur",
    "CODEBASE_AUDIT.md": "photographie datée de l'audit du 11 août 2026",
    "docs/design_decisions.md": "journal chronologique des décisions de conception",
    **{
        f"docs/phase_{numero}_{nom}.md": "archive d'une phase de conception achevée"
        for numero, nom in (
            (0, "cadrage"),
            (1, "model_conceptuel"),
            (2, "dsl"),
            (3, "parser"),
            (4, "ast"),
            (5, "generator"),
            (6, "systeme_complet"),
            (7, "ia"),
        )
    },
}

# Ces noms désignent des artefacts produits dans un projet compilé. Leur
# absence du dépôt est donc normale, mais chaque exception doit rester utilisée.
FICHIERS_GENERES = {
    "app.py": "backend FastAPI produit par la compilation",
    "schema.sql": "schéma SQL produit par la compilation",
    "manage.py": "outil d'administration produit par la compilation",
    "serve.py": "lanceur produit dans certains exemples",
    "sandbox_ai.py": "bac à sable métier produit par la compilation",
    "monl.json": "état de compilation produit dans le projet cible",
    "frontend_contract.json": "contrat frontend produit par la compilation",
    "FRONTEND_PROMPT.md": "brief frontend produit par la compilation",
    "FRONTEND_UPDATE_PROMPT.md": "brief de mise à jour produit par la compilation",
    "frontend": "dossier d'interface produit ou rempli dans le projet cible",
    "LISEZMOI.txt": "mode d'emploi produit avec l'export de contenu",
    "DESIGN_SYSTEM.md": "système de design produit dans le projet cible",
    "DESIGN_SPEC.md": "spécification visuelle produite dans le projet cible",
    "ASSET_MANIFEST.json": "manifeste d'assets produit dans le projet cible",
    "platform-projects": "espace de compilation créé par la plateforme",
    "projets": "anciens projets complets produits par les exemples",
    "dist": "répertoire d'artefacts produit par l'outil de packaging",
    "anciens": "sous-répertoire historique d'artefacts de packaging",
}

MOTIF_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
MOTIF_LIEN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
MOTIF_CLI = re.compile(r"(?<![\w-])(monl(?:-platform)?)\s+([a-z][a-z0-9-]*)\b")
MOTIF_CHIFFRE_TESTS = re.compile(r"\b\d[\d _]*(?:tests?|réussites?)\b", re.IGNORECASE)
MOTIF_COUVERTURE = re.compile(
    r"(?:\b\d+(?:[,.]\d+)?\s*%[^\n]{0,40}\bcouverture\b|"
    r"\bcouverture\b[^\n]{0,40}\b\d+(?:[,.]\d+)?\s*%)",
    re.IGNORECASE,
)
SUFFIXES_FICHIER = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".md", ".ml",
    ".py", ".sql", ".toml", ".txt", ".yaml", ".yml",
}


def _documents() -> dict[str, str]:
    chemins = list(RACINE.glob("*.md"))
    for dossier in ("docs", "exemples", "demo", "deploy"):
        base = RACINE / dossier
        if base.exists():
            chemins.extend(base.rglob("*.md"))
    return {p.relative_to(RACINE).as_posix(): p.read_text(encoding="utf-8") for p in chemins}


def _citations_de_fichiers(texte: str) -> list[str]:
    citations = []
    for brut in MOTIF_CODE.findall(texte):
        cible = brut.strip().rstrip(".,:;")
        if any(c in cible for c in " \n\t*{}[]()=<>|'\""):
            continue
        if "/" in cible or Path(cible).suffix.lower() in SUFFIXES_FICHIER:
            citations.append(cible)
    return citations


def _liens(texte: str) -> list[str]:
    return [cible.split(maxsplit=1)[0].strip("<>") for cible in MOTIF_LIEN.findall(texte)]


def _commandes(parseur: argparse.ArgumentParser) -> set[str]:
    return {
        choix
        for action in parseur._actions
        if isinstance(action, argparse._SubParsersAction)
        for choix in action.choices
    }


def _racines_de_paquets() -> tuple[str, ...]:
    """Les préfixes que le PACKAGING retire, lus sur `pyproject.toml`.

    Un document qui décrit le contenu d'une ROUE cite `monl_platform/static/`,
    et ce chemin n'existe pas dans le dépôt : il y vit sous `src/`. Refuser
    cette écriture forcerait à documenter `src/monl_platform/static/`, ce qui
    serait FAUX — c'est arrivé en écrivant ce témoin, et il a fallu défaire la
    correction qu'il avait provoquée. *Une garantie trop large n'est pas plus
    sûre, elle est fausse ailleurs* (point 84).

    La liste est DÉRIVÉE de `package-dir`, jamais écrite ici : le jour où le
    dépôt change de disposition, le témoin suit au lieu de mentir.
    """
    texte = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    bloc = re.search(r"\[tool\.setuptools\.package-dir\](.*?)(?:\n\[|\Z)",
                     texte, re.S)
    assert bloc, "extracteur inopérant : [tool.setuptools.package-dir] introuvable"
    racines = tuple(re.findall(r'=\s*"([^"]+)"', bloc.group(1)))
    assert racines, "extracteur inopérant : aucune racine de paquet lue"
    return racines


RACINES_DE_PAQUETS = _racines_de_paquets()


def _resout(citation: str, document: str, fichiers: set[str]) -> bool:
    cible = citation.split("#", 1)[0].split("?", 1)[0]
    if not cible:
        return True
    if re.match(r"^(?:https?://|ghcr\.io/|[/$~]|\$|[\w.+-]+://)", cible):
        return True
    normalise = os.path.normpath((Path(document).parent / cible).as_posix())
    racine = os.path.normpath(cible)
    # Un basename seul est une ellipse admise s'il est non ambigu quant à
    # l'existence : la documentation n'est pas tenue de répéter src/monl/.
    if "/" not in cible:
        noms = {Path(f).name for f in fichiers} | {Path(f).parent.name for f in fichiers}
        return cible in noms or (cible.endswith(".py") and cible[:-3] in noms)
    # Un chemin tel qu'il apparaît dans un paquet INSTALLÉ est valide aussi :
    # le packaging retire le préfixe déclaré par `package-dir`.
    candidats = [normalise, racine]
    candidats += [f"{prefixe}/{c}" for prefixe in RACINES_DE_PAQUETS
                  for c in (normalise, racine) if prefixe]
    return any(
        c in fichiers or any(f.startswith(c.rstrip("/") + "/") for f in fichiers)
        for c in candidats
    )


def _commandes_citees(texte: str) -> list[tuple[str, str]]:
    return [commande for code in MOTIF_CODE.findall(texte) for commande in MOTIF_CLI.findall(code)]


#: Le tableau du README qui fait office de référence des commandes. Un verbe
#: livré et absent de ce tableau n'existe pour personne.
TABLEAU_DES_COMMANDES = "README.md"

#: Les verbes qu'on ne met pas dans le tableau, avec leur raison. `init` est le
#: dialogue guidé, que le README présente partout comme `monl` tout court —
#: l'y répéter sous son nom interne embrouillerait au lieu d'informer.
VERBES_HORS_TABLEAU = {
    "init": "c'est `monl` sans argument, présenté comme tel dans tout le README",
}


def test_tout_verbe_livre_est_documente():
    """Le sens INVERSE : une commande qu'on livre et que personne ne nomme.

    L'autre témoin refuse un verbe cité qui n'existe pas. Celui-ci refuse un
    verbe qui existe et que rien ne cite — le défaut symétrique, et le plus
    silencieux des deux : `monl usage` était livré, fonctionnel, et documenté
    NULLE PART. C'est l'arbitrage du point 169 sur les versions de Python
    (*toute version éprouvée doit être annoncée*), transposé aux commandes.

    La mesure porte sur le TABLEAU du README et pas sur « le mot apparaît
    quelque part » : trois verbes étaient mentionnés au détour d'une phrase
    ailleurs, ce qui ne fait pas une référence consultable.
    """
    attendus = _commandes(build_monl_parser()) - set(VERBES_HORS_TABLEAU)
    assert attendus, "extracteur inopérant : aucun verbe lu sur le parseur"
    tableau = (RACINE / TABLEAU_DES_COMMANDES).read_text(encoding="utf-8")
    lignes = [ligne for ligne in tableau.splitlines()
              if ligne.startswith("| `monl")]
    assert lignes, "extracteur inopérant : tableau des commandes introuvable"
    documentes = {verbe for ligne in lignes
                  for _, verbe in MOTIF_CLI.findall(ligne)}

    manquants = sorted(attendus - documentes)
    assert not manquants, (
        f"verbes livrés et absents du tableau de {TABLEAU_DES_COMMANDES} : "
        f"{manquants}")

    perimes = sorted(set(VERBES_HORS_TABLEAU) - _commandes(build_monl_parser()))
    assert not perimes, f"exemption de verbe devenue inutile : {perimes}"


def test_un_chemin_de_projet_compile_pointe_ou_le_fichier_sort_vraiment(tmp_path):
    """Ce que l'exemption des fichiers générés laissait passer.

    `FRONTEND_PROMPT.md` est produit par la compilation, donc absent du dépôt,
    donc exempté par l'autre témoin — qui ne pouvait donc pas voir que le
    README envoyait vers `Boutique/FRONTEND_PROMPT.md` alors que le fichier
    sort dans `Boutique/docs/`. *Une garantie trop large n'est pas plus sûre,
    elle est fausse ailleurs* (point 84).

    Le remède n'est pas de retirer l'exemption — l'absence du dépôt est
    normale — mais de confronter ces chemins à une VRAIE compilation. Celle-ci
    est déterministe et hors ligne, donc la mesure est fiable et rejouable.
    """
    from monl.cli import compile_project

    cible = tmp_path / "projet"
    compile_project(str(RACINE / "exemples" / "01_portfolio.ml"), str(cible))
    produits = {p.relative_to(cible).as_posix() for p in cible.rglob("*") if p.is_file()}
    assert produits, "extracteur inopérant : la compilation n'a rien produit"
    par_nom = {}
    for chemin in produits:
        par_nom.setdefault(Path(chemin).name, []).append(chemin)

    # La recherche porte sur TOUT le texte, pas seulement sur ce qui est entre
    # backticks : le défaut d'origine vivait dans un commentaire à l'intérieur
    # d'un bloc `bash`, c'est-à-dire exactement là où un lecteur copie-colle.
    # Le motif reste étroit — il ne juge que les fichiers dont la compilation
    # a réellement produit un homonyme — donc élargir la fenêtre n'élargit pas
    # ce qu'on accuse.
    noms_juges = "|".join(re.escape(n) for n in sorted(par_nom) if n in FICHIERS_GENERES)
    assert noms_juges, "extracteur inopérant : aucun artefact généré à confronter"
    motif = re.compile(rf"([A-Za-z<][\w<>./-]*)/({noms_juges})\b")

    documents = _documents()
    fautes = []
    for doc, texte in documents.items():
        if doc in DOCUMENTS_HISTORIQUES:
            continue
        for prefixe, nom in motif.findall(texte):
            # Un préfixe qui EST un dossier du dépôt parle du dépôt, pas d'un
            # projet compilé.
            if prefixe.split("/")[0] in {"src", "docs", "tests", "exemples",
                                         "deploy", "scripts", "demo"}:
                continue
            reels = par_nom[nom]
            attendu = {Path(r).parent.as_posix() for r in reels}
            # Le préfixe est le nom du projet (`Boutique`, `<App>`) suivi ou
            # non d'un sous-dossier : on compare ce qui vient APRÈS le nom.
            sous = prefixe.split("/", 1)[1] if "/" in prefixe else ""
            if sous not in attendu:
                fautes.append(
                    f"{doc}: `{prefixe}/{nom}` — le fichier sort dans "
                    f"`<projet>/{sorted(attendu)[0] or '.'}/`")

    assert not fautes, "\n" + "\n".join(fautes)


def test_les_extracteurs_ne_peuvent_pas_reussir_a_vide():
    exemple = (
        "Voir `src/monl/cli/dispatch.py`, lancer `monl compile`, puis "
        "[le guide](docs/GUIDE.md). La suite avait 12 tests et 91,5 % de couverture."
    )
    assert _citations_de_fichiers(exemple) == ["src/monl/cli/dispatch.py"]
    assert _commandes_citees(exemple) == [("monl", "compile")]
    assert _liens(exemple) == ["docs/GUIDE.md"]
    assert MOTIF_CHIFFRE_TESTS.search(exemple)
    assert MOTIF_COUVERTURE.search(exemple)


def test_la_documentation_respecte_les_invariants_du_depot():
    documents = _documents()
    assert documents, "extracteur inopérant : aucun document Markdown lu"
    fichiers = set(subprocess.check_output(
        ["git", "ls-files"], cwd=RACINE, text=True
    ).splitlines())
    citations = {
        doc: _citations_de_fichiers(texte) for doc, texte in documents.items()
    }
    commandes = {doc: _commandes_citees(texte) for doc, texte in documents.items()}
    assert sum(map(len, citations.values())), "extracteur inopérant : aucun chemin extrait"
    assert sum(map(len, commandes.values())), "extracteur inopérant : aucun verbe CLI extrait"

    # Les deux programmes dispatchent différemment, donc la vérité se lit à
    # deux endroits différents — mais dans les DEUX cas c'est ce que le code
    # EXÉCUTE, jamais une liste tenue pour le test.
    commandes_valides = {
        "monl": _commandes(build_monl_parser()),
        "monl-platform": set(VERBES_PLATEFORME),
    }
    assert all(commandes_valides.values()), (
        "extracteur inopérant : un programme ne déclare aucun verbe")
    erreurs: list[str] = []
    historiques_utilises: set[str] = set()
    generes_utilises: set[str] = set()

    for doc, texte in documents.items():
        problemes_doc: list[str] = []
        for citation in citations[doc]:
            nom = Path(citation).name
            genere = nom if nom in FICHIERS_GENERES else next(
                (partie for partie in Path(citation).parts if partie in FICHIERS_GENERES),
                None,
            )
            if genere is not None and (
                "/" not in citation.rstrip("/") or not _resout(citation, doc, fichiers)
            ):
                generes_utilises.add(genere)
            elif not _resout(citation, doc, fichiers):
                problemes_doc.append(f"chemin inexistant `{citation}`")

        for programme, verbe in commandes[doc]:
            if verbe not in commandes_valides[programme]:
                problemes_doc.append(f"verbe CLI inexistant `{programme} {verbe}`")

        for cible in _liens(texte):
            if re.match(r"^(?:https?://|mailto:|#)", cible):
                continue
            if not _resout(cible, doc, fichiers):
                problemes_doc.append(f"lien local inexistant `{cible}`")

        if MOTIF_CHIFFRE_TESTS.search(texte):
            problemes_doc.append("nombre de tests figé dans un document prescriptif")
        if MOTIF_COUVERTURE.search(texte):
            problemes_doc.append("pourcentage de couverture figé dans un document prescriptif")

        if doc in DOCUMENTS_HISTORIQUES:
            if problemes_doc or "Document historique" in texte:
                historiques_utilises.add(doc)
        else:
            erreurs.extend(f"{doc}: {probleme}" for probleme in problemes_doc)

    historiques_absents = set(DOCUMENTS_HISTORIQUES) - set(documents)
    historiques_inutiles = set(DOCUMENTS_HISTORIQUES) - historiques_utilises
    generes_inutiles = set(FICHIERS_GENERES) - generes_utilises
    erreurs.extend(f"exemption historique absente: {doc}" for doc in sorted(historiques_absents))
    erreurs.extend(f"exemption historique devenue inutile: {doc}" for doc in sorted(historiques_inutiles))
    erreurs.extend(f"exemption de fichier généré devenue inutile: {nom}" for nom in sorted(generes_inutiles))
    assert not erreurs, "\n" + "\n".join(erreurs)
