"""A coverage gate covers the WHOLE suite, or it lies.

CI measured the platform on a hand-written list of files:

    python -m pytest tests/test_platform_*.py tests/test_oauth.py
      tests/test_administration.py tests/test_recovery_codes.py
      --cov=src/monl_platform --cov-fail-under=90

Measured before fixing: **five files exercised the platform outside this
list** — including `tests/test_console_javascript.py`, which guards point
163's dead pages. Their lines did not count in the 90%, and a test filed
under another name would have left the measurement without a word. It is
point 169 for the fourth time: a hand-kept list stops guarding, and its
silence is complete.

The fix does not lengthen the list, it REMOVES it: the suite runs once
measuring both packages, then `coverage report --include=…` draws two gates
from the same run.

Three rules live here, each in a FUNCTION its counter-proof exercises on a
faulty workflow — and not in a test body, which would force the
counter-proof to rewrite the rule to check it (point 170's removed witness).
"""

import pytest
from support.ci_workflow import (
    CI,
    RACINE,
    collect_test_files,
    command_selection,
    coverage_commands,
    coverage_options,
    project_coverage_threshold,
    pytest_commands,
)


def _orders(text):
    commands = pytest_commands(text)
    assert commands, "no pytest invocation found"
    return commands


def unmeasured_files(text):
    """For each command that MEASURES coverage, the test files it does not run.
    These files exercise the package without counting in the measurement: the
    announced percentage is not the package's."""
    all_ = collect_test_files()
    outside = {}
    for command in _orders(text):
        if not any(o.startswith("--cov=") for o in coverage_options(command)):
            continue
        missing = all_ - command_selection(command)
        if missing:
            outside[command] = sorted(str(f) for f in missing)
    return outside


def files_never_run(text):
    """The test files NO workflow command selects."""
    executes = set()
    for command in _orders(text):
        executes |= command_selection(command)
    return sorted(str(f) for f in collect_test_files() - executes)


def gates_by_package(text):
    """The threshold the workflow sets against each package of `src/`.

    The packages are read from DISK: copying them here would recreate, in the
    witness, the hand-written list it exists to forbid.
    """
    packages = {d.name for d in (RACINE / "src").iterdir()
               if d.is_dir() and (d / "__init__.py").exists()}
    assert packages, "no package found under src/"
    gates = {}
    for command in coverage_commands(text):
        thresholds = [j for j in command.split() if j.startswith("--fail-under=")]
        if not thresholds:
            continue
        for package in packages:
            if f"src/{package}/*" in command:
                gates[package] = float(thresholds[-1].split("=", 1)[1])
    return packages, gates


# ─────────────────────────────────────────────────────────────────────────
# The three rules, on the REAL workflow.
# ─────────────────────────────────────────────────────────────────────────
def test_a_coverage_gate_covers_the_whole_suite():
    """The heart of the file. Coverage measured on a SELECTION announces a
    percentage of the package having exercised only part of what exercises it:
    the number is too low because it ignores real tests, and fragile because the
    next test filed elsewhere will silently leave it."""
    outside = unmeasured_files(CI.read_text(encoding="utf-8"))
    assert not outside, (
        "a coverage gate must not be measured on a "
        "selection of files: tests outside the selection exercise the package "
        "without counting in the measure, and the next test stored under another "
        f"name will leave it without a word (point 169). {outside}")


def test_ci_runs_every_test_file():
    """The other end of the same defect: a file NO command selects is a file
    nobody runs. The repository has none today — it is precisely while it has
    none that the guard is set, otherwise it would arrive afterwards (point
    167bis)."""
    forgotten = files_never_run(CI.read_text(encoding="utf-8"))
    assert not forgotten, (
        f"no ci.yml command runs these files: {forgotten}")


def test_each_repository_package_carries_its_gate():
    """A removed gate makes no noise. The threshold comes from `pyproject.toml`:
    writing it a second time here would make it diverge the day it moves."""
    packages, gates = gates_by_package(CI.read_text(encoding="utf-8"))
    missing = sorted(packages - set(gates))
    assert not missing, (
        f"these src/ packages no longer have a coverage gate in "
        f"ci.yml: {missing}")
    floor = project_coverage_threshold()
    weak = {p: v for p, v in gates.items() if v < floor}
    assert not weak, (
        f"`pyproject.toml` declares a gate at {floor} %; ci.yml measures "
        f"less than that: {weak}")


