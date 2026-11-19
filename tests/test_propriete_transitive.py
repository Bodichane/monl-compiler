"""Brick 11 (transitive ownership) tested against a real server — point 81.

Why this file exists. A multi-item cart needs an "order line" entity, and a
line belongs to nobody directly: it belongs to whoever owns its order. Until
point 80, `ownedBy` could only designate an ACTOR; naming an entity compiled
silently and produced a false attachment — the calling account's id written
instead of the requested order.

What these tests require, and what a review does not prove:

* the stored foreign key is indeed the designated ORDER, never the calling
  account's id (point 80's exact defect, which compiled without a word);
* attaching a line to someone else's order is refused — without this check,
  the brick would open a wider hole than the one it closes, since the foreign
  key is no longer deduced from the token but provided by the client;
* the four read/write paths filter by the JOIN (list, detail, update,
  delete), not by a column comparison;
* the composition with `derivedFrom` holds: the line amount stays calculated
  by the server.

The identifiers are deliberately DIVERGENT (several orders created before
those used for the assertions): the probe's first try had shown nothing
because "user 1" and "order 1" coincided, and a wrong comparison looked
right.
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

SPEC = """app BancTransitif

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Admin
actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client

# The brick: a line belongs to whoever owns its order.
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite

workflow GererArticle for Admin
    Create Article
    Read Article

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
PRICE_CHER, PRICE_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base_spec(folder):
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


@pytest.fixture(scope="module")
def alice(application):
    headers = _headers(application, "alice")
    # Three orders before any assertion: order ids thus stop coinciding with
    # account ids. Without this gap, a comparison confusing "order id" and
    # "account id" looks right — that is precisely what hid point 80's defect.
    base, _ = application
    for label in ("brouillon", "abandonnée", "en cours"):
        _order(base, headers, label)
    return headers


@pytest.fixture(scope="module")
def bob(application):
    return _headers(application, "bob")


def _id_article(folder, price):
    with _base_spec(folder) as conn:
        return conn.execute('SELECT id FROM article WHERE prix = ?',
                           (price,)).fetchone()[0]


def _order(base, headers, label):
    response = requests.post(f"{base}/commande", headers=headers,
                            json={"libelle": label})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _line(base, headers, order_id, article_id, quantity):
    return requests.post(f"{base}/ligne", headers=headers,
                         json={"commande_id": order_id,
                               "article_id": article_id,
                               "quantite": quantity})


def _account_id(folder, identifier):
    with _base_spec(folder) as conn:
        return conn.execute("SELECT id FROM _monl_users WHERE username = ?",
                           (identifier,)).fetchone()[0]


# --------------------------------------------------------------------------
# What the brick must produce in the input contract
# --------------------------------------------------------------------------

def test_the_client_designates_the_order_in_the_body(application):
    """The owning parent's foreign key is PROVIDED by the client.

    It is the brick's reversal: in direct ownership, this column is deduced from
    the token and does not appear in the schema. Here, without it, the client
    could attach its line to no order."""
    base, _ = application
    schema = requests.get(f"{base}/openapi.json").json()
    fields = schema["components"]["schemas"]["LigneSchema"]["properties"]
    assert "commande_id" in fields
    assert "article_id" in fields
    # Composition with brick 10: the amount stays calculated by the server.
    assert "sousTotal" not in fields


# --------------------------------------------------------------------------
# Point 80's defect, as a non-regression test
# --------------------------------------------------------------------------

def test_the_stored_order_is_the_one_requested(application, alice):
    """Point 80's exact defect: the requested attachment was ignored and
    replaced with the calling account's id, silently."""
    base, folder = application
    order = _order(base, alice, "panier réel")
    article = _id_article(folder, PRICE_CHER)
    response = _line(base, alice, order, article, 2)
    assert response.status_code in (200, 201), response.text
    line_id = response.json()["id"]

    with _base_spec(folder) as conn:
        stored = conn.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (line_id,)).fetchone()[0]
    account = _account_id(folder, "alice")
    assert stored == order, "the designated order was not recorded"
    # The assertion that counts: the two values DIVERGE, so the equality above
    # cannot be chance.
    assert order != account, "ids conflated: the test proves nothing"
    assert stored != account


def test_the_line_amount_is_calculated_by_the_server(application, alice):
    """Brick 10 + brick 11 composition: nine bricks tested one by one do not test
    their pairs (point 78's lesson)."""
    base, folder = application
    order = _order(base, alice, "calcul")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order, article, 3).json()["id"]
    detail = requests.get(f"{base}/ligne/{line_id}", headers=alice).json()
    assert detail["data"]["sousTotal"] == pytest.approx(PRICE_CHER * 3)


# --------------------------------------------------------------------------
# Writing: attaching a line to someone else's order
# --------------------------------------------------------------------------

