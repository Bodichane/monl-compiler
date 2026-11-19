"""Deletion removes data and processes on a real server."""

import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

from monl_platform.app import create_app
from monl_platform.hosting_control import _addresses
from tests.support.sqlite import sqlite_db
from tests.test_platform_hebergement import _compiler, _get, _platform_server


def _wait_workers(server, base, workspace, log):
    limit = time.monotonic() + 30
    while time.monotonic() < limit:
        assert server.poll() is None, log.read_text()
        addresses = _addresses(workspace)
        if len(addresses) == 2:
            try:
                response = requests.get(base + "/health", timeout=1)
                if response.status_code == 200:
                    return {int(address.rsplit("-", 1)[1]) for address in addresses}
            except requests.RequestException:
                pass
        time.sleep(0.1)
    pytest.fail("Two ready workers expected: " + log.read_text())


def _check_workers(pids):
    assert len(pids) == 2
    for pid in pids:
        os.kill(pid, 0)
        assert Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"


def test_cli_deletion_with_two_uvicorn_workers(tmp_path):
    app = create_app(workspace=tmp_path)
    user = app.state.identity_store.register("workers@monl.test", "MotDePasse-123")
    project, folder = _project(app, user, "multiworker")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    log = tmp_path / "uvicorn.log"
    with log.open("w") as output:
        server = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "monl_platform.app:app",
            "--host", "127.0.0.1", "--port", str(port), "--workers", "2"],
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "PYTHONPATH": "src", "MONL_PLATFORM_WORKSPACE": str(tmp_path)})
        try:
            pids = _wait_workers(server, base, tmp_path, log)
            time.sleep(1)
            _check_workers(pids)
            session = _login(base, user["email"])
            response = session.post(base + f"/api/projects/{project['project_id']}/start",
                                   timeout=30)
            assert response.status_code == 200, response.text
            site = response.json()
            assert _get(site["port"], "/openapi.json")[0] == 200
            os.kill(site["pid"], 0)
            _delete("cli", app, base, session, user, project)
            with pytest.raises(ProcessLookupError):
                os.kill(site["pid"], 0)
            assert not folder.exists()
            _check_workers(pids)
            assert requests.get(base + "/health", timeout=5).status_code == 200
        finally:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)


def _project(app, user, name):
    pid = uuid.uuid4().hex
    app.state.identity_store.add_project(user["id"], pid, name)
    app.state.store.create_project(user["id"], pid, name)
    project = app.state.store.get_project(pid)
    folder = _compiler(project, app.state.compilation_service.workspace,
                        app.state.compilation_service.workspace)
    with sqlite_db(folder / "app.db") as db:
        db.execute("CREATE TABLE visiteurs_prives (email TEXT)")
        db.execute("INSERT INTO visiteurs_prives VALUES (?)", ("visiteur@prive.test",))
    (folder / ".jwt_secret").write_text("secret du site", encoding="utf-8")
    return project, folder


def _login(base, address):
    session = requests.Session()
    response = session.post(base + "/api/auth/login", json={
        "email": address, "password": "MotDePasse-123"}, timeout=10)
    assert response.status_code == 200, response.text
    return session


def _delete(mode, app, base, session, user, project):
    if mode == "cli":
        rendered = subprocess.run([
            sys.executable, "-m", "monl_platform", "admin", "supprimer-compte",
            user["email"], "--confirmer", "--workspace",
            str(app.state.compilation_service.workspace)],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": "src"})
        assert rendered.returncode == 0, rendered.stderr
    elif mode == "purge":
        with app.state.identity_store._connect() as db:
            db.execute("UPDATE projects SET expires_at = ? WHERE project_id = ?",
                       (int(time.time()) - 1, project["project_id"]))
    else:
        path = "/api/auth/account" if mode == "compte" else (
            "/api/projects/" + project["project_id"])
        response = session.delete(base + path, json={"password": "MotDePasse-123"},
                                 timeout=30)
        assert response.status_code == 204, response.text


@pytest.mark.parametrize("mode", ["projet", "compte", "cli", "purge"])
def test_complete_deletion_and_neighbor_sites_preserved(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("MONL_PURGE_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES", "3")
    monkeypatch.setenv("MONL_MAX_RUNNING_SITES_PER_ACCOUNT", "2")
    app = create_app(workspace=tmp_path)
    identities = app.state.identity_store
    alice = identities.register("alice@monl.test", "MotDePasse-123")
    bob = identities.register("bob@monl.test", "MotDePasse-123")
    target, folder = _project(app, alice, "cible")
    neighbor, folder_neighbor = _project(app, bob, "voisin")
    other, folder_other = _project(app, alice, "autre")
    sites = app.state.sites
    with _platform_server(app) as base:
        session = _login(base, alice["email"])
        key = session.post(base + "/api/keys", json={"name": "preuve"}, timeout=10).json()
        live = sites.start_project(target)
        neighbor_live = sites.start_project(neighbor)
        other_live = sites.start_project(other)
        assert _get(live.port, "/openapi.json")[0] == 200
        _delete(mode, app, base, session, alice, target)
        for _ in range(200):
            # The purge can still remove the database rows after the folder.
            if (live.process.poll() is not None and not folder.exists()
                    and app.state.store.get_project(target["project_id"]) is None
                    and not any(project["project_id"] == target["project_id"]
                                for project in identities.projects(alice["id"]))):
                break
            time.sleep(0.05)
        assert live.process.poll() is not None, "The deleted site's process is still alive"
        with pytest.raises(ProcessLookupError):
            os.kill(live.process.pid, 0)
        assert not folder.exists(), "The deleted private folder keeps visitor data"
        assert app.state.store.get_project(target["project_id"]) is None
        assert folder_neighbor.exists(), "The neighbor account's folder was erased"
        assert _get(neighbor_live.port, "/openapi.json")[0] == 200
        if mode in {"cli", "compte"}:
            assert other_live.process.poll() is not None
            assert not folder_other.exists()
            assert session.get(base + "/api/auth/me", timeout=10).status_code == 401
            assert identities.api_key_user(key["key"]) is None
            alice = identities.register("remplacante@monl.test", "MotDePasse-123")
        else:
            assert folder_other.exists()
            assert _get(other_live.port, "/openapi.json")[0] == 200
        replacement, _ = _project(app, alice, "remplacement")
        new = sites.start_project(replacement)
        assert _get(new.port, "/openapi.json")[0] == 200, "The deleted site's slot is not released"
        # Server cleanup stops every site still legitimately running.


def test_local_account_always_requires_its_password(tmp_path):
    app = create_app(workspace=tmp_path)
    app.state.identity_store.register("locale@monl.test", "MotDePasse-123")
    with _platform_server(app) as base:
        session = _login(base, "locale@monl.test")
        for charge in ({}, {"password": "incorrect"}):
            refusal = session.delete(base + "/api/auth/account", json=charge, timeout=10)
            assert refusal.status_code == 403, "A local account is deleted without its password"
            assert "Incorrect password" in refusal.text
            assert session.get(base + "/api/auth/me", timeout=10).status_code == 200
        succes = session.delete(base + "/api/auth/account",
                                json={"password": "MotDePasse-123"}, timeout=10)
        assert succes.status_code == 204, succes.text
