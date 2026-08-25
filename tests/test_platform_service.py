import json
import subprocess
import zipfile

import pytest

from monl_platform.mcp_server import MCPDispatcher
from monl_platform.service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    PlatformNotFoundError,
)

SPEC = """app NotesEquipe

actor Member selfRegister

entity Note
    title: String
    content: Text

workflow ManageNotes for Member
    Create Note
    Read Note
"""


def test_validation_compile_inspection_et_archive_partagent_le_pipeline(tmp_path):
    service = CompilationService(tmp_path)
    validation = service.validate(SPEC)
    assert validation.valid, validation.errors
    assert validation.summary["entities"] == ["Note"]

    project = service.compile(SPEC)
    assert len(project["id"]) == 32
    assert project["summary"]["app"] == "NotesEquipe"
    assert project["summary"]["counts"]["routes"] >= 2
    assert ".jwt_secret" not in project["files"]
    assert service.contract(project["id"])["app"] == "NotesEquipe"

    archive = service.archive(project["id"])
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
    assert {"spec.ml", "app.py", "schema.sql", "frontend_contract.json"} <= names
    assert ".jwt_secret" not in names


def test_entrees_bornees_et_identifiants_opaques(tmp_path):
    service = CompilationService(tmp_path)
    with pytest.raises(PlatformInputError, match="vide"):
        service.validate(" ")
    with pytest.raises(PlatformInputError, match="256 ko"):
        service.validate("x" * 256_001)
    with pytest.raises(PlatformNotFoundError):
        service.inspect("../../etc/passwd")


def test_worker_interrompu_ne_publie_aucun_projet(tmp_path, monkeypatch):
    service = CompilationService(tmp_path)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(PlatformExecutionError, match="délai maximal"):
        service.compile(SPEC)
    assert list(tmp_path.iterdir()) == []


def test_mcp_expose_validation_compilation_et_inspection(tmp_path):
    dispatcher = MCPDispatcher(CompilationService(tmp_path))
    initialized = dispatcher.dispatch({"jsonrpc": "2.0", "id": 1,
                                       "method": "initialize", "params": {}})
    assert initialized["result"]["capabilities"]["tools"]

    listed = dispatcher.dispatch({"jsonrpc": "2.0", "id": 2,
                                  "method": "tools/list"})
    assert {tool["name"] for tool in listed["result"]["tools"]} == {
        "monl_list_templates", "monl_validate_spec", "monl_compile_backend",
        "monl_inspect_contract",
    }

    compiled = dispatcher.dispatch({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "monl_compile_backend", "arguments": {"spec": SPEC}},
    })
    payload = json.loads(compiled["result"]["content"][0]["text"])
    inspected = dispatcher.dispatch({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "monl_inspect_contract",
                   "arguments": {"project_id": payload["project_id"]}},
    })
    assert "NotesEquipe" in inspected["result"]["content"][0]["text"]
