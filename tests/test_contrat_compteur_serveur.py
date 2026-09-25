"""Un corps repris mot pour mot du contrat doit agir sur sa cible réelle."""

import shutil
import sqlite3
from pathlib import Path

import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

RACINE = Path(__file__).resolve().parents[1]
MOT_DE_PASSE = "MotDePasse123!"


def _compiler_exemple(tmp_path, nom):
    source = RACINE / "exemples" / nom
    projet = tmp_path / source.stem
    projet.mkdir()
    (projet / "spec.ml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    assets = source.parent / "assets"
    if assets.is_dir():
        shutil.copytree(assets, projet / "assets")
    contrat = compile_project(str(projet / "spec.ml"), str(projet))
    return projet, contrat


def _jeton(base, acteur, identifiant):
    r = requests.post(f"{base}/register", timeout=10,
                      json={"username": identifiant, "password": MOT_DE_PASSE,
                            "actor": acteur})
    assert r.status_code == 200, r.text
    r = requests.post(f"{base}/login", timeout=10,
                      json={"username": identifiant, "password": MOT_DE_PASSE})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json().get("access_token", r.json().get("token"))}


def test_post_orderline_du_contrat_decremente_la_variante(tmp_path):
    projet, contrat = _compiler_exemple(tmp_path, "02_boutique.ml")
    route = next(r for r in contrat["routes"]
                 if r["method"] == "POST" and r["path"] == "/orderline")
    assert set(route["request_fields"]) == {"order_id", "quantity", "variant_id"}
    with uvicorn_server(str(projet)) as base:
        headers = _jeton(base, "Customer", "client@example.test")
        commande_r = requests.post(f"{base}/order", timeout=10, headers=headers, json={})
        assert commande_r.status_code == 200, commande_r.text
        commande = commande_r.json()
        variantes = requests.get(f"{base}/variant", timeout=10).json()["data"]
        variante = variantes[0]
        before = sqlite3.connect(projet / "app.db").execute(
            "SELECT stock FROM variant WHERE id = ?", (variante["id"],)).fetchone()[0]
        valeurs = {"order_id": commande["id"], "variant_id": variante["id"], "quantity": 1}
        corps = {field: valeurs[field] for field in route["request_fields"]}
        resultat = requests.post(f"{base}/orderline", timeout=10, headers=headers, json=corps)
        assert resultat.status_code == 200, resultat.text
        with sqlite3.connect(projet / "app.db") as db:
            after = db.execute("SELECT stock FROM variant WHERE id = ?",
                               (variante["id"],)).fetchone()[0]
    assert after == before - 1


def test_post_like_du_contrat_incremente_le_post(tmp_path):
    projet, contrat = _compiler_exemple(tmp_path, "03_reseau_social.ml")
    route = next(r for r in contrat["routes"]
                 if r["method"] == "POST" and r["path"] == "/like")
    assert set(route["request_fields"]) == {"note", "post_id"}
    with uvicorn_server(str(projet)) as base:
        headers = _jeton(base, "Member", "membre@example.test")
        post = requests.get(f"{base}/post", timeout=10).json()["data"][0]
        with sqlite3.connect(projet / "app.db") as db:
            before = db.execute("SELECT likes FROM post WHERE id = ?",
                                 (post["id"],)).fetchone()[0]
        valeurs = {"note": "bravo", "post_id": post["id"]}
        corps = {field: valeurs[field] for field in route["request_fields"]}
        resultat = requests.post(f"{base}/like", timeout=10, headers=headers, json=corps)
        assert resultat.status_code == 200, resultat.text
        with sqlite3.connect(projet / "app.db") as db:
            after = db.execute("SELECT likes FROM post WHERE id = ?",
                               (post["id"],)).fetchone()[0]
    assert after == before + 1
