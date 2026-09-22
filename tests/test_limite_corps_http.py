"""Témoins HTTP de la borne commune des corps JSON de la plateforme."""

import ast
import http.client
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn

from monl_platform.app import create_app


def _port_libre():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def plateforme(tmp_path):
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
        yield "127.0.0.1", port
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)
        assert not fil.is_alive()


def _post_chunked(plateforme, morceaux):
    hote, port = plateforme
    connexion = http.client.HTTPConnection(hote, port, timeout=10)
    connexion.request(
        "POST",
        "/api/auth/login",
        body=iter(morceaux),
        headers={"Content-Type": "application/json"},
        encode_chunked=True,
    )
    reponse = connexion.getresponse()
    contenu = reponse.read()
    connexion.close()
    return reponse.status, json.loads(contenu)


def test_un_corps_chunked_trop_grand_est_refuse(plateforme):
    morceaux = [b'{"email":"x","password":"y","remplissage":"']
    morceaux += [b"a" * 50_000] * 7
    morceaux.append(b'"}')

    statut, contenu = _post_chunked(plateforme, morceaux)

    assert statut == 413
    assert contenu["detail"] == "Requête trop volumineuse."


def test_un_corps_chunked_borne_et_valide_reste_accepte(plateforme):
    statut, contenu = _post_chunked(
        plateforme,
        [b'{"email":"inconnu@exemple.test",', b'"password":"mauvais"}'],
    )

    assert statut == 401
    assert contenu["detail"] == "Email ou mot de passe incorrect."


def test_content_length_trop_grand_est_refuse_avant_lecture(plateforme):
    hote, port = plateforme
    connexion = http.client.HTTPConnection(hote, port, timeout=10)
    connexion.request(
        "POST",
        "/api/auth/login",
        body=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "300001",
        },
    )
    reponse = connexion.getresponse()
    contenu = json.loads(reponse.read())
    connexion.close()

    assert reponse.status == 413
    assert contenu["detail"] == "Requête trop volumineuse."


def test_un_json_chunked_non_objet_garde_son_erreur(plateforme):
    statut, contenu = _post_chunked(plateforme, [b"[", b"]"])

    assert statut == 400
    assert contenu["detail"] == "Un objet JSON est attendu."


def test_les_routes_ne_lisent_pas_le_corps_hors_des_lecteurs_bornes():
    racine = Path(__file__).parents[1] / "src" / "monl_platform"
    # DEUX lecteurs, pas un de plus, et chacun est BORNÉ. La liste a déjà
    # servi : le relais lisait `route_by_host` → `request.body()`, sans borne,
    # et le point 188 l'a déplacé dans `_bounded_body` → `request.stream()`.
    # Ce témoin a rougi sur ce déplacement alors que tout le reste était vert,
    # ce qui est exactement ce qu'on lui demande : un lecteur qui bouge se
    # redéclare, il ne se glisse pas.
    autorises = {
        ("app_http.py", "_json_body", "stream"),
        ("builder_host.py", "_bounded_body", "stream"),
    }
    lectures = set()
    for chemin in racine.glob("*.py"):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        parents = {
            enfant: parent
            for parent in ast.walk(arbre)
            for enfant in ast.iter_child_nodes(parent)
        }
        for appel in (n for n in ast.walk(arbre) if isinstance(n, ast.Call)):
            cible = appel.func
            if not isinstance(cible, ast.Attribute) or cible.attr not in {
                "json", "body", "form", "stream"
            }:
                continue
            parent = appel
            while parent in parents and not isinstance(
                parent, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                parent = parents[parent]
            lectures.add((chemin.name, parent.name, cible.attr))

    assert lectures == autorises
