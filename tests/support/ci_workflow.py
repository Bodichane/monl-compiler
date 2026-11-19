"""Reading `.github/workflows/ci.yml` — the SINGLE source, for every witness.

Two test files now query this workflow: the one requiring skips to be
visible (point 161) and the one requiring a coverage gate to cover the whole
suite. YAML folding and path recognition are subtle enough that writing two
versions would make them diverge — that is point 146, and it holds for test
tooling too.

One rule runs through this whole module: **nothing here fails silently**. An
extractor returning an empty set would make the guarantees using it green,
without looking at anything (point 161). Every target that cannot be resolved
therefore raises, rather than disappearing.
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CI = RACINE / ".github" / "workflows" / "ci.yml"
PYPROJECT = RACINE / "pyproject.toml"

# A YAML list item ("- name: ...") or a key ("run: ...") closes the current
# command. "--cov=..." also starts with a dash: it is the dash FOLLOWED BY A
# SPACE that makes the list, and the distinction is not cosmetic — without it,
# a folded command would be cut in the middle.
NOUVEL_ELEMENT = re.compile(r"^\s*-\s")
NOUVELLE_CLE = re.compile(r"^\s*[A-Za-z_][\w -]*:(\s|$)")


def _charger_pyproject():
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def project_addopts():
    """The options `pyproject.toml` adds to every pytest invocation."""
    ini = _charger_pyproject()["tool"]["pytest"]["ini_options"]
    return ini["addopts"].split()


def project_testpaths():
    """What pytest collects when the command names no path.

    Read and not copied: a command without a target selects exactly that, and a
    second list would end up no longer saying the same thing as the first.
    """
    ini = _charger_pyproject()["tool"]["pytest"]["ini_options"]
    return list(ini["testpaths"])


def project_coverage_threshold():
    """The gate declared by `pyproject.toml`, never copied here.

    The workflow must hold AT LEAST this requirement; writing it a second time
    in a test would make it diverge the day it moves.
    """
    return _charger_pyproject()["tool"]["coverage"]["report"]["fail_under"]


def _orders(texte, marqueur):
    """The workflow commands containing `marqueur`, joined back on one line.

    The workflow uses both forms: "run: <command>" on one line, and a folded
    scalar "run: >-" whose command spans several lines at the SAME indentation.
    A single implementation for all markers: two readings of the same folding
    would diverge (point 146).
    """
    commandes, courante = [], None
    for ligne in texte.splitlines():
        if not ligne.strip() or ligne.strip().startswith("#"):
            continue
        if courante is not None:
            suite = (not NOUVEL_ELEMENT.match(ligne)
                     and not NOUVELLE_CLE.match(ligne))
            # A literal block "run: |" carries SEVERAL commands, one per line:
            # a line repeating the marker opens a new one instead of extending
            # the previous one. Without this distinction, two successive
            # coverage gates would be glued into one, and a rule about "each
            # command" would see only one.
            if suite and marqueur not in ligne:
                courante += " " + ligne.strip()
                continue
            commandes.append(courante)
            courante = None
            if suite:
                courante = ligne.strip()
                continue
        if marqueur in ligne:
            courante = ligne.strip()
    if courante is not None:
        commandes.append(courante)
    return commandes


def pytest_commands(texte):
    """The workflow's pytest invocations."""
    return _orders(texte, "python -m pytest")


def coverage_commands(texte):
    """The workflow's coverage reports — where the gates live."""
    return _orders(texte, "coverage report")


def test_files_of(racine=RACINE):
    """The test files present on DISK, never a written list.

    That is the whole point of point 169: a hand-kept list stops guarding the
    day someone files a test under another name.
    """
    dossiers = [racine / chemin for chemin in project_testpaths()]
    trouves = {f.relative_to(racine) for d in dossiers for f in d.rglob("test_*.py")}
    if not trouves:
        raise AssertionError(
            f"aucun fichier de tests trouvé sous {dossiers} : l'extracteur "
            "rendrait vertes des garanties en ne regardant rien.")
    return trouves


def order_selection(commande, racine=RACINE):
    """The test files a pytest command really selects.

    Patterns (`tests/test_platform_*.py`) are expanded, a folder is walked the
    way pytest walks it, and a command without a target falls back to
    `testpaths`. A target designating NO existing file raises: it is the only way
    to tell "this command selects nothing" from "I could not read this command".
    """
    jetons = commande.split()
    if "pytest" not in jetons:
        raise AssertionError(f"commande sans `pytest` : {commande!r}")
    cibles = [j for j in jetons[jetons.index("pytest") + 1:] if not j.startswith("-")]
    if not cibles:
        cibles = project_testpaths()

    selection = set()
    for cible in cibles:
        chemins = sorted(racine.glob(cible)) if "*" in cible else [racine / cible]
        atteints = set()
        for chemin in chemins:
            if chemin.is_dir():
                atteints |= {f.relative_to(racine) for f in chemin.rglob("test_*.py")}
            elif chemin.is_file():
                atteints.add(chemin.relative_to(racine))
        if not atteints:
            raise AssertionError(
                f"la cible {cible!r} de la commande {commande!r} ne désigne "
                "aucun fichier existant : l'extracteur ne sait pas la lire, et "
                "l'ignorer ferait passer une commande pour plus large qu'elle "
                "n'est.")
        selection |= atteints
    return selection


def coverage_options(commande):
    """The `--cov…` options a command carries."""
    return [j for j in commande.split() if j.startswith("--cov")]
