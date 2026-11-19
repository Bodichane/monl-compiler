"""Bricks 3, 4, 5 and 7 tested against a real server.

Of the eight bricks of the capability ecosystem, only three were exercised
against a real server: `accessibleBy` (test_access_parties.py), `ownedBy` read
filtering (test_lecture_privee.py) and `hidden` (test_masquage_hidden.py,
point 64). The others only had the COMPILE coverage brought by
`exemples/03_reseau_social.ml` — and CLAUDE.md says it bluntly: compiling is
not behaving correctly.

This file closes the gap for the four bricks whose promise is behavioral, and
which each carry a guarantee a review does not prove:

* `generated` (brick 7) — the pseudonym must not be forgeable from the
  request body. It is the only one of the four whose defect is an integrity
  flaw and not a wrong display.
* `increments` / `decrements` (bricks 3 and 4) — the counter must move, by
  the declared amount, and on the RIGHT record. CLAUDE.md precisely lists "a
  foreign key mechanism that decremented the wrong record" among the bugs
  that never showed on reading; a neighboring witness catches it here.
* `categorized` (brick 5) — the numeric value must be replaced, not doubled,
  including at the exact bound (`below N` is strict), and stay in the
  database.

The spec assembles the four in the roles they hold in
`exemples/03_reseau_social.ml`, in miniature: it is this assembly that had
revealed two real bugs at point 29, not the bricks taken alone.
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

SPEC_BANC = """app BancEssai

entity Member
    name: String

entity Post
    content: Text
    author: String
    likes: Integer
    score: Integer

entity Like
    note: String

entity Report
    reason: String

relation Member hasMany Post
relation Post hasMany Like
relation Member hasMany Report
relation Post hasMany Report

actor Member selfRegister

rule Post.Read public
rule Post.author generated
rule Post.likes categorized: "discret" below 10, "populaire" below 100, "viral" otherwise
rule Like.Create increments Post.likes by 1
rule Report.Create decrements Post.score by 10

workflow Inscrire for Member
    Create Member
    Read Member

workflow Publier for Member
    Create Post
    Read Post
    Update Post

workflow Reagir for Member
    Create Like
    Create Report
"""

MOT_DE_PASSE = "motdepasse123"


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_BANC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            yield base, dossier


@contextlib.contextmanager
def _base_spec(dossier):
    """Opens app.db, committing AND closing on exit.

    `with sqlite3.connect(...)` alone does NOT close the connection — it only
    commits or rolls back the transaction. It is the trap that let the suite emit
    ResourceWarnings; closings happened at the garbage collector's mercy. The
    produced code does close explicitly (see generator/runtime.py): the leak only
    ever concerned the test bench.
    """
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


def _vider_quota(dossier):
    """Clears the attempt counter (5 / 60 s / IP, points 13 and 33).

    Same gesture as at point 67, for the same reason: this file opens an account
    per test so that tests do not implicitly order one another, which exceeds the
    quota. Emptying a counter table on the bench side weakens nothing in the
    product — loosening the quota itself would.
    """
    with _base_spec(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")


def _entetes(application, identifiant):
    """Registers an account and returns its authentication headers.

    Each test uses its own credentials: the database lives for the module, and
    tests sharing an account implicitly order one another.
    """
    base, dossier = application
    _vider_quota(dossier)
    requests.post(f"{base}/register",
                  json={"username": identifiant, "password": MOT_DE_PASSE,
                        "actor": "Member"})
    jeton = requests.post(f"{base}/login",
                          json={"username": identifiant,
                                "password": MOT_DE_PASSE}).json()
    assert "access_token" in jeton, jeton
    return {"Authorization": "Bearer " + jeton["access_token"]}


def _created(base, chemin, entetes, corps):
    reponse = requests.post(f"{base}/{chemin}", headers=entetes, json=corps)
    assert reponse.status_code in (200, 201), reponse.text
    identifiant = reponse.json().get("id")
    assert identifiant, reponse.text
    return identifiant


def _post(base, identifiant):
    detail = requests.get(f"{base}/post/{identifiant}").json()
    return detail.get("data", detail)


# --------------------------------------------------- brique 7 : generated --
def test_the_generated_field_cannot_be_forged_by_the_client(application):
    """Point 30's promise: the author comes from the account, never from the
    request body. A client sending the field anyway must not see its value land
    in the database — otherwise `generated` would only be a display convention."""
    base, dossier = application
    entetes = _entetes(application, "forgeuse")

    identifiant = _created(base, "post", entetes,
                        {"content": "coucou", "author": "Administration",
                         "likes": 0, "score": 0})

    corps = _post(base, identifiant)
    assert corps["author"] != "Administration", (
        f"the author provided by the client was kept: {corps}")
    assert corps["author"].startswith("Anon#"), corps

    # And not only on display: the forged value is not in the database either,
    # where another reader (export, direct query) would find it.
    with _base_spec(dossier) as cnx:
        en_base = cnx.execute("SELECT author FROM post WHERE id = ?",
                              (identifiant,)).fetchone()
    assert en_base and en_base[0] == corps["author"], en_base


def test_the_pseudonym_is_stable_per_account_and_distinct_between_accounts(application):
    """"Stable per account" is the half of the promise a single creation cannot
    check: two posts of the same account, separated by a reconnection, must carry
    the same pseudonym — and another account's must differ."""
    base, _dossier = application
    entetes = _entetes(application, "stable")

    premier = _created(base, "post", entetes, {"content": "un", "score": 0})
    second = _created(base, "post", entetes, {"content": "deux", "score": 0})
    assert _post(base, premier)["author"] == _post(base, second)["author"]

    # Reconnection: the pseudonym is fixed at registration, not drawn at each
    # session — a draw per login would break the thread of one author.
    rejeton = requests.post(f"{base}/login",
                            json={"username": "stable",
                                  "password": MOT_DE_PASSE}).json()
    apres = _created(base, "post",
                  {"Authorization": "Bearer " + rejeton["access_token"]},
                  {"content": "trois", "score": 0})
    assert _post(base, apres)["author"] == _post(base, premier)["author"]

    autre = _entetes(application, "voisine")
    ailleurs = _created(base, "post", autre, {"content": "quatre", "score": 0})
    assert _post(base, ailleurs)["author"] != _post(base, premier)["author"]


