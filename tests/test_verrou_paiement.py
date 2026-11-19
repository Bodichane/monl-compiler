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
from tests.support.cas import check_each_case
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

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_banc_verrou"
CLE_WEBHOOK = "whsec_banc_verrou"
PRIX = 89.00
PRIX_CHER = 149.00


class _PrestataireFactice(BaseHTTPRequestHandler):
    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append(
            {c: v[0] for c, v in urllib.parse.parse_qs(brut.decode()).items()})
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
                            ("Deck", PRIX))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Halo", PRIX_CHER))
            yield base, dossier


def _entetes(application, identifiant):
    base, dossier = application
    with _base_spec(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")
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


def _article(dossier, prix):
    with _base_spec(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (prix,)).fetchone()[0]


def _order(base, entetes, libelle="panier"):
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle,
                                  "courriel": "acheteuse@exemple.fr"})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _line(base, entetes, commande_id, article_id, quantite=1):
    return requests.post(f"{base}/ligne", headers=entetes,
                         json={"commande_id": commande_id,
                               "article_id": article_id,
                               "quantite": quantite})


def _total(base, entetes, commande_id):
    return requests.get(f"{base}/commande/{commande_id}",
                        headers=entetes).json()["data"]["total"]


def _etat(dossier, commande_id):
    with _base_spec(dossier) as cnx:
        ligne = cnx.execute(
            'SELECT payment_status FROM commande WHERE id = ?',
            (commande_id,)).fetchone()
    return ligne[0] if ligne else None


def _webhook(base, commande_id, decalage=0, session="cs_test_1"):
    """Signs and posts a payment event. `decalage` in seconds serves the replay
    test: it is the only parameter that changes between a legitimate call and a
    call captured then replayed later."""
    corps = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": session,
                            "client_reference_id": f"Commande:{commande_id}"}},
    }).encode()
    horodatage = str(int(time.time()) + decalage)
    signature = hmac.new(CLE_WEBHOOK.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    return requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={horodatage},v1={signature}"},
        timeout=10)


def _settled_order(application, entetes):
    """A one-line order at €89, really sent through the payment route then the
    provider's signed webhook."""
    base, dossier = application
    identifiant = _order(base, entetes)
    assert _line(base, entetes, identifiant,
                  _article(dossier, PRIX)).status_code in (200, 201)
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes)
    assert reponse.status_code == 200, reponse.text
    assert _webhook(base, identifiant).status_code == 200
    assert _etat(dossier, identifiant) == "payee"
    return identifiant


# -------------------------------------------------------------------- the lock

def test_a_settled_order_refuses_updates(application, alice):
    base, dossier = application
    identifiant = _settled_order(application, alice)

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=alice,
                           json={"libelle": "renommée",
                                 "courriel": "acheteuse@exemple.fr"})

    assert reponse.status_code == 409, reponse.text
    assert "already paid" in reponse.json()["detail"]
    with _base_spec(dossier) as cnx:
        assert cnx.execute('SELECT libelle FROM commande WHERE id = ?',
                           (identifiant,)).fetchone()[0] == "panier"


def test_a_settled_order_refuses_deletion(application, alice):
    """Deleting erased the trace of a charge. The 409 the foreign key returned
    only held as long as a line remained: this test empties the order first,
    which is exactly the path through which it disappeared."""
    base, dossier = application
    identifiant = _settled_order(application, alice)
    lignes = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    ligne = next(li for li in lignes if li["commande_id"] == identifiant)

    retrait = requests.delete(f"{base}/ligne/{ligne['id']}", headers=alice)
    suppression = requests.delete(f"{base}/commande/{identifiant}", headers=alice)

    assert retrait.status_code == 409, retrait.text
    assert suppression.status_code == 409, suppression.text
    with _base_spec(dossier) as cnx:
        assert cnx.execute('SELECT COUNT(*) FROM commande WHERE id = ?',
                           (identifiant,)).fetchone()[0] == 1


def test_a_line_can_no_longer_be_added_to_a_settled_order(application, alice):
    """The original hole, in the direction it was exploited: €89 charged, then a
    pair at €149 added, and €238 shown still 'payee'."""
    base, dossier = application
    identifiant = _settled_order(application, alice)

    ajout = _line(base, alice, identifiant, _article(dossier, PRIX_CHER))

    assert ajout.status_code == 409, ajout.text
    # The total must not have moved by a cent: a refusal returned AFTER the
    # recalculation would warn instead of prevent.
    assert float(_total(base, alice, identifiant)) == PRIX


