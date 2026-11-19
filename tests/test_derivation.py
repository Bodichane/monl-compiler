"""Brick 10 (`derivedFrom`) tested against a real server — point 77.

Why this file exists. `payable` (point 74) promises that the charged amount
comes from the DATABASE and never from the request body. True, and it
protected nothing: nobody had asked **who writes the amount into the
database**. The answer was the client, through two paths — creation, and
update (the owner may `PUT`). Two three-request exploits, which none of the
24 tests of `test_paiement.py` covered: they checked that the ROUTE ignores
the body it is given, without ever going back to the source of the value it
rereads.

What these tests require, and what a review does not prove:

* the amount sent by the client is **ignored**, on creation as on update (the
  field does not exist in the Pydantic schema);
* the amount **follows** the quantity: without recalculation on `PUT`, the
  flaw would simply move from the amount to the quantity (create at 1, update
  to 5);
* the amount is calculated on the **stored** linked row, never on the one the
  body declares. Both directions were tried: calculating from `data.<fk>` let
  a client be charged €89 for an item priced €189 by declaring a cheap item it
  did not point to. It is the only defect of the brick that execution found
  and review had let through.
"""
import contextlib
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app BancDerivation

entity Article
    nom: String
    prix: Money

entity Commande
    quantite: Integer
    total: Money
    libelle: String

entity Client
    displayName: String

relation Client hasMany Commande
relation Article hasMany Commande
relation Client hasMany Client

actor Admin
actor Client selfRegister

rule Commande.quantite required
rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client

rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total payable

workflow GererArticle for Admin
    Create Article
    Read Article
    Update Article

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande

workflow Profil for Client
    Create Client
    Read Client
"""

MOT_DE_PASSE = "motdepasse123"
PRIX_CHER, PRIX_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base_spec(dossier):
    # As in test_briques_comportement.py: `with connect(...)` commits the
    # transaction but does not CLOSE — hence the test bench's ResourceWarnings.
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            # Two items with different prices: the neighboring witness is what
            # lets us state the right one was read (point 70's lesson, where a
            # counter decremented the wrong record).
            with _base_spec(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article cher", PRIX_CHER))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article bon marché", PRIX_BON_MARCHE))
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


def _id_article_cher(dossier):
    with _base_spec(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (PRIX_CHER,)).fetchone()[0]


def _id_article_bon_marche(dossier):
    with _base_spec(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (PRIX_BON_MARCHE,)).fetchone()[0]


def _order(base, entetes, corps):
    reponse = requests.post(f"{base}/commande", headers=entetes, json=corps)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _read(base, entetes, identifiant):
    detail = requests.get(f"{base}/commande/{identifiant}",
                          headers=entetes).json()
    return detail.get("data", detail)


# --------------------------------------------------- the field is not there --

def test_the_calculated_field_is_absent_from_the_input_schema(application):
    """The brick's contract starts here: the client cannot even TRY to provide
    the amount. It is the same mechanism as `generated` (brick 7), and the
    Pydantic schema is shared between creation and update — that is what closes
    both paths at once."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()
    champs = schema["components"]["schemas"]["CommandeSchema"]["properties"]
    assert "total" not in champs, champs
    # The multiplier and the item reference do come from the client.
    assert "quantite" in champs and "article_id" in champs


# ----------------------------------------------------------------- creation --

def test_the_total_sent_on_creation_is_ignored(application):
    """The original exploit, replayed: 5 items at €189 ordered while declaring a
    total of 1 cent. Before the brick, the database kept 0.01 and `payable`
    charged one cent for €945 of goods."""
    base, dossier = application
    entetes = _entetes(application, "cree_ignore")
    identifiant = _order(base, entetes, {
        "quantite": 5, "article_id": _id_article_cher(dossier),
        "libelle": "5x cher", "total": 0.01})
    assert _read(base, entetes, identifiant)["total"] == PRIX_CHER * 5


def test_the_total_is_calculated_on_the_right_item(application):
    """The neighboring witness: two items with different prices exist, and the
    one the client designated must be read. A foreign key defect would give a
    plausible but wrong amount — exactly the bug CLAUDE.md cites as invisible on
    reading."""
    base, dossier = application
    entetes = _entetes(application, "cree_bon_article")
    identifiant = _order(base, entetes, {
        "quantite": 2, "article_id": _id_article_bon_marche(dossier),
        "libelle": "2x bon marché"})
    assert _read(base, entetes, identifiant)["total"] == PRIX_BON_MARCHE * 2


