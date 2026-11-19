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

from support.ci_workflow import CI, project_addopts, commandes_pytest

# `commandes_pytest` lives in `tests/support/ci_workflow.py` and not here: two
# test files now read this workflow, and two readings of the same YAML folding
# would diverge (point 146). Its extractor witness stays at the bottom of THIS
# file — this is where it was born.


def test_the_project_does_set_q_in_addopts():
    """The premise witness. If `addopts` stopped carrying `-q`, the test below
    would keep a rule that no longer has a purpose — it would refuse a `-q`
    that, alone, would be legitimate. Better to learn it here."""
    assert "-q" in project_addopts(), (
        "addopts ne porte plus `-q` : relire la règle de ce fichier avant de "
        "continuer à interdire `-q` dans les commandes de la CI.")


def test_no_ci_command_sets_q_again():
    commandes = commandes_pytest(CI.read_text(encoding="utf-8"))
    assert commandes, "aucune invocation pytest trouvée dans ci.yml"
    fautives = [c for c in commandes if "-q" in c.split()]
    assert not fautives, (
        "`addopts` pose déjà `-q` : un second donne `-qq`, qui supprime la "
        f"ligne de décompte et la section de résumé. Commande(s) : {fautives}")


def test_every_ci_command_names_skipped_tests():
    commandes = commandes_pytest(CI.read_text(encoding="utf-8"))
    assert commandes, "aucune invocation pytest trouvée dans ci.yml"
    muettes = [c for c in commandes
               if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())]
    assert not muettes, (
        "sans `-rs`, un saut n'apparaît que comme un `s` au milieu des points "
        f"et personne ne le lit. Commande(s) : {muettes}")


# The two tests above are only worth what `commandes_pytest` is worth. An
# extractor that finds NOTHING would make them green while looking at nothing —
# the exact error this file exists to forbid elsewhere.
CI_TEMOIN = """
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
    commandes = commandes_pytest(CI_TEMOIN)
    assert len(commandes) == 2, commandes
    assert commandes[0].endswith("--cov=src/monl")
    # The folded command is joined back IN FULL: otherwise the `-q` on its
    # second line would escape the check.
    assert "tests/test_oauth.py -q" in commandes[1]
    assert "--cov-fail-under=90" in commandes[1]
    assert "ruff" not in commandes[1]


def test_both_rules_bite_on_a_faulty_workflow():
    """The counter-proof: on the witness above, which sets `-q` and has no
    `-rs`, both rules must REPORT. A test that passes does not prove it bites
    (point 145)."""
    commandes = commandes_pytest(CI_TEMOIN)
    assert [c for c in commandes if "-q" in c.split()] == commandes
    assert [c for c in commandes
            if not any(o.startswith("-r") and "s" in o[2:] for o in c.split())] == commandes
