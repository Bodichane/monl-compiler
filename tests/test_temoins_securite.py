"""Témoins contre les vrais serveurs pour les garanties auth les plus basses."""
import os
import pathlib
from http.cookies import SimpleCookie

import jwt
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

SPEC = """app TemoinJeton
entity Note
    texte: String
relation Client hasMany Note
actor Client selfRegister
rule Note.Read ownedBy Client
workflow Ecrire for Client
    Create Note
    Read Note
"""
SECRET = "mot-de-passe-temoin-92"


def test_le_serveur_refuse_les_jetons_non_signes_ou_signes_autrement(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    projet = tmp_path / "projet"
    compile_project(str(spec), str(projet))
    with uvicorn_server(str(projet)) as base:
        session = requests.Session()
        inscrit = session.post(base + "/register", json={
            "username": "cliente@example.test", "password": SECRET, "actor": "Client",
        }, timeout=20)
        assert inscrit.status_code == 200, inscrit.text
        connecte = requests.post(base + "/login", json={
            "username": "cliente@example.test", "password": SECRET,
        }, timeout=20)
        assert connecte.status_code == 200, connecte.text
        token = connecte.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        valide = requests.get(base + "/note", headers=headers, timeout=10)
        assert valide.status_code == 200, valide.text

        contenu = jwt.decode(token, options={"verify_signature": False})
        mal_signe = jwt.encode(contenu, "secret-different-du-projet-92-32-octets", algorithm="HS256")
        refuse = requests.get(base + "/note", headers={
            "Authorization": f"Bearer {mal_signe}"
        }, timeout=10)
        assert refuse.status_code == 401, refuse.text

        sans_signature = jwt.encode(contenu, key="", algorithm="none")
        refuse = requests.get(base + "/note", headers={
            "Authorization": f"Bearer {sans_signature}"
        }, timeout=10)
        assert refuse.status_code == 401, refuse.text


def test_le_cookie_plateforme_reel_est_http_only_et_strict(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(pathlib.Path(__file__).resolve().parents[1] / "src")
    env["MONL_PLATFORM_WORKSPACE"] = str(tmp_path / "workspace")
    with uvicorn_server(str(tmp_path), env=env, module="monl_platform.app:app",
                        ready_path="/health") as base:
        response = requests.post(base + "/api/auth/register", timeout=20, json={
            "email": "cookie@example.test", "password": SECRET,
        })
        assert response.status_code == 201, response.text
        cookie = SimpleCookie()
        cookie.load(response.headers["Set-Cookie"])
        morsel = cookie["monl_session"]
        assert morsel["httponly"]
        assert morsel["samesite"].lower() == "strict"
