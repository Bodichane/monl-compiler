"""Brick 18 (lock on a paid record) tested against a real server — point 91.

Why this file exists. `payable` (brick 9) guaranteed that the charged amount
came from the DATABASE, never from the client. It said nothing about what
happens AFTER the charge — and the answer, measured on a real shop before
writing a line of code, was: everything. An order settled for €89 gained a
pair at €149, showed €238 still marked 'payee', then €594 by raising the
quantity to five. Emptied of its lines, it could be deleted; the 409 the
foreign key returned then protected nothing, it delayed.

What these tests require, and what a review does not prove:

* all five doors are closed, not one: the payable entity on update and
  delete, and its LINE on create, update and delete — the total went up
  through the line, a lock on the order alone would have left the whole hole;
* the total does not move by a cent after a refusal (a 409 returned AFTER the
  recalculation would be a lock that warns instead of prevents);
* the COUNTER-PROOF: before payment, the five writes still pass. A lock that
  froze everything would make the first five tests pass while guaranteeing
  nothing, and would make the shop unusable;
* a signed but OLD webhook is refused: the timestamp was read to check the
  signature and never dated, so a captured call stayed replayable;
* the `Email` type finally refuses an address that is not one.
"""
import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.cases import check_each_case
from tests.support.server import uvicorn_server

SPEC = """app BancVerrou

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
    courriel: Email
    total: Money

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client

rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite

rule Commande.total sumOf Ligne.sousTotal
rule Commande.total payable

workflow Acheter for Client
    Read Article
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

PASSWORD = "motdepasse123"
KEY_SECRETE = "sk_test_banc_verrou"
KEY_WEBHOOK = "whsec_banc_verrou"
PRICE = 89.00
PRICE_CHER = 149.00


class _ProviderFake(BaseHTTPRequestHandler):
    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.received.append(
            {c: v[0] for c, v in urllib.parse.parse_qs(brut.decode()).items()})
        body = json.dumps({
            "id": f"cs_test_{len(self.server.received)}",
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
    conn = sqlite3.connect(os.path.join(folder, "app.db"))
    try:
        with conn:
            yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def application(faux_stripe):
    hote, port_stripe = faux_stripe.server_address[:2]
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        env = {**os.environ,
               "STRIPE_SECRET_KEY": KEY_SECRETE,
               "STRIPE_WEBHOOK_SECRET": KEY_WEBHOOK,
               "MONL_STRIPE_BASE_URL": f"http://{hote}:{port_stripe}"}
        with uvicorn_server(folder, env=env) as base:
            with _base_spec(folder) as conn:
                conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Deck", PRICE))
                conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Halo", PRICE_CHER))
            yield base, folder


def _headers(application, identifier):
    base, folder = application
    with _base_spec(folder) as conn:
        conn.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register",
                  json={"username": identifier, "password": PASSWORD,
                        "actor": "Client"})
    token = requests.post(f"{base}/login",
                          json={"username": identifier,
                                "password": PASSWORD}).json()
    assert "access_token" in token, token
    return {"Authorization": "Bearer " + token["access_token"]}


@pytest.fixture(scope="module")
def alice(application):
    return _headers(application, "alice")


def _article(folder, price):
    with _base_spec(folder) as conn:
        return conn.execute('SELECT id FROM article WHERE prix = ?',
                           (price,)).fetchone()[0]


def _order(base, headers, label="panier"):
    response = requests.post(f"{base}/commande", headers=headers,
                            json={"libelle": label,
                                  "courriel": "acheteuse@exemple.fr"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _line(base, headers, order_id, article_id, quantity=1):
    return requests.post(f"{base}/ligne", headers=headers,
                         json={"commande_id": order_id,
                               "article_id": article_id,
                               "quantite": quantity})


def _total(base, headers, order_id):
    return requests.get(f"{base}/commande/{order_id}",
                        headers=headers).json()["data"]["total"]


def _state(folder, order_id):
    with _base_spec(folder) as conn:
        line = conn.execute(
            'SELECT payment_status FROM commande WHERE id = ?',
            (order_id,)).fetchone()
    return line[0] if line else None


def _webhook(base, order_id, offset=0, session="cs_test_1"):
    """Signs and posts a payment event. `decalage` in seconds serves the replay
    test: it is the only parameter that changes between a legitimate call and a
    call captured then replayed later."""
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": session,
                            "client_reference_id": f"Commande:{order_id}"}},
    }).encode()
    timestamp = str(int(time.time()) + offset)
    signature = hmac.new(KEY_WEBHOOK.encode(),
                         (timestamp + ".").encode() + body,
                         hashlib.sha256).hexdigest()
    return requests.post(
        f"{base}/paiement/webhook", data=body,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={timestamp},v1={signature}"},
        timeout=10)


def _settled_order(application, headers):
    """A one-line order at €89, really sent through the payment route then the
    provider's signed webhook."""
    base, folder = application
    identifier = _order(base, headers)
    assert _line(base, headers, identifier,
                  _article(folder, PRICE)).status_code in (200, 201)
    response = requests.post(f"{base}/commande/{identifier}/paiement",
                            headers=headers)
    assert response.status_code == 200, response.text
    assert _webhook(base, identifier).status_code == 200
    assert _state(folder, identifier) == "payee"
    return identifier


