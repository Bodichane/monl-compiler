"""Charging an entity owned TRANSITIVELY — point 87.

Why this file exists. Point 81 refused `payable` on any entity owned through
an intermediate, with this reason: "the payment route identifies the payer by
an ACCOUNT foreign key, which a transitive chain does not provide". It was
true of the code then, and false of the brick: transitive ownership ALREADY
provided, in `_owner_lookup_sql`, the join that returns the account id. The
refusal protected against a wrong comparison — not an impossibility.

What these tests require, and what a review does not prove:

* **the third party is refused.** It is THE reason the refusal was lifted. If
  the route still compared `current_user_id` with the intermediate's foreign
  key, the verdict would be a coin toss — letting the wrong account pay, or
  blocking the right one. The bench's identifiers are therefore deliberately
  DIVERGENT: without this precaution point 81's probe had shown nothing,
  because "user 1" and "order 1" coincided;
* **the amount is checked on what the PROVIDER receives**, not on what the
  database holds: it is the only statement that counts for a shop;
* **an orphan line answers 404**, never "payable by anyone" — the join
  returns no result, and that is the right answer;
* **the check and the amount come out of the SAME read.** Point 74's
  invariant was not to be paid to get the join: two queries would reopen the
  window between the access check and the amount calculation.
"""
import contextlib
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
from tests.support.server import uvicorn_server

# The LINE is chargeable, not the order: that is exactly what point 81 refused.
# The case is not artificial — an invoice attached to a contract, a service
# attached to a case file have the same shape.
SPEC = """app BancTransitif

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

entity Client
    nom: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne
relation Client hasMany Client

actor Client selfRegister

rule Article.nom required
rule Commande.libelle required
rule Client.nom required
rule Ligne.quantite required
rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Ligne.sousTotal payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
    Create Client
    Read Client
    Read Article
"""

CLE_SECRETE = "sk_test_banc_transitif"
CLE_WEBHOOK = "whsec_banc_transitif"
PRIX = 42.5
QUANTITE = 3


class _PrestataireFactice(BaseHTTPRequestHandler):
    """It DECODES the received body: it is the only way to state which amount was
    really requested. Reading the database would only tell what monl believes."""

    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append(
            {c: v[0] for c, v in urllib.parse.parse_qs(brut.decode()).items()})
        corps = json.dumps({"id": f"cs_{len(self.server.recu)}",
                            "url": "https://paiement.example/s"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def faux_stripe():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _PrestataireFactice)
    serveur.recu = []
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)


@contextlib.contextmanager
def _base_spec(dossier):
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


@pytest.fixture(scope="module")
def application(faux_stripe):
    hote, port_stripe = faux_stripe.server_address[:2]
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        env = {**os.environ, "STRIPE_SECRET_KEY": CLE_SECRETE,
               "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
               "MONL_STRIPE_BASE_URL": f"http://{hote}:{port_stripe}"}
        with uvicorn_server(dossier, env=env) as base:
            with _base_spec(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article", PRIX))
            yield base, dossier


def _compte(application, identifiant):
    base, dossier = application
    with _base_spec(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register", json={"username": identifiant,
                                            "password": "motdepasse1",
                                            "actor": "Client"}, timeout=10)
    reponse = requests.post(f"{base}/login", json={"username": identifiant,
                                                   "password": "motdepasse1"},
                            timeout=10)
    entetes = {"Authorization": f"Bearer {reponse.json()['access_token']}"}
    requests.post(f"{base}/client", json={"nom": identifiant},
                  headers=entetes, timeout=10)
    return entetes


@pytest.fixture(scope="module")
def alice(application):
    return _compte(application, "alice")


@pytest.fixture(scope="module")
def bob(application):
    return _compte(application, "bob")


def _line_of(base, entetes, libelle):
    """An order and its line, and the identifier of both."""
    commande = requests.post(f"{base}/commande", json={"libelle": libelle},
                             headers=entetes, timeout=10).json()["id"]
    article = requests.get(f"{base}/article?limit=1", timeout=10).json()["data"][0]["id"]
    ligne = requests.post(f"{base}/ligne",
                          json={"quantite": QUANTITE, "commande_id": commande,
                                "article_id": article},
                          headers=entetes, timeout=10).json()["id"]
    return commande, ligne


