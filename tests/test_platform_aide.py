"""Issue #84: `monl-platform --help` must announce the served verbs.

The top-level help only described `--host` and `--port`: `admin` and
`sauvegarde` could only be discovered in `docs/EXPLOITATION.md`, which does
not travel in the wheel. The operator of a platform installed from the index
thought they had to go through `sqlite3` with the server stopped — the cliff
point 142 closed.
"""

import pytest

from monl_platform import __main__ as point_d_entry


def _aide(capsys):
    with pytest.raises(SystemExit) as output:
        point_d_entry.main(["--help"])
    assert output.value.code == 0
    return capsys.readouterr().out


def test_help_announces_every_dispatched_verb(capsys):
    aide = _aide(capsys)
    # Non-emptiness: an empty table would make the loop silent (point 161).
    assert point_d_entry.VERBS
    for name, function in point_d_entry.VERBS.items():
        # The verb AND its summary: a name without a sentence does not say what
        # it is for.
        assert name in aide, aide
        assert point_d_entry._resume(function) in aide, aide


def test_a_verb_added_to_the_table_appears_in_the_help(capsys, monkeypatch):
    """The guarantee comes from READING the table, not from a list written for
    the witness (point 190): a new verb appears with no other change."""
    def _attempt(argv):
        """Trial verb added by the witness."""
        return 0

    monkeypatch.setitem(point_d_entry.VERBS, "essai", _attempt)
    aide = _aide(capsys)
    assert "essai" in aide and "Trial verb added by the witness." in aide


def test_a_verb_without_docstring_makes_the_help_fail(monkeypatch):
    """A mute help is precisely the issue's defect: better to fail than to show a
    verb without saying anything about it."""
    monkeypatch.setitem(point_d_entry.VERBS, "muet", lambda argv: 0)
    with pytest.raises(ValueError, match="docstring"):
        point_d_entry.main(["--help"])