def test_the_quantity_of_a_settled_line_no_longer_changes(application, alice):
    base, dossier = application
    identifiant = _settled_order(application, alice)
    lignes = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    ligne = next(li for li in lignes if li["commande_id"] == identifiant)

    modif = requests.put(f"{base}/ligne/{ligne['id']}", headers=alice,
                         json={"quantite": 5, "commande_id": identifiant,
                               "article_id": ligne["article_id"]})

    assert modif.status_code == 409, modif.text
    assert float(_total(base, alice, identifiant)) == PRIX


# ----------------------------------------------------------- the counter-proof

def test_before_payment_the_five_writes_still_pass(application, alice):
    """WITHOUT this test, a lock freezing everything would make the previous
    ones pass while guaranteeing nothing — and would make the shop unusable."""
    base, dossier = application
    identifiant = _order(base, alice, "en cours")

    ajout = _line(base, alice, identifiant, _article(dossier, PRIX))
    ligne_id = ajout.json()["id"]
    modif_ligne = requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                               json={"quantite": 3, "commande_id": identifiant,
                                     "article_id": _article(dossier, PRIX)})
    total_apres_modif = float(_total(base, alice, identifiant))
    modif_commande = requests.put(f"{base}/commande/{identifiant}", headers=alice,
                                  json={"libelle": "renommée",
                                        "courriel": "acheteuse@exemple.fr"})
    retrait = requests.delete(f"{base}/ligne/{ligne_id}", headers=alice)
    suppression = requests.delete(f"{base}/commande/{identifiant}", headers=alice)

    assert ajout.status_code in (200, 201), ajout.text
    assert modif_ligne.status_code == 200, modif_ligne.text
    assert total_apres_modif == round(PRIX * 3, 2)
    assert modif_commande.status_code == 200, modif_commande.text
    assert retrait.status_code == 200, retrait.text
    assert suppression.status_code == 200, suppression.text


def test_the_lock_does_not_spill_onto_the_next_order(application, alice):
    """A settled order only freezes itself: the lock reads the line's parent,
    not "a paid order exists somewhere"."""
    base, dossier = application
    _settled_order(application, alice)
    voisine = _order(base, alice, "voisine")

    ajout = _line(base, alice, voisine, _article(dossier, PRIX))

    assert ajout.status_code in (200, 201), ajout.text
    assert float(_total(base, alice, voisine)) == PRIX


# -------------------------------------------------------------- webhook replay

def test_a_signed_but_old_webhook_is_refused(application, alice):
    """Signature freshness: the timestamp served to CHECK the signature without
    ever being dated, so a legitimate captured call stayed replayable
    indefinitely. Ten minutes are enough to show it."""
    base, dossier = application
    identifiant = _order(base, alice, "rejeu")
    _line(base, alice, identifiant, _article(dossier, PRIX))

    reponse = _webhook(base, identifiant, decalage=-600)

    assert reponse.status_code == 400, reponse.text
    assert "Expired" in reponse.json()["detail"]
    assert _etat(dossier, identifiant) == "en_attente"


def test_an_unreadable_timestamp_does_not_pass_as_fresh(application, alice):
    base, dossier = application
    identifiant = _order(base, alice, "horodatage")
    corps = json.dumps({"type": "checkout.session.completed",
                        "data": {"object": {"id": "cs_x",
                                            "client_reference_id":
                                            f"Commande:{identifiant}"}}}).encode()
    signature = hmac.new(CLE_WEBHOOK.encode(), b"jamais." + corps,
                         hashlib.sha256).hexdigest()

    reponse = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t=jamais,v1={signature}"}, timeout=10)

    assert reponse.status_code == 400, reponse.text
    assert _etat(dossier, identifiant) == "en_attente"


# ------------------------------------------------------------------- courriel

def test_the_email_type_refuses_an_address_that_is_not_one(application, alice):
    """POINT 91: the type only set a length. 'pas-un-courriel' entered the
    database with a 200 — an address no parcel goes to."""
    table = [
        "pas-un-courriel", "sans@point", "espace @exemple.fr", "@exemple.fr",
        "deux@@exemple.fr",
    ]

    def cas(adresse):
        base, _dossier = application

        reponse = requests.post(f"{base}/commande", headers=alice,
                                json={"libelle": "adresse", "courriel": adresse})

        assert reponse.status_code == 422, reponse.text

    check_each_case([(valeur,) for valeur in table], cas)


def test_a_valid_address_stays_accepted(application, alice):
    """The refusal's counter-proof: a too strict pattern would make the previous
    test pass while also rejecting real addresses."""
    table = [
        "acheteuse@exemple.fr", "prenom.nom+etiquette@sous.domaine.co.uk",
    ]

    def cas(adresse):
        base, _dossier = application

        reponse = requests.post(f"{base}/commande", headers=alice,
                                json={"libelle": "adresse", "courriel": adresse})

        assert reponse.status_code in (200, 201), reponse.text

    check_each_case([(valeur,) for valeur in table], cas)