def test_a_zero_or_negative_quantity_is_refused(application):
    """A zero amount is not chargeable (`payable` already refuses it with 400);
    refusing it here avoids writing to the database an order that can never be
    settled. A negative quantity would produce a negative amount."""
    base, dossier = application
    entetes = _entetes(application, "quantite_nulle")
    article = _id_article_cher(dossier)
    for quantite in (0, -3):
        reponse = requests.post(f"{base}/commande", headers=entetes, json={
            "quantite": quantite, "article_id": article, "libelle": "vide"})
        assert reponse.status_code == 400, (quantite, reponse.text)


def test_a_nonexistent_item_gives_409_and_creates_nothing(application):
    """The 409 is better than a wrong amount: a bogus reference must stop the
    order, not create it at zero euros — hence free."""
    base, dossier = application
    entetes = _entetes(application, "article_absent")
    with _base_spec(dossier) as cnx:
        avant = cnx.execute("SELECT COUNT(*) FROM commande").fetchone()[0]
    reponse = requests.post(f"{base}/commande", headers=entetes, json={
        "quantite": 1, "article_id": 999999, "libelle": "fantôme"})
    assert reponse.status_code == 409, reponse.text
    with _base_spec(dossier) as cnx:
        assert cnx.execute("SELECT COUNT(*) FROM commande").fetchone()[0] == avant


# ------------------------------------------------------------------- update --

def test_the_total_sent_on_update_is_ignored(application):
    """The SECOND exploit, the one fixing creation alone would have left whole:
    an honest order, then a `PUT` rewriting the amount. `ownedBy` does give the
    owner that right — that is its role — so the protection cannot come from
    access control."""
    base, dossier = application
    entetes = _entetes(application, "put_ignore")
    article = _id_article_cher(dossier)
    identifiant = _order(base, entetes, {
        "quantite": 1, "article_id": article, "libelle": "1x cher"})
    assert _read(base, entetes, identifiant)["total"] == PRIX_CHER

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                           json={"quantite": 1, "article_id": article,
                                 "libelle": "1x cher", "total": 0.01})
    assert reponse.status_code == 200, reponse.text
    assert _read(base, entetes, identifiant)["total"] == PRIX_CHER


def test_the_total_follows_the_updated_quantity(application):
    """Without recalculation on `PUT`, the flaw would move from the amount to the
    quantity: creating at 1 then updating to 5 would give five items for the
    price of one. The amount must therefore FOLLOW, in both directions."""
    base, dossier = application
    entetes = _entetes(application, "put_quantite")
    article = _id_article_cher(dossier)
    identifiant = _order(base, entetes, {
        "quantite": 1, "article_id": article, "libelle": "1x"})

    for quantite in (5, 2):
        reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                               json={"quantite": quantite, "article_id": article,
                                     "libelle": f"{quantite}x"})
        assert reponse.status_code == 200, reponse.text
        assert _read(base, entetes, identifiant)["total"] == PRIX_CHER * quantite


def test_declaring_another_item_on_put_does_not_lower_the_total(application):
    """The defect found by testing the brick, and the only one review had let
    through. monl's `Update` route does NOT write foreign key columns: the FK in
    the database therefore stays the only truth about "which item". An
    intermediate version calculated from `data.article_id` — a client was then
    charged €89 for an item priced €189 by declaring a cheap item it did not
    point to."""
    base, dossier = application
    entetes = _entetes(application, "put_autre_article")
    cher, bon_marche = _id_article_cher(dossier), _id_article_bon_marche(dossier)
    identifiant = _order(base, entetes, {
        "quantite": 1, "article_id": cher, "libelle": "1x cher"})

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                           json={"quantite": 1, "article_id": bon_marche,
                                 "libelle": "1x cher"})
    assert reponse.status_code == 200, reponse.text
    ligne = _read(base, entetes, identifiant)
    assert ligne["total"] == PRIX_CHER, (
        "the amount followed the DECLARED item instead of the stored item")
    assert ligne["article_id"] == cher


# ------------------------------------- what the brick gives back to payable --

def test_the_charged_amount_is_now_the_catalogs(application):
    """The loop is closed: `payable` rereads from the database an amount the
    client could never write. Without a Stripe key the route answers 503 (point
    74), so it is the value IN THE DATABASE that is checked — the one the route
    would reread."""
    base, dossier = application
    entetes = _entetes(application, "encaisse")
    identifiant = _order(base, entetes, {
        "quantite": 3, "article_id": _id_article_cher(dossier),
        "libelle": "3x cher", "total": 0.01})
    with _base_spec(dossier) as cnx:
        en_base = cnx.execute('SELECT total, payment_status FROM commande '
                              'WHERE id = ?', (identifiant,)).fetchone()
    assert en_base[0] == PRIX_CHER * 3
    assert en_base[1] == "en_attente"
    # And the payment route does exist, without a configured key: 503.
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes)
    assert reponse.status_code == 503, reponse.text
    assert "STRIPE_SECRET_KEY" in reponse.text