# -------------------------------------------------------------------- the lock

def test_a_settled_order_refuses_updates(application, alice):
    base, folder = application
    identifier = _settled_order(application, alice)

    response = requests.put(f"{base}/commande/{identifier}", headers=alice,
                           json={"libelle": "renommée",
                                 "courriel": "acheteuse@exemple.fr"})

    assert response.status_code == 409, response.text
    assert "already paid" in response.json()["detail"]
    with _base_spec(folder) as conn:
        assert conn.execute('SELECT libelle FROM commande WHERE id = ?',
                           (identifier,)).fetchone()[0] == "panier"


def test_a_settled_order_refuses_deletion(application, alice):
    """Deleting erased the trace of a charge. The 409 the foreign key returned
    only held as long as a line remained: this test empties the order first,
    which is exactly the path through which it disappeared."""
    base, folder = application
    identifier = _settled_order(application, alice)
    lines = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    line = next(li for li in lines if li["commande_id"] == identifier)

    removal = requests.delete(f"{base}/ligne/{line['id']}", headers=alice)
    deletion = requests.delete(f"{base}/commande/{identifier}", headers=alice)

    assert removal.status_code == 409, removal.text
    assert deletion.status_code == 409, deletion.text
    with _base_spec(folder) as conn:
        assert conn.execute('SELECT COUNT(*) FROM commande WHERE id = ?',
                           (identifier,)).fetchone()[0] == 1


def test_a_line_can_no_longer_be_added_to_a_settled_order(application, alice):
    """The original hole, in the direction it was exploited: €89 charged, then a
    pair at €149 added, and €238 shown still 'payee'."""
    base, folder = application
    identifier = _settled_order(application, alice)

    addition = _line(base, alice, identifier, _article(folder, PRICE_CHER))

    assert addition.status_code == 409, addition.text
    # The total must not have moved by a cent: a refusal returned AFTER the
    # recalculation would warn instead of prevent.
    assert float(_total(base, alice, identifier)) == PRICE


def test_the_quantity_of_a_settled_line_no_longer_changes(application, alice):
    base, folder = application
    identifier = _settled_order(application, alice)
    lines = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    line = next(li for li in lines if li["commande_id"] == identifier)

    change = requests.put(f"{base}/ligne/{line['id']}", headers=alice,
                         json={"quantite": 5, "commande_id": identifier,
                               "article_id": line["article_id"]})

    assert change.status_code == 409, change.text
    assert float(_total(base, alice, identifier)) == PRICE


# ----------------------------------------------------------- the counter-proof

