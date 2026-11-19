"""The web platform, tested against a REAL server.

This file mounted the platform with Starlette's `TestClient`. Two reasons to
stop doing so, the first measured in CI:

1. `starlette.testclient` now requires `httpx2`, missing from the
   repository's dependencies. The suite stopped at COLLECTION on all three
   Python versions — a perfectly working platform declared broken by its own
   checker, which point 95 already names: the checker is a client like any
   other.
2. The rest of the repository tests every HTTP scenario against an ephemeral
   uvicorn (`tests/support/server.py`). This file was the only one taking an
   in-process shortcut, and that shortcut crosses neither the real ASGI layer
   nor server startup.

The subprocess runs in `tmp_path` with `src/` on the PYTHONPATH: the
repository root can therefore receive nothing (point 64), and the test stays
true whether the package is installed or not.
"""

import os

import requests

from monl_platform.guide_data import LIMITES
from tests.support.server import uvicorn_server
from tests.test_platform_service import SPEC

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def _plateforme(tmp_path):
    """Mounts the platform on a free port, with an isolated workspace."""
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


def test_page_explains_compile_and_mcp(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base)
        page = requests.get(base + "/", timeout=30)
        assert page.status_code == 200
        assert "Describe your business" in page.text
        assert "A Monl compilation" in page.text
        assert "verified specification" in page.text
        assert "scroll-progress" in page.text
        assert "Keep your infrastructure. Make the business rules non-negotiable." in page.text
        assert "0</b><span>network calls to compile" in page.text
        assert "Try it in the console" in page.text
        assert "A clear rule becomes a usable backend." in page.text
        # The section's TITLE, not its overline: overlines were removed from
        # the site, and a test hooked to an ornament keeps a decoration instead
        # of content.
        assert "Four applications, four families of rules" in page.text
        assert 'href="/security"' in page.text
        assert "The same engine for MCP agents" in page.text
        assert 'href="/console"' in page.text
        assert 'href="/console" target="_blank" rel="noopener"' in page.text
        assert "DSL reference" in page.text
        assert "Service operational" in page.text
        assert 'id="spec-input"' not in page.text

        assert requests.get(base + "/console", allow_redirects=False, timeout=30).status_code == 303
        console = session.get(base + "/console", timeout=30)
        assert console.status_code == 200
        assert "Compilation console" in console.text
        assert 'id="spec-input"' in console.text
        assert "Your interface is free" not in console.text
        assert 'href="/docs"' in console.text
        account = session.get(base + "/account", timeout=30)
        assert account.status_code == 200
        assert "Your projects" in account.text
        assert "<h2>MCP keys" not in account.text
        mcp_page = session.get(base + "/mcp", timeout=30)
        assert mcp_page.status_code == 200
        assert "Access keys" in mcp_page.text
        assert "Create a key" in mcp_page.text
        for tool in (
            "monl_list_templates", "monl_validate_spec", "monl_compile_backend",
            "monl_list_projects", "monl_inspect_contract", "monl_diff_spec",
            "monl_update_backend",
        ):
            assert f"<span>{tool}</span>" in mcp_page.text
        for obsolete in ("monl_validate", "monl_compile", "monl_templates", "monl_example"):
            assert f"<span>{obsolete}</span>" not in mcp_page.text

        docs = requests.get(base + "/docs", timeout=30)
        assert docs.status_code == 200
        assert "Write a Monl specification" in docs.text
        assert "The essential keywords" in docs.text
        assert "Access and security" in docs.text
        assert 'href="/api-docs"' in docs.text
        assert requests.get(base + "/api-docs", timeout=30).status_code == 200

        security = requests.get(base + "/security", timeout=30)
        assert security.status_code == 200
        assert "The rules are enforced" in security.text
        assert "What the suite actually tries to break" in security.text
        assert "The deployment must guarantee" in security.text

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
        assert len(mcp.json()["result"]["tools"]) == 7


def test_web_errors_stay_actionable(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base)
        empty = requests.post(base + "/api/validate", json={"spec": ""}, timeout=30)
        assert empty.status_code == 422
        assert "empty" in empty.json()["detail"]
        assert session.get(base + "/api/projects/invalide", timeout=30).status_code == 404


