"""Brique B3 : filtres exacts et tri déclaré, contre de vrais serveurs.

La recherche textuelle n'est volontairement pas testée : elle n'existe pas.
Chaque scénario de comportement est exécuté séquentiellement sur SQLite puis
sur PostgreSQL quand MONL_TEST_DATABASE_URL est fourni.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import _contract_signature, compile_project
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app B3

entity User
    name: String

entity Item
    title: String
    status: String
    active: Boolean
    rank: Integer

relation User hasMany Item
actor User selfRegister

rule Item.Read ownedBy User
rule Item.status oneOf "pending", "shipped"
rule Item.Read filter status
rule Item.Read filter title
rule Item.Read sort rank

workflow W for User
    Create Item
    Read Item
"""


@pytest.fixture(params=["sqlite", "postgres"])
def database_url(request):
    if request.param == "sqlite":
        yield None
        return
    base = os.environ.get("MONL_TEST_DATABASE_URL", "").strip()
    if not base:
        pytest.skip("MONL_TEST_DATABASE_URL absent : PostgreSQL B3 non demandé")
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg absent")
    schema = f"monl_b3_{uuid4().hex[:12]}"
    admin = psycopg.connect(base)
    try:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
    finally:
        admin.close()
    morceaux = urlsplit(base)
    params = dict(parse_qsl(morceaux.query, keep_blank_values=True))
    params["options"] = f"-c search_path={schema}"
    dsn = urlunsplit(morceaux._replace(
        query=urlencode(params, quote_via=quote)))
    try:
        yield dsn
    finally:
        admin = psycopg.connect(base)
        try:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            admin.commit()
        finally:
            admin.close()


@contextlib.contextmanager
def _application(spec, database_url):
    with tempfile.TemporaryDirectory(prefix="monl-b3-") as directory:
        ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=directory).generate_all()
        env = os.environ.copy()
        if database_url:
            env["MONL_DATABASE_URL"] = database_url
        else:
            env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "b3-integration-secret-32-bytes-min"
        with uvicorn_server(directory, env=env) as base:
            yield base


