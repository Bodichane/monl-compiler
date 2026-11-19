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
NEW_ELEMENT = re.compile(r"^\s*-\s")
NOUVELLE_KEY = re.compile(r"^\s*[A-Za-z_][\w -]*:(\s|$)")


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


def _orders(text, marker):
    """The workflow commands containing `marqueur`, joined back on one line.

    The workflow uses both forms: "run: <command>" on one line, and a folded
    scalar "run: >-" whose command spans several lines at the SAME indentation.
    A single implementation for all markers: two readings of the same folding
    would diverge (point 146).
    """
    commands, current = [], None
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if current is not None:
            suite = (not NEW_ELEMENT.match(line)
                     and not NOUVELLE_KEY.match(line))
            # A literal block "run: |" carries SEVERAL commands, one per line:
            # a line repeating the marker opens a new one instead of extending
            # the previous one. Without this distinction, two successive
            # coverage gates would be glued into one, and a rule about "each
            # command" would see only one.
            if suite and marker not in line:
                current += " " + line.strip()
                continue
            commands.append(current)
            current = None
            if suite:
                current = line.strip()
                continue
        if marker in line:
            current = line.strip()
    if current is not None:
        commands.append(current)
    return commands


def pytest_commands(text):
    """The workflow's pytest invocations."""
    return _orders(text, "python -m pytest")


def coverage_commands(text):
    """The workflow's coverage reports — where the gates live."""
    return _orders(text, "coverage report")


def collect_test_files(racine=RACINE):
    """The test files present on DISK, never a written list.

    That is the whole point of point 169: a hand-kept list stops guarding the
    day someone files a test under another name.
    """
    dossiers = [racine / path for path in project_testpaths()]
    found = {f.relative_to(racine) for d in dossiers for f in d.rglob("test_*.py")}
    if not found:
        raise AssertionError(
            f"no test file found under {dossiers}: the extractor "
            "would make guarantees green while looking at nothing.")
    return found


def command_selection(command, racine=RACINE):
    """The test files a pytest command really selects.

    Patterns (`tests/test_platform_*.py`) are expanded, a folder is walked the
    way pytest walks it, and a command without a target falls back to
    `testpaths`. A target designating NO existing file raises: it is the only way
    to tell "this command selects nothing" from "I could not read this command".
    """
    tokens = command.split()
    if "pytest" not in tokens:
        raise AssertionError(f"command without `pytest`: {command!r}")
    targets = [j for j in tokens[tokens.index("pytest") + 1:] if not j.startswith("-")]
    if not targets:
        targets = project_testpaths()

    selection = set()
    for target in targets:
        paths = sorted(racine.glob(target)) if "*" in target else [racine / target]
        reached = set()
        for path in paths:
            if path.is_dir():
                reached |= {f.relative_to(racine) for f in path.rglob("test_*.py")}
            elif path.is_file():
                reached.add(path.relative_to(racine))
        if not reached:
            raise AssertionError(
                f"target {target!r} of command {command!r} designates "
                "no existing file: the extractor cannot read it, and "
                "ignoring it would make a command look wider than it "
                "is.")
        selection |= reached
    return selection


def coverage_options(command):
    """The `--cov…` options a command carries."""
    return [j for j in command.split() if j.startswith("--cov")]
