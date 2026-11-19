"""Cross-cutting invariants of the repository's documentation."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

from monl.cli.dispatch import build_parser as build_monl_parser
from monl_platform.__main__ import ALIAS_OF_VERBS
from monl_platform.__main__ import VERBS as VERBS_PLATFORM

RACINE = Path(__file__).resolve().parents[1]

# These documents tell a past state: their references are evidence, not
# instructions to apply to the current tree.
DOCUMENTS_HISTORICAL = {
    "CHANGELOG.md": "journal des versions passées",
    "CLAUDE.md": "journal de travail conservé par le mainteneur",
    "CODEBASE_AUDIT.md": "photographie datée de l'audit du 11 août 2026",
    "docs/design_decisions.md": "journal chronologique des décisions de conception",
    **{
        f"docs/phase_{number}_{name}.md": "archive d'une phase de conception achevée"
        for number, name in (
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
FILES_GENERATED = {
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
MOTIF_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
MOTIF_CLI = re.compile(r"(?<![\w-])(monl(?:-platform)?)\s+([a-z][a-z0-9-]*)\b")
MOTIF_DIGIT_TESTS = re.compile(r"\b\d[\d _]*(?:tests?|réussites?)\b", re.IGNORECASE)
MOTIF_COVERAGE = re.compile(
    r"(?:\b\d+(?:[,.]\d+)?\s*%[^\n]{0,40}\bcouverture\b|"
    r"\bcouverture\b[^\n]{0,40}\b\d+(?:[,.]\d+)?\s*%)",
    re.IGNORECASE,
)
SUFFIXES_FILE = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".md", ".ml",
    ".py", ".sql", ".toml", ".txt", ".yaml", ".yml",
}


def _documents() -> dict[str, str]:
    paths = list(RACINE.glob("*.md"))
    for folder in ("docs", "exemples", "demo", "deploy"):
        base = RACINE / folder
        if base.exists():
            paths.extend(base.rglob("*.md"))
    return {p.relative_to(RACINE).as_posix(): p.read_text(encoding="utf-8") for p in paths}


def _file_citations(text: str) -> list[str]:
    citations = []
    for brut in MOTIF_CODE.findall(text):
        target = brut.strip().rstrip(".,:;")
        if any(c in target for c in " \n\t*{}[]()=<>|'\""):
            continue
        if "/" in target or Path(target).suffix.lower() in SUFFIXES_FILE:
            citations.append(target)
    return citations


def _links(text: str) -> list[str]:
    return [target.split(maxsplit=1)[0].strip("<>") for target in MOTIF_LINK.findall(text)]


def _orders(parser: argparse.ArgumentParser) -> set[str]:
    return {
        choice
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
        for choice in action.choices
    }


def _package_roots() -> tuple[str, ...]:
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
    text = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"\[tool\.setuptools\.package-dir\](.*?)(?:\n\[|\Z)",
                     text, re.S)
    assert block, "extractor not working: [tool.setuptools.package-dir] not found"
    roots = tuple(re.findall(r'=\s*"([^"]+)"', block.group(1)))
    assert roots, "extractor not working: no package root read"
    return roots


ROOTS_OF_PACKAGES = _package_roots()


def _resolves(citation: str, document: str, files: set[str]) -> bool:
    target = citation.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return True
    if re.match(r"^(?:https?://|ghcr\.io/|[/$~]|\$|[\w.+-]+://)", target):
        return True
    normalise = os.path.normpath((Path(document).parent / target).as_posix())
    racine = os.path.normpath(target)
    # A bare basename is an accepted ellipsis if it is unambiguous as to
    # existence: the documentation is not bound to repeat src/monl/.
    if "/" not in target:
        names = {Path(f).name for f in files} | {Path(f).parent.name for f in files}
        return target in names or (target.endswith(".py") and target[:-3] in names)
    # A path as it appears in an INSTALLED package is valid too: packaging
    # removes the prefix declared by `package-dir`.
    candidates = [normalise, racine]
    candidates += [f"{prefix}/{c}" for prefix in ROOTS_OF_PACKAGES
                  for c in (normalise, racine) if prefix]
    return any(
        c in files or any(f.startswith(c.rstrip("/") + "/") for f in files)
        for c in candidates
    )


def _cited_commands(text: str) -> list[tuple[str, str]]:
    return [command for code in MOTIF_CODE.findall(text) for command in MOTIF_CLI.findall(code)]


#: The README table that serves as the command reference. A verb shipped and
#: absent from this table exists for nobody.
TABLE_OF_COMMANDS = "README.md"

#: The verbs left out of the table, with their reason. `init` is the guided
#: dialogue, which the README presents everywhere as plain `monl` — repeating
#: it there under its internal name would confuse instead of inform.
VERBS_OUTSIDE_TABLE = {
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
    expected_items = _orders(build_monl_parser()) - set(VERBS_OUTSIDE_TABLE)
    assert expected_items, "extractor not working: no verb read on the parser"
    tableau = (RACINE / TABLE_OF_COMMANDS).read_text(encoding="utf-8")
    lines = [line for line in tableau.splitlines()
              if line.startswith("| `monl")]
    assert lines, "extractor not working: commands table not found"
    documented = {verb for line in lines
                  for _, verb in MOTIF_CLI.findall(line)}

    missing = sorted(expected_items - documented)
    assert not missing, (
        f"verbs shipped and missing from the {TABLE_OF_COMMANDS} table: "
        f"{missing}")

    stale = sorted(set(VERBS_OUTSIDE_TABLE) - _orders(build_monl_parser()))
    assert not stale, f"exemption de verbe devenue inutile : {stale}"


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

    target = tmp_path / "projet"
    compile_project(str(RACINE / "exemples" / "01_portfolio.ml"), str(target))
    products = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert products, "extractor not working: compilation produced nothing"
    by_name = {}
    for path in products:
        by_name.setdefault(Path(path).name, []).append(path)

    # The search covers ALL the text, not only what is between backticks: the
    # original defect lived in a comment inside a `bash` block, that is exactly
    # where a reader copy-pastes. The pattern stays narrow — it only judges
    # files whose compilation really produced a namesake — so widening the
    # window does not widen what is accused.
    names_judged = "|".join(re.escape(n) for n in sorted(by_name) if n in FILES_GENERATED)
    assert names_judged, "extractor not working: no generated artifact to confront"
    motif = re.compile(rf"([A-Za-z<][\w<>./-]*)/({names_judged})\b")

    documents = _documents()
    faults = []
    for doc, text in documents.items():
        if doc in DOCUMENTS_HISTORICAL:
            continue
        for prefix, name in motif.findall(text):
            # A prefix that IS a folder of the repository talks about the
            # repository, not about a compiled project.
            if prefix.split("/")[0] in {"src", "docs", "tests", "exemples",
                                         "deploy", "scripts", "demo"}:
                continue
            reels = by_name[name]
            expected = {Path(r).parent.as_posix() for r in reels}
            # The prefix is the project name (`Boutique`, `<App>`) followed or
            # not by a subfolder: we compare what comes AFTER the name.
            sous = prefix.split("/", 1)[1] if "/" in prefix else ""
            if sous not in expected:
                faults.append(
                    f"{doc}: `{prefix}/{name}` — le fichier sort dans "
                    f"`<projet>/{sorted(expected)[0] or '.'}/`")

    assert not faults, "\n" + "\n".join(faults)


def test_the_extractors_cannot_succeed_on_nothing():
    example = (
        "Voir `src/monl/cli/dispatch.py`, lancer `monl compile`, puis "
        "[le guide](docs/GUIDE.md). La suite avait 12 tests et 91,5 % de couverture."
    )
    assert _file_citations(example) == ["src/monl/cli/dispatch.py"]
    assert _cited_commands(example) == [("monl", "compile")]
    assert _links(example) == ["docs/GUIDE.md"]
    assert MOTIF_DIGIT_TESTS.search(example)
    assert MOTIF_COVERAGE.search(example)


def test_the_documentation_respects_the_repository_invariants():
    documents = _documents()
    assert documents, "extractor not working: no Markdown document read"
    files = set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=RACINE, text=True
    ).splitlines())
    citations = {
        doc: _file_citations(text) for doc, text in documents.items()
    }
    commands = {doc: _cited_commands(text) for doc, text in documents.items()}
    assert sum(map(len, citations.values())), "extractor not working: no path extracted"
    assert sum(map(len, commands.values())), "extractor not working: no CLI verb extracted"

    # The two programs dispatch differently, so the truth is read in two
    # different places — but in BOTH cases it is what the code RUNS, never a
    # list kept for the test.
    commands_valid = {
        "monl": _orders(build_monl_parser()),
        # The French aliases are served by the same dispatch: the design
        # journal, which stays in French, may cite them.
        "monl-platform": set(VERBS_PLATFORM) | set(ALIAS_OF_VERBS),
    }
    assert all(commands_valid.values()), (
        "extractor not working: a program declares no verb")
    errors: list[str] = []
    historical_utilises: set[str] = set()
    generated_utilises: set[str] = set()

    for doc, text in documents.items():
        problems_doc: list[str] = []
        for citation in citations[doc]:
            name = Path(citation).name
            generated = name if name in FILES_GENERATED else next(
                (part for part in Path(citation).parts if part in FILES_GENERATED),
                None,
            )
            if generated is not None and (
                "/" not in citation.rstrip("/") or not _resolves(citation, doc, files)
            ):
                generated_utilises.add(generated)
            elif not _resolves(citation, doc, files):
                problems_doc.append(f"chemin inexistant `{citation}`")

        for programme, verb in commands[doc]:
            if verb not in commands_valid[programme]:
                problems_doc.append(f"verbe CLI inexistant `{programme} {verb}`")

        for target in _links(text):
            if re.match(r"^(?:https?://|mailto:|#)", target):
                continue
            if not _resolves(target, doc, files):
                problems_doc.append(f"lien local inexistant `{target}`")

        if MOTIF_DIGIT_TESTS.search(text):
            problems_doc.append("nombre de tests figé dans un document prescriptif")
        if MOTIF_COVERAGE.search(text):
            problems_doc.append("pourcentage de couverture figé dans un document prescriptif")

        if doc in DOCUMENTS_HISTORICAL:
            if problems_doc or "Document historique" in text:
                historical_utilises.add(doc)
        else:
            errors.extend(f"{doc}: {problem}" for problem in problems_doc)

    historical_missing = set(DOCUMENTS_HISTORICAL) - set(documents)
    historical_useless = set(DOCUMENTS_HISTORICAL) - historical_utilises
    generated_useless = set(FILES_GENERATED) - generated_utilises
    errors.extend(f"exemption historique absente: {doc}" for doc in sorted(historical_missing))
    errors.extend(f"exemption historique devenue inutile: {doc}" for doc in sorted(historical_useless))
    errors.extend(f"exemption de fichier généré devenue inutile: {name}" for name in sorted(generated_useless))
    assert not errors, "\n" + "\n".join(errors)
