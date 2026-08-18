"""Preuves HTTP de la console de plateforme et de sa frontière d'hôte."""

import json
import re
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app

SPEC = """app ConsoleWeb

entity Item
    label: String

# Admin est provisionné hors ligne : la console ne teste pas une inscription
# publique ni un back-office livré dans la vitrine.
actor Admin

rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item
"""

FRONTEND = """<!doctype html>
<html><body>
<section data-monl-section="hero"><h1>site servi par son hôte</h1></section>
<section data-monl-section="editorial">Récit</section>
<section data-monl-section="a-propos">À propos</section>
<section data-monl-section="services">Services</section>
<section data-monl-section="trust">Confiance</section>
<section data-monl-section="contact">Contact</section>
<section data-monl-section="workspace">Espace de travail</section>
<section data-monl-section="closing-cta">Fin</section>
</body></html>
"""


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):
        self.last_usage = {
            "duration_seconds": 0.01,
            "input_tokens": 17,
            "output_tokens": 23,
            "total_tokens": 40,
        }
        return json.dumps({"files": {"index.html": FRONTEND}})


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def running_platform(tmp_path):
    app = create_app(
        database=tmp_path / "platform.db",
        workspace_root=tmp_path / "projects",
        domain="localhost",
        jwt_secret="secret-for-platform-console-tests-123456",
        provider=FakeProvider(),
        poll_interval=0.01,
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
            pytest.fail("le serveur de console n'a pas démarré")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _register(base, identifier="console@example.test"):
    response = requests.post(
        f"{base}/register",
        json={"identifier": identifier, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _wait_for_build(base, token, project_id):
    for _ in range(200):
        response = requests.get(
            f"{base}/projects/{project_id}", headers=_auth(token), timeout=10
        )
        assert response.status_code == 200, response.text
        build = response.json()["project"]["builds"][-1]
        if build["state"] in {"reussie", "echouee"}:
            return build
        time.sleep(0.02)
    pytest.fail("la construction n'a pas atteint un état terminal")


def test_la_console_est_servie_a_la_racine_sans_ressource_distante(running_platform):
    response = requests.get(running_platform, timeout=10)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="fr">' in response.text
    assert "Créer et lancer la construction" in response.text
    assert "prefers-reduced-motion" in response.text
    assert not re.search(r"https?://|<link\b|<script[^>]+\bsrc=|@import", response.text, re.I)


def test_la_console_expose_le_catalogue_le_quota_et_l_etat_d_un_projet(running_platform):
    base = running_platform
    token = _register(base)

    catalogue = requests.get(f"{base}/catalogue", timeout=10)
    assert catalogue.status_code == 200
    assert len(catalogue.json()["models"]) == 10

    usage = requests.get(f"{base}/usage", headers=_auth(token), timeout=10)
    assert usage.status_code == 200
    assert usage.json()["usage"]["consumed_tokens"] == 0

    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={"slug": "console-site", "spec": SPEC},
        timeout=10,
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    assert project["host"] == "console-site.localhost"
    assert project["running"] is False

    queued = requests.post(
        f"{base}/projects/{project['id']}/builds",
        headers=_auth(token),
        timeout=10,
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["build"]["state"] in {"en_attente", "en_cours", "reussie"}
    build = _wait_for_build(base, token, project["id"])
    assert build["state"] == "reussie", build

    refreshed = requests.get(
        f"{base}/projects/{project['id']}", headers=_auth(token), timeout=10
    )
    assert refreshed.json()["project"]["host"] == "console-site.localhost"
    assert refreshed.json()["project"]["running"] is True


def test_le_routage_par_hote_des_sites_reste_distinct_de_la_console(running_platform):
    base = running_platform
    token = _register(base, "host@example.test")
    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={"slug": "host-site", "spec": SPEC},
        timeout=10,
    )
    project_id = created.json()["project"]["id"]
    build = requests.post(
        f"{base}/projects/{project_id}/builds",
        headers=_auth(token),
        timeout=10,
    )
    assert build.status_code == 202
    result = _wait_for_build(base, token, project_id)
    assert result["state"] == "reussie", result

    site = requests.get(
        f"{base}/site/",
        headers={"Host": f"host-site.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=10,
    )
    console = requests.get(base, timeout=10)
    assert site.status_code == 200, site.text
    assert "site servi par son hôte" in site.text
    assert console.status_code == 200
    assert "monl / console" in console.text