def test_the_generated_field_is_absent_from_the_creation_schema(application):
    """The public contract says the same thing as the server: the creation input
    model does not expose the field, while it exposes its neighbors.

    We query the component really referenced by the request rather than the
    route text: `author` missing from a string would prove as well that the field
    disappeared as that it was never looked for in the right place. READ routes
    declare no `response_model` — their content is checked against the server
    (tests above), not in OpenAPI.
    """
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()

    reference = schema["paths"]["/post"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["$ref"]
    modele = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    proprietes = modele["properties"]
    assert "content" in proprietes and "likes" not in proprietes, proprietes
    assert "author" not in proprietes, (
        f"the 'generated' field is offered as input: {proprietes}")


# ----------------------------------- briques 3 et 4 : compteurs transactionnels --
def test_increments_touches_the_right_record_and_only_it(application):
    """The neighboring witness is the point of the test. A counter going up only
    proves an UPDATE happened; it is the NON-targeted post, left at its value,
    that proves the foreign key designates the right one."""
    base, dossier = application
    entetes = _entetes(application, "likeuse")

    vise = _created(base, "post", entetes, {"content": "visé", "score": 0})
    temoin = _created(base, "post", entetes, {"content": "témoin", "score": 0})

    _created(base, "like", entetes, {"note": "bravo", "post_id": vise})

    with _base_spec(dossier) as cnx:
        valeurs = dict(cnx.execute(
            "SELECT id, likes FROM post WHERE id IN (?, ?)", (vise, temoin)))
    assert valeurs[vise] == 1, valeurs
    assert valeurs[temoin] == 0, f"the neighbor moved: {valeurs}"


def test_decrements_removes_the_declared_amount_from_the_target(application):
    """`by 10` must remove 10, not 1: the amount is declared in the spec and the
    generator writes it into the UPDATE."""
    base, _dossier = application
    entetes = _entetes(application, "signaleuse")

    cible = _created(base, "post", entetes, {"content": "cible", "score": 100})
    temoin = _created(base, "post", entetes, {"content": "témoin", "score": 100})

    _created(base, "report", entetes, {"reason": "spam", "post_id": cible})

    assert _post(base, cible)["score"] == 90
    assert _post(base, temoin)["score"] == 100


def test_a_nonexistent_target_cancels_the_whole_creation(application):
    """Atomicity (beta 1): creation and counter effect hold in a single
    transaction. A foreign key pointing to nothing is refused with 409 — and the
    triggering record must NOT remain, otherwise the database would keep an
    orphan like whose counter never moved."""
    base, dossier = application
    entetes = _entetes(application, "fantome")

    with _base_spec(dossier) as cnx:
        avant = cnx.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]

    refus = requests.post(f"{base}/like", headers=entetes,
                          json={"note": "sur du vide", "post_id": 999_999})
    assert refus.status_code == 409, refus.text

    with _base_spec(dossier) as cnx:
        apres = cnx.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]
        orphelin = cnx.execute(
            'SELECT COUNT(*) FROM "like" WHERE note = ?', ("sur du vide",)
        ).fetchone()[0]
    assert apres == avant, f"{apres - avant} row(s) left by a refusal"
    assert orphelin == 0


