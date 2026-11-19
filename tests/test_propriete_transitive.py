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

MOT_DE_PASSE = "motdepasse123"
PRIX_CHER, PRIX_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base_spec(dossier):
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


@pytest.fixture(scope="module")
def alice(application):
    entetes = _entetes(application, "alice")
    # Three orders before any assertion: order ids thus stop coinciding with
    # account ids. Without this gap, a comparison confusing "order id" and
    # "account id" looks right — that is precisely what hid point 80's defect.
    base, _ = application
    for libelle in ("brouillon", "abandonnée", "en cours"):
        _order(base, entetes, libelle)
    return entetes


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


def _account_id(dossier, identifiant):
    with _base_spec(dossier) as cnx:
        return cnx.execute("SELECT id FROM _monl_users WHERE username = ?",
                           (identifiant,)).fetchone()[0]


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
    champs = schema["components"]["schemas"]["LigneSchema"]["properties"]
    assert "commande_id" in champs
    assert "article_id" in champs
    # Composition with brick 10: the amount stays calculated by the server.
    assert "sousTotal" not in champs


# --------------------------------------------------------------------------
# Point 80's defect, as a non-regression test
# --------------------------------------------------------------------------

def test_the_stored_order_is_the_one_requested(application, alice):
    """Point 80's exact defect: the requested attachment was ignored and
    replaced with the calling account's id, silently."""
    base, dossier = application
    commande = _order(base, alice, "panier réel")
    article = _id_article(dossier, PRIX_CHER)
    reponse = _line(base, alice, commande, article, 2)
    assert reponse.status_code in (200, 201), reponse.text
    ligne_id = reponse.json()["id"]

    with _base_spec(dossier) as cnx:
        stocke = cnx.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (ligne_id,)).fetchone()[0]
    compte = _account_id(dossier, "alice")
    assert stocke == commande, "la commande désignée n'a pas été enregistrée"
    # The assertion that counts: the two values DIVERGE, so the equality above
    # cannot be chance.
    assert commande != compte, "identifiants confondus : le test ne prouve rien"
    assert stocke != compte


def test_the_line_amount_is_calculated_by_the_server(application, alice):
    """Brick 10 + brick 11 composition: nine bricks tested one by one do not test
    their pairs (point 78's lesson)."""
    base, dossier = application
    commande = _order(base, alice, "calcul")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande, article, 3).json()["id"]
    detail = requests.get(f"{base}/ligne/{ligne_id}", headers=alice).json()
    assert detail["data"]["sousTotal"] == pytest.approx(PRIX_CHER * 3)


# --------------------------------------------------------------------------
# Writing: attaching a line to someone else's order
# --------------------------------------------------------------------------

def test_attaching_a_line_to_someone_elses_order_is_refused(application, alice, bob):
    """Without this check, the brick would open a wider hole than the one it
    closes: the foreign key is no longer deduced from the token."""
    base, dossier = application
    commande_alice = _order(base, alice, "privée")
    article = _id_article(dossier, PRIX_CHER)
    reponse = _line(base, bob, commande_alice, article, 1)
    assert reponse.status_code == 403, reponse.text

    with _base_spec(dossier) as cnx:
        compte = cnx.execute(
            'SELECT COUNT(*) FROM ligne WHERE commande_id = ?',
            (commande_alice,)).fetchone()[0]
    assert compte == 0, "la ligne a été écrite malgré le refus"


def test_a_nonexistent_order_gives_the_same_answer(application, bob):
    """Telling "does not exist" from "not yours" would allow enumerating others'
    orders — same reason as the detail read's 404."""
    base, dossier = application
    article = _id_article(dossier, PRIX_CHER)
    reponse = _line(base, bob, 99999, article, 1)
    assert reponse.status_code == 403, reponse.text


# --------------------------------------------------------------------------
# Reading: does the join really filter?
# --------------------------------------------------------------------------