# ─────────────────────────────────────────────────────────────────────────
# The counter-proofs. A passing test does not prove it bites (point 145), and
# the three rules above are only worth what the extractors are worth: an
# extractor always returning the complete set would make them green while
# looking at nothing (point 161).
# ─────────────────────────────────────────────────────────────────────────
CI_OFFENDER = """
      - name: Suite complète
        run: python -m pytest tests/ -rs --cov=src/monl

      - name: Couverture de la plateforme (barrière à 90 %)
        run: >-
          python -m pytest tests/test_platform_*.py tests/test_oauth.py
          tests/test_administration.py tests/test_recovery_codes.py -rs
          --cov=src/monl_platform --cov-report=term --cov-fail-under=90
"""

CI_TRUNCATED = """
      - name: On n'exécute qu'une partie de la suite
        run: python -m pytest tests/test_platform_*.py -rs

      - name: Une seule barrière, et trop basse
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=10
"""


def test_the_rule_bites_on_the_form_ci_carried():
    """On the EXACT text `ci.yml` carried before this fix."""
    outside = unmeasured_files(CI_OFFENDER)
    assert len(outside) == 1, outside
    missing = next(iter(outside.values()))
    # The file NAMED by this session's measurement must be among them.
    assert "tests/test_console_javascript.py" in missing
    # And the command that does take the whole suite must NOT be denounced.
    assert all("--cov=src/monl_platform" in c for c in outside)


def test_the_two_other_rules_bite_on_a_truncated_workflow():
    forgotten = files_never_run(CI_TRUNCATED)
    assert forgotten, "a workflow running only a pattern must be denounced"
    assert "tests/test_golden_artifacts.py" in forgotten

    packages, gates = gates_by_package(CI_TRUNCATED)
    assert sorted(packages - set(gates)) == ["monl_platform"]
    assert gates["monl"] < project_coverage_threshold()


def test_the_extractor_expands_patterns_folders_and_missing_target():
    """The three forms the workflow can take, on REAL paths."""
    all_ = collect_test_files()
    # A folder is walked the way pytest walks it.
    assert command_selection("run: python -m pytest tests/ -rs") == all_
    # Without a target, pytest falls back to `testpaths` — hence the same set.
    assert command_selection("run: python -m pytest -rs") == all_
    # A pattern expands ONLY what it designates.
    motif = command_selection(
        "run: python -m pytest tests/test_platform_*.py")
    assert motif and motif < all_
    assert all(f.name.startswith("test_platform_") for f in motif)


def test_the_extractor_raises_on_a_target_it_cannot_read():
    """A target that cannot be resolved must never evaporate: ignored, it would
    make a narrow command pass for a wide one."""
    with pytest.raises(AssertionError, match="no existing file"):
        command_selection("run: python -m pytest tests/test_inexistant.py")


def test_the_extractor_splits_the_commands_of_a_literal_block():
    """A "run: |" block carries several commands, one per line. Joined into one,
    the two gates would make only one — and the rule above would declare a
    package guarded while it no longer is."""
    block = """
      - name: Deux barrières
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=90
          python -m coverage report --include='src/monl_platform/*' --fail-under=90
"""
    commands = coverage_commands(block)
    assert len(commands) == 2, commands
    assert "src/monl/*" in commands[0] and "src/monl_platform" not in commands[0]
    assert "src/monl_platform/*" in commands[1]

    # And the FOLDED command stays joined back in full: the distinction is
    # about the repeated marker, not about a continuation being present.
    plie = """
      - name: Suite
        run: >-
          python -m pytest tests/ -rs
          --cov=src/monl --cov-fail-under=0
"""
    assert pytest_commands(plie) == [
        "python -m pytest tests/ -rs --cov=src/monl --cov-fail-under=0"]
