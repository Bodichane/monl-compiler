"""Reference journey on the real CodexShop spec, up to its update."""

import os
import shutil
from pathlib import Path

import requests

from monl.cli import check_coherence, compile_project
from monl.cli.delta import cmd_update
from tests.support.server import uvicorn_server

DEMO = Path(__file__).resolve().parents[1] / "demo"


def test_codexshop_keeps_the_order_and_stock_after_update(tmp_path):
    project = tmp_path / "codexshop"
    shutil.copytree(DEMO, project)
    spec = project / "spec.ml"
    compile_project(str(spec), str(project))
    frontend = (project / "frontend" / "index.html").read_bytes()
    secret = (project / ".jwt_secret").read_bytes()
    # The scenario is local: no external database nor inherited payment key.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("MONL_", "STRIPE_", "FEDAPAY_"))}

    def call(base, method, path, *, token=None, body=None, status=200):
        response = requests.request(
            method, base + path, json=body, timeout=10,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        assert response.status_code == status, (method, path, response.text)
        return response.json()

    def login(base, email):
        return call(base, "POST", "/login", body={
            "username": email, "password": "DemoLocale-2026!",
        })["access_token"]

    with uvicorn_server(project, env=env) as base:
        catalog = call(base, "GET", "/product?limit=100")["data"]
        assert len(catalog) == 12
        product = next(item for item in catalog if item["name"] == "Carnet Lin Ivoire")
        product_path = f"/product/{product['id']}"
        for email in ("lea@example.test", "sam@example.test"):
            call(base, "POST", "/register", body={
                "username": email, "password": "DemoLocale-2026!", "actor": "Customer",
            })
        token = login(base, "lea@example.test")
        other = login(base, "sam@example.test")
        call(base, "POST", "/order", token=token,
             body={"status": "À confirmer"}, status=409)
        call(base, "POST", "/customer", token=token, body={
            "displayName": "Léa", "email": "lea@example.test",
            "address": "12 rue du Test", "postalCode": "75001",
            "city": "Paris", "country": "France",
        })
        order_id = call(base, "POST", "/order", token=token,
                        body={"status": "À confirmer"})["id"]
        order_path = f"/order/{order_id}"
        line = {"order_id": order_id, "product_id": product["id"], "quantite": 2}
        call(base, "POST", "/ligneorder", token=token, body=line)
        order = call(base, "GET", order_path, token=token)["data"]
        assert order["total"] == 48
        assert order["reference"].startswith("CMD-")
        assert order["creeLe"]
        assert call(base, "GET", product_path)["data"]["stock"] == product["stock"] - 2
        assert call(base, "GET", "/order", token=other)["data"] == []
        call(base, "GET", order_path, token=other, status=404)

        # An impossible cart must change neither stock, nor lines, nor total.
        call(base, "POST", "/ligneorder", token=token,
             body={**line, "quantite": product["stock"] + 1}, status=409)
        assert call(base, "GET", product_path)["data"]["stock"] == product["stock"] - 2
        assert call(base, "GET", order_path, token=token)["data"] == order
        assert len(call(base, "GET", "/ligneorder", token=token)["data"]) == 1
        payment = call(base, "POST", order_path + "/paiement", token=token, status=503)
        assert "STRIPE_SECRET_KEY" in payment["detail"]

    # The exercise uses the same update command as the operator, with the
    # server stopped.
    spec.write_text(spec.read_text(encoding="utf-8").replace(
        "entity Order\n", "entity Order\n    note: Text\n", 1), encoding="utf-8")
    ok, errors, _ = check_coherence(str(project))
    assert not ok and errors
    cmd_update(str(project))
    assert "Order.note" in (project / "docs" / "FRONTEND_UPDATE_PROMPT.md").read_text(
        encoding="utf-8")
    assert (project / "frontend" / "index.html").read_bytes() == frontend
    assert (project / ".jwt_secret").read_bytes() == secret

    with uvicorn_server(project, env=env) as base:
        # The existing account and token stay usable after recompiling.
        login(base, "lea@example.test")
        migrated = call(base, "GET", order_path, token=token)["data"]
        assert migrated == {**order, "note": None}
        assert call(base, "GET", product_path)["data"]["stock"] == product["stock"] - 2
        assert len(call(base, "GET", "/product?limit=100")["data"]) == len(catalog)
        call(base, "PUT", order_path, token=token,
             body={"status": "À confirmer", "note": "Livrer le matin"})
        assert call(base, "GET", order_path, token=token)["data"]["note"] == "Livrer le matin"

        # Cancelling gives the stock back once, even if the client retries.
        cancelled = {"status": "Annulée", "note": "Livrer le matin"}
        call(base, "PUT", order_path, token=token, body=cancelled)
        call(base, "PUT", order_path, token=token, body=cancelled)
        assert call(base, "GET", product_path)["data"]["stock"] == product["stock"]
        assert call(base, "GET", order_path, token=token)["data"]["status"] == "Annulée"