# ------------------------------------------------- brique 5 : categorized --
def test_categorized_replaces_the_value_in_list_and_detail(application):
    """Substitution, not addition: the exact value disappears from both read
    routes. Leaving it beside the label would make the brick useless — its
    purpose is precisely not to publish the score."""
    base, dossier = application
    entetes = _entetes(application, "categorisee")

    identifiant = _created(base, "post", entetes, {"content": "chiffres", "score": 0})

    _peupler_compteur(dossier, identifiant, 137)
    detail = _post(base, identifiant)
    assert detail["likes_category"] == "viral", detail
    assert "likes" not in detail, f"the exact value leaks in detail: {detail}"

    ligne = next(r for r in requests.get(f"{base}/post").json()["data"]
                 if r["id"] == identifiant)
    assert ligne["likes_category"] == "viral", ligne
    assert "likes" not in ligne, f"the exact value leaks in list: {ligne}"


def test_categorized_treats_below_as_a_strict_bound(application):
    """`below 10` excludes 10. The bound is the only place where a generated
    if/elif chain can shift by one without anything reporting it; 9, 10 and 100
    frame it on both sides."""
    base, dossier = application
    entetes = _entetes(application, "bornes")

    attendus = {9: "discret", 10: "populaire", 99: "populaire", 100: "viral"}
    for valeur, libelle in attendus.items():
        identifiant = _created(base, "post", entetes,
                            {"content": f"likes={valeur}", "score": 0})
        _peupler_compteur(dossier, identifiant, valeur)
        assert _post(base, identifiant)["likes_category"] == libelle, (
            f"{valeur} classified {_post(base, identifiant)['likes_category']}, "
            f"expected {libelle}")


def test_categorized_does_not_touch_the_stored_value(application):
    """Like `hidden`, the brick acts on read: the number stays in the database,
    intact — it is the one `increments` keeps raising."""
    base, dossier = application
    entetes = _entetes(application, "stockage")

    identifiant = _created(base, "post", entetes, {"content": "en base", "score": 0})

    _peupler_compteur(dossier, identifiant, 137)
    with _base_spec(dossier) as cnx:
        stocke = cnx.execute("SELECT likes FROM post WHERE id = ?",
                             (identifiant,)).fetchone()
    assert stocke and stocke[0] == 137, stocke


def _peupler_compteur(dossier, identifiant, valeur):
    """Server-side preparation of the categories, without simulating client input."""
    with _base_spec(dossier) as cnx:
        cnx.execute("UPDATE post SET likes = ? WHERE id = ?", (valeur, identifiant))


def test_counter_ignores_post_and_put(application):
    base, dossier = application
    entetes = _entetes(application, "forgecompteur")
    identifiant = _created(base, "post", entetes,
                       {"content": "attaque", "score": 100, "likes": 5000})
    with _base_spec(dossier) as cnx:
        assert cnx.execute("SELECT likes FROM post WHERE id = ?", (identifiant,)).fetchone()[0] == 0
    reponse = requests.put(f"{base}/post/{identifiant}", headers=entetes,
                           json={"content": "modifié", "score": 100, "likes": 9000})
    assert reponse.status_code == 200, reponse.text
    _created(base, "like", entetes, {"note": "bravo", "post_id": identifiant})
    with _base_spec(dossier) as cnx:
        assert cnx.execute("SELECT likes FROM post WHERE id = ?", (identifiant,)).fetchone()[0] == 1
