"""Brick 24 (transitive ownership at any depth) — point 107.

Brick 11 (point 81) could only walk ONE intermediate: a line belonged to its
order, and the order to the customer. Two levels — a line in a block of an
order — compiled filtering on the WRONG link (point 80's defect reopened
through depth), so the validator refused them.

This brick extends the chain walk up to an ACTOR, link by link, whatever the
depth. What these tests require, and what a review does not prove:

* the validator resolves a chain of 2 and 3 links up to the right actor;
* a cycle, a dead end (no account) and a link owned by several entities are
  REFUSED — point 80's defect class does not reappear through depth;
* on a real server, the 2-hop chain filters by the JOIN on all four paths
  (list, detail, update, delete) and refuses attaching to a parent that does
  not belong to the caller.

The identifiers are deliberately DIVERGENT (several orders created before
the assertions), as in brick 11.
"""

import contextlib
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server


def _validate(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


CADRE = """entity Commande
    libelle: String
entity Bloc
    note: String
entity Ligne
    quantite: Integer
relation Machin hasMany Ligne

"""

# -----------------------------------------------------------------------------
# Chain resolution — the heart of brick 24
# -----------------------------------------------------------------------------

def test_a_two_link_chain_is_resolved():
    spec = """app P2
""" + CADRE + """relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne
actor Client selfRegister
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client
rule Bloc.Read ownedBy Commande
rule Bloc.Update ownedBy Commande
rule Bloc.Delete ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc
workflow W for Client
    Create Commande
    Create Bloc
    Create Ligne
    Read Commande
    Read Bloc
    Read Ligne
    Update Commande
    Update Bloc
    Update Ligne
    Delete Commande
    Delete Bloc
    Delete Ligne
"""
    ast = _validate(spec)
    transitive = ast["security"]["transitive_ownership"]
    # La brique 11 (un saut) reste LA MÊME forme.
    assert transitive["Bloc"] == {"chain": ["Commande"], "actor": "Client"}
    # Brick 24 walks the whole depth up to the actor.
    assert transitive["Ligne"] == {"chain": ["Bloc", "Commande"], "actor": "Client"}


def test_a_three_link_chain_is_resolved():
    spec = """app P3
entity Commande
    libelle: String
entity Palette
    ref: String
entity Carton
    ref: String
entity Bloc
    note: String
entity Ligne
    quantite: Integer
relation Client hasMany Commande
relation Commande hasMany Palette
relation Palette hasMany Carton
relation Carton hasMany Bloc
relation Bloc hasMany Ligne
actor Client selfRegister
rule Commande.Read ownedBy Client
rule Palette.Read ownedBy Commande
rule Carton.Read ownedBy Palette
rule Bloc.Read ownedBy Carton
rule Ligne.Read ownedBy Bloc
workflow W for Client
    Create Commande
    Create Palette
    Create Carton
    Create Bloc
    Create Ligne
    Read Commande
    Read Palette
    Read Carton
    Read Bloc
    Read Ligne
"""
    ast = _validate(spec)
    transitive = ast["security"]["transitive_ownership"]
    assert transitive["Ligne"] == {"chain": ["Bloc", "Carton", "Palette", "Commande"],
                                  "actor": "Client"}


def test_a_cycle_is_refused():
    spec = """app Cyc
entity C1
    champ: Integer
entity C2
    champ: Integer
relation C1 hasMany C2
relation C2 hasMany C1
actor A selfRegister
rule C1.Read ownedBy C2
rule C2.Read ownedBy C1
workflow W for A
    Read C1
    Read C2
"""
    with pytest.raises(ASTValidationError, match="loops"):
        _validate(spec)


def test_a_chain_reaching_no_account_is_refused():
    spec = """app SansCompte
entity D1
    champ: Integer
entity D2
    champ: Integer
relation D2 hasMany D1
actor A selfRegister
rule D1.Read ownedBy D2
workflow W for A
    Read D1
"""
    with pytest.raises(ASTValidationError, match=r"does not lead to ANY actor"):
        _validate(spec)


def test_a_link_owned_by_several_entities_is_ambiguous():
    spec = """app Ambigu
entity X1
    champ: Integer
entity X2
    champ: Integer
entity A2
    champ: Integer
entity A3
    champ: Integer
relation X2 hasMany X1
relation A2 hasMany X2
relation A3 hasMany X2
actor A selfRegister
rule X1.Read ownedBy X2
rule X2.Read ownedBy A2
rule X2.Delete ownedBy A3
workflow W for A
    Read X1
    Read X2
    Delete X2
"""
    with pytest.raises(ASTValidationError, match="ambigu"):
        _validate(spec)



# -----------------------------------------------------------------------------
# E2E on a real server: a TWO-hop chain
#   Ligne -> Bloc -> Commande -> Client
# -----------------------------------------------------------------------------

SPEC = """app Profondeur

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Bloc
    note: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne
relation Article hasMany Ligne

actor Admin
actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client
rule Bloc.Read ownedBy Commande
rule Bloc.Update ownedBy Commande
rule Bloc.Delete ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc

workflow GererArticle for Admin
    Create Article
    Read Article

workflow Acheter for Client
    Read Article
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
    Create Bloc
    Read Bloc
    Update Bloc
    Delete Bloc
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

PASSWORD = "motdepasse123"
PRICE = 42.5


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
                            ("Article test", PRICE))
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
    headers = _headers(application, "alice_prof")
    base, _ = application
    # Several orders AND blocks BEFORE any assertion: neither order ids nor
    # block ids then coincide with account ids (point 80's lesson — a link
    # confused with an account would hide the bug we try to settle at depth 2).
    last = None
    for label in ("brouillon", "abandonnée", "en cours"):
        last = _order(base, headers, label)
    for _ in range(3):
        _block(base, headers, last)
    return headers


@pytest.fixture(scope="module")
def bob(application):
    return _headers(application, "bob_prof")


def _order(base, headers, label):
    r = requests.post(f"{base}/commande", headers=headers,
                      json={"libelle": label})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _block(base, headers, order_id):
    r = requests.post(f"{base}/bloc", headers=headers,
                      json={"note": "bloc", "commande_id": order_id})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _line(base, headers, block_id, article_id, quantity):
    return requests.post(f"{base}/ligne", headers=headers,
                         json={"bloc_id": block_id, "article_id": article_id,
                               "quantite": quantity})


def _id_article(folder):
    with _base_spec(folder) as conn:
        return conn.execute('SELECT id FROM article WHERE prix = ?',
                           (PRICE,)).fetchone()[0]


def _account_id(folder, identifier):
    with _base_spec(folder) as conn:
        return conn.execute("SELECT id FROM _monl_users WHERE username = ?",
                           (identifier,)).fetchone()[0]


# -----------------------------------------------------------------------------
# Depth opens the schema the way depth 1 did
# -----------------------------------------------------------------------------

def test_the_chain_foreign_keys_are_in_the_schema(application):
    base, _ = application
    schema = requests.get(f"{base}/openapi.json").json()
    block = schema["components"]["schemas"]["BlocSchema"]["properties"]
    line = schema["components"]["schemas"]["LigneSchema"]["properties"]
    assert "commande_id" in block       # Bloc -> Commande
    assert "bloc_id" in line          # Ligne -> Bloc (the owning parent)
    assert "article_id" in line       # the plain relation, too


# -----------------------------------------------------------------------------
# Point 80's defect, transposed to depth 2
# -----------------------------------------------------------------------------

def test_the_stored_link_is_the_one_requested(application, alice):
    base, folder = application
    order = _order(base, alice, "panier profond")
    block = _block(base, alice, order)
    article = _id_article(folder)
    response = _line(base, alice, block, article, 2)
    assert response.status_code in (200, 201), response.text
    line_id = response.json()["id"]

    with _base_spec(folder) as conn:
        stored = conn.execute('SELECT bloc_id FROM ligne WHERE id = ?',
                             (line_id,)).fetchone()[0]
    account = _account_id(folder, "alice_prof")
    assert stored == block, "the designated link was not recorded"
    assert block != account and stored != account, "maillon et compte confondus"


# -----------------------------------------------------------------------------
# Cross refusals: the caller does not touch another customer's line
# -----------------------------------------------------------------------------

def test_reading_someone_elses_line_answers_404(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "lire")
    block = _block(base, alice, order)
    line_id = _line(base, alice, block, _id_article(folder), 1).json()["id"]
    assert requests.get(f"{base}/ligne/{line_id}",
                        headers=bob).status_code == 404


def test_creating_in_someone_elses_block_is_refused(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "créer")
    block = _block(base, alice, order)
    response = _line(base, bob, block, _id_article(folder), 1)
    assert response.status_code == 403, response.text


def test_updating_someone_elses_line_is_refused(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "modifier")
    block = _block(base, alice, order)
    line_id = _line(base, alice, block, _id_article(folder), 1).json()["id"]
    refuse = requests.put(f"{base}/ligne/{line_id}", headers=bob,
                          json={"quantite": 50, "bloc_id": block,
                                "article_id": _id_article(folder)})
    assert refuse.status_code == 403, refuse.text
    with _base_spec(folder) as conn:
        quantity = conn.execute('SELECT quantite FROM ligne WHERE id = ?',
                               (line_id,)).fetchone()[0]
    assert quantity == 1, "the line was modified despite the refusal"


def test_deleting_someone_elses_line_is_refused(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "supprimer")
    block = _block(base, alice, order)
    line_id = _line(base, alice, block, _id_article(folder), 1).json()["id"]
    refuse = requests.delete(f"{base}/ligne/{line_id}", headers=bob)
    assert refuse.status_code == 403, refuse.text
    with _base_spec(folder) as conn:
        reste = conn.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (line_id,)).fetchone()[0]
    assert reste == 1, "the line was deleted despite the refusal"


def test_the_owner_updates_and_deletes_their_line(application, alice):
    base, folder = application
    order = _order(base, alice, "à moi")
    block = _block(base, alice, order)
    line_id = _line(base, alice, block, _id_article(folder), 1).json()["id"]

    modified = requests.put(f"{base}/ligne/{line_id}", headers=alice,
                           json={"quantite": 4, "bloc_id": block,
                                 "article_id": _id_article(folder)})
    assert modified.status_code == 200, modified.text
    detail = requests.get(f"{base}/ligne/{line_id}", headers=alice).json()
    assert detail["data"]["quantite"] == 4

    assert requests.delete(f"{base}/ligne/{line_id}",
                           headers=alice).status_code == 200
    with _base_spec(folder) as conn:
        reste = conn.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (line_id,)).fetchone()[0]
    assert reste == 0


def test_the_list_only_shows_the_customers_lines(application, alice, bob):
    base, folder = application
    order = _order(base, alice, "liste")
    block = _block(base, alice, order)
    article = _id_article(folder)
    ids_alice = {_line(base, alice, block, article, 1).json()["id"] for _ in range(2)}

    order_bob = _order(base, bob, "liste bob")
    block_bob = _block(base, bob, order_bob)
    _line(base, bob, block_bob, article, 1)

    list_ = requests.get(f"{base}/ligne", headers=alice).json()
    seen = {line["id"] for line in list_["data"]}
    assert ids_alice.issubset(seen)
    assert all(line["id"] not in seen
               for line in requests.get(f"{base}/ligne", headers=bob).json()["data"])
