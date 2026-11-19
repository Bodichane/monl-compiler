"""Issue #73: an after-payment status is born in the oneOf's first state."""

import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.process import close_tubes, stop_process
from tests.support.server import free_port, uvicorn_server

SPEC = """app BancStatutInitial

entity Article
    prix: Money
    stock: Integer

entity Commande
    total: Money
    statut: String
    suivi: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister
actor Gestionnaire selfRegister

rule Article.Read public
rule Article.stock min 0
rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Commande.total sumOf Ligne.sousTotal
rule Commande.total payable
rule Commande.statut oneOf "panier", "expédiée", "annulée"
rule Commande.statut writableAfterPayment Gestionnaire
rule Commande.suivi writableAfterPayment Gestionnaire

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Read Article

workflow Gerer for Gestionnaire
    Update Commande.statut
    Update Commande.suivi
"""

PASSWORD = "motdepasse123"
KEY_WEBHOOK = "whsec_statut_initial"


class _ProviderFake(BaseHTTPRequestHandler):
    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.received.append(urllib.parse.parse_qs(brut.decode()))
        body = json.dumps({
            "id": f"cs_statut_{len(self.server.received)}",
            "url": "https://paiement.example/session",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def faux_stripe():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderFake)
    server.received = []
    fil = threading.Thread(target=server.serve_forever, daemon=True)
    fil.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        fil.join(timeout=5)


@contextlib.contextmanager
def _base_spec(folder):
    login = sqlite3.connect(Path(folder) / "app.db")
    try:
        with login:
            yield login
    finally:
        login.close()


def _env_payment(faux_stripe):
    hote, port = faux_stripe.server_address[:2]
    return {
        **os.environ,
        "STRIPE_SECRET_KEY": "sk_test_statut_initial",
        "STRIPE_WEBHOOK_SECRET": KEY_WEBHOOK,
        "MONL_STRIPE_BASE_URL": f"http://{hote}:{port}",
    }


def _register(base, name, actor):
    response = requests.post(
        f"{base}/register",
        json={"username": name, "password": PASSWORD, "actor": actor},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    login = requests.post(
        f"{base}/login",
        json={"username": name, "password": PASSWORD},
        timeout=10,
    )
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def _webhook(base, order_id):
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_statut_1",
            "client_reference_id": f"Commande:{order_id}",
        }},
    }).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        KEY_WEBHOOK.encode(), (timestamp + ".").encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return requests.post(
        f"{base}/paiement/webhook",
        data=body,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={timestamp},v1={signature}"},
        timeout=10,
    )


@pytest.fixture(scope="module")
def application(faux_stripe):
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        with uvicorn_server(folder, env=_env_payment(faux_stripe)) as base:
            with _base_spec(folder) as login:
                login.execute(
                    "INSERT INTO article (prix, stock) VALUES (12.5, 10)")
            client = _register(base, "cliente", "Client")
            manager = _register(base, "gestionnaire", "Gestionnaire")
            yield base, folder, client, manager


def test_creation_takes_the_first_oneof_and_leaves_text_empty(application):
    base, folder, client, _manager = application
    creation = requests.post(f"{base}/commande", headers=client, json={}, timeout=10)
    assert creation.status_code == 200, creation.text
    identifier = creation.json()["id"]

    lecture = requests.get(
        f"{base}/commande/{identifier}", headers=client, timeout=10)
    assert lecture.status_code == 200, lecture.text
    assert lecture.json()["data"]["statut"] == "panier"
    assert lecture.json()["data"]["suivi"] is None
    with _base_spec(folder) as login:
        assert login.execute(
            "SELECT statut, suivi FROM commande WHERE id = ?", (identifier,),
        ).fetchone() == ("panier", None)


def test_after_payment_changes_the_status(application):
    base, folder, client, manager = application
    order = requests.post(
        f"{base}/commande", headers=client, json={}, timeout=10).json()["id"]
    line = requests.post(
        f"{base}/ligne", headers=client,
        json={"commande_id": order, "article_id": 1, "quantite": 1},
        timeout=10,
    )
    assert line.status_code == 200, line.text
    payment = requests.post(
        f"{base}/commande/{order}/paiement", headers=client, timeout=10)
    assert payment.status_code == 200, payment.text
    assert _webhook(base, order).status_code == 200

    modification = requests.put(
        f"{base}/commande/{order}/apres-paiement",
        headers=manager, json={"statut": "expédiée"}, timeout=10)
    assert modification.status_code == 200, modification.text
    with _base_spec(folder) as login:
        assert login.execute(
            "SELECT statut FROM commande WHERE id = ?", (order,),
        ).fetchone()[0] == "expédiée"


def test_a_release_first_state_is_refused(capsys):
    spec = SPEC.replace(
        'rule Commande.statut oneOf "panier", "expédiée", "annulée"',
        'rule Commande.statut oneOf "annulée", "panier", "expédiée"',
    ).replace(
        "rule Commande.statut writableAfterPayment Gestionnaire",
        'rule Commande.statut "annulée" releases Ligne\n'
        "rule Ligne.Create decrements Article.stock by quantite\n"
        "rule Commande.statut writableAfterPayment Gestionnaire",
    )
    with pytest.raises(ASTValidationError) as refusal:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    message = str(refusal.value)
    assert "Commande.statut" in message
    assert "annulée" in message
    assert "First declare the initial state" in message
    capsys.readouterr()


def _start_with_log(folder, env):
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        if process.poll() is not None:
            output = process.stdout.read().decode("utf-8", "replace")
            close_tubes(process)
            pytest.fail(output)
        try:
            if requests.get(base + "/openapi.json", timeout=1).status_code == 200:
                return process
        except requests.RequestException:
            time.sleep(0.25)
    stop_process(process)
    pytest.fail("the server never answered")


def test_an_old_null_row_is_counted_not_backfilled(
        tmp_path, faux_stripe):
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    env = _env_payment(faux_stripe)
    with uvicorn_server(str(tmp_path), env=env), _base_spec(tmp_path) as login:
        login.execute(
            "INSERT INTO commande (total, statut, suivi) VALUES (0, NULL, NULL)")

    process = _start_with_log(str(tmp_path), env)
    process.terminate()
    output, _ = process.communicate(timeout=10)
    log = output.decode("utf-8", "replace")
    assert '"commande"."statut": 1 record(s)' in log
    assert "NULL value outside the oneOf" in log
    with _base_spec(tmp_path) as login:
        assert login.execute(
            "SELECT statut FROM commande WHERE id = 1").fetchone()[0] is None


def test_shop_example_creates_an_order_in_cart_status(tmp_path):
    racine = Path(__file__).parents[1]
    compile_project(str(racine / "exemples" / "02_boutique.ml"), str(tmp_path))
    with uvicorn_server(str(tmp_path)) as base:
        client = _register(base, "boutique@example.com", "Customer")
        creation = requests.post(
            f"{base}/order", headers=client, json={}, timeout=10)
        assert creation.status_code == 200, creation.text
        lecture = requests.get(
            f"{base}/order/{creation.json()['id']}", headers=client, timeout=10)
        assert lecture.status_code == 200, lecture.text
        assert lecture.json()["data"]["status"] == "panier"
