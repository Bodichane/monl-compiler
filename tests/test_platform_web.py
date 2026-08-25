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


def _compte(base, email="test@example.com"):
    session = requests.Session()
    response = session.post(base + "/api/auth/register", json={
        "email": email, "password": "mot-de-passe-test-123",
    }, timeout=30)
    assert response.status_code == 201, response.text
    return session


def test_page_explique_compile_et_mcp(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base)
        page = requests.get(base + "/", timeout=30)
        assert page.status_code == 200
        assert "Décrivez vos règles" in page.text
        assert "Ce que vous allez faire" in page.text
        assert "Créer un backend" in page.text
        assert "Une spec entre. Un backend complet sort" in page.text
        assert "Cas métier compilables" in page.text
        assert 'href="/security"' in page.text
        assert "Le même moteur par MCP" in page.text
        assert 'href="/console"' in page.text
        assert "Documentation développeur" in page.text
        assert "Service opérationnel" in page.text
        assert 'id="spec-input"' not in page.text

        assert requests.get(base + "/console", allow_redirects=False, timeout=30).status_code == 303
        console = session.get(base + "/console", timeout=30)
        assert console.status_code == 200
        assert "Console de compilation" in console.text
        assert 'id="spec-input"' in console.text
        assert "Votre interface est libre" not in console.text
        assert 'href="/docs"' in console.text
        account = session.get(base + "/account", timeout=30)
        assert account.status_code == 200
        assert "Vos projets et accès" in account.text
        assert "Clés MCP" in account.text

        docs = requests.get(base + "/docs", timeout=30)
        assert docs.status_code == 200
        assert "Écrire une spécification Monl" in docs.text
        assert "Les mots-clés essentiels" in docs.text
        assert "Accès et sécurité" in docs.text
        assert 'href="/api-docs"' in docs.text
        assert requests.get(base + "/api-docs", timeout=30).status_code == 200

        security = requests.get(base + "/security", timeout=30)
        assert security.status_code == 200
        assert "Les règles sont exécutées" in security.text
        assert "Attaques couvertes" in security.text
        assert "Le déploiement doit garantir" in security.text

        assert requests.get(base + "/health", timeout=30).json()["status"] == "ok"
        templates = requests.get(base + "/api/templates", timeout=30).json()
        assert len(templates["templates"]) == 10

        validation = requests.post(base + "/api/validate", json={"spec": SPEC}, timeout=60)
        assert validation.status_code == 200
        assert validation.json()["valid"] is True

        compiled = session.post(base + "/api/compile", json={"spec": SPEC}, timeout=120)
        assert compiled.status_code == 201, compiled.text
        project_id = compiled.json()["id"]
        assert session.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 200
        contract = session.get(f"{base}/api/projects/{project_id}/contract", timeout=30)
        assert contract.json()["app"] == "NotesEquipe"
        download = session.get(f"{base}/api/projects/{project_id}/download", timeout=60)
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

        key = session.post(base + "/api/keys", json={"name": "Test MCP"}, timeout=30)
        assert key.status_code == 201
        mcp = requests.post(base + "/mcp", headers={
            "Authorization": "Bearer " + key.json()["key"]},
            json={"jsonrpc": "2.0", "id": 8, "method": "tools/list"}, timeout=30)
        assert mcp.status_code == 200
        assert len(mcp.json()["result"]["tools"]) == 4


def test_erreurs_web_restent_actionnables(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base)
        empty = requests.post(base + "/api/validate", json={"spec": ""}, timeout=30)
        assert empty.status_code == 422
        assert "vide" in empty.json()["detail"]
        assert session.get(base + "/api/projects/invalide", timeout=30).status_code == 404


