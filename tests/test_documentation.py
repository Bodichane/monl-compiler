"""Cross-cutting invariants of the repository's documentation."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

from monl.cli.dispatch import build_parser as build_monl_parser
from monl_platform.__main__ import ALIAS_DES_VERBES
from monl_platform.__main__ import VERBES as VERBES_PLATEFORME

RACINE = Path(__file__).resolve().parents[1]

# These documents tell a past state: their references are evidence, not
# instructions to apply to the current tree.
DOCUMENTS_HISTORIQUES = {
    "CHANGELOG.md": "journal des versions passées",
    "CLAUDE.md": "journal de travail conservé par le mainteneur",
    "CODEBASE_AUDIT.md": "photographie datée de l'audit du 11 août 2026",
    "docs/design_decisions.md": "journal chronologique des décisions de conception",
    **{
        f"docs/phase_{numero}_{nom}.md": "archive d'une phase de conception achevée"
        for numero, nom in (
            (3, "parser"),
            (4, "ast"),
            (5, "generator"),
            (6, "systeme_complet"),
            (7, "ia"),
        )
    },
}

# These names designate artifacts produced in a compiled project. Their absence
# from the repository is therefore normal, but every exception must stay in
# use.
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
    """The prefixes PACKAGING removes, read from `pyproject.toml`.

    A document describing the contents of a WHEEL cites `monl_platform/static/`,
    and that path does not exist in the repository: it lives under `src/` there.
    Refusing this spelling would force documenting `src/monl_platform/static/`,
    which would be FALSE — it happened while writing this witness, and the
    correction it caused had to be undone. *A guarantee that is too broad is not
    safer, it is wrong elsewhere* (point 84).

    The list is DERIVED from `package-dir`, never written here: the day the
    repository changes layout, the witness follows instead of lying.
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
    # A bare basename is an accepted ellipsis if it is unambiguous as to
    # existence: the documentation is not bound to repeat src/monl/.
    if "/" not in cible:
        noms = {Path(f).name for f in fichiers} | {Path(f).parent.name for f in fichiers}
        return cible in noms or (cible.endswith(".py") and cible[:-3] in noms)
    # A path as it appears in an INSTALLED package is valid too: packaging
    # removes the prefix declared by `package-dir`.
    candidats = [normalise, racine]
    candidats += [f"{prefixe}/{c}" for prefixe in RACINES_DE_PAQUETS
                  for c in (normalise, racine) if prefixe]
    return any(
        c in fichiers or any(f.startswith(c.rstrip("/") + "/") for f in fichiers)
        for c in candidats
    )


def _commandes_citees(texte: str) -> list[tuple[str, str]]:
    return [commande for code in MOTIF_CODE.findall(texte) for commande in MOTIF_CLI.findall(code)]


#: The README table that serves as the command reference. A verb shipped and
#: absent from this table exists for nobody.
TABLEAU_DES_COMMANDES = "README.md"

#: The verbs left out of the table, with their reason. `init` is the guided
#: dialogue, which the README presents everywhere as plain `monl` — repeating
#: it there under its internal name would confuse instead of inform.
VERBES_HORS_TABLEAU = {
    "init": "c'est `monl` sans argument, présenté comme tel dans tout le README",
}


