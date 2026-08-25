"""La plateforme web, éprouvée contre un VRAI serveur.

Ce fichier montait la plateforme avec `TestClient` de Starlette. Deux raisons
de ne plus le faire, la première mesurée en CI :

1. `starlette.testclient` exige désormais `httpx2`, absent des dépendances du
   dépôt. La suite s'arrêtait à la COLLECTE sur les trois versions de Python
   — une plateforme parfaitement fonctionnelle déclarée cassée par son propre
   vérificateur, ce que le point 95 nomme déjà : le vérificateur est un client
   comme un autre.
2. Le reste du dépôt éprouve tout scénario HTTP contre un uvicorn éphémère
   (`tests/support/server.py`). Ce fichier était le seul à prendre un
   raccourci en processus, et ce raccourci ne traverse ni la couche ASGI
   réelle, ni le démarrage du serveur.

Le sous-processus tourne dans `tmp_path` avec `src/` sur le PYTHONPATH : la
racine du dépôt ne peut donc rien recevoir (point 64), et le test reste vrai
que le paquet soit installé ou non.
"""

import os

import requests

from tests.support.server import uvicorn_server
from tests.test_platform_service import SPEC

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def _plateforme(tmp_path):
    """Monte la plateforme sur un port libre, l'espace de travail isolé."""
    env = os.environ.copy()
    env["MONL_PLATFORM_WORKSPACE"] = str(tmp_path / "espace")
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return uvicorn_server(str(tmp_path), env=env,
                          module="monl_platform.app:app", ready_path="/health")


def test_page_explique_compile_et_mcp(tmp_path):
    with _plateforme(tmp_path) as base:
        page = requests.get(base + "/", timeout=30)
        assert page.status_code == 200
        assert "Votre métier est compilé" in page.text
        assert "Studio de compilation" in page.text
        assert "serveur MCP" in page.text

        assert requests.get(base + "/health", timeout=30).json()["status"] == "ok"
        templates = requests.get(base + "/api/templates", timeout=30).json()
        assert len(templates["templates"]) == 10

        validation = requests.post(base + "/api/validate", json={"spec": SPEC}, timeout=60)
        assert validation.status_code == 200
        assert validation.json()["valid"] is True

        compiled = requests.post(base + "/api/compile", json={"spec": SPEC}, timeout=120)
        assert compiled.status_code == 201, compiled.text
        project_id = compiled.json()["id"]
        assert requests.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 200
        contract = requests.get(f"{base}/api/projects/{project_id}/contract", timeout=30)
        assert contract.json()["app"] == "NotesEquipe"
        download = requests.get(f"{base}/api/projects/{project_id}/download", timeout=60)
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

        mcp = requests.post(base + "/mcp", json={"jsonrpc": "2.0", "id": 8,
                                                 "method": "tools/list"}, timeout=30)
        assert mcp.status_code == 200
        assert len(mcp.json()["result"]["tools"]) == 4


def test_erreurs_web_restent_actionnables(tmp_path):
    with _plateforme(tmp_path) as base:
        empty = requests.post(base + "/api/validate", json={"spec": ""}, timeout=30)
        assert empty.status_code == 422
        assert "vide" in empty.json()["detail"]
        assert requests.get(base + "/api/projects/invalide", timeout=30).status_code == 404


def test_le_module_de_la_plateforme_est_livre_par_le_depot(tmp_path):
    """Témoin du défaut de `.gitignore` : `src/monl_platform/app.py` avait
    disparu du dépôt sans un mot, avalé par un motif non ancré.

    Il faut une assertion à part parce qu'elle nomme la cause. Les deux tests
    ci-dessus font désormais ÉCHOUER un module absent — `uvicorn_server` ne
    traduit plus la mort d'un serveur par un `pytest.skip` (point 139) — mais
    ils le rapportent comme une panne de serveur, avec la trace d'uvicorn.
    Celui-ci dit en une ligne que le dépôt est amputé, ce qui est le vrai
    diagnostic. Le garder coûte un import ; le perdre coûterait une enquête.
    """
    from monl_platform.app import create_app

    chemins = {getattr(route, "path", None) for route in create_app(workspace=tmp_path).routes}
    assert {"/", "/health", "/api/templates", "/api/validate", "/api/compile",
            "/mcp"} <= chemins
