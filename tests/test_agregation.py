"""Brick 12 (`sumOf`) tested against a real server — point 82.

Why this file exists. `derivedFrom` (brick 10) calculates an amount from ONE
linked row: an order could therefore carry only one item. Transitive
ownership (brick 11) gave the order properly protected lines, but the order
still did not know what it cost — the total stayed a field the client wrote,
or did not exist. `sumOf` closes the third and last cart brick scoped at
point 80.

What these tests require, and what a review does not prove:

* the total follows the lines in all THREE directions — add, update, delete.
  Recalculating on creation only would let point 77's flaw come back through
  the quantity, then through removing an item;
* an emptied cart falls back to 0 and not to NULL (which no interface
  displays);
* the CHARGED amount is the sum, checked on what the provider really
  receives — it is the only statement that counts for a shop, and it requires
  a fake Stripe, not a database read;
* a third party's total does not move when one tries to add a line to their
  order (composition with brick 11: the 403 is not enough, NOTHING must have
  been recalculated);
* the sum is rounded: adding floats drifts, and this is an amount.
"""
import contextlib
import json
import os
import sqlite3
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app BancAgregation

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
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
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_banc_agregation"
CLE_WEBHOOK = "whsec_banc_agregation"
# Prices CHOSEN so that the sum really drifts in floating point: round(10.05*3,
# 2) + round(10.15*7, 2) == 101.19999999999999, not 101.2. My first values
# (12.35 and 7.80) did not drift, which made the rounding test tautological: it
# passed with or without the ROUND. Checked in Python before being written
# here.
PRIX_A, PRIX_B = 10.05, 10.15
# The quantity that triggers the drift, used by the rounding test.
QTE_A, QTE_B = 3, 7


class _PrestataireFactice(BaseHTTPRequestHandler):
    """Same fake Stripe as tests/test_paiement.py: it DECODES the body it is
    sent, which is the only way to state which amount was really requested —
    reading the database would only tell what monl believes it charges."""

    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append({
            "chemin": self.path,
            "champs": {c: v[0] for c, v
                       in urllib.parse.parse_qs(brut.decode()).items()},
        })
        corps = json.dumps({
            "id": f"cs_test_{len(self.server.recu)}",
            "url": "https://paiement.example/session",
        }).encode()
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
        env = {**os.environ,
               "STRIPE_SECRET_KEY": CLE_SECRETE,
               "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
               "MONL_STRIPE_BASE_URL": f"http://{hote}:{port_stripe}"}
        with uvicorn_server(dossier, env=env) as base:
            with _base_spec(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article A", PRIX_A))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article B", PRIX_B))
            yield base, dossier


