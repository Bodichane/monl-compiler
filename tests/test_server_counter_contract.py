"""A body copied word for word from the contract must act on its real target."""

import shutil
from pathlib import Path

import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server
from tests.support.sqlite import sqlite_db

RACINE = Path(__file__).resolve().parents[1]
PASSWORD = "MotDePasse123!"


def _compiler_example(tmp_path, name):
    source = RACINE / "exemples" / name
    project = tmp_path / source.stem
    project.mkdir()
    (project / "spec.ml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    assets = source.parent / "assets"
    if assets.is_dir():
        shutil.copytree(assets, project / "assets")
    contract = compile_project(str(project / "spec.ml"), str(project))
    return project, contract


def _token(base, actor, identifier):
    r = requests.post(f"{base}/register", timeout=10,
                      json={"username": identifier, "password": PASSWORD,
                            "actor": actor})
    assert r.status_code == 200, r.text
    r = requests.post(f"{base}/login", timeout=10,
                      json={"username": identifier, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json().get("access_token", r.json().get("token"))}


def test_contract_orderline_post_decrements_the_variant(tmp_path):
    project, contract = _compiler_example(tmp_path, "02_boutique.ml")
    route = next(r for r in contract["routes"]
                 if r["method"] == "POST" and r["path"] == "/orderline")
    assert set(route["request_fields"]) == {"order_id", "quantity", "variant_id"}
    with uvicorn_server(str(project)) as base:
        headers = _token(base, "Customer", "client@example.test")
        order_r = requests.post(f"{base}/order", timeout=10, headers=headers, json={})
        assert order_r.status_code == 200, order_r.text
        order = order_r.json()
        variants = requests.get(f"{base}/variant", timeout=10).json()["data"]
        variant = variants[0]
        with sqlite_db(project / "app.db") as db:
            before = db.execute("SELECT stock FROM variant WHERE id = ?",
                                (variant["id"],)).fetchone()[0]
        values = {"order_id": order["id"], "variant_id": variant["id"], "quantity": 1}
        body = {field: values[field] for field in route["request_fields"]}
        result = requests.post(f"{base}/orderline", timeout=10, headers=headers, json=body)
        assert result.status_code == 200, result.text
        with sqlite_db(project / "app.db") as db:
            after = db.execute("SELECT stock FROM variant WHERE id = ?",
                               (variant["id"],)).fetchone()[0]
    assert after == before - 1


def test_contract_like_post_increments_the_post(tmp_path):
    project, contract = _compiler_example(tmp_path, "03_reseau_social.ml")
    route = next(r for r in contract["routes"]
                 if r["method"] == "POST" and r["path"] == "/like")
    assert set(route["request_fields"]) == {"note", "post_id"}
    with uvicorn_server(str(project)) as base:
        headers = _token(base, "Member", "membre@example.test")
        post = requests.get(f"{base}/post", timeout=10).json()["data"][0]
        with sqlite_db(project / "app.db") as db:
            before = db.execute("SELECT likes FROM post WHERE id = ?",
                                 (post["id"],)).fetchone()[0]
        values = {"note": "bravo", "post_id": post["id"]}
        body = {field: values[field] for field in route["request_fields"]}
        result = requests.post(f"{base}/like", timeout=10, headers=headers, json=body)
        assert result.status_code == 200, result.text
        with sqlite_db(project / "app.db") as db:
            after = db.execute("SELECT likes FROM post WHERE id = ?",
                               (post["id"],)).fetchone()[0]
    assert after == before + 1
