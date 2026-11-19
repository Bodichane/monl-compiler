"""Bricks 3, 4, 5 and 7 tested against a real server.

Of the eight bricks of the capability ecosystem, only three were exercised
against a real server: `accessibleBy` (test_access_parties.py), `ownedBy` read
filtering (test_private_read.py) and `hidden` (test_hidden_masking.py,
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

SPEC_BENCH = """app BancEssai

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

PASSWORD = "motdepasse123"


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC_BENCH)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        with uvicorn_server(folder) as base:
            yield base, folder


@contextlib.contextmanager
def _base_spec(folder):
    """Opens app.db, committing AND closing on exit.

    `with sqlite3.connect(...)` alone does NOT close the connection — it only
    commits or rolls back the transaction. It is the trap that let the suite emit
    ResourceWarnings; closings happened at the garbage collector's mercy. The
    produced code does close explicitly (see generator/runtime.py): the leak only
    ever concerned the test bench.
    """
    conn = sqlite3.connect(os.path.join(folder, "app.db"))
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _empty_quota(folder):
    """Clears the attempt counter (5 / 60 s / IP, points 13 and 33).

    Same gesture as at point 67, for the same reason: this file opens an account
    per test so that tests do not implicitly order one another, which exceeds the
    quota. Emptying a counter table on the bench side weakens nothing in the
    product — loosening the quota itself would.
    """
    with _base_spec(folder) as conn:
        conn.execute("DELETE FROM _monl_rate_limit")


def _headers(application, identifier):
    """Registers an account and returns its authentication headers.

    Each test uses its own credentials: the database lives for the module, and
    tests sharing an account implicitly order one another.
    """
    base, folder = application
    _empty_quota(folder)
    requests.post(f"{base}/register",
                  json={"username": identifier, "password": PASSWORD,
                        "actor": "Member"})
    token = requests.post(f"{base}/login",
                          json={"username": identifier,
                                "password": PASSWORD}).json()
    assert "access_token" in token, token
    return {"Authorization": "Bearer " + token["access_token"]}


def _created(base, path, headers, body):
    response = requests.post(f"{base}/{path}", headers=headers, json=body)
    assert response.status_code in (200, 201), response.text
    identifier = response.json().get("id")
    assert identifier, response.text
    return identifier


def _post(base, identifier):
    detail = requests.get(f"{base}/post/{identifier}").json()
    return detail.get("data", detail)


# --------------------------------------------------- brique 7 : generated --
def test_the_generated_field_cannot_be_forged_by_the_client(application):
    """Point 30's promise: the author comes from the account, never from the
    request body. A client sending the field anyway must not see its value land
    in the database — otherwise `generated` would only be a display convention."""
    base, folder = application
    headers = _headers(application, "forgeuse")

    identifier = _created(base, "post", headers,
                        {"content": "coucou", "author": "Administration",
                         "likes": 0, "score": 0})

    body = _post(base, identifier)
    assert body["author"] != "Administration", (
        f"the author provided by the client was kept: {body}")
    assert body["author"].startswith("Anon#"), body

    # And not only on display: the forged value is not in the database either,
    # where another reader (export, direct query) would find it.
    with _base_spec(folder) as conn:
        in_base = conn.execute("SELECT author FROM post WHERE id = ?",
                              (identifier,)).fetchone()
    assert in_base and in_base[0] == body["author"], in_base


def test_the_pseudonym_is_stable_per_account_and_distinct_between_accounts(application):
    """"Stable per account" is the half of the promise a single creation cannot
    check: two posts of the same account, separated by a reconnection, must carry
    the same pseudonym — and another account's must differ."""
    base, _folder = application
    headers = _headers(application, "stable")

    first = _created(base, "post", headers, {"content": "un", "score": 0})
    second = _created(base, "post", headers, {"content": "deux", "score": 0})
    assert _post(base, first)["author"] == _post(base, second)["author"]

    # Reconnection: the pseudonym is fixed at registration, not drawn at each
    # session — a draw per login would break the thread of one author.
    offspring = requests.post(f"{base}/login",
                            json={"username": "stable",
                                  "password": PASSWORD}).json()
    apres = _created(base, "post",
                  {"Authorization": "Bearer " + offspring["access_token"]},
                  {"content": "trois", "score": 0})
    assert _post(base, apres)["author"] == _post(base, first)["author"]

    other = _headers(application, "voisine")
    elsewhere = _created(base, "post", other, {"content": "quatre", "score": 0})
    assert _post(base, elsewhere)["author"] != _post(base, first)["author"]


