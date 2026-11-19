"""HTTP witnesses of the platform's shared JSON body bound."""

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
            pytest.fail("the platform did not start")
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


def test_a_too_large_chunked_body_is_refused(plateforme):
    morceaux = [b'{"email":"x","password":"y","remplissage":"']
    morceaux += [b"a" * 50_000] * 7
    morceaux.append(b'"}')

    statut, contenu = _post_chunked(plateforme, morceaux)

    assert statut == 413
    assert contenu["detail"] == "Request too large."


def test_a_bounded_valid_chunked_body_stays_accepted(plateforme):
    statut, contenu = _post_chunked(
        plateforme,
        [b'{"email":"inconnu@exemple.test",', b'"password":"mauvais"}'],
    )

    assert statut == 401
    assert contenu["detail"] == "Incorrect email or password."


def test_too_large_content_length_is_refused_before_reading(plateforme):
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
    assert contenu["detail"] == "Request too large."


def test_a_non_object_chunked_json_keeps_its_error(plateforme):
    statut, contenu = _post_chunked(plateforme, [b"[", b"]"])

    assert statut == 400
    assert contenu["detail"] == "A JSON object is expected."


def test_routes_do_not_read_the_body_outside_bounded_readers():
    racine = Path(__file__).parents[1] / "src" / "monl_platform"
    # TWO readers, not one more, and each is BOUNDED. The list has served
    # already: the relay read `route_by_host` → `request.body()`, unbounded,
    # and point 188 moved it into `_bounded_body` → `request.stream()`. This
    # witness went red on that move while everything else was green, which is
    # exactly what it is asked to do: a reader that moves declares itself
    # again, it does not slip through.
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