def _register(base, username):
    response = requests.post(
        f"{base}/register",
        json={"username": username, "password": "motdepasse8", "actor": "User"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    response = requests.post(
        f"{base}/login",
        json={"username": username, "password": "motdepasse8"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create(base, headers, title, status, active, rank):
    response = requests.post(
        f"{base}/item", headers=headers,
        json={"title": title, "status": status, "active": active, "rank": rank},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_filtre_exact_tri_acl_pagination_et_valeurs_hostiles(database_url):
    with _application(SPEC, database_url) as base:
        alice = _register(base, f"alice-{uuid4().hex[:8]}")
        bob = _register(base, f"bob-{uuid4().hex[:8]}")
        alice_first = _create(base, alice, "alice-pending", "pending", True, 2)
        alice_second = _create(base, alice, "alice-shipped", "shipped", False, 1)
        bob_item = _create(base, bob, "bob-shipped", "shipped", True, 3)

        all_alice = requests.get(f"{base}/item", headers=alice, timeout=10)
        assert all_alice.status_code == 200
        assert {row["id"] for row in all_alice.json()["data"]} == {
            alice_first, alice_second}

        shipped_alice = requests.get(
            f"{base}/item", headers=alice, params={"status": "shipped"}, timeout=10)
        assert shipped_alice.status_code == 200
        assert [row["title"] for row in shipped_alice.json()["data"]] == ["alice-shipped"]

        shipped_bob = requests.get(
            f"{base}/item", headers=bob, params={"status": "shipped"}, timeout=10)
        assert shipped_bob.status_code == 200
        assert [row["id"] for row in shipped_bob.json()["data"]] == [bob_item]
        assert bob_item not in {row["id"] for row in shipped_alice.json()["data"]}

        # Une colonne non filtrable est inconnue de FastAPI et reste ignorée ;
        # la liste n'est pas rétrécie silencieusement par un champ libre.
        ignored = requests.get(
            f"{base}/item", headers=alice, params={"active": "false"}, timeout=10)
        assert ignored.status_code == 200
        assert ignored.json()["total"] == 2

        for hostile in ("' OR 1=1 --", "%", "_", "x" * 10000):
            response = requests.get(
                f"{base}/item", headers=alice, params={"title": hostile}, timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 0
            assert response.json()["data"] == []

        ascending = requests.get(
            f"{base}/item", headers=alice,
            params={"sort": "rank", "direction": "asc"}, timeout=10)
        descending = requests.get(
            f"{base}/item", headers=alice,
            params={"sort": "rank", "direction": "desc"}, timeout=10)
        assert [row["rank"] for row in ascending.json()["data"]] == [1, 2]
        assert [row["rank"] for row in descending.json()["data"]] == [2, 1]

        # rank est la seule colonne triable ; le champ déclaré seulement
        # filtrable, et le sens arbitraire, sont refusés.
        refused_column = requests.get(
            f"{base}/item", headers=alice,
            params={"sort": "status", "direction": "asc"}, timeout=10)
        refused_direction = requests.get(
            f"{base}/item", headers=alice,
            params={"sort": "rank", "direction": "sideways"}, timeout=10)
        assert refused_column.status_code == 422
        assert refused_direction.status_code == 422

        page = requests.get(
            f"{base}/item", headers=alice,
            params={"limit": 0, "offset": -4}, timeout=10)
        assert page.status_code == 200
        assert page.json()["limit"] == 1
        assert page.json()["offset"] == 0
        assert len(page.json()["data"]) == 1


def test_contrat_et_signature_decrivent_les_capacites(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path / "avec"))
    contract = json.loads(
        (tmp_path / "avec" / "frontend_contract.json").read_text(encoding="utf-8"))
    fields = {field["name"]: field
              for field in contract["entities"]["Item"]["fields"]}
    assert fields["status"]["filterable"] is True
    assert fields["status"]["filter"]["allowed_values"] == ["pending", "shipped"]
    assert fields["rank"]["sortable"] is True
    liste = next(route for route in contract["routes"]
                 if route["action"] == "List" and route["entity"] == "Item")
    assert liste["list_query"]["sort"]["fields"] == ["rank"]
    assert {item["field"] for item in liste["list_query"]["filters"]} == {
        "status", "title"}

    sans = tmp_path / "sans.ml"
    sans.write_text(SPEC.replace("rule Item.Read filter title\n", ""), encoding="utf-8")
    compile_project(str(sans), str(tmp_path / "sans"))
    contract_sans = json.loads(
        (tmp_path / "sans" / "frontend_contract.json").read_text(encoding="utf-8"))
    assert _contract_signature(contract)[6] != _contract_signature(contract_sans)[6]


@pytest.mark.parametrize(
    ("fragment", "needle"),
    [
        ("rule Doc.value hidden\nrule Doc.Read filter value", "hidden"),
        (
            "rule Doc.score categorized: \"low\" below 10, \"high\" otherwise\n"
            "rule Doc.Read filter score",
            "categorized",
        ),
        ("rule Doc.Read filter file", "Upload"),
        ("rule Doc.Read filter apiSecret", "secret"),
    ],
)
def test_oracles_refuses_a_la_compilation(fragment, needle):
    field = "file: Upload" if "filter file" in fragment else (
        "score: Integer" if "score" in fragment else (
            "apiSecret: String" if "apiSecret" in fragment else "value: String"))
    upload_rule = (
        "rule Doc.file upload max 1024 types \"application/pdf\"\n"
        "rule Doc.Read ownedBy User\n"
        "rule Doc.Update ownedBy User\n"
        if field == "file: Upload" else "")
    spec = f"""app Oracle

entity User
    name: String

entity Doc
    {field}

relation User hasMany Doc
actor User selfRegister

rule Doc.Read ownedBy User
{upload_rule}{fragment}

workflow W for User
    Create Doc
    Read Doc
    Update Doc
"""
    with pytest.raises(ASTValidationError, match=needle):
        MonlAST(parse_monl_string(spec)).validate_and_audit()
