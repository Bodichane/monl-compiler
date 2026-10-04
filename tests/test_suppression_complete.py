"""La suppression retire les données et les processus sur un vrai serveur."""

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

from monl_platform.app import create_app
from monl_platform.hosting_control import _adresses
from tests.test_platform_hebergement import _compiler, _get, _serveur_plateforme


def _attendre_workers(serveur, base, workspace, journal):
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        assert serveur.poll() is None, journal.read_text()
        adresses = _adresses(workspace)
        if len(adresses) == 2:
            try:
                reponse = requests.get(base + "/health", timeout=1)
                if reponse.status_code == 200:
                    return {int(adresse.rsplit("-", 1)[1]) for adresse in adresses}
            except requests.RequestException:
                pass
        time.sleep(0.1)
    pytest.fail("Deux workers prêts attendus : " + journal.read_text())


def _verifier_workers(pids):
    assert len(pids) == 2
    for pid in pids:
        os.kill(pid, 0)
        assert Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"


def test_suppression_cli_avec_deux_workers_uvicorn(tmp_path):
    app = create_app(workspace=tmp_path)
    user = app.state.identity_store.register("workers@monl.test", "MotDePasse-123")
    projet, dossier = _projet(app, user, "multiworker")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    journal = tmp_path / "uvicorn.log"
    with journal.open("w") as sortie:
        serveur = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "monl_platform.app:app",
            "--host", "127.0.0.1", "--port", str(port), "--workers", "2"],
            stdout=sortie, stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "PYTHONPATH": "src", "MONL_PLATFORM_WORKSPACE": str(tmp_path)})
        try:
            pids = _attendre_workers(serveur, base, tmp_path, journal)
            time.sleep(1)
            _verifier_workers(pids)
            session = _connexion(base, user["email"])
            reponse = session.post(base + f"/api/projects/{projet['project_id']}/start",
                                   timeout=30)
            assert reponse.status_code == 200, reponse.text
            site = reponse.json()
            assert _get(site["port"], "/openapi.json")[0] == 200
            os.kill(site["pid"], 0)
            _supprimer("cli", app, base, session, user, projet)
            with pytest.raises(ProcessLookupError):
                os.kill(site["pid"], 0)
            assert not dossier.exists()
            _verifier_workers(pids)
            assert requests.get(base + "/health", timeout=5).status_code == 200
        finally:
            try:
                os.killpg(serveur.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                serveur.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(serveur.pid, signal.SIGKILL)
                serveur.wait(timeout=5)


def _projet(app, user, nom):
    pid = uuid.uuid4().hex
    app.state.identity_store.add_project(user["id"], pid, nom)
    app.state.store.create_project(user["id"], pid, nom)
    projet = app.state.store.get_project(pid)
    dossier = _compiler(projet, app.state.compilation_service.workspace,
                        app.state.compilation_service.workspace)
    with sqlite3.connect(dossier / "app.db") as db:
        db.execute("CREATE TABLE visiteurs_prives (email TEXT)")
        db.execute("INSERT INTO visiteurs_prives VALUES (?)", ("visiteur@prive.test",))
    (dossier / ".jwt_secret").write_text("secret du site", encoding="utf-8")
    return projet, dossier


def _connexion(base, adresse):
    session = requests.Session()
    reponse = session.post(base + "/api/auth/login", json={
        "email": adresse, "password": "MotDePasse-123"}, timeout=10)
    assert reponse.status_code == 200, reponse.text
    return session


def _supprimer(mode, app, base, session, user, projet):
    if mode == "cli":
        rendu = subprocess.run([
            sys.executable, "-m", "monl_platform", "admin", "supprimer-compte",
            user["email"], "--confirmer", "--workspace",
            str(app.state.compilation_service.workspace)],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": "src"})
        assert rendu.returncode == 0, rendu.stderr
    elif mode == "purge":
        with app.state.identity_store._connect() as db:
            db.execute("UPDATE projects SET expires_at = ? WHERE project_id = ?",
                       (int(time.time()) - 1, projet["project_id"]))
    else:
        chemin = "/api/auth/account" if mode == "compte" else (
            "/api/projects/" + projet["project_id"])
        reponse = session.delete(base + chemin, json={"password": "MotDePasse-123"},
                                 timeout=30)
        assert reponse.status_code == 204, reponse.text


@pytest.mark.parametrize("mode", ["projet", "compte", "cli", "purge"])
def test_suppression_complete_et_sites_voisins_preserves(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("MONL_PURGE_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "3")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "2")
    app = create_app(workspace=tmp_path)
    identites = app.state.identity_store
    alice = identites.register("alice@monl.test", "MotDePasse-123")
    bob = identites.register("bob@monl.test", "MotDePasse-123")
    cible, dossier = _projet(app, alice, "cible")
    voisin, dossier_voisin = _projet(app, bob, "voisin")
    autre, dossier_autre = _projet(app, alice, "autre")
    sites = app.state.sites
    with _serveur_plateforme(app) as base:
        session = _connexion(base, alice["email"])
        cle = session.post(base + "/api/keys", json={"name": "preuve"}, timeout=10).json()
        vivant = sites.start_project(cible)
        voisin_vivant = sites.start_project(voisin)
        autre_vivant = sites.start_project(autre)
        assert _get(vivant.port, "/openapi.json")[0] == 200
        _supprimer(mode, app, base, session, alice, cible)
        for _ in range(200):
            if vivant.process.poll() is not None and not dossier.exists():
                break
            time.sleep(0.05)
        assert vivant.process.poll() is not None, "Le processus du site supprimé est encore vivant"
        with pytest.raises(ProcessLookupError):
            os.kill(vivant.process.pid, 0)
        assert not dossier.exists(), "Le dossier privé supprimé conserve les données visiteurs"
        assert app.state.store.get_project(cible["project_id"]) is None
        assert dossier_voisin.exists(), "Le dossier du compte voisin a été effacé"
        assert _get(voisin_vivant.port, "/openapi.json")[0] == 200
        if mode in {"cli", "compte"}:
            assert autre_vivant.process.poll() is not None
            assert not dossier_autre.exists()
            assert session.get(base + "/api/auth/me", timeout=10).status_code == 401
            assert identites.api_key_user(cle["key"]) is None
            alice = identites.register("remplacante@monl.test", "MotDePasse-123")
        else:
            assert dossier_autre.exists()
            assert _get(autre_vivant.port, "/openapi.json")[0] == 200
        remplacement, _ = _projet(app, alice, "remplacement")
        nouveau = sites.start_project(remplacement)
        assert _get(nouveau.port, "/openapi.json")[0] == 200, "Le créneau du site supprimé n'est pas libéré"
        # Le nettoyage du serveur arrête tous les sites encore légitimes.


def test_compte_local_exige_toujours_son_mot_de_passe(tmp_path):
    app = create_app(workspace=tmp_path)
    app.state.identity_store.register("locale@monl.test", "MotDePasse-123")
    with _serveur_plateforme(app) as base:
        session = _connexion(base, "locale@monl.test")
        for charge in ({}, {"password": "incorrect"}):
            refus = session.delete(base + "/api/auth/account", json=charge, timeout=10)
            assert refus.status_code == 403, "Un compte local est supprimé sans son mot de passe"
            assert "Mot de passe incorrect" in refus.text
            assert session.get(base + "/api/auth/me", timeout=10).status_code == 200
        succes = session.delete(base + "/api/auth/account",
                                json={"password": "MotDePasse-123"}, timeout=10)
        assert succes.status_code == 204, succes.text
