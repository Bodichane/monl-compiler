"""Preuves HTTP de la plateforme, contre Uvicorn et ses processus enfants."""

import json
import os
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.store import PlatformStore

SPEC = """app PlatformWeb

entity Item
    label: String

# Admin est provisionné hors ligne ; ces tests portent sur l'hébergement et
# le routage, pas sur un parcours de vitrine pour ce rôle.
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
<section data-monl-section="hero"><img src="hero.svg"><h1>site produit réel</h1><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Commencer</a></section>
<section data-monl-section="editorial"><h2>Notre récit</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="a-propos"><h2>À propos</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="services"><h2>Services</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="trust"><h2>Ce que nous garantissons</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="contact"><h2>Nous écrire</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a><form><label>Message<input></label><button>Envoyer</button></form></section>
<section data-monl-section="workspace"><h2>Espace de travail</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="footer"><p>Atelier de démonstration, exploité
pour les besoins du test. Aucune donnée réelle.</p><a href="#haut">Revenir en
haut</a></section>
<section data-monl-section="closing-cta"><h2>Passer à l'action</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<div data-monl-media="project"></div>
</body></html>
"""


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __init__(self):
        self.calls = 0
        self.last_usage = None

    def __call__(self, _prompt):
        self.calls += 1
        self.last_usage = {
            "duration_seconds": 0.01,
            "input_tokens": 17,
            "output_tokens": 23,
            "total_tokens": 40,
        }
        return json.dumps(
            {
                "files": {
                    "index.html": FRONTEND,
                    "hero.svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
                    "editorial.svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
                }
            }
        )


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def running_platform(tmp_path):
    provider = FakeProvider()
    app = create_app(
        database=tmp_path / "platform.db",
        workspace_root=tmp_path / "projects",
        domain="localhost",
        jwt_secret="secret-for-platform-web-tests-123456",
        provider=provider,
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
            pytest.fail("le serveur de plateforme n'a pas démarré")
        yield base, app, provider
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _register(base, identifier):
    response = requests.post(
        f"{base}/register",
        json={"identifier": identifier, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _wait_for_build(base, token, project_id):
    for _ in range(200):
        response = requests.get(
            f"{base}/projects/{project_id}", headers=_auth(token), timeout=10
        )
        assert response.status_code == 200, response.text
        builds = response.json()["project"]["builds"]
        if builds and builds[-1]["state"] in {"reussie", "echouee"}:
            return builds[-1]
        time.sleep(0.02)
    pytest.fail("la construction n'a pas atteint un état terminal")


def test_parcours_complet_modele_construction_et_site_serve(running_platform):
    base, _app, provider = running_platform
    token = _register(base, "alice@example.test")

    catalogue = requests.get(f"{base}/catalogue", timeout=10)
    assert catalogue.status_code == 200
    assert catalogue.json()["models"]

    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={
            "slug": "alice-site",
            "model": "Portfolio / site vitrine",
            "app_name": "PlatformPortfolio",
            "description": "Un portfolio construit depuis le catalogue.",
        },
        timeout=10,
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]

    queued = requests.post(
        f"{base}/projects/{project['id']}/builds",
        headers=_auth(token),
        timeout=10,
    )
    assert queued.status_code == 202, queued.text
    build = _wait_for_build(base, token, project["id"])
    assert build["state"] == "reussie", build
    assert build["tokens_consumed"] == 40
    assert build["snapshot_path"] == f"revisions/build-{build['id']}"
    assert build["snapshot_sha256"]
    assert build["snapshot_bytes"] > 0
    assert provider.calls == 1
    # Une construction ne doit pas garder un uvicorn par projet inactif : le
    # relais est lancé à la demande par le sous-domaine ou POST /start.
    assert not _app.state.sites.is_running(project["id"])

    site = requests.get(
        f"{base}/site/",
        headers={"Host": f"alice-site.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=10,
    )
    assert site.status_code == 200, site.text
    assert "site produit réel" in site.text
    api = requests.get(
        f"{base}/project?limit=5",
        headers={"Host": f"alice-site.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=10,
    )
    assert api.status_code == 200, api.text


def test_un_nom_d_application_non_identifiant_est_un_refus_client(running_platform):
    base, _app, _provider = running_platform
    token = _register(base, "nom-invalide@example.test")

    response = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={
            "slug": "nom-invalide",
            "model": "Portfolio / site vitrine",
            "app_name": "Atelier Horizon",
            "description": "Un portfolio de démonstration.",
        },
        timeout=10,
    )

    assert response.status_code == 422
    assert "Nom de l'application" in response.json()["detail"]


def test_echec_ecriture_spec_ne_laissent_pas_un_projet_orphelin(
        running_platform, monkeypatch):
    base, app, _provider = running_platform
    token = _register(base, "spec-echouee@example.test")

    class BrokenDirectory:
        def joinpath(self, _name):
            return self

        def write_text(self, _text, encoding=None):
            raise OSError("disque de test indisponible")

    import monl_platform.app as platform_app
    original_directory = platform_app.project_directory
    monkeypatch.setattr(platform_app, "project_directory", lambda *_args, **_kwargs: BrokenDirectory())
    body = {"slug": "spec-echouee", "spec": SPEC}
    failed = requests.post(
        f"{base}/projects", headers=_auth(token), json=body, timeout=10
    )
    assert failed.status_code == 422
    assert app.state.store.list_projects("spec-echouee@example.test") == []

    monkeypatch.setattr(platform_app, "project_directory", original_directory)
    recovered = requests.post(
        f"{base}/projects", headers=_auth(token), json=body, timeout=10
    )
    assert recovered.status_code == 201, recovered.text


def test_un_compte_nevoit_pas_le_projet_dun_autre(running_platform):
    base, _app, _provider = running_platform
    alice = _register(base, "alice@example.test")
    bob = _register(base, "bob@example.test")
    created = requests.post(
        f"{base}/projects", headers=_auth(alice), json={"slug": "secret", "spec": SPEC}, timeout=10
    )
    assert created.status_code == 201
    project_id = created.json()["project"]["id"]

    forbidden = requests.get(
        f"{base}/projects/{project_id}", headers=_auth(bob), timeout=10
    )
    missing = requests.get(
        f"{base}/projects/999999", headers=_auth(bob), timeout=10
    )
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json()
    assert requests.get(f"{base}/projects", headers=_auth(bob), timeout=10).json() == {
        "projects": []
    }


def test_une_construction_en_cours_est_marquee_echouee_au_demarrage(tmp_path):
    database = tmp_path / "platform.db"
    store = PlatformStore(database)
    account = store.create_account("restart@example.test")
    project = store.create_project(account, "restart")
    build = store.create_build(project)
    store.start_build(build)
    store.close()

    app = create_app(
        database=database,
        workspace_root=tmp_path / "projects",
        jwt_secret="secret-for-platform-restart-tests-123456",
        provider=FakeProvider(),
        poll_interval=0.01,
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        status = app.state.store.get_build(build)
        assert status["state"] == "echouee"
        assert "redémarrage" in status["error_message"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_un_site_non_construit_refuse_de_demarrer_proprement(running_platform):
    base, _app, _provider = running_platform
    token = _register(base, "new@example.test")
    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={"slug": "non-construit", "spec": SPEC},
        timeout=10,
    )
    project_id = created.json()["project"]["id"]
    host = {"Host": f"non-construit.localhost:{base.rsplit(':', 1)[1]}"}

    response = requests.get(f"{base}/site/", headers=host, timeout=10)
    assert response.status_code == 409
    assert "pas construit" in response.json()["detail"]
    started = requests.post(
        f"{base}/projects/{project_id}/start", headers=_auth(token), timeout=10
    )
    assert started.status_code == 409


def test_un_snapshot_manquant_ne_fait_pas_servir_un_dossier_actif(running_platform):
    base, app, _provider = running_platform
    token = _register(base, "missing-snapshot@example.test")
    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={"slug": "missing-snapshot", "spec": SPEC},
        timeout=10,
    )
    project_id = created.json()["project"]["id"]
    queued = requests.post(
        f"{base}/projects/{project_id}/builds",
        headers=_auth(token),
        timeout=10,
    )
    assert queued.status_code == 202
    build = _wait_for_build(base, token, project_id)
    assert build["state"] == "reussie"
    project = app.state.store.get_project(project_id)
    project_dir = app.state.sites._project_directory(project)
    snapshot = project_dir / build["snapshot_path"]
    stopped = requests.post(
        f"{base}/projects/{project_id}/stop",
        headers=_auth(token),
        timeout=10,
    )
    assert stopped.status_code == 200
    snapshot.rename(snapshot.with_name("deleted"))
    response = requests.post(
        f"{base}/projects/{project_id}/start",
        headers=_auth(token),
        timeout=10,
    )
    assert response.status_code == 409
    assert "snapshot" in response.json()["detail"]


def test_arreter_un_projet_arrete_son_processus(running_platform):
    base, _app, _provider = running_platform
    token = _register(base, "stop@example.test")
    created = requests.post(
        f"{base}/projects",
        headers=_auth(token),
        json={"slug": "stop-site", "spec": SPEC},
        timeout=10,
    )
    project_id = created.json()["project"]["id"]
    requests.post(f"{base}/projects/{project_id}/builds", headers=_auth(token), timeout=10)
    _wait_for_build(base, token, project_id)
    started = requests.post(
        f"{base}/projects/{project_id}/start", headers=_auth(token), timeout=10
    )
    assert started.status_code == 200, started.text
    pid = started.json()["pid"]
    stopped = requests.post(
        f"{base}/projects/{project_id}/stop", headers=_auth(token), timeout=10
    )
    assert stopped.status_code == 200
    for _ in range(100):
        if not os.path.exists(f"/proc/{pid}"):
            break
        time.sleep(0.02)
    assert not os.path.exists(f"/proc/{pid}")
