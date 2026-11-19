"""HTTP proofs of the platform console and of its host boundary."""

import re
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.paths import project_directory

SPEC = """app ConsoleWeb

entity Item
    label: String

# Admin is provisioned offline: the console tests neither a public registration
# nor a back office shipped in the showcase.
actor Admin

rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item
"""

RESSOURCE_EXTERNE = re.compile(
    r"<(?:link|script|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def running_platform(tmp_path):
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("the console server did not start")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _register(base, identifier="console@example.test"):
    session = requests.Session()
    response = requests.post(
        f"{base}/api/auth/register",
        json={"email": identifier, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    session.cookies.update(response.cookies)
    return session


def test_the_console_is_served_without_remote_resources(running_platform):
    """The console lives at /console: the root carries the presentation page."""
    session = _register(running_platform, "console-page@example.test")
    response = session.get(f"{running_platform}/console", timeout=10)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="en">' in response.text
    # The apostrophe is ESCAPED in the served JavaScript literal. This
    # assertion looked for the BARE form and therefore passed precisely because
    # the page was dead: the script raised `SyntaxError: Unexpected identifier
    # 'API'` and no button answered any more. A string present in HTML cannot
    # tell a working page from a broken one — tests/test_console_javascript.py
    # decides, by parsing it.
    assert "Start the project\\'s API" in response.text
    assert "prefers-reduced-motion" in response.text
    assert not RESSOURCE_EXTERNE.search(response.text)


def test_the_console_compiles_then_starts_the_project_api(running_platform):
    """The console's whole journey, against a real server (point 162).

    What the earlier version proved — an AI build carried through — no longer
    exists. What counts now: the catalog answers, the spec compiles, the API
    starts, and it REALLY answers.
    """
    base = running_platform
    session = _register(base)

    catalogue = requests.get(f"{base}/api/models", timeout=10)
    assert catalogue.status_code == 200
    assert len(catalogue.json()["models"]) == 10

    created = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    compilation = session.post(f"{base}/api/projects/{project_id}/compiler", timeout=60)
    assert compilation.status_code == 201, compilation.text
    assert compilation.json()["routes"] > 0

    started = session.post(f"{base}/api/projects/{project_id}/start", timeout=30)
    assert started.status_code == 200, started.text
    assert started.json()["host"].endswith(".localhost")

    # The started API REALLY answers, on its own port.
    port = started.json()["port"]
    ouvert = requests.get(f"http://127.0.0.1:{port}/item", timeout=10)
    assert ouvert.status_code == 200, ouvert.text

    arret = session.post(f"{base}/api/projects/{project_id}/stop", timeout=30)
    assert arret.status_code == 200 and arret.json()["stopped"] is True


def test_starting_without_compiling_is_refused_with_a_reason(running_platform, tmp_path):
    """Point 162's counter-proof: starting REQUIRES a compilation.

    Without it, a permissive ``_require_site`` would let uvicorn die on an empty
    folder and the console would show "the server did not start" — one would
    look for the failure on the wrong side.
    """
    base = running_platform
    session = _register(base, "sans-compilation@example.test")
    cree = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    project_id = cree.json()["id"]

    # A missing backend must always be refused, even with a manifest.
    compte = session.get(f"{base}/api/auth/me", timeout=10).json()["id"]
    dossier = project_directory(tmp_path / "projects", compte, project_id)
    (dossier / "app.py").unlink()

    refus = session.post(f"{base}/api/projects/{project_id}/start", timeout=30)

    assert refus.status_code == 409, refus.text
    assert "not compiled" in refus.json()["detail"]


def test_host_routing_serves_the_api_and_stays_distinct_from_the_console(running_platform):
    base = running_platform
    session = _register(base, "host@example.test")
    created = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    project_id = created.json()["id"]
    assert session.post(
        f"{base}/api/projects/{project_id}/compiler", timeout=60
    ).status_code == 201

    # The relay is born on the first access to the subdomain, without an
    # explicit start.
    servi = requests.get(
        f"{base}/item",
        headers={"Host": f"consoleweb.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=30,
    )
    console = session.get(f"{base}/console", timeout=10)

    assert servi.status_code == 200, servi.text
    assert "data" in servi.json()
    assert console.status_code == 200
    assert "Compilation console" in console.text
    session.post(f"{base}/api/projects/{project_id}/stop", timeout=30)


def test_an_account_can_only_compile_its_own_projects(running_platform):
    """Compiling writes into a private folder: it is an owned action."""
    base = running_platform
    alice = _register(base, "compilatrice@example.test")
    bob = _register(base, "intrus@example.test")

    cree = alice.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    assert cree.status_code == 201, cree.text
    project_id = cree.json()["id"]

    pour_alice = alice.post(f"{base}/api/projects/{project_id}/compiler", timeout=60)
    pour_bob = bob.post(f"{base}/api/projects/{project_id}/compiler", timeout=60)

    assert pour_alice.status_code == 201, pour_alice.text
    assert pour_bob.status_code == 404, pour_bob.text
    assert bob.post(
        f"{base}/api/projects/{project_id}/start", timeout=30
    ).status_code == 404
