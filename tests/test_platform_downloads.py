"""Une page qui propose un téléchargement doit livrer un fichier qui existe.

Le nom demandé est comparé à ce qui est RÉELLEMENT sur le disque, jamais
concaténé à un chemin : la remontée de répertoire est impossible, pas
seulement improbable.
"""

import hashlib
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.downloads import (
    default_directory,
    list_artifacts,
    resolve_artifact,
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - jamais appelé ici
        raise AssertionError("le téléchargement n'appelle aucune IA")


@pytest.fixture()
def dist(tmp_path):
    dossier = tmp_path / "dist"
    dossier.mkdir()
    (dossier / "monl_compiler-1.0.0-py3-none-any.whl").write_bytes(b"roue" * 64)
    (dossier / "monl_compiler-1.0.0.tar.gz").write_bytes(b"sources" * 32)
    # Ce qui n'est pas une distribution ne doit pas être publié.
    (dossier / "journal.txt").write_text("bruit", encoding="utf-8")
    (dossier / "anciens").mkdir()
    (dossier / "anciens" / "vieux-0.1.0.whl").write_bytes(b"vieux")
    return dossier


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path, dist):
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
        downloads_dir=str(dist),
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


def test_seules_les_distributions_sont_publiees(dist):
    noms = [a["name"] for a in list_artifacts(dist)]

    assert noms == [
        "monl_compiler-1.0.0-py3-none-any.whl",
        "monl_compiler-1.0.0.tar.gz",
    ]


def test_la_roue_passe_devant_les_sources(dist):
    """C'est la roue qui s'installe : la proposer en second rallonge le chemin."""
    assert list_artifacts(dist)[0]["kind"] == "wheel"


def test_l_empreinte_publiee_est_celle_du_fichier(dist):
    artefact = list_artifacts(dist)[0]
    attendu = hashlib.sha256(
        (dist / artefact["name"]).read_bytes()
    ).hexdigest()

    assert artefact["sha256"] == attendu
    assert artefact["bytes"] == (dist / artefact["name"]).stat().st_size


def test_un_dossier_absent_ne_fait_pas_echouer(tmp_path):
    """La plateforme peut tourner sans distribution construite."""
    assert list_artifacts(tmp_path / "nulle-part") == []
    assert list_artifacts(None) == []


def test_le_telechargement_rend_les_octets_du_fichier(platform, dist):
    listing = requests.get(f"{platform}/api/telechargements", timeout=10).json()
    nom = listing["artifacts"][0]["name"]

    reponse = requests.get(f"{platform}/api/telechargements/{nom}", timeout=10)

    assert reponse.status_code == 200
    assert reponse.content == (dist / nom).read_bytes()


@pytest.mark.parametrize("nom", [
    "../../etc/passwd",
    "..%2f..%2fetc%2fpasswd",
    "/etc/passwd",
    "journal.txt",
    "anciens/vieux-0.1.0.whl",
    "inconnu-9.9.9.whl",
])
def test_un_nom_hostile_ou_inconnu_est_refuse(platform, nom):
    reponse = requests.get(f"{platform}/api/telechargements/{nom}", timeout=10)

    assert reponse.status_code == 404, reponse.text


def test_la_resolution_ne_concatene_jamais_le_nom_recu(dist):
    assert resolve_artifact(dist, "../dist/journal.txt") is None
    assert resolve_artifact(dist, "journal.txt") is None
    assert resolve_artifact(dist, "monl_compiler-1.0.0.tar.gz") is not None
    assert resolve_artifact(None, "monl_compiler-1.0.0.tar.gz") is None


def test_le_dossier_vient_de_l_environnement_seulement():
    assert default_directory({}) is None
    assert default_directory({"MONL_PLATFORM_DOWNLOADS": "  "}) is None
    assert default_directory({"MONL_PLATFORM_DOWNLOADS": " dist "}) == "dist"
