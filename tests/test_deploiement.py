"""Preuves d'exécution des briques de déploiement du backend généré."""

import contextlib
import json
import os
import socket
import subprocess
import sys
import time

import pytest
import requests

from monl.cli import compile_project

SPEC = """app Deploiement

entity Note
    titre: String

actor Membre selfRegister

workflow Ecrire for Membre
    Create Note
"""


def _port_libre():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _environnement(**valeurs):
    env = os.environ.copy()
    for nom in ("MONL_CORS_ORIGINS", "MONL_LOG_FORMAT", "MONL_ENV",
                "MONL_JWT_SECRET"):
        env.pop(nom, None)
    env.update({nom: valeur for nom, valeur in valeurs.items() if valeur is not None})
    return env


@contextlib.contextmanager
def _serveur(projet, **variables):
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port), "--no-access-log"],
        cwd=str(projet), env=_environnement(**variables),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if processus.poll() is not None:
                sortie = processus.stdout.read() if processus.stdout else ""
                pytest.fail(f"serveur arrêté au démarrage :\n{sortie}")
            try:
                reponse = requests.get(f"{base}/health", timeout=1)
                if reponse.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.05)
        else:
            pytest.fail("serveur non démarré")
        yield base, processus
    finally:
        if processus.poll() is None:
            processus.terminate()
        try:
            sortie, _ = processus.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            sortie, _ = processus.communicate(timeout=5)
        processus._monl_sortie = sortie


@pytest.fixture
def projet(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    return tmp_path


def test_sante_et_readiness_sont_accessibles_sans_jeton(projet):
    with _serveur(projet) as (base, _processus):
        vivacite = requests.get(f"{base}/health", timeout=5)
        readiness = requests.get(f"{base}/health/ready", timeout=5)

    assert vivacite.status_code == 200
    assert vivacite.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}


def test_readiness_renvoie_503_si_la_base_devient_inaccessible(projet):
    with _serveur(projet) as (base, _processus):
        base_de_donnees = projet / "app.db"
        sauvegarde = projet / "app.db.sauvegarde-a3"
        base_de_donnees.rename(sauvegarde)
        base_de_donnees.mkdir()
        try:
            reponse = requests.get(f"{base}/health/ready", timeout=5)
        finally:
            base_de_donnees.rmdir()
            sauvegarde.rename(base_de_donnees)

    assert reponse.status_code == 503
    assert reponse.json() == {"detail": "Service indisponible"}


def test_cors_est_absent_sans_variable(projet):
    with _serveur(projet) as (base, _processus):
        reponse = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert reponse.status_code == 200
    assert "access-control-allow-origin" not in reponse.headers


def test_cors_nautorise_que_lorigine_declaree(projet):
    with _serveur(projet, MONL_CORS_ORIGINS="https://client.test, https://admin.test") as (
        base, _processus
    ):
        reponse = requests.get(f"{base}/health", headers={"Origin": "https://client.test"},
                               timeout=5)

    assert reponse.status_code == 200
    assert reponse.headers["access-control-allow-origin"] == "https://client.test"
    assert reponse.headers["access-control-allow-credentials"] == "true"


def test_cors_refuse_etoile_au_demarrage(projet):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_libre()), "--no-access-log"],
        cwd=str(projet), env=_environnement(MONL_CORS_ORIGINS="*"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sortie, _ = processus.communicate(timeout=10)

    assert processus.returncode != 0
    assert "MONL_CORS_ORIGINS" in sortie
    assert "origine '*'" in sortie


def test_logs_json_sont_structures_et_ne_contiennent_pas_le_mot_de_passe(projet):
    mot_de_passe = "MotDePasse-A3-NE-JAMAIS-JOURNALISER"
    with _serveur(projet, MONL_LOG_FORMAT="json") as (base, processus):
        inscription = requests.post(
            f"{base}/register", timeout=5,
            json={"username": "log@exemple.test", "password": mot_de_passe,
                  "actor": "Membre"},
        )
        assert inscription.status_code == 200
        reponse = requests.get(
            f"{base}/health", headers={"X-Request-ID": "demande-A3"}, timeout=5)
        assert reponse.status_code == 200
        assert reponse.headers["X-Request-ID"] == "demande-A3"
    sortie = getattr(processus, "_monl_sortie", "")

    assert mot_de_passe not in sortie
    lignes_json = []
    for ligne in sortie.splitlines():
        try:
            objet = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if "request_id" in objet:
            lignes_json.append(objet)
    assert lignes_json
    assert all({"timestamp", "method", "path", "status_code", "duration_ms",
                "request_id"} <= set(objet) for objet in lignes_json)
    assert any(objet["request_id"] == "demande-A3" for objet in lignes_json)


def test_production_sans_secret_refuse_le_demarrage(projet):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(_port_libre()), "--no-access-log"],
        cwd=str(projet), env=_environnement(MONL_ENV="production"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sortie, _ = processus.communicate(timeout=10)

    assert processus.returncode != 0
    assert "MONL_JWT_SECRET" in sortie


def test_dockerfile_et_dockerignore_sont_crees_et_preserves(projet):
    dockerfile = projet / "Dockerfile"
    dockerignore = projet / ".dockerignore"
    assert dockerfile.exists()
    assert dockerignore.exists()
    contenu_dockerignore = dockerignore.read_text(encoding="utf-8")
    for motif in (".jwt_secret", "*.db", "__pycache__", "frontend.precedent/"):
        assert motif in contenu_dockerignore

    dockerfile.write_text("FROM image-adaptee\n", encoding="utf-8")
    dockerignore.write_text(".jwt_secret\n# adaptation locale\n", encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))

    assert dockerfile.read_text(encoding="utf-8") == "FROM image-adaptee\n"
    assert dockerignore.read_text(encoding="utf-8") == ".jwt_secret\n# adaptation locale\n"


def test_les_healthchecks_ne_sont_pas_dans_le_contrat_frontend(projet):
    contract = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    chemins = {route["path"] for route in contract["routes"]}

    assert "/health" not in chemins
    assert "/health/ready" not in chemins
