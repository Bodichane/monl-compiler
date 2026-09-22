"""Témoins HTTP de l'admission commune aux deux routes de compilation."""

import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform import builder_build_routes
from monl_platform.app import create_app
from monl_platform.service import CompilationService

SPEC = """app Admission

entity Item
    label: String

actor Admin
rule Item.Read public
workflow Manage for Admin
    Create Item
    Read Item
"""


def _port_libre():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def plateforme(tmp_path, monkeypatch):
    monkeypatch.setenv("MONL_MAX_CONCURRENT_COMPILES", "1")
    port = _port_libre()
    serveur = uvicorn.Server(uvicorn.Config(
        create_app(workspace=tmp_path / "projects"),
        host="127.0.0.1",
        port=port,
        log_level="error",
    ))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("la plateforme n'a pas démarré")
        yield base
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)
        assert not fil.is_alive()


def _inscrire(base, email):
    session = requests.Session()
    reponse = session.post(
        f"{base}/api/auth/register",
        json={"email": email, "password": "MotDePasse-123"},
        timeout=10,
    )
    assert reponse.status_code == 201, reponse.text
    return session


def _creer_projet(base, session):
    reponse = session.post(f"{base}/api/compile", json={"spec": SPEC}, timeout=60)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def test_compilation_et_recompilation_partagent_le_quota(plateforme):
    session = _inscrire(plateforme, "quota@exemple.test")
    projet = _creer_projet(plateforme, session)

    for _ in range(9):
        reponse = session.post(
            f"{plateforme}/api/projects/{projet}/compiler", timeout=60
        )
        assert reponse.status_code == 201, reponse.text

    refusee = session.post(f"{plateforme}/api/compile", json={"spec": SPEC}, timeout=10)
    assert refusee.status_code == 429
    assert "Retry-After" in refusee.headers


def test_une_recompilation_occupe_le_semaphore_puis_le_libere(
    plateforme, monkeypatch
):
    session = _inscrire(plateforme, "semaphore@exemple.test")
    projet = _creer_projet(plateforme, session)
    entre = threading.Event()
    sortir = threading.Event()
    vrai_compilateur = builder_build_routes.compiler_le_projet

    def compilation_retenue(*args, **kwargs):
        entre.set()
        assert sortir.wait(timeout=10)
        return vrai_compilateur(*args, **kwargs)

    monkeypatch.setattr(builder_build_routes, "compiler_le_projet", compilation_retenue)
    resultat = {}

    def lancer():
        resultat["reponse"] = session.post(
            f"{plateforme}/api/projects/{projet}/compiler", timeout=60
        )

    fil = threading.Thread(target=lancer)
    fil.start()
    assert entre.wait(timeout=10)
    occupe = session.post(f"{plateforme}/api/projects/{projet}/compiler", timeout=10)
    assert occupe.status_code == 503
    assert occupe.headers["Retry-After"] == "5"
    sortir.set()
    fil.join(timeout=60)
    assert resultat["reponse"].status_code == 201, resultat["reponse"].text

    suivante = session.post(f"{plateforme}/api/projects/{projet}/compiler", timeout=60)
    assert suivante.status_code == 201, suivante.text


def test_compilation_et_recompilation_partagent_le_semaphore(
    plateforme, monkeypatch
):
    session = _inscrire(plateforme, "semaphore-partage@exemple.test")
    projet = _creer_projet(plateforme, session)
    entre = threading.Event()
    sortir = threading.Event()
    vraie_compilation = CompilationService.compile

    def compilation_retenue(service, spec):
        entre.set()
        assert sortir.wait(timeout=10)
        return vraie_compilation(service, spec)

    monkeypatch.setattr(CompilationService, "compile", compilation_retenue)
    resultat = {}

    def lancer():
        resultat["reponse"] = session.post(
            f"{plateforme}/api/compile", json={"spec": SPEC}, timeout=60
        )

    fil = threading.Thread(target=lancer)
    fil.start()
    assert entre.wait(timeout=10)
    occupe = session.post(f"{plateforme}/api/projects/{projet}/compiler", timeout=10)
    assert occupe.status_code == 503
    assert occupe.headers["Retry-After"] == "5"
    sortir.set()
    fil.join(timeout=60)
    assert resultat["reponse"].status_code == 201, resultat["reponse"].text

    suivante = session.post(f"{plateforme}/api/projects/{projet}/compiler", timeout=60)
    assert suivante.status_code == 201, suivante.text


def test_un_appel_legitime_passe_et_les_erreurs_liberent_la_place(plateforme):
    session = _inscrire(plateforme, "erreurs@exemple.test")

    invalide = session.post(f"{plateforme}/api/compile", json={"spec": ""}, timeout=10)
    assert invalide.status_code == 422
    projet = _creer_projet(plateforme, session)

    absent = session.post(
        f"{plateforme}/api/projects/projet-absent/compiler", timeout=10
    )
    assert absent.status_code == 404
    legitime = session.post(
        f"{plateforme}/api/projects/{projet}/compiler", timeout=60
    )
    assert legitime.status_code == 201, legitime.text