def test_attaching_a_line_to_someone_elses_order_is_refused(application, alice, bob):
    """Without this check, the brick would open a wider hole than the one it
    closes: the foreign key is no longer deduced from the token."""
    base, folder = application
    order_alice = _order(base, alice, "privée")
    article = _id_article(folder, PRICE_CHER)
    response = _line(base, bob, order_alice, article, 1)
    assert response.status_code == 403, response.text

    with _base_spec(folder) as conn:
        account = conn.execute(
            'SELECT COUNT(*) FROM ligne WHERE commande_id = ?',
            (order_alice,)).fetchone()[0]
    assert account == 0, "the line was written despite the refusal"


def test_a_nonexistent_order_gives_the_same_answer(application, bob):
    """Telling "does not exist" from "not yours" would allow enumerating others'
    orders — same reason as the detail read's 404."""
    base, folder = application
    article = _id_article(folder, PRICE_CHER)
    response = _line(base, bob, 99999, article, 1)
    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------
# Reading: does the join really filter?
# --------------------------------------------------------------------------

def test_the_list_only_shows_ones_own_lines(application, alice, bob):
    base, folder = application
    article = _id_article(folder, PRICE_CHER)
    order_alice = _order(base, alice, "liste alice")
    line_alice = _line(base, alice, order_alice, article, 1).json()["id"]
    order_bob = _order(base, bob, "liste bob")
    line_bob = _line(base, bob, order_bob, article, 1).json()["id"]

    views_bob = [line["id"] for line
                in requests.get(f"{base}/ligne", headers=bob).json()["data"]]
    assert line_bob in views_bob
    assert line_alice not in views_bob

    views_alice = [line["id"] for line
                  in requests.get(f"{base}/ligne", headers=alice).json()["data"]]
    assert line_alice in views_alice
    assert line_bob not in views_alice


def test_the_detail_of_someone_elses_line_is_indistinguishable_from_absence(
        application, alice, bob):
    base, folder = application
    order = _order(base, alice, "détail")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order, article, 1).json()["id"]

    assert requests.get(f"{base}/ligne/{line_id}",
                        headers=alice).status_code == 200
    refuse = requests.get(f"{base}/ligne/{line_id}", headers=bob)
    assert refuse.status_code == 404, refuse.text


# --------------------------------------------------------------------------
# Modification et suppression
# --------------------------------------------------------------------------

def test_updating_someone_elses_line_is_refused(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "put")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order, article, 1).json()["id"]

    refuse = requests.put(f"{base}/ligne/{line_id}", headers=bob,
                          json={"quantite": 50, "commande_id": order,
                                "article_id": article})
    assert refuse.status_code == 403, refuse.text
    with _base_spec(folder) as conn:
        quantity = conn.execute('SELECT quantite FROM ligne WHERE id = ?',
                               (line_id,)).fetchone()[0]
    assert quantity == 1, "the line was modified despite the refusal"


def test_deleting_someone_elses_line_is_refused(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "delete")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order, article, 1).json()["id"]

    refuse = requests.delete(f"{base}/ligne/{line_id}", headers=bob)
    assert refuse.status_code == 403, refuse.text
    with _base_spec(folder) as conn:
        reste = conn.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (line_id,)).fetchone()[0]
    assert reste == 1, "the line was deleted despite the refusal"


def test_the_owner_updates_and_deletes_their_own_line(application, alice):
    """The indispensable counterpart of the three refusals above: a brick
    refusing everyone would pass these tests while allowing nothing."""
    base, folder = application
    order = _order(base, alice, "à moi")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order, article, 1).json()["id"]

    modified = requests.put(f"{base}/ligne/{line_id}", headers=alice,
                           json={"quantite": 4, "commande_id": order,
                                 "article_id": article})
    assert modified.status_code == 200, modified.text
    detail = requests.get(f"{base}/ligne/{line_id}", headers=alice).json()
    assert detail["data"]["quantite"] == 4
    # The amount follows the quantity: otherwise point 77's flaw would simply
    # move from the amount to the quantity.
    assert detail["data"]["sousTotal"] == pytest.approx(PRICE_CHER * 4)

    assert requests.delete(f"{base}/ligne/{line_id}",
                           headers=alice).status_code == 200
    with _base_spec(folder) as conn:
        reste = conn.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (line_id,)).fetchone()[0]
    assert reste == 0


def test_moving_ones_line_to_someone_elses_order_is_impossible(
        application, alice, bob):
    """monl's Update route does not write foreign keys. This test pins that
    behavior: if it changed, a client could drop a line into a third party's cart
    through an update."""
    base, folder = application
    order_bob = _order(base, bob, "cible")
    order_alice = _order(base, alice, "source")
    article = _id_article(folder, PRICE_CHER)
    line_id = _line(base, alice, order_alice, article, 1).json()["id"]

    requests.put(f"{base}/ligne/{line_id}", headers=alice,
                 json={"quantite": 2, "commande_id": order_bob,
                       "article_id": article})
    with _base_spec(folder) as conn:
        stored = conn.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (line_id,)).fetchone()[0]
    assert stored == order_alice
    assert requests.get(f"{base}/ligne/{line_id}",
                        headers=bob).status_code == 404
