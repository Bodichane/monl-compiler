"""CI must NAME its skipped tests, not drown them in a wall of dots.

`pyproject.toml` already sets `-q` in `addopts`. Every command of
`.github/workflows/ci.yml` set a SECOND one, and two `-q` make `-qq`: pytest
then removes the count line AND the summary section. A skip only showed as a
single `s` among a thousand dots.

This is not a hypothesis. The JPEG re-encoding test skipped in this CI for
the repository's whole life — Pillow only lived in the `ai` extra, which CI
does not install — and nothing ever said so. A skip does not say "nothing to
check here", it says "I did not check" (point 140).

This file therefore guards TWO properties, because one without the other is
not enough: no command sets `-q` again (otherwise the summary disappears
again), and each carries `-rs` (otherwise the summary exists but names
nobody).
"""

from support.ci_workflow import CI, project_addopts, pytest_commands

# `pytest_commands` lives in `tests/support/ci_workflow.py` and not here: two
# test files now read this workflow, and two readings of the same YAML folding
# would diverge (point 146). Its extractor witness stays at the bottom of THIS
# file — this is where it was born.


def test_the_project_does_set_q_in_addopts():
    """The premise witness. If `addopts` stopped carrying `-q`, the test below
    would keep a rule that no longer has a purpose — it would refuse a `-q`
    that, alone, would be legitimate. Better to learn it here."""
    assert "-q" in project_addopts(), (
        "addopts no longer carries `-q`: reread this file's rule before "
        "continuing to forbid `-q` in the CI commands.")


def test_no_ci_command_sets_q_again():
    commands = pytest_commands(CI.read_text(encoding="utf-8"))
    assert commands, "no pytest invocation found in ci.yml"
    offending = [c for c in commands if "-q" in c.split()]
    assert not offending, (
        "`addopts` already sets `-q`: a second one gives `-qq`, which removes the "
        f"count line and the summary section. Command(s): {offending}")


def test_every_ci_command_names_skipped_tests():
    commands = pytest_commands(CI.read_text(encoding="utf-8"))
    assert commands, "no pytest invocation found in ci.yml"
    mute = [c for c in commands
               if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())]
    assert not mute, (
        "without `-rs`, a skip only shows as an `s` among the dots "
        f"and nobody reads it. Command(s): {mute}")


# The two tests above are only worth what `pytest_commands` is worth. An
# extractor that finds NOTHING would make them green while looking at nothing —
# the exact error this file exists to forbid elsewhere.
CI_WITNESS = """
      - name: Une étape sur une ligne
        run: python -m pytest tests/ -q --cov=src/monl

      - name: Une étape repliée
        # A comment, which does not belong to the command.
        run: >-
          python -m pytest tests/test_platform_*.py
          tests/test_oauth.py -q
          --cov=src/monl_platform --cov-fail-under=90

      - name: Une étape sans pytest
        run: ruff check src tests
"""


def test_the_extractor_finds_both_forms_without_mixing_them():
    commands = pytest_commands(CI_WITNESS)
    assert len(commands) == 2, commands
    assert commands[0].endswith("--cov=src/monl")
    # The folded command is joined back IN FULL: otherwise the `-q` on its
    # second line would escape the check.
    assert "tests/test_oauth.py -q" in commands[1]
    assert "--cov-fail-under=90" in commands[1]
    assert "ruff" not in commands[1]


def test_both_rules_bite_on_a_faulty_workflow():
    """The counter-proof: on the witness above, which sets `-q` and has no
    `-rs`, both rules must REPORT. A test that passes does not prove it bites
    (point 145)."""
    commands = pytest_commands(CI_WITNESS)
    assert [c for c in commands if "-q" in c.split()] == commands
    assert [c for c in commands
            if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())] == commands
