"""A coverage gate covers the WHOLE suite, or it lies.

CI measured the platform on a hand-written list of files:

    python -m pytest tests/test_platform_*.py tests/test_oauth.py
      tests/test_administration.py tests/test_codes_de_secours.py
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
    coverage_commands,
    coverage_options,
    order_selection,
    project_coverage_threshold,
    pytest_commands,
    test_files_of,
)


def _orders(texte):
    commandes = pytest_commands(texte)
    assert commandes, "no pytest invocation found"
    return commandes


def unmeasured_files(texte):
    """For each command that MEASURES coverage, the test files it does not run.
    These files exercise the package without counting in the measurement: the
    announced percentage is not the package's."""
    tous = test_files_of()
    hors = {}
    for commande in _orders(texte):
        if not any(o.startswith("--cov=") for o in coverage_options(commande)):
            continue
        manquants = tous - order_selection(commande)
        if manquants:
            hors[commande] = sorted(str(f) for f in manquants)
    return hors


def files_never_run(texte):
    """The test files NO workflow command selects."""
    executes = set()
    for commande in _orders(texte):
        executes |= order_selection(commande)
    return sorted(str(f) for f in test_files_of() - executes)


def barrieres_par_paquet(texte):
    """The threshold the workflow sets against each package of `src/`.

    The packages are read from DISK: copying them here would recreate, in the
    witness, the hand-written list it exists to forbid.
    """
    paquets = {d.name for d in (RACINE / "src").iterdir()
               if d.is_dir() and (d / "__init__.py").exists()}
    assert paquets, "no package found under src/"
    barrieres = {}
    for commande in coverage_commands(texte):
        seuils = [j for j in commande.split() if j.startswith("--fail-under=")]
        if not seuils:
            continue
        for paquet in paquets:
            if f"src/{paquet}/*" in commande:
                barrieres[paquet] = float(seuils[-1].split("=", 1)[1])
    return paquets, barrieres


# ─────────────────────────────────────────────────────────────────────────
# The three rules, on the REAL workflow.
# ─────────────────────────────────────────────────────────────────────────
def test_a_coverage_gate_covers_the_whole_suite():
    """The heart of the file. Coverage measured on a SELECTION announces a
    percentage of the package having exercised only part of what exercises it:
    the number is too low because it ignores real tests, and fragile because the
    next test filed elsewhere will silently leave it."""
    hors = unmeasured_files(CI.read_text(encoding="utf-8"))
    assert not hors, (
        "a coverage gate must not be measured on a "
        "selection of files: tests outside the selection exercise the package "
        "without counting in the measure, and the next test stored under another "
        f"name will leave it without a word (point 169). {hors}")


def test_ci_runs_every_test_file():
    """The other end of the same defect: a file NO command selects is a file
    nobody runs. The repository has none today — it is precisely while it has
    none that the guard is set, otherwise it would arrive afterwards (point
    167bis)."""
    oublies = files_never_run(CI.read_text(encoding="utf-8"))
    assert not oublies, (
        f"no ci.yml command runs these files: {oublies}")


def test_each_repository_package_carries_its_gate():
    """A removed gate makes no noise. The threshold comes from `pyproject.toml`:
    writing it a second time here would make it diverge the day it moves."""
    paquets, barrieres = barrieres_par_paquet(CI.read_text(encoding="utf-8"))
    manquants = sorted(paquets - set(barrieres))
    assert not manquants, (
        f"these src/ packages no longer have a coverage gate in "
        f"ci.yml: {manquants}")
    plancher = project_coverage_threshold()
    faibles = {p: v for p, v in barrieres.items() if v < plancher}
    assert not faibles, (
        f"`pyproject.toml` declares a gate at {plancher} %; ci.yml measures "
        f"less than that: {faibles}")


# ─────────────────────────────────────────────────────────────────────────
# The counter-proofs. A passing test does not prove it bites (point 145), and
# the three rules above are only worth what the extractors are worth: an
# extractor always returning the complete set would make them green while
# looking at nothing (point 161).
# ─────────────────────────────────────────────────────────────────────────
CI_FAUTIF = """
      - name: Suite complète
        run: python -m pytest tests/ -rs --cov=src/monl

      - name: Couverture de la plateforme (barrière à 90 %)
        run: >-
          python -m pytest tests/test_platform_*.py tests/test_oauth.py
          tests/test_administration.py tests/test_codes_de_secours.py -rs
          --cov=src/monl_platform --cov-report=term --cov-fail-under=90
"""

CI_AMPUTE = """
      - name: On n'exécute qu'une partie de la suite
        run: python -m pytest tests/test_platform_*.py -rs

      - name: Une seule barrière, et trop basse
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=10
"""


def test_the_rule_bites_on_the_form_ci_carried():
    """On the EXACT text `ci.yml` carried before this fix."""
    hors = unmeasured_files(CI_FAUTIF)
    assert len(hors) == 1, hors
    manquants = next(iter(hors.values()))
    # The file NAMED by this session's measurement must be among them.
    assert "tests/test_console_javascript.py" in manquants
    # And the command that does take the whole suite must NOT be denounced.
    assert all("--cov=src/monl_platform" in c for c in hors)


def test_the_two_other_rules_bite_on_a_truncated_workflow():
    oublies = files_never_run(CI_AMPUTE)
    assert oublies, "a workflow running only a pattern must be denounced"
    assert "tests/test_golden_artifacts.py" in oublies

    paquets, barrieres = barrieres_par_paquet(CI_AMPUTE)
    assert sorted(paquets - set(barrieres)) == ["monl_platform"]
    assert barrieres["monl"] < project_coverage_threshold()


def test_the_extractor_expands_patterns_folders_and_missing_target():
    """The three forms the workflow can take, on REAL paths."""
    tous = test_files_of()
    # A folder is walked the way pytest walks it.
    assert order_selection("run: python -m pytest tests/ -rs") == tous
    # Without a target, pytest falls back to `testpaths` — hence the same set.
    assert order_selection("run: python -m pytest -rs") == tous
    # A pattern expands ONLY what it designates.
    motif = order_selection(
        "run: python -m pytest tests/test_platform_*.py")
    assert motif and motif < tous
    assert all(f.name.startswith("test_platform_") for f in motif)


def test_the_extractor_raises_on_a_target_it_cannot_read():
    """A target that cannot be resolved must never evaporate: ignored, it would
    make a narrow command pass for a wide one."""
    with pytest.raises(AssertionError, match="no existing file"):
        order_selection("run: python -m pytest tests/test_inexistant.py")


def test_the_extractor_splits_the_commands_of_a_literal_block():
    """A "run: |" block carries several commands, one per line. Joined into one,
    the two gates would make only one — and the rule above would declare a
    package guarded while it no longer is."""
    bloc = """
      - name: Deux barrières
        run: |
          python -m coverage report --include='src/monl/*' --fail-under=90
          python -m coverage report --include='src/monl_platform/*' --fail-under=90
"""
    commandes = coverage_commands(bloc)
    assert len(commandes) == 2, commandes
    assert "src/monl/*" in commandes[0] and "src/monl_platform" not in commandes[0]
    assert "src/monl_platform/*" in commandes[1]

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