def test_the_list_only_shows_ones_own_lines(application, alice, bob):
    base, dossier = application
    article = _id_article(dossier, PRIX_CHER)
    commande_alice = _order(base, alice, "liste alice")
    ligne_alice = _line(base, alice, commande_alice, article, 1).json()["id"]
    commande_bob = _order(base, bob, "liste bob")
    ligne_bob = _line(base, bob, commande_bob, article, 1).json()["id"]

    vues_bob = [ligne["id"] for ligne
                in requests.get(f"{base}/ligne", headers=bob).json()["data"]]
    assert ligne_bob in vues_bob
    assert ligne_alice not in vues_bob

    vues_alice = [ligne["id"] for ligne
                  in requests.get(f"{base}/ligne", headers=alice).json()["data"]]
    assert ligne_alice in vues_alice
    assert ligne_bob not in vues_alice


def test_the_detail_of_someone_elses_line_is_indistinguishable_from_absence(
        application, alice, bob):
    base, dossier = application
    commande = _order(base, alice, "détail")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande, article, 1).json()["id"]

    assert requests.get(f"{base}/ligne/{ligne_id}",
                        headers=alice).status_code == 200
    refuse = requests.get(f"{base}/ligne/{ligne_id}", headers=bob)
    assert refuse.status_code == 404, refuse.text


# --------------------------------------------------------------------------
# Modification et suppression
# --------------------------------------------------------------------------

def test_updating_someone_elses_line_is_refused(application, alice, bob):
    base, dossier = application
    commande = _order(base, alice, "put")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande, article, 1).json()["id"]

    refuse = requests.put(f"{base}/ligne/{ligne_id}", headers=bob,
                          json={"quantite": 50, "commande_id": commande,
                                "article_id": article})
    assert refuse.status_code == 403, refuse.text
    with _base_spec(dossier) as cnx:
        quantite = cnx.execute('SELECT quantite FROM ligne WHERE id = ?',
                               (ligne_id,)).fetchone()[0]
    assert quantite == 1, "la ligne a été modifiée malgré le refus"


def test_deleting_someone_elses_line_is_refused(application, alice, bob):
    base, dossier = application
    commande = _order(base, alice, "delete")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande, article, 1).json()["id"]

    refuse = requests.delete(f"{base}/ligne/{ligne_id}", headers=bob)
    assert refuse.status_code == 403, refuse.text
    with _base_spec(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 1, "la ligne a été supprimée malgré le refus"


def test_the_owner_updates_and_deletes_their_own_line(application, alice):
    """The indispensable counterpart of the three refusals above: a brick
    refusing everyone would pass these tests while allowing nothing."""
    base, dossier = application
    commande = _order(base, alice, "à moi")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande, article, 1).json()["id"]

    modifie = requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                           json={"quantite": 4, "commande_id": commande,
                                 "article_id": article})
    assert modifie.status_code == 200, modifie.text
    detail = requests.get(f"{base}/ligne/{ligne_id}", headers=alice).json()
    assert detail["data"]["quantite"] == 4
    # The amount follows the quantity: otherwise point 77's flaw would simply
    # move from the amount to the quantity.
    assert detail["data"]["sousTotal"] == pytest.approx(PRIX_CHER * 4)

    assert requests.delete(f"{base}/ligne/{ligne_id}",
                           headers=alice).status_code == 200
    with _base_spec(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 0


def test_moving_ones_line_to_someone_elses_order_is_impossible(
        application, alice, bob):
    """monl's Update route does not write foreign keys. This test pins that
    behavior: if it changed, a client could drop a line into a third party's cart
    through an update."""
    base, dossier = application
    commande_bob = _order(base, bob, "cible")
    commande_alice = _order(base, alice, "source")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _line(base, alice, commande_alice, article, 1).json()["id"]

    requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                 json={"quantite": 2, "commande_id": commande_bob,
                       "article_id": article})
    with _base_spec(dossier) as cnx:
        stocke = cnx.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (ligne_id,)).fetchone()[0]
    assert stocke == commande_alice
    assert requests.get(f"{base}/ligne/{ligne_id}",
                        headers=bob).status_code == 404