def test_every_shipped_verb_is_documented():
    """The REVERSE direction: a command we ship and nobody names.

    The other witness refuses a cited verb that does not exist. This one refuses
    a verb that exists and that nothing cites — the symmetric defect, and the
    quieter of the two: `monl usage` was shipped, working, and documented
    NOWHERE. It is point 169's ruling on Python versions (*every tested version
    must be announced*), transposed to commands.

    The measurement covers the README TABLE and not "the word appears somewhere":
    three verbs were mentioned in passing in a sentence elsewhere, which does not
    make a reference one can look up.
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


def test_a_compiled_project_path_points_where_the_file_really_goes(tmp_path):
    """What the generated-files exemption let through.

    `FRONTEND_PROMPT.md` is produced by compilation, hence absent from the
    repository, hence exempted by the other witness — which therefore could not
    see that the README pointed to `Boutique/FRONTEND_PROMPT.md` while the file
    comes out in `Boutique/docs/`. *A guarantee that is too broad is not safer,
    it is wrong elsewhere* (point 84).

    The remedy is not to remove the exemption — absence from the repository is
    normal — but to check these paths against a REAL compilation. It is
    deterministic and offline, so the measurement is reliable and repeatable.
    """
    from monl.cli import compile_project

    cible = tmp_path / "projet"
    compile_project(str(RACINE / "exemples" / "01_portfolio.ml"), str(cible))
    produits = {p.relative_to(cible).as_posix() for p in cible.rglob("*") if p.is_file()}
    assert produits, "extracteur inopérant : la compilation n'a rien produit"
    par_nom = {}
    for chemin in produits:
        par_nom.setdefault(Path(chemin).name, []).append(chemin)

    # The search covers ALL the text, not only what is between backticks: the
    # original defect lived in a comment inside a `bash` block, that is exactly
    # where a reader copy-pastes. The pattern stays narrow — it only judges
    # files whose compilation really produced a namesake — so widening the
    # window does not widen what is accused.
    noms_juges = "|".join(re.escape(n) for n in sorted(par_nom) if n in FICHIERS_GENERES)
    assert noms_juges, "extracteur inopérant : aucun artefact généré à confronter"
    motif = re.compile(rf"([A-Za-z<][\w<>./-]*)/({noms_juges})\b")

    documents = _documents()
    fautes = []
    for doc, texte in documents.items():
        if doc in DOCUMENTS_HISTORIQUES:
            continue
        for prefixe, nom in motif.findall(texte):
            # A prefix that IS a folder of the repository talks about the
            # repository, not about a compiled project.
            if prefixe.split("/")[0] in {"src", "docs", "tests", "exemples",
                                         "deploy", "scripts", "demo"}:
                continue
            reels = par_nom[nom]
            attendu = {Path(r).parent.as_posix() for r in reels}
            # The prefix is the project name (`Boutique`, `<App>`) followed or
            # not by a subfolder: we compare what comes AFTER the name.
            sous = prefixe.split("/", 1)[1] if "/" in prefixe else ""
            if sous not in attendu:
                fautes.append(
                    f"{doc}: `{prefixe}/{nom}` — le fichier sort dans "
                    f"`<projet>/{sorted(attendu)[0] or '.'}/`")

    assert not fautes, "\n" + "\n".join(fautes)


def test_the_extractors_cannot_succeed_on_nothing():
    exemple = (
        "Voir `src/monl/cli/dispatch.py`, lancer `monl compile`, puis "
        "[le guide](docs/GUIDE.md). La suite avait 12 tests et 91,5 % de couverture."
    )
    assert _citations_de_fichiers(exemple) == ["src/monl/cli/dispatch.py"]
    assert _commandes_citees(exemple) == [("monl", "compile")]
    assert _liens(exemple) == ["docs/GUIDE.md"]
    assert MOTIF_CHIFFRE_TESTS.search(exemple)
    assert MOTIF_COUVERTURE.search(exemple)


def test_the_documentation_respects_the_repository_invariants():
    documents = _documents()
    assert documents, "extracteur inopérant : aucun document Markdown lu"
    fichiers = set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=RACINE, text=True
    ).splitlines())
    citations = {
        doc: _citations_de_fichiers(texte) for doc, texte in documents.items()
    }
    commandes = {doc: _commandes_citees(texte) for doc, texte in documents.items()}
    assert sum(map(len, citations.values())), "extracteur inopérant : aucun chemin extrait"
    assert sum(map(len, commandes.values())), "extracteur inopérant : aucun verbe CLI extrait"

    # The two programs dispatch differently, so the truth is read in two
    # different places — but in BOTH cases it is what the code RUNS, never a
    # list kept for the test.
    commandes_valides = {
        "monl": _commandes(build_monl_parser()),
        # The French aliases are served by the same dispatch: the design
        # journal, which stays in French, may cite them.
        "monl-platform": set(VERBES_PLATEFORME) | set(ALIAS_DES_VERBES),
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