def _vider_quota(dossier):
    with _base_spec(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")


def _entetes(application, identifiant):
    base, dossier = application
    _vider_quota(dossier)
    requests.post(f"{base}/register",
                  json={"username": identifiant, "password": MOT_DE_PASSE,
                        "actor": "Client"})
    jeton = requests.post(f"{base}/login",
                          json={"username": identifiant,
                                "password": MOT_DE_PASSE}).json()
    assert "access_token" in jeton, jeton
    return {"Authorization": "Bearer " + jeton["access_token"]}


@pytest.fixture(scope="module")
def alice(application):
    return _entetes(application, "alice")


@pytest.fixture(scope="module")
def bob(application):
    return _entetes(application, "bob")


def _id_article(dossier, prix):
    with _base_spec(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (prix,)).fetchone()[0]


def _order(base, entetes, libelle):
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _line(base, entetes, commande_id, article_id, quantite):
    return requests.post(f"{base}/ligne", headers=entetes,
                         json={"commande_id": commande_id,
                               "article_id": article_id,
                               "quantite": quantite})


def _total(base, entetes, commande_id):
    reponse = requests.get(f"{base}/commande/{commande_id}", headers=entetes)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()["data"]["total"]


# --------------------------------------------------------------------------
# The total leaves the request bodies
# --------------------------------------------------------------------------

def test_the_total_is_not_a_request_field(application):
    base, _ = application
    champs = requests.get(f"{base}/openapi.json").json()[
        "components"]["schemas"]["CommandeSchema"]["properties"]
    assert "total" not in champs, (
        "the client could write a cart's total — point 77's flaw "
        "back through the cart")
    assert "libelle" in champs  # witness: the schema is not empty


def test_an_order_starts_at_zero_not_null(application, alice):
    """NULL is not 0: no interface can display "null €", and a sum starting from
    NULL would stay NULL in SQLite."""
    base, _ = application
    commande = _order(base, alice, "panier vide")
    assert _total(base, alice, commande) == 0


def test_the_total_sent_by_the_client_is_ignored(application, alice):
    base, dossier = application
    commande = _order(base, alice, "tentative")
    article = _id_article(dossier, PRIX_A)
    _line(base, alice, commande, article, 1)
    # The field does not exist in the schema: Pydantic silently ignores it.
    requests.put(f"{base}/commande/{commande}", headers=alice,
                 json={"libelle": "tentative", "total": 0.01})
    assert _total(base, alice, commande) == pytest.approx(PRIX_A)


# --------------------------------------------------------------------------
# The total follows the lines in all three directions
# --------------------------------------------------------------------------

def test_the_total_is_the_sum_of_several_items(application, alice):
    """The heart of the brick: what `derivedFrom` could not do."""
    base, dossier = application
    commande = _order(base, alice, "deux articles")
    assert _line(base, alice, commande, _id_article(dossier, PRIX_A),
                  2).status_code in (200, 201)
    assert _total(base, alice, commande) == pytest.approx(PRIX_A * 2)

    assert _line(base, alice, commande, _id_article(dossier, PRIX_B),
                  3).status_code in (200, 201)
    attendu = round(PRIX_A * 2 + PRIX_B * 3, 2)
    assert _total(base, alice, commande) == pytest.approx(attendu)


def test_the_total_follows_the_updated_quantity(application, alice):
    """Without recalculation on PUT, the flaw would move from the line to the
    quantity: add an item at 1 then switch to 10."""
    base, dossier = application
    commande = _order(base, alice, "modification")
    article = _id_article(dossier, PRIX_A)
    ligne = _line(base, alice, commande, article, 1).json()["id"]
    assert _total(base, alice, commande) == pytest.approx(PRIX_A)

    requests.put(f"{base}/ligne/{ligne}", headers=alice,
                 json={"quantite": 10, "commande_id": commande,
                       "article_id": article})
    assert _total(base, alice, commande) == pytest.approx(PRIX_A * 10)


def test_the_total_goes_down_when_a_line_is_deleted(application, alice):
    """The direction one forgets: without it, removing an item from the cart
    would let a returned item be paid for."""
    base, dossier = application
    commande = _order(base, alice, "suppression")
    ligne_a = _line(base, alice, commande, _id_article(dossier, PRIX_A),
                     1).json()["id"]
    _line(base, alice, commande, _id_article(dossier, PRIX_B), 1)
    assert _total(base, alice, commande) == pytest.approx(
        round(PRIX_A + PRIX_B, 2))

    assert requests.delete(f"{base}/ligne/{ligne_a}",
                           headers=alice).status_code == 200
    assert _total(base, alice, commande) == pytest.approx(PRIX_B)


def test_a_cart_emptied_of_its_lines_falls_back_to_zero(application, alice):
    base, dossier = application
    commande = _order(base, alice, "à vider")
    ligne = _line(base, alice, commande, _id_article(dossier, PRIX_A),
                   2).json()["id"]
    requests.delete(f"{base}/ligne/{ligne}", headers=alice)
    assert _total(base, alice, commande) == 0, "an emptied cart must be worth 0"


def test_the_sum_is_rounded(application, alice):
    """Adding floats drifts. On an amount, a cent of drift is a cent charged too
    much or too little."""
    base, dossier = application
    commande = _order(base, alice, "arrondi")
    _line(base, alice, commande, _id_article(dossier, PRIX_A), QTE_A)
    _line(base, alice, commande, _id_article(dossier, PRIX_B), QTE_B)
    total = _total(base, alice, commande)
    # These quantities drift: the raw sum is 101.19999999999999. The test would
    # prove nothing with values that fall right.
    brute = round(PRIX_A * QTE_A, 2) + round(PRIX_B * QTE_B, 2)
    assert brute != round(brute, 2), (
        "the bench prices no longer drift: this test becomes tautological")
    assert total == round(brute, 2), f"total non arrondi : {total!r}"


# --------------------------------------------------------------------------
# Composition with brick 11: a third party's total
# --------------------------------------------------------------------------

def test_someone_elses_total_does_not_move(application, alice, bob):
    """Brick 11's 403 is not enough to assert it: we must check that NOTHING was
    recalculated on the targeted order."""
    base, dossier = application
    commande = _order(base, alice, "privée")
    _line(base, alice, commande, _id_article(dossier, PRIX_A), 1)
    avant = _total(base, alice, commande)

    refuse = _line(base, bob, commande, _id_article(dossier, PRIX_B), 100)
    assert refuse.status_code == 403, refuse.text
    assert _total(base, alice, commande) == pytest.approx(avant)


# --------------------------------------------------------------------------
# What is really charged
# --------------------------------------------------------------------------

def test_the_charged_amount_is_the_cart_sum(application, alice, faux_stripe):
    """The statement that counts for a shop. It is about what the PROVIDER
    receives, decoded from its request body — not about what the database holds,
    nor what monl believes it sends.

    It is also the proof that the full chain holds: brick 10 calculates each
    line, brick 11 attaches and protects it, brick 12 sums them, brick 9 charges
    the result."""
    base, dossier = application
    commande = _order(base, alice, "à régler")
    _line(base, alice, commande, _id_article(dossier, PRIX_A), 2)
    _line(base, alice, commande, _id_article(dossier, PRIX_B), 3)
    attendu_centimes = str(round(round(PRIX_A * 2 + PRIX_B * 3, 2) * 100))

    avant = len(faux_stripe.recu)
    reglement = requests.post(f"{base}/commande/{commande}/paiement",
                              headers=alice)
    assert reglement.status_code == 200, reglement.text
    assert len(faux_stripe.recu) == avant + 1, "no call to the provider"

    demande = faux_stripe.recu[avant]
    assert demande["champs"][
        "line_items[0][price_data][unit_amount]"] == attendu_centimes, (
        f"wrong charged amount: {demande['champs']}")
    # The reference stays qualified by the entity (point 75).
    assert demande["champs"]["client_reference_id"] == f"Commande:{commande}"


def test_the_charged_amount_follows_a_removed_line(application, alice, faux_stripe):
    """The case that tells "recalculated" from "calculated once": a returned item
    must not be charged before payment."""
    base, dossier = application
    commande = _order(base, alice, "panier corrigé")
    ligne_a = _line(base, alice, commande, _id_article(dossier, PRIX_A),
                     4).json()["id"]
    _line(base, alice, commande, _id_article(dossier, PRIX_B), 1)
    requests.delete(f"{base}/ligne/{ligne_a}", headers=alice)

    avant = len(faux_stripe.recu)
    assert requests.post(f"{base}/commande/{commande}/paiement",
                         headers=alice).status_code == 200
    assert faux_stripe.recu[avant]["champs"][
        "line_items[0][price_data][unit_amount]"] == str(round(PRIX_B * 100))