def test_before_payment_the_five_writes_still_pass(application, alice):
    """WITHOUT this test, a lock freezing everything would make the previous
    ones pass while guaranteeing nothing — and would make the shop unusable."""
    base, folder = application
    identifier = _order(base, alice, "en cours")

    addition = _line(base, alice, identifier, _article(folder, PRICE))
    line_id = addition.json()["id"]
    change_line = requests.put(f"{base}/ligne/{line_id}", headers=alice,
                               json={"quantite": 3, "commande_id": identifier,
                                     "article_id": _article(folder, PRICE)})
    total_after_change = float(_total(base, alice, identifier))
    change_order = requests.put(f"{base}/commande/{identifier}", headers=alice,
                                  json={"libelle": "renommée",
                                        "courriel": "acheteuse@exemple.fr"})
    removal = requests.delete(f"{base}/ligne/{line_id}", headers=alice)
    deletion = requests.delete(f"{base}/commande/{identifier}", headers=alice)

    assert addition.status_code in (200, 201), addition.text
    assert change_line.status_code == 200, change_line.text
    assert total_after_change == round(PRICE * 3, 2)
    assert change_order.status_code == 200, change_order.text
    assert removal.status_code == 200, removal.text
    assert deletion.status_code == 200, deletion.text


def test_the_lock_does_not_spill_onto_the_next_order(application, alice):
    """A settled order only freezes itself: the lock reads the line's parent,
    not "a paid order exists somewhere"."""
    base, folder = application
    _settled_order(application, alice)
    neighbor = _order(base, alice, "voisine")

    addition = _line(base, alice, neighbor, _article(folder, PRICE))

    assert addition.status_code in (200, 201), addition.text
    assert float(_total(base, alice, neighbor)) == PRICE


# -------------------------------------------------------------- webhook replay

def test_a_signed_but_old_webhook_is_refused(application, alice):
    """Signature freshness: the timestamp served to CHECK the signature without
    ever being dated, so a legitimate captured call stayed replayable
    indefinitely. Ten minutes are enough to show it."""
    base, folder = application
    identifier = _order(base, alice, "rejeu")
    _line(base, alice, identifier, _article(folder, PRICE))

    response = _webhook(base, identifier, offset=-600)

    assert response.status_code == 400, response.text
    assert "Expired" in response.json()["detail"]
    assert _state(folder, identifier) == "en_attente"


def test_an_unreadable_timestamp_does_not_pass_as_fresh(application, alice):
    base, folder = application
    identifier = _order(base, alice, "horodatage")
    body = json.dumps({"type": "checkout.session.completed",
                        "data": {"object": {"id": "cs_x",
                                            "client_reference_id":
                                            f"Commande:{identifier}"}}}).encode()
    signature = hmac.new(KEY_WEBHOOK.encode(), b"jamais." + body,
                         hashlib.sha256).hexdigest()

    response = requests.post(
        f"{base}/paiement/webhook", data=body,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t=jamais,v1={signature}"}, timeout=10)

    assert response.status_code == 400, response.text
    assert _state(folder, identifier) == "en_attente"


# ------------------------------------------------------------------- courriel

def test_the_email_type_refuses_an_address_that_is_not_one(application, alice):
    """POINT 91: the type only set a length. 'pas-un-courriel' entered the
    database with a 200 — an address no parcel goes to."""
    table = [
        "pas-un-courriel", "sans@point", "espace @exemple.fr", "@exemple.fr",
        "deux@@exemple.fr",
    ]

    def cas(address):
        base, _folder = application

        response = requests.post(f"{base}/commande", headers=alice,
                                json={"libelle": "adresse", "courriel": address})

        assert response.status_code == 422, response.text

    check_each_case([(valeur,) for valeur in table], cas)


def test_a_valid_address_stays_accepted(application, alice):
    """The refusal's counter-proof: a too strict pattern would make the previous
    test pass while also rejecting real addresses."""
    table = [
        "acheteuse@exemple.fr", "prenom.nom+etiquette@sous.domaine.co.uk",
    ]

    def cas(address):
        base, _folder = application

        response = requests.post(f"{base}/commande", headers=alice,
                                json={"libelle": "adresse", "courriel": address})

        assert response.status_code in (200, 201), response.text

    check_each_case([(valeur,) for valeur in table], cas)