def test_login_is_limited_and_announces_the_delay(tmp_path):
    with _plateforme(tmp_path) as base:
        for _ in range(5):
            response = requests.post(base + "/api/auth/login", json={
                "email": "absent@example.com", "password": "mauvais-secret",
            }, timeout=30)
            assert response.status_code == 401
        blocked = requests.post(base + "/api/auth/login", json={
            "email": "absent@example.com", "password": "mauvais-secret",
        }, timeout=30)
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0


def test_accounts_isolate_projects_and_mcp_keys(tmp_path):
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
        assert "not found" in foreign.text
        assert alice.delete(f"{base}/api/keys/{key_id}", timeout=30).status_code == 204
        assert requests.post(base + "/mcp", json=call,
                             headers={"Authorization": f"Bearer {raw_key}"},
                             timeout=30).status_code == 401
        assert alice.delete(f"{base}/api/projects/{project_id}", timeout=30).status_code == 204
        assert alice.get(f"{base}/api/projects/{project_id}", timeout=30).status_code == 404


def test_the_platform_module_is_shipped_by_the_repository(tmp_path):
    """Witness of the `.gitignore` defect: `src/monl_platform/app.py` had
    vanished from the repository without a word, swallowed by an unanchored
    pattern.

    A separate assertion is needed because it names the cause. The two tests
    above now make a missing module FAIL — `uvicorn_server` no longer turns a
    server's death into a `pytest.skip` (point 140) — but they report it as a
    server failure, with uvicorn's trace. This one says in one line that the
    repository is truncated, which is the real diagnosis. Keeping it costs an
    import; losing it would cost an investigation.
    """
    from monl_platform.app import create_app

    chemins = {getattr(route, "path", None) for route in create_app(workspace=tmp_path).routes}
    assert {"/", "/console", "/login", "/account", "/docs", "/api-docs", "/security", "/health", "/api/templates", "/api/validate", "/api/compile",
            "/mcp"} <= chemins


def test_the_guide_is_served_and_covers_its_sections(tmp_path):
    """A platform that accepts a specification must say how to write one. The
    guide is therefore a route like any other, tested as such — not a file one
    hopes is present."""
    with _plateforme(tmp_path) as base:
        page = requests.get(base + "/guide", timeout=30)
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        for ancre in ('id="frontiere"', 'id="demarrer"', 'id="dsl"',
                      'id="api"', 'id="mcp"', 'id="limites"'):
            assert ancre in page.text, ancre
        # The limits must be STATED, not discovered by pasting a spec that
        # declares a logo. The labels are READ from the table and never copied
        # here: the frozen sentence that lived on this line survived the brick
        # that had made it false (point 180).
        for titre, _texte in LIMITES:
            assert titre in page.text, titre


def test_the_examples_are_served_and_compile_through_the_api(tmp_path):
    """The catalog is not decorative: what it serves must go through the whole
    journey, from the gallery to the archive."""
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


def test_version_favicon_and_not_found_page(tmp_path):
    with _plateforme(tmp_path) as base:
        session = _compte(base, "errors@example.com")
        version = requests.get(base + "/api/version", timeout=30).json()
        assert version["compiler"] and version["contract"]

        favicon = requests.get(base + "/favicon.svg", timeout=30)
        assert favicon.status_code == 200
        assert favicon.headers["content-type"].startswith("image/svg+xml")

        wordmark = requests.get(base + "/brand/monl-wordmark.png", timeout=30)
        assert wordmark.status_code == 200
        assert wordmark.headers["content-type"].startswith("image/png")
        assert wordmark.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert "<text" not in favicon.text

        logo = requests.get(base + "/logo.svg", timeout=30)
        assert logo.status_code == 200
        assert logo.headers["content-type"].startswith("image/svg+xml")
        # Compared with the SOURCE and not a literal: a logo served in another
        # color than the sheet's is a defect, whatever the palette of the
        # moment.
        from monl_platform.theme import LOGO_SVG
        assert logo.text == LOGO_SVG

        # A visitor gets a page, an API client gets JSON: serving HTML to curl
        # would make the error unreadable where it is read.
        navigateur = requests.get(base + "/inexistant",
                                  headers={"Accept": "text/html"}, timeout=30)
        assert navigateur.status_code == 404
        assert "This page does not exist" in navigateur.text

        client = session.get(base + "/api/projects/inexistant", timeout=30)
        assert client.status_code == 404
        assert client.json()["detail"]
