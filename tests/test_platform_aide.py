"""Issue #84: `monl-platform --help` must announce the served verbs.

The top-level help only described `--host` and `--port`: `admin` and
`sauvegarde` could only be discovered in `docs/EXPLOITATION.md`, which does
not travel in the wheel. The operator of a platform installed from the index
thought they had to go through `sqlite3` with the server stopped — the cliff
point 142 closed.
"""

import pytest

from monl_platform import __main__ as point_d_entree


def _aide(capsys):
    with pytest.raises(SystemExit) as sortie:
        point_d_entree.main(["--help"])
    assert sortie.value.code == 0
    return capsys.readouterr().out


def test_help_announces_every_dispatched_verb(capsys):
    aide = _aide(capsys)
    # Non-emptiness: an empty table would make the loop silent (point 161).
    assert point_d_entree.VERBES
    for nom, fonction in point_d_entree.VERBES.items():
        # The verb AND its summary: a name without a sentence does not say what
        # it is for.
        assert nom in aide, aide
        assert point_d_entree._resume(fonction) in aide, aide


def test_a_verb_added_to_the_table_appears_in_the_help(capsys, monkeypatch):
    """The guarantee comes from READING the table, not from a list written for
    the witness (point 190): a new verb appears with no other change."""
    def _essai(argv):
        """Trial verb added by the witness."""
        return 0

    monkeypatch.setitem(point_d_entree.VERBES, "essai", _essai)
    aide = _aide(capsys)
    assert "essai" in aide and "Trial verb added by the witness." in aide


def test_a_verb_without_docstring_makes_the_help_fail(monkeypatch):
    """A mute help is precisely the issue's defect: better to fail than to show a
    verb without saying anything about it."""
    monkeypatch.setitem(point_d_entree.VERBES, "muet", lambda argv: 0)
    with pytest.raises(ValueError, match="docstring"):
        point_d_entree.main(["--help"])
