"""Two messages that sent people fixing what was not broken — point 105.

The maintainer's finding, running a touch-up on a real project:

    monl retouche /projets/SneakerLab "utilise plutôt des icônes …"
    ❌ monl.json introuvable — ce dossier n'est pas un projet monl.

Two mistakes in a single answer.

**The folder did not exist at all.** `_load_state` answers `None` both for
"missing folder" and for "folder without monl.json", and every caller
concluded the latter. `monl frontend` went as far as advising "run 'monl
compile'": the message sent people recompiling a project monl had never
found. It is point 97's complaint, on another message — an assumption shown
as a diagnosis is worse than a vague message.

**And the two arguments were swapped.** `retouche` is the ONLY gesture whose
first argument is not the folder: `run`, `update`, `diff`, `compile` and
`frontend` all take it first. Writing the folder first is therefore the
reflex, and monl answered "this folder is not a monl project" talking about
the SENTENCE.

What both fixes have in common: they NAME what blocks and fix nothing on
their own. Putting the arguments back in place for the author would be
guessing — and getting it wrong the day a request looks like a path.
"""
from pathlib import Path

import pytest

from monl.cli import (
    _arguments_inverses,
    _erreur_de_chemin,
    check_coherence,
    cmd_diff,
    cmd_retouche,
    cmd_update,
    compile_project,
)

EXAMPLES_DIR = Path(__file__).parents[1] / "exemples"

SPEC = """app BancChemin

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""


@pytest.fixture
def projet(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    return tmp_path


# --------------------------------------------------------------------------
# The folder that does not exist
# --------------------------------------------------------------------------

def test_a_missing_folder_is_named_as_such(tmp_path):
    """The heart of the point: do not talk about the CONTENT of a folder that was
    not found."""
    message = _erreur_de_chemin(str(tmp_path / "nulle-part"))
    assert "Directory not found" in message
    assert "monl.json" not in message
    assert "compile" not in message.lower().replace("compilation", "")


def test_a_missing_folder_says_its_content_was_not_looked_at(tmp_path):
    """Without this sentence, the author still looks for what is missing IN the
    folder."""
    message = _erreur_de_chemin(str(tmp_path / "nulle-part"))
    assert "have not been inspected yet" in message


def test_an_existing_folder_triggers_nothing(tmp_path):
    """The witness: the project question must stay asked where it makes sense."""
    assert _erreur_de_chemin(str(tmp_path)) is None


def test_the_leading_slash_is_explained(tmp_path, monkeypatch):
    """THE mistake that motivated the point. '/projets/X' is not "projets/X
    here": it is X at the SYSTEM root."""
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    message = _erreur_de_chemin("/projets/SneakerLab")
    assert "system root" in message
    assert "projets/SneakerLab" in message.split("Did you mean:")[1]


def test_without_a_plausible_neighbor_no_suggestion_is_invented(tmp_path, monkeypatch):
    """The suggestion's safeguard: proposing a path that does not exist either
    would send people searching a second time for nothing."""
    monkeypatch.chdir(tmp_path)
    message = _erreur_de_chemin("/vraiment/nulle/part")
    assert "Did you mean" not in message


@pytest.mark.parametrize("geste", [cmd_update, cmd_diff])
def test_the_gestures_stop_on_the_path_not_the_state(geste, tmp_path, capsys):
    """The two gestures reading the state must ask the questions in order: does
    the folder exist, THEN does it carry a project."""
    with pytest.raises(SystemExit):
        geste(str(tmp_path / "nulle-part"))
    sortie = capsys.readouterr().out
    assert "Directory not found" in sortie
    assert "monl.json introuvable" not in sortie


def test_the_consistency_check_also_distinguishes(tmp_path):
    """`monl frontend` goes through here, and it is the one advising to
    recompile a project never found."""
    ok, erreurs, _avertissements = check_coherence(str(tmp_path / "nulle-part"))
    assert not ok
    assert any("Directory not found" in e for e in erreurs)
    assert not any("monl compile" in e for e in erreurs)


# --------------------------------------------------------------------------
# The swapped arguments
# --------------------------------------------------------------------------

def test_the_swap_is_detected(tmp_path, monkeypatch):
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert _arguments_inverses("/projets/SneakerLab",
                               "utilise plutôt des icônes et un peu de texte")
    assert _arguments_inverses("projets/SneakerLab", "la FAQ est collée")


def test_the_correct_order_triggers_nothing():
    """The witness, and it counts: a false positive here would REFUSE a
    perfectly written touch-up."""
    assert not _arguments_inverses("la FAQ est collée", ".")
    assert not _arguments_inverses("les images sont mal cadrées", "projets/X")


def test_a_request_without_spaces_is_not_enough_to_conclude():
    """A one-word request is odd but legitimate; what makes the swap is that it
    looks like a path AND the folder looks like a sentence."""
    assert not _arguments_inverses("illisible", ".")


def test_the_swap_message_proposes_a_usable_command(tmp_path, monkeypatch,
                                                               capsys):
    """The proposed command must WORK as is: copying a path already known to be
    wrong would make people stumble a second time."""
    (tmp_path / "projets" / "SneakerLab").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    lignes = []
    with pytest.raises(SystemExit):
        cmd_retouche("utilise plutôt des icônes", "/projets/SneakerLab",
                     say=lignes.append)
    capsys.readouterr()
    rendu = "\n".join(lignes)
    assert "arguments appear to be reversed" in rendu
    propose = next(li for li in lignes if li.strip().startswith("monl retouche"))
    assert '"utilise plutôt des icônes"' in propose
    assert "/projets/SneakerLab" not in propose
    assert propose.strip().endswith("projets/SneakerLab")


def test_a_well_written_touch_up_passes_the_check(projet, capsys):
    """The end-to-end witness: detection must not get in the way of normal use.
    We stop for lack of a frontend, not on the arguments."""
    with pytest.raises(SystemExit):
        cmd_retouche(str(projet), "les images sont mal cadrées")
    sortie = capsys.readouterr().out
    assert "arguments appear to be reversed" not in sortie
    assert "No frontend to touch up (frontend/index.html is missing)" in sortie


def test_compile_with_output_looks_for_assets_next_to_the_spec(tmp_path, capsys):
    """`--output` must not move the asset resolution root."""
    compile_project(str(EXAMPLES_DIR / "01_portfolio.ml"), str(tmp_path))

    assert (tmp_path / "app.py").exists()
    assert (tmp_path / "frontend_contract.json").exists()
    capsys.readouterr()
