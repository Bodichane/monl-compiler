"""The orchestrator's command journey — compile → run --check → update
(point 64).

`cli.py` was the low point of coverage (35%): its paths were only tested
indirectly, through other tests or subprocesses the instrument does not
follow. The choice made here is NOT to raise a figure, but to cover what a
user really goes through, and whose failure would be silent: the state
written in monl.json, detection of an inconsistency between spec and backend,
and the contract delta `monl update` relies on.

The smoke test is deliberately left out (`skip_smoke=True`): it starts a
server and is already tested by tests/test_smoke_and_frontend_ai.py —
replaying it here would only add slowness.
"""
import json

import pytest

from monl.cli import STATE_FILENAME, check_coherence, cmd_run, cmd_update, compile_project

SPEC = """app Carnet

entity Note
    title: String

actor Admin selfRegister

rule Note.Read public

workflow GererNote for Admin
    Create Note
    Read Note
"""

SPEC_EXTENT = SPEC.replace("    title: String",
                            "    title: String\n    body: Text")


@pytest.fixture
def project(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return tmp_path


def test_compile_writes_the_state_and_contract(project):
    for artifact in ("app.py", "schema.sql", "manage.py",
                     "frontend_contract.json", "docs/FRONTEND_PROMPT.md",
                     "requirements.txt", STATE_FILENAME):
        assert (project / artifact).exists(), artifact
    state = json.loads((project / STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["spec"].endswith("spec.ml")
    from monl.parser.version import LANGUAGE_VERSION
    assert state["language_version"] == LANGUAGE_VERSION


def test_consistency_passes_right_after_a_compilation(project):
    ok, errors, _warnings = check_coherence(str(project))
    assert ok, errors


def test_a_hand_edited_backend_is_detected(project):
    """The promise of `monl run`: app.py is SEALED. A manual edit must be seen,
    otherwise the spec stops being the source of truth without anyone knowing."""
    path = project / "app.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# retouche\n",
                      encoding="utf-8")
    ok, errors, _ = check_coherence(str(project))
    assert not ok
    assert any("app.py" in e for e in errors), errors


def test_run_check_stops_on_an_inconsistency(project):
    """And it stops BEFORE starting anything: non-zero exit, no server started."""
    path = project / "schema.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- retouche\n",
                      encoding="utf-8")
    with pytest.raises(SystemExit) as output:
        cmd_run(str(project), check_only=True, skip_smoke=True)
    assert output.value.code == 1


def test_run_check_passes_on_a_healthy_project(project):
    cmd_run(str(project), check_only=True, skip_smoke=True)   # must not exit


def test_update_reports_the_added_field_and_prepares_the_instruction(project, capsys):
    (project / "spec.ml").write_text(SPEC_EXTENT, encoding="utf-8")
    cmd_update(str(project))
    output = capsys.readouterr().out
    assert "Note.body" in output, output
    assert "field added" in output, output
    assert (project / "docs/FRONTEND_UPDATE_PROMPT.md").exists()
    # The delta must also have reached the contract itself.
    contract = json.loads((project / "frontend_contract.json").read_text(encoding="utf-8"))
    assert "body" in str(contract)


def test_update_without_change_makes_no_instruction(project, capsys):
    """An update instruction sent for nothing would make the frontend AI rework
    an interface that is already right."""
    cmd_update(str(project))
    output = capsys.readouterr().out
    assert "no interface changes" in output, output
    assert not (project / "docs/FRONTEND_UPDATE_PROMPT.md").exists()


def test_update_refuses_a_folder_that_is_not_a_project(tmp_path):
    with pytest.raises(SystemExit) as output:
        cmd_update(str(tmp_path))
    assert output.value.code == 1


def test_legacy_state_without_language_version_remains_valid(project):
    _, _, original_warnings = check_coherence(str(project))
    path = project / STATE_FILENAME
    state = json.loads(path.read_text(encoding="utf-8"))
    del state["language_version"]
    path.write_text(json.dumps(state), encoding="utf-8")
    ok, errors, warnings = check_coherence(str(project))
    assert ok, errors
    assert warnings == original_warnings
    cmd_run(str(project), check_only=True, skip_smoke=True)
    backend = project / "app.py"
    backend.write_text(backend.read_text(encoding="utf-8") + "\n# changed\n")
    ok, errors, _ = check_coherence(str(project))
    assert not ok
    assert any("app.py" in error for error in errors)
