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
<section data-monl-section="hero"><h1>site servi par son hôte</h1><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Commencer</a></section>
<section data-monl-section="editorial"><h2>Notre récit</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="a-propos"><h2>À propos</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="services"><h2>Services</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="trust"><h2>Ce que nous garantissons</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="contact"><h2>Nous écrire</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a><form><label>Message<input></label><button>Envoyer</button></form></section>
<section data-monl-section="workspace"><h2>Espace de travail</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>
<section data-monl-section="closing-cta"><h2>Passer à l'action</h2><p>Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. Un paragraphe qui décrit réellement ce que ce site propose, assez long pour qu'un visiteur y trouve une information et non un gabarit vide. </p><a href="#suite">Continuer</a></section>

</body></html>
"""

RESSOURCE_EXTERNE = re.compile(
    r"<(?:link|script|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)


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
        workspace=tmp_path / "projects",
        domain="localhost",
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
    session = requests.Session()
    response = requests.post(
        f"{base}/api/auth/register",
        json={"email": identifier, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert response.status_code == 201, response.text
    session.cookies.update(response.cookies)
    return session


def _wait_for_build(base, session, project_id):
    for _ in range(200):
        response = requests.get(
            f"{base}/api/projects/{project_id}/builds", cookies=session.cookies, timeout=10
        )
        assert response.status_code == 200, response.text
        build = response.json()["builds"][-1]
        if build["state"] in {"reussie", "echouee"}:
            return build
        time.sleep(0.02)
    pytest.fail("la construction n'a pas atteint un état terminal")


def test_la_console_est_servie_sans_ressource_distante(running_platform):
    """La console vit sur /console : la racine porte la page de présentation."""
    session = _register(running_platform, "console-page@example.test")
    response = session.get(f"{running_platform}/console", timeout=10)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="fr">' in response.text
    assert "Créer et lancer la construction" in response.text
    assert "prefers-reduced-motion" in response.text
    assert not RESSOURCE_EXTERNE.search(response.text)


def test_la_console_expose_le_catalogue_le_quota_et_l_etat_d_un_projet(running_platform):
    base = running_platform
    session = _register(base)

    catalogue = requests.get(f"{base}/api/models", timeout=10)
    assert catalogue.status_code == 200
    assert len(catalogue.json()["models"]) == 10

    usage = session.get(f"{base}/api/usage", timeout=10)
    assert usage.status_code == 200
    assert usage.json()["usage"]["consumed_tokens"] == 0

    created = session.post(
        f"{base}/api/compile",
        json={"spec": SPEC},
        timeout=10,
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    queued = session.post(
        f"{base}/api/projects/{project_id}/builds",
        timeout=10,
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["build"]["state"] in {"en_attente", "en_cours", "reussie"}
    build = _wait_for_build(base, session, project_id)
    assert build["state"] == "reussie", build

    started = session.post(f"{base}/api/projects/{project_id}/start", timeout=30)
    assert started.status_code == 200, started.text
    started_host = started.json()["host"]
    assert started_host.endswith(".localhost")

    # Le build publie un snapshot mais ne monopolise pas un processus : le
    # relais naît au premier accès au sous-domaine.
    site = requests.get(
        f"{base}/site/",
        headers={"Host": f"{started_host}:{base.rsplit(':', 1)[1]}"},
        timeout=10,
    )
    assert site.status_code == 200, site.text
    assert session.post(f"{base}/api/projects/{project_id}/stop", timeout=30).status_code == 200


def test_le_routage_par_hote_des_sites_reste_distinct_de_la_console(running_platform):
    base = running_platform
    session = _register(base, "host@example.test")
    created = session.post(
        f"{base}/api/compile",
        json={"spec": SPEC},
        timeout=10,
    )
    project_id = created.json()["id"]
    build = session.post(
        f"{base}/api/projects/{project_id}/builds",
        timeout=10,
    )
    assert build.status_code == 202
    result = _wait_for_build(base, session, project_id)
    assert result["state"] == "reussie", result

    site = requests.get(
        f"{base}/site/",
        headers={"Host": f"consoleweb.localhost:{base.rsplit(':', 1)[1]}"},
        timeout=10,
    )
    console = session.get(f"{base}/console", timeout=10)
    assert site.status_code == 200, site.text
    assert "site servi par son hôte" in site.text
    assert console.status_code == 200
    assert "Console de compilation" in console.text


def test_la_console_peut_suivre_les_etapes_reelles_d_une_construction(running_platform):
    """Le suivi s'appuie sur ce que la construction a JOURNALISÉ, pas sur une
    progression inventée : la route existe et répond pour une construction
    réelle, même quand le fournisseur ne travaille pas par morceaux."""
    base = running_platform
    session = _register(base, "etapes@example.test")

    cree = session.post(
        f"{base}/api/compile",
        json={"spec": SPEC},
        timeout=10,
    )
    assert cree.status_code == 201, cree.text
    project_id = cree.json()["id"]

    lance = session.post(f"{base}/api/projects/{project_id}/builds", timeout=10)
    assert lance.status_code == 202, lance.text
    build = _wait_for_build(base, session, project_id)

    etapes = requests.get(
        f"{base}/api/projects/{project_id}/builds/{build['id']}/etapes",
        cookies=session.cookies,
        timeout=10,
    )
    assert etapes.status_code == 200, etapes.text
    corps = etapes.json()
    assert isinstance(corps["stages"], list)
    # Une construction terminée n'annonce plus de reste à faire.
    assert corps["remaining"] == []
    for etape in corps["stages"]:
        assert etape["name"]
        assert etape["at"]


def test_les_etapes_d_une_construction_d_autrui_sont_refusees(running_platform):
    base = running_platform
    mien = _register(base, "mien@example.test")
    autre = _register(base, "autre@example.test")

    cree = mien.post(
        f"{base}/api/compile",
        json={"spec": SPEC},
        timeout=10,
    )
    assert cree.status_code == 201, cree.text
    project_id = cree.json()["id"]

    refus = autre.get(
        f"{base}/api/projects/{project_id}/builds/1/etapes",
        timeout=10,
    )
    assert refus.status_code == 404, refus.text


def test_un_compte_ne_peut_construire_que_ses_propres_projets(running_platform):
    """La construction est une action possédée, pas une simple lecture."""
    base = running_platform
    alice = _register(base, "constructrice@example.test")
    bob = _register(base, "intrus@example.test")

    cree = alice.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=10)
    assert cree.status_code == 201, cree.text
    project_id = cree.json()["id"]

    pour_alice = alice.post(
        f"{base}/api/projects/{project_id}/build", timeout=10
    )
    pour_bob = bob.post(
        f"{base}/api/projects/{project_id}/build", timeout=10
    )

    assert pour_alice.status_code == 202, pour_alice.text
    assert pour_bob.status_code == 404, pour_bob.text
    assert bob.get(f"{base}/api/projects/{project_id}/builds", timeout=10).status_code == 404