# --------------------------------------------------------------------------

def test_the_transitive_owner_can_pay(application, alice, faux_stripe):
    """What point 81 forbade. The amount is checked on what the PROVIDER
    receives — not on what the database holds."""
    base, _dossier = application
    _commande, ligne = _line_of(base, alice, "panier alice")

    avant = len(faux_stripe.recu)
    reponse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)
    assert reponse.status_code == 200, reponse.text
    assert len(faux_stripe.recu) == avant + 1

    demande = faux_stripe.recu[-1]
    attendu = str(round(PRIX * QUANTITE * 100))
    assert demande["line_items[0][price_data][unit_amount]"] == attendu, demande
    # The reference is qualified by the entity name (point 75): otherwise the
    # webhook would confuse the ids of two payable tables.
    assert demande.get("client_reference_id") == f"Ligne:{ligne}"


def test_a_third_party_cannot_pay(application, alice, bob):
    """THE test that justifies lifting the refusal.

    If the route still compared `current_user_id` with the intermediate's
    foreign key — an ORDER id — the verdict would be a coin toss. The identifiers
    are deliberately divergent so that the confusion shows."""
    base, dossier = application
    commande, ligne = _line_of(base, alice, "panier privé")

    with _base_spec(dossier) as cnx:
        compte_alice = cnx.execute(
            "SELECT id FROM _monl_users WHERE username = 'alice'").fetchone()[0]
    assert commande != compte_alice, "identifiants confondus : le test ne prouve rien"
    assert ligne != compte_alice, "identifiants confondus : le test ne prouve rien"

    refuse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=bob, timeout=15)
    assert refuse.status_code == 403, refuse.text
    # And the owner does get through: a 403 for everyone would "pass" this test
    # while proving nothing.
    assert requests.post(f"{base}/ligne/{ligne}/paiement",
                         headers=alice, timeout=15).status_code == 200


def test_an_orphan_line_is_not_found(application, alice):
    """The join returns no result: the line belongs to nobody. 404 — certainly
    not "payable by anyone"."""
    base, dossier = application
    _commande, ligne = _line_of(base, alice, "panier à orpheliner")
    with _base_spec(dossier) as cnx:
        cnx.execute('UPDATE "ligne" SET "commande_id" = 999999 WHERE id = ?', (ligne,))
    reponse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)
    assert reponse.status_code == 404, reponse.text


def test_the_webhook_marks_the_line_paid(application, alice, faux_stripe):
    """The full chain: the qualified reference comes back from the provider and
    designates the right table."""
    import hashlib
    import hmac

    base, dossier = application
    _commande, ligne = _line_of(base, alice, "panier réglé")
    requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)

    corps = json.dumps({"type": "checkout.session.completed",
                        "data": {"object": {"client_reference_id": f"Ligne:{ligne}",
                                            "id": "cs_x"}}}).encode()
    # POINT 91: the CURRENT time, like the real provider — the signature is now
    # dated, and a frozen timestamp would be refused as a replay.
    horodatage = str(int(time.time()))
    signature = hmac.new(CLE_WEBHOOK.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    reponse = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={horodatage},v1={signature}"}, timeout=10)
    assert reponse.status_code == 200, reponse.text

    with _base_spec(dossier) as cnx:
        etat = cnx.execute('SELECT payment_status FROM "ligne" WHERE id = ?',
                           (ligne,)).fetchone()[0]
    assert etat == "payee"


def test_the_check_and_the_amount_come_from_the_same_read(tmp_path):
    """Point 74's invariant, not to be paid for the join: two separate queries
    would reopen the window between the access check and the amount calculation.
    The route must therefore contain only ONE execute."""
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    # Cut at the next decorator: "\ndef" would also catch the webhook, whose
    # execute is legitimate and would skew the count.
    corps = genere.split("def payer_ligne(")[1].split("@app.post")[0]
    assert corps.count("cursor.execute(") == 1, corps
    # The join is indeed IN this single SELECT.
    assert "JOIN" in corps and "commande" in corps
