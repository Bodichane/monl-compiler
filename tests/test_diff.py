"""`monl diff`: see the delta before writing — point 103.

`monl update` writes THEN reports. As long as the report says what was
expected, the order has no consequence; the day it announces a whole screen
to rewrite, one would like to have known before recompiling and replacing the
reference contract. `monl diff` answers the same question without touching
anything.

What the gesture decides:

* **the report has ONE source.** `_rapporter_delta` is extracted from
  `cmd_update` and shared: two delta calculations would end up diverging, and
  it is precisely the calculation six points (88 to 91, 94, 99) showed to be
  hard to keep right. The test attesting it is
  `test_diff_and_update_say_exactly_the_same_thing`;
* **the output folder is throwaway, but `base_dir` stays the REAL project.**
  Declared assets live in the project; looking for them in a temporary folder
  would make compilation fail for a reason that does not exist (brick 13,
  point 83). It is the trap this gesture had to avoid, and `compile_project`
  had to be opened for it;
* **no project file is written** — neither `app.py`, nor the contract, nor
  `monl.json`, nor the evolution instruction. Checked by fingerprint of the
  WHOLE tree, not by a list of names one could forget to complete.
"""
import hashlib
import os

import pytest

from monl.cli import cmd_diff, cmd_update, compile_project

SPEC = """app BancDiff

entity Article
    titre: String
    corps: Text

actor Auteur selfRegister

relation Auteur hasMany Article

rule Article.Read public
rule Article.Update ownedBy Auteur

workflow Ecrire for Auteur
    Create Article
    Read Article
    Update Article
"""


def _fingerprint(folder):
    """Fingerprint of the WHOLE tree — paths, sizes and contents.

    Listing the files one expects not to move would let through the one nobody
    thought of; it is the reasoning of point 73's fingerprint safeguard, applied
    in reverse."""
    digest = hashlib.sha256()
    for racine, _sous, files in sorted(os.walk(folder)):
        for name in sorted(files):
            path = os.path.join(racine, name)
            digest.update(os.path.relpath(path, folder).encode())
            with open(path, "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()


@pytest.fixture
def project(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    return tmp_path


def _delta_lines(output):
    """The report lines, without the compilation noise nor the banners specific
    to each of the two gestures."""
    kept, inside = [], False
    for line in output.splitlines():
        if line.startswith("─── Frontend contract delta"):
            inside = True
            continue
        if inside:
            if line.startswith("───"):
                break
            if "Instructions ready" in line:
                continue  # specific to `update`, which writes the brief
            kept.append(line.rstrip())
    return kept


def _modifier(project):
    spec = (project / "spec.ml").read_text(encoding="utf-8")
    spec = spec.replace("    corps: Text", "    corps: Text\n    chapeau: String")
    spec = spec.replace("rule Article.Read public",
                        "rule Article.Read public\n"
                        'rule Article.statut oneOf "brouillon", "publie"')
    spec = spec.replace("    titre: String", "    titre: String\n    statut: String")
    (project / "spec.ml").write_text(spec, encoding="utf-8")


# --------------------------------------------------------------------------
# What the dry run must NOT do
# --------------------------------------------------------------------------

def test_diff_writes_nothing_when_the_spec_changed(project, capsys):
    """THE test that carries the gesture. The fingerprint covers the whole tree."""
    _modifier(project)
    before = _fingerprint(project)
    cmd_diff(str(project))
    capsys.readouterr()
    assert _fingerprint(project) == before


def test_diff_does_not_write_the_evolution_instruction(project, capsys):
    """`update` writes FRONTEND_UPDATE_PROMPT.md when there is something to
    rewrite. `diff` must announce the same change and drop nothing."""
    _modifier(project)
    cmd_diff(str(project))
    capsys.readouterr()
    assert not (project / "docs/FRONTEND_UPDATE_PROMPT.md").exists()

    cmd_update(str(project))
    capsys.readouterr()
    assert (project / "docs/FRONTEND_UPDATE_PROMPT.md").exists()


def test_diff_does_not_touch_the_reference_contract(project, capsys):
    """The contract already in place is the comparison's REFERENCE: overwriting
    it during a dry run would make the next gesture blind."""
    _modifier(project)
    before = (project / "frontend_contract.json").read_text(encoding="utf-8")
    cmd_diff(str(project))
    capsys.readouterr()
    assert (project / "frontend_contract.json").read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------
# What it must say
# --------------------------------------------------------------------------

def test_diff_and_update_say_exactly_the_same_thing(project, capsys):
    """The test the gesture called for from its design: one report, one source.
    Two implementations of the delta would end up diverging."""
    _modifier(project)
    cmd_diff(str(project))
    par_diff = _delta_lines(capsys.readouterr().out)
    cmd_update(str(project))
    par_update = _delta_lines(capsys.readouterr().out)

    assert par_diff == par_update
    assert par_diff, "the bench must produce a delta, otherwise it compares nothing"


def test_diff_stays_quiet_when_the_spec_did_not_move(project, capsys):
    cmd_diff(str(project))
    output = capsys.readouterr().out
    assert "no interface changes" in output
    assert "monl update" not in output, \
        "do not send people to apply a change that does not exist"


def test_diff_announces_it_wrote_nothing(project, capsys):
    _modifier(project)
    cmd_diff(str(project))
    output = capsys.readouterr().out
    assert "[DRY-RUN]" in output
    assert "No files changed" in output


def test_diff_points_to_update_when_there_is_something(project, capsys):
    _modifier(project)
    cmd_diff(str(project))
    assert "monl update" in capsys.readouterr().out


def test_diff_without_project_state_stops(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cmd_diff(str(tmp_path))
    assert "not found" in capsys.readouterr().out


# --------------------------------------------------------------------------
# The trap the temporary folder set
# --------------------------------------------------------------------------

SPEC_WITH_ASSET = SPEC.replace("entity Article", """assets
    logo: "medias/logo.svg"

entity Article""")


def test_diff_finds_the_real_projects_assets(tmp_path, capsys):
    """The throwaway folder trap. `compile_project` checked asset existence in
    its OUTPUT folder; compiling elsewhere, a perfectly valid project would have
    failed announcing a missing file that is actually there. That is why
    `base_dir` had to become a parameter."""
    (tmp_path / "medias").mkdir()
    (tmp_path / "medias" / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (tmp_path / "spec.ml").write_text(SPEC_WITH_ASSET, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    cmd_diff(str(tmp_path))
    output = capsys.readouterr().out
    assert "no interface changes" in output
    assert "not found" not in output
    assert "manquant" not in output


def test_a_broken_spec_shows_the_compiler_message(project, capsys):
    """When the trial compilation fails, ITS message is the useful one — ours
    would only say "it did not work"."""
    spec = (project / "spec.ml").read_text(encoding="utf-8")
    (project / "spec.ml").write_text(
        spec + "rule Article.fantome hidden\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cmd_diff(str(project))
    assert "fantome" in capsys.readouterr().out
