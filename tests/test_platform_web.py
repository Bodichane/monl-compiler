from fastapi.testclient import TestClient

from monl_platform.app import create_app
from tests.test_platform_service import SPEC


def test_page_explique_compile_et_mcp(tmp_path):
    client = TestClient(create_app(workspace=tmp_path))
    page = client.get("/")
    assert page.status_code == 200
    assert "Votre métier est compilé" in page.text
    assert "Studio de compilation" in page.text
    assert "serveur MCP" in page.text

    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/api/templates").json()["templates"]) == 10

    validation = client.post("/api/validate", json={"spec": SPEC})
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    compiled = client.post("/api/compile", json={"spec": SPEC})
    assert compiled.status_code == 201, compiled.text
    project_id = compiled.json()["id"]
    assert client.get(f"/api/projects/{project_id}").status_code == 200
    assert client.get(f"/api/projects/{project_id}/contract").json()["app"] == "NotesEquipe"
    download = client.get(f"/api/projects/{project_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"

    mcp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 8,
                                    "method": "tools/list"})
    assert mcp.status_code == 200
    assert len(mcp.json()["result"]["tools"]) == 4


def test_erreurs_web_restent_actionnables(tmp_path):
    client = TestClient(create_app(workspace=tmp_path))
    empty = client.post("/api/validate", json={"spec": ""})
    assert empty.status_code == 422
    assert "vide" in empty.json()["detail"]
    assert client.get("/api/projects/invalide").status_code == 404
