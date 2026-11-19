"""Brick 10 (`derivedFrom`) tested against a real server — point 77.

Why this file exists. `payable` (point 74) promises that the charged amount
comes from the DATABASE and never from the request body. True, and it
protected nothing: nobody had asked **who writes the amount into the
database**. The answer was the client, through two paths — creation, and
update (the owner may `PUT`). Two three-request exploits, which none of the
24 tests of `test_payment.py` covered: they checked that the ROUTE ignores
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

PASSWORD = "motdepasse123"
PRICE_CHER, PRICE_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base_spec(folder):
    # As in test_brick_behavior.py: `with connect(...)` commits the
    # transaction but does not CLOSE — hence the test bench's ResourceWarnings.
    conn = sqlite3.connect(os.path.join(folder, "app.db"))
    try:
        with conn:
            yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        with uvicorn_server(folder) as base:
            # Two items with different prices: the neighboring witness is what
            # lets us state the right one was read (point 70's lesson, where a
            # counter decremented the wrong record).
            with _base_spec(folder) as conn:
                conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article cher", PRICE_CHER))
                conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article bon marché", PRICE_BON_MARCHE))
            yield base, folder


def _empty_quota(folder):
    with _base_spec(folder) as conn:
        conn.execute("DELETE FROM _monl_rate_limit")


def _headers(application, identifier):
    base, folder = application
    _empty_quota(folder)
    requests.post(f"{base}/register",
                  json={"username": identifier, "password": PASSWORD,
                        "actor": "Client"})
    token = requests.post(f"{base}/login",
                          json={"username": identifier,
                                "password": PASSWORD}).json()
    assert "access_token" in token, token
    return {"Authorization": "Bearer " + token["access_token"]}


def _id_article_cher(folder):
    with _base_spec(folder) as conn:
        return conn.execute('SELECT id FROM article WHERE prix = ?',
                           (PRICE_CHER,)).fetchone()[0]


def _id_article_bon_marche(folder):
    with _base_spec(folder) as conn:
        return conn.execute('SELECT id FROM article WHERE prix = ?',
                           (PRICE_BON_MARCHE,)).fetchone()[0]


def _order(base, headers, body):
    response = requests.post(f"{base}/commande", headers=headers, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _read(base, headers, identifier):
    detail = requests.get(f"{base}/commande/{identifier}",
                          headers=headers).json()
    return detail.get("data", detail)


# --------------------------------------------------- the field is not there --

def test_the_calculated_field_is_missing_from_the_input_schema(application):
    """The brick's contract starts here: the client cannot even TRY to provide
    the amount. It is the same mechanism as `generated` (brick 7), and the
    Pydantic schema is shared between creation and update — that is what closes
    both paths at once."""
    base, _folder = application
    schema = requests.get(f"{base}/openapi.json").json()
    fields = schema["components"]["schemas"]["CommandeSchema"]["properties"]
    assert "total" not in fields, fields
    # The multiplier and the item reference do come from the client.
    assert "quantite" in fields and "article_id" in fields


# ----------------------------------------------------------------- creation --

def test_the_total_sent_on_creation_is_ignored(application):
    """The original exploit, replayed: 5 items at €189 ordered while declaring a
    total of 1 cent. Before the brick, the database kept 0.01 and `payable`
    charged one cent for €945 of goods."""
    base, folder = application
    headers = _headers(application, "cree_ignore")
    identifier = _order(base, headers, {
        "quantite": 5, "article_id": _id_article_cher(folder),
        "libelle": "5x cher", "total": 0.01})
    assert _read(base, headers, identifier)["total"] == PRICE_CHER * 5


def test_the_total_is_calculated_on_the_right_item(application):
    """The neighboring witness: two items with different prices exist, and the
    one the client designated must be read. A foreign key defect would give a
    plausible but wrong amount — exactly the bug CLAUDE.md cites as invisible on
    reading."""
    base, folder = application
    headers = _headers(application, "cree_bon_article")
    identifier = _order(base, headers, {
        "quantite": 2, "article_id": _id_article_bon_marche(folder),
        "libelle": "2x bon marché"})
    assert _read(base, headers, identifier)["total"] == PRICE_BON_MARCHE * 2


def test_a_zero_or_negative_quantity_is_refused(application):
    """A zero amount is not chargeable (`payable` already refuses it with 400);
    refusing it here avoids writing to the database an order that can never be
    settled. A negative quantity would produce a negative amount."""
    base, folder = application
    headers = _headers(application, "quantite_nulle")
    article = _id_article_cher(folder)
    for quantity in (0, -3):
        response = requests.post(f"{base}/commande", headers=headers, json={
            "quantite": quantity, "article_id": article, "libelle": "vide"})
        assert response.status_code == 400, (quantity, response.text)


def test_a_nonexistent_item_gives_409_and_creates_nothing(application):
    """The 409 is better than a wrong amount: a bogus reference must stop the
    order, not create it at zero euros — hence free."""
    base, folder = application
    headers = _headers(application, "article_absent")
    with _base_spec(folder) as conn:
        before = conn.execute("SELECT COUNT(*) FROM commande").fetchone()[0]
    response = requests.post(f"{base}/commande", headers=headers, json={
        "quantite": 1, "article_id": 999999, "libelle": "fantôme"})
    assert response.status_code == 409, response.text
    with _base_spec(folder) as conn:
        assert conn.execute("SELECT COUNT(*) FROM commande").fetchone()[0] == before


# ------------------------------------------------------------------- update --

def test_the_total_sent_on_update_is_ignored(application):
    """The SECOND exploit, the one fixing creation alone would have left whole:
    an honest order, then a `PUT` rewriting the amount. `ownedBy` does give the
    owner that right — that is its role — so the protection cannot come from
    access control."""
    base, folder = application
    headers = _headers(application, "put_ignore")
    article = _id_article_cher(folder)
    identifier = _order(base, headers, {
        "quantite": 1, "article_id": article, "libelle": "1x cher"})
    assert _read(base, headers, identifier)["total"] == PRICE_CHER

    response = requests.put(f"{base}/commande/{identifier}", headers=headers,
                           json={"quantite": 1, "article_id": article,
                                 "libelle": "1x cher", "total": 0.01})
    assert response.status_code == 200, response.text
    assert _read(base, headers, identifier)["total"] == PRICE_CHER


def test_the_total_follows_the_updated_quantity(application):
    """Without recalculation on `PUT`, the flaw would move from the amount to the
    quantity: creating at 1 then updating to 5 would give five items for the
    price of one. The amount must therefore FOLLOW, in both directions."""
    base, folder = application
    headers = _headers(application, "put_quantite")
    article = _id_article_cher(folder)
    identifier = _order(base, headers, {
        "quantite": 1, "article_id": article, "libelle": "1x"})

    for quantity in (5, 2):
        response = requests.put(f"{base}/commande/{identifier}", headers=headers,
                               json={"quantite": quantity, "article_id": article,
                                     "libelle": f"{quantity}x"})
        assert response.status_code == 200, response.text
        assert _read(base, headers, identifier)["total"] == PRICE_CHER * quantity


def test_declaring_another_item_on_put_does_not_lower_the_total(application):
    """The defect found by testing the brick, and the only one review had let
    through. monl's `Update` route does NOT write foreign key columns: the FK in
    the database therefore stays the only truth about "which item". An
    intermediate version calculated from `data.article_id` — a client was then
    charged €89 for an item priced €189 by declaring a cheap item it did not
    point to."""
    base, folder = application
    headers = _headers(application, "put_autre_article")
    cher, bon_marche = _id_article_cher(folder), _id_article_bon_marche(folder)
    identifier = _order(base, headers, {
        "quantite": 1, "article_id": cher, "libelle": "1x cher"})

    response = requests.put(f"{base}/commande/{identifier}", headers=headers,
                           json={"quantite": 1, "article_id": bon_marche,
                                 "libelle": "1x cher"})
    assert response.status_code == 200, response.text
    line = _read(base, headers, identifier)
    assert line["total"] == PRICE_CHER, (
        "the amount followed the DECLARED item instead of the stored item")
    assert line["article_id"] == cher


# ------------------------------------- what the brick gives back to payable --

def test_the_charged_amount_is_now_the_catalogs(application):
    """The loop is closed: `payable` rereads from the database an amount the
    client could never write. Without a Stripe key the route answers 503 (point
    74), so it is the value IN THE DATABASE that is checked — the one the route
    would reread."""
    base, folder = application
    headers = _headers(application, "encaisse")
    identifier = _order(base, headers, {
        "quantite": 3, "article_id": _id_article_cher(folder),
        "libelle": "3x cher", "total": 0.01})
    with _base_spec(folder) as conn:
        in_base = conn.execute('SELECT total, payment_status FROM commande '
                              'WHERE id = ?', (identifier,)).fetchone()
    assert in_base[0] == PRICE_CHER * 3
    assert in_base[1] == "en_attente"
    # And the payment route does exist, without a configured key: 503.
    response = requests.post(f"{base}/commande/{identifier}/paiement",
                            headers=headers)
    assert response.status_code == 503, response.text
    assert "STRIPE_SECRET_KEY" in response.text
