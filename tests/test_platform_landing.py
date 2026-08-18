"""La racine porte la page de présentation, la console vit sur /console.

La console est un OUTIL : elle suppose qu'on sait déjà ce que monl fait. Une
personne qui l'ignore avait la console en pleine figure, sans un mot sur le
produit ni le moindre moyen de l'installer.
"""

import re
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.landing import LANDING_HTML

#: Le même contrôle que pour la console : une page servie en local doit
#: fonctionner sans réseau. Un lien sortant compris — la page n'en a aucun.
RESSOURCE_DISTANTE = re.compile(
    r"https?://|<link\b|<script[^>]+\bsrc=|@import", re.IGNORECASE
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - jamais appelé ici
        raise AssertionError("la page de présentation n'appelle aucune IA")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path):
    app = create_app(
        database=tmp_path / "platform.db",
        workspace_root=tmp_path / "projects",
        domain="localhost",
        jwt_secret="secret-for-platform-landing-tests-123456",
        provider=FakeProvider(),
        poll_interval=0.01,
        start_worker=False,
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
            pytest.fail("le serveur n'a pas démarré")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_la_racine_presente_le_produit(platform):
    reponse = requests.get(platform, timeout=10)

    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]
    assert '<html lang="fr">' in reponse.text
    # Ce qu'une page produit doit dire : ce que c'est, et comment l'obtenir.
    assert "compilateur" in reponse.text.lower()
    assert "Télécharger" in reponse.text


def test_la_page_conduit_a_la_console(platform):
    reponse = requests.get(platform, timeout=10)

    assert 'href="/console"' in reponse.text
    assert requests.get(f"{platform}/console", timeout=10).status_code == 200


def test_la_page_ne_charge_aucune_ressource_distante(platform):
    """Servie en local, elle doit fonctionner sans le moindre réseau."""
    reponse = requests.get(platform, timeout=10)

    faute = RESSOURCE_DISTANTE.search(reponse.text)
    assert faute is None, f"ressource distante dans la page : {faute.group(0)}"


def test_la_page_respecte_le_mouvement_reduit():
    """Le terminal du héros s'anime : il doit pouvoir s'arrêter."""
    assert "prefers-reduced-motion" in LANDING_HTML


def test_la_console_n_est_plus_a_la_racine(platform):
    """La racine et la console sont deux pages distinctes, pas la même."""
    racine = requests.get(platform, timeout=10).text
    console = requests.get(f"{platform}/console", timeout=10).text

    assert racine != console
    assert "monl / console" in console
    assert "monl / console" not in racine


def test_la_pastille_de_marque_garde_sa_couleur_d_encre():
    """Deux fois le même défaut : une règle LARGE écrase une règle précise.

    `.logo span` (0,1,1) l'emporte sur `.logo-mark` (0,1,0) et repeignait le
    « m » en gris sourd sur argile — 1,35:1, c'est-à-dire invisible. Le même
    piège avait déjà mangé le bouton d'appel à l'action à l'autre bout de la
    barre. Ce qu'on corrige n'est pas la règle précise qu'il faudrait
    renforcer, c'est la règle large qu'il faut restreindre : on interdit donc
    le sélecteur fourre-tout, pas une couleur particulière.
    """
    assert ".logo span {" not in LANDING_HTML
    assert ".logo span:not(.logo-mark)" in LANDING_HTML


def test_la_marque_se_lit_monl_compiler(platform):
    reponse = requests.get(platform, timeout=10)

    assert "<b>monl</b><span>/ compiler</span>" in reponse.text