def test_comptes_isolent_projets_et_cles_mcp(tmp_path):
    with _plateforme(tmp_path) as base:
        alice = _compte(base, "alice@example.com")
        bob = _compte(base, "bob@example.com")

        anonymous = requests.post(base + "/api/compile", json={"spec": SPEC}, timeout=30)
        assert anonymous.status_code == 401
        compiled = alice.post(base + "/api/compile", json={"spec": SPEC}, timeout=120)
        assert compiled.status_code == 201, compiled.text
        project_id = compiled.json()["id"]
        assert alice.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 200
        assert bob.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 404
        assert bob.delete(f"{base}/api/projects/{project_id}", timeout=30).status_code == 404
        assert alice.get(base + "/api/projects", timeout=30).json()["projects"][0][
            "project_id"] == project_id
        assert bob.get(base + "/api/projects", timeout=30).json()["projects"] == []

        created = alice.post(base + "/api/keys", json={"name": "Claude Code"}, timeout=30)
        raw_key, key_id = created.json()["key"], created.json()["id"]
        listed = alice.get(base + "/api/keys", timeout=30).json()["keys"]
        assert "key" not in listed[0]
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert requests.post(base + "/mcp", json=call, timeout=30).status_code == 401
        assert requests.post(base + "/mcp", json=call,
                             headers={"Authorization": f"Bearer {raw_key}"},
                             timeout=30).status_code == 200
        inspect_call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "monl_inspect_contract", "arguments": {"project_id": project_id}}}
        own_inspect = requests.post(base + "/mcp", json=inspect_call,
                                    headers={"Authorization": f"Bearer {raw_key}"}, timeout=30)
        assert "NotesEquipe" in own_inspect.text
        bob_key = bob.post(base + "/api/keys", json={"name": "Bob"}, timeout=30).json()["key"]
        foreign = requests.post(base + "/mcp", json=inspect_call,
                                headers={"Authorization": f"Bearer {bob_key}"}, timeout=30)
        assert foreign.json()["result"]["isError"] is True
        assert "introuvable" in foreign.text
        assert alice.delete(f"{base}/api/keys/{key_id}", timeout=30).status_code == 204
        assert requests.post(base + "/mcp", json=call,
                             headers={"Authorization": f"Bearer {raw_key}"},
                             timeout=30).status_code == 401
        assert alice.delete(f"{base}/api/projects/{project_id}", timeout=30).status_code == 204
        assert alice.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 404


def test_le_module_de_la_plateforme_est_livre_par_le_depot(tmp_path):
    """Témoin du défaut de `.gitignore` : `src/monl_platform/app.py` avait
    disparu du dépôt sans un mot, avalé par un motif non ancré.

    Il faut une assertion à part, car les deux tests ci-dessus ne le
    rattraperaient PAS : un module absent tue le sous-processus uvicorn, et
    `uvicorn_server` traduit ce cas par un `pytest.skip`. Un dépôt amputé
    reviendrait donc au vert — un faux vert exactement là où le projet vient
    d'en payer un.
    """
    from monl_platform.app import create_app

    chemins = {getattr(route, "path", None) for route in create_app(workspace=tmp_path).routes}
    assert {"/", "/console", "/login", "/account", "/docs", "/api-docs", "/security", "/health", "/api/templates", "/api/validate", "/api/compile",
            "/mcp"} <= chemins


def test_le_guide_est_servi_et_couvre_ses_sections(tmp_path):
    """Une plateforme qui accepte une spécification doit dire comment on
    l'écrit. Le guide est donc une route comme une autre, éprouvée comme
    telle — pas un fichier qu'on espère présent."""
    with _plateforme(tmp_path) as base:
        page = requests.get(base + "/guide", timeout=30)
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        for ancre in ('id="frontiere"', 'id="demarrer"', 'id="dsl"',
                      'id="api"', 'id="mcp"', 'id="limites"'):
            assert ancre in page.text, ancre
        # La limite la plus surprenante doit être ÉNONCÉE, pas découverte en
        # collant une spec qui déclare un logo.
        assert "Aucun téléversement" in page.text


def test_les_exemples_sont_servis_et_compilent_par_lapi(tmp_path):
    """Le catalogue n'est pas décoratif : ce qu'il sert doit traverser tout le
    parcours, de la galerie à l'archive."""
    with _plateforme(tmp_path) as base:
        session = _compte(base, "examples@example.com")
        catalogue = requests.get(base + "/api/examples", timeout=30).json()["examples"]
        assert len(catalogue) >= 4
        assert all("spec" not in entree for entree in catalogue)

        premier = catalogue[0]["id"]
        spec = requests.get(f"{base}/api/examples/{premier}", timeout=30).json()["spec"]
        assert "app " in spec

        compile = session.post(base + "/api/compile", json={"spec": spec}, timeout=180)
        assert compile.status_code == 201, compile.text
        archive = session.get(
            f"{base}/api/projects/{compile.json()['id']}/download", timeout=60)
        assert archive.status_code == 200
        assert archive.headers["content-type"] == "application/zip"

        assert requests.get(base + "/api/examples/inconnu", timeout=30).status_code == 404


def test_version_favicon_et_page_introuvable(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base, "errors@example.com")
        version = requests.get(base + "/api/version", timeout=30).json()
        assert version["compiler"] and version["contract"]

        favicon = requests.get(base + "/favicon.svg", timeout=30)
        assert favicon.status_code == 200
        assert favicon.headers["content-type"].startswith("image/svg+xml")

        # Un visiteur reçoit une page, un client d'API reçoit du JSON : servir
        # du HTML à curl rendrait l'erreur illisible là où on la lit.
        navigateur = requests.get(base + "/inexistant",
                                  headers={"Accept": "text/html"}, timeout=30)
        assert navigateur.status_code == 404
        assert "Cette page n'existe pas" in navigateur.text

        client = session.get(base + "/api/projects/inexistant", timeout=30)
        assert client.status_code == 404
        assert client.json()["detail"]