def test_the_generated_field_is_missing_from_the_creation_schema(application):
    """The public contract says the same thing as the server: the creation input
    model does not expose the field, while it exposes its neighbors.

    We query the component really referenced by the request rather than the
    route text: `author` missing from a string would prove as well that the field
    disappeared as that it was never looked for in the right place. READ routes
    declare no `response_model` — their content is checked against the server
    (tests above), not in OpenAPI.
    """
    base, _folder = application
    schema = requests.get(f"{base}/openapi.json").json()

    reference = schema["paths"]["/post"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["$ref"]
    template = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    properties = template["properties"]
    assert "content" in properties and "likes" not in properties, properties
    assert "author" not in properties, (
        f"the 'generated' field is offered as input: {properties}")


# ----------------------------------- briques 3 et 4 : compteurs transactionnels --
def test_increments_touches_the_right_record_and_only_it(application):
    """The neighboring witness is the point of the test. A counter going up only
    proves an UPDATE happened; it is the NON-targeted post, left at its value,
    that proves the foreign key designates the right one."""
    base, folder = application
    headers = _headers(application, "likeuse")

    vise = _created(base, "post", headers, {"content": "visé", "score": 0})
    witness = _created(base, "post", headers, {"content": "témoin", "score": 0})

    _created(base, "like", headers, {"note": "bravo", "post_id": vise})

    with _base_spec(folder) as conn:
        values = dict(conn.execute(
            "SELECT id, likes FROM post WHERE id IN (?, ?)", (vise, witness)))
    assert values[vise] == 1, values
    assert values[witness] == 0, f"the neighbor moved: {values}"


def test_decrements_removes_the_declared_amount_from_the_target(application):
    """`by 10` must remove 10, not 1: the amount is declared in the spec and the
    generator writes it into the UPDATE."""
    base, _folder = application
    headers = _headers(application, "signaleuse")

    target = _created(base, "post", headers, {"content": "cible", "score": 100})
    witness = _created(base, "post", headers, {"content": "témoin", "score": 100})

    _created(base, "report", headers, {"reason": "spam", "post_id": target})

    assert _post(base, target)["score"] == 90
    assert _post(base, witness)["score"] == 100


def test_a_nonexistent_target_cancels_the_whole_creation(application):
    """Atomicity (beta 1): creation and counter effect hold in a single
    transaction. A foreign key pointing to nothing is refused with 409 — and the
    triggering record must NOT remain, otherwise the database would keep an
    orphan like whose counter never moved."""
    base, folder = application
    headers = _headers(application, "fantome")

    with _base_spec(folder) as conn:
        before = conn.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]

    refusal = requests.post(f"{base}/like", headers=headers,
                          json={"note": "sur du vide", "post_id": 999_999})
    assert refusal.status_code == 409, refusal.text

    with _base_spec(folder) as conn:
        apres = conn.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]
        orphan = conn.execute(
            'SELECT COUNT(*) FROM "like" WHERE note = ?', ("sur du vide",)
        ).fetchone()[0]
    assert apres == before, f"{apres - before} row(s) left by a refusal"
    assert orphan == 0


# ------------------------------------------------- brique 5 : categorized --
def test_categorized_replaces_the_value_in_list_and_detail(application):
    """Substitution, not addition: the exact value disappears from both read
    routes. Leaving it beside the label would make the brick useless — its
    purpose is precisely not to publish the score."""
    base, folder = application
    headers = _headers(application, "categorisee")

    identifier = _created(base, "post", headers, {"content": "chiffres", "score": 0})

    _populate_counter(folder, identifier, 137)
    detail = _post(base, identifier)
    assert detail["likes_category"] == "viral", detail
    assert "likes" not in detail, f"the exact value leaks in detail: {detail}"

    line = next(r for r in requests.get(f"{base}/post").json()["data"]
                 if r["id"] == identifier)
    assert line["likes_category"] == "viral", line
    assert "likes" not in line, f"the exact value leaks in list: {line}"


def test_categorized_treats_below_as_a_strict_bound(application):
    """`below 10` excludes 10. The bound is the only place where a generated
    if/elif chain can shift by one without anything reporting it; 9, 10 and 100
    frame it on both sides."""
    base, folder = application
    headers = _headers(application, "bornes")

    expected_items = {9: "discret", 10: "populaire", 99: "populaire", 100: "viral"}
    for valeur, label in expected_items.items():
        identifier = _created(base, "post", headers,
                            {"content": f"likes={valeur}", "score": 0})
        _populate_counter(folder, identifier, valeur)
        assert _post(base, identifier)["likes_category"] == label, (
            f"{valeur} classified {_post(base, identifier)['likes_category']}, "
            f"expected {label}")


def test_categorized_does_not_touch_the_stored_value(application):
    """Like `hidden`, the brick acts on read: the number stays in the database,
    intact — it is the one `increments` keeps raising."""
    base, folder = application
    headers = _headers(application, "stockage")

    identifier = _created(base, "post", headers, {"content": "en base", "score": 0})

    _populate_counter(folder, identifier, 137)
    with _base_spec(folder) as conn:
        stored = conn.execute("SELECT likes FROM post WHERE id = ?",
                             (identifier,)).fetchone()
    assert stored and stored[0] == 137, stored


def _populate_counter(folder, identifier, valeur):
    """Server-side preparation of the categories, without simulating client input."""
    with _base_spec(folder) as conn:
        conn.execute("UPDATE post SET likes = ? WHERE id = ?", (valeur, identifier))


def test_counter_ignores_post_and_put(application):
    base, folder = application
    headers = _headers(application, "forgecompteur")
    identifier = _created(base, "post", headers,
                       {"content": "attaque", "score": 100, "likes": 5000})
    with _base_spec(folder) as conn:
        assert conn.execute("SELECT likes FROM post WHERE id = ?", (identifier,)).fetchone()[0] == 0
    response = requests.put(f"{base}/post/{identifier}", headers=headers,
                           json={"content": "modifié", "score": 100, "likes": 9000})
    assert response.status_code == 200, response.text
    _created(base, "like", headers, {"note": "bravo", "post_id": identifier})
    with _base_spec(folder) as conn:
        assert conn.execute("SELECT likes FROM post WHERE id = ?", (identifier,)).fetchone()[0] == 1
