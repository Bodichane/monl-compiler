"""Preuves HTTP de la console de plateforme et de sa frontière d'hôte."""

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
            pytest.fail("le serveur de console n'a pas démarré")
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


def test_la_console_est_servie_sans_ressource_distante(running_platform):
    """La console vit sur /console : la racine porte la page de présentation."""
    session = _register(running_platform, "console-page@example.test")
    response = session.get(f"{running_platform}/console", timeout=10)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="fr">' in response.text
    assert "Démarrer l'API" in response.text
    assert "prefers-reduced-motion" in response.text
    assert not RESSOURCE_EXTERNE.search(response.text)


def test_la_console_compile_puis_demarre_l_api_du_projet(running_platform):
    """Le parcours entier de la console, contre un vrai serveur (point 161).

    Ce que la version d'avant prouvait — une construction IA menée à son
    terme — n'existe plus. Ce qui compte désormais : le catalogue répond, la
    spec compile, l'API démarre, et elle RÉPOND vraiment.
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

    # L'API démarrée répond POUR DE VRAI, sur son propre port.
    port = started.json()["port"]
    ouvert = requests.get(f"http://127.0.0.1:{port}/item", timeout=10)
    assert ouvert.status_code == 200, ouvert.text

    arret = session.post(f"{base}/api/projects/{project_id}/stop", timeout=30)
    assert arret.status_code == 200 and arret.json()["stopped"] is True


def test_demarrer_sans_compiler_est_refuse_en_le_disant(running_platform):
    """La contre-épreuve du point 161 : le démarrage EXIGE une compilation.

    Sans elle, un ``_require_site`` permissif laisserait uvicorn mourir sur un
    dossier vide et la console afficherait « le serveur n'a pas démarré » —
    on chercherait la panne du mauvais côté.
    """
    base = running_platform
    session = _register(base, "sans-compilation@example.test")
    cree = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    project_id = cree.json()["id"]

    refus = session.post(f"{base}/api/projects/{project_id}/start", timeout=30)

    assert refus.status_code == 409, refus.text
    assert "compilé" in refus.json()["detail"]


def test_le_routage_par_hote_sert_l_api_et_reste_distinct_de_la_console(running_platform):
    base = running_platform
    session = _register(base, "host@example.test")
    created = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    project_id = created.json()["id"]
    assert session.post(
        f"{base}/api/projects/{project_id}/compiler", timeout=60
    ).status_code == 201

    # Le relais naît au premier accès au sous-domaine, sans démarrage explicite.
    servi = requests.get(
        f"{base}/item",
        headers={"Host": f"consoleweb.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=30,
    )
    console = session.get(f"{base}/console", timeout=10)

    assert servi.status_code == 200, servi.text
    assert "data" in servi.json()
    assert console.status_code == 200
    assert "Console de compilation" in console.text
    session.post(f"{base}/api/projects/{project_id}/stop", timeout=30)


def test_un_compte_ne_peut_compiler_que_ses_propres_projets(running_platform):
    """Compiler écrit dans un dossier privé : c'est une action possédée."""
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
