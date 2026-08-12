"""Épreuves d'intégration du backend généré contre un vrai PostgreSQL.

La suite est volontairement indépendante de SQLite : elle démarre les
artefacts générés avec ``MONL_DATABASE_URL`` et utilise un schéma PostgreSQL
éphémère. Sans ``MONL_TEST_DATABASE_URL``, un poste de contributeur sans
serveur saute proprement ces tests.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server


def _psycopg():
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg absent : installer l'extra optionnel .[postgres]")
    return psycopg


@pytest.fixture(params=["sqlite", "postgres"])
def database_url(request):
    if request.param == "sqlite":
        return None
    return request.getfixturevalue("postgres_dsn")


@pytest.fixture(scope="module")
def postgres_dsn():
    base = os.environ.get("MONL_TEST_DATABASE_URL", "").strip()
    if not base:
        pytest.skip("MONL_TEST_DATABASE_URL absent : PostgreSQL d'intégration non demandé")
    psycopg = _psycopg()
    schema = f"monl_test_{uuid4().hex[:12]}"
    admin = psycopg.connect(base)
    try:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
    finally:
        admin.close()
    morceaux = urlsplit(base)
    options = f"-c search_path={schema}"
    params = dict(parse_qsl(morceaux.query, keep_blank_values=True))
    params["options"] = options
    # libpq ne traite pas '+' comme un espace dans l'option ``options``;
    # encoder explicitement l'espace est nécessaire pour ``-c search_path``.
    dsn = urlunsplit(morceaux._replace(query=urlencode(params, quote_via=quote)))
    try:
        yield dsn
    finally:
        admin = psycopg.connect(base)
        try:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            admin.commit()
        finally:
            admin.close()


def _compile(spec: str, directory: str) -> None:
    ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=directory).generate_all()


@contextlib.contextmanager
def _application(spec: str, postgres_dsn: str | None):
    with tempfile.TemporaryDirectory(prefix="monl-pg-") as directory:
        _compile(spec, directory)
        env = os.environ.copy()
        if postgres_dsn:
            env["MONL_DATABASE_URL"] = postgres_dsn
        else:
            env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "postgres-integration-secret-32-bytes-min"
        env["MONL_TRUST_PROXY"] = "1"
        with uvicorn_server(directory, env=env) as base:
            yield Path(directory), base, env


def _register(base: str, username: str) -> dict:
    forwarded = {"X-Forwarded-For": username}
    response = requests.post(
        f"{base}/register",
        headers=forwarded,
        json={"username": username, "password": "motdepasse8", "actor": "User"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    login = requests.post(
        f"{base}/login",
        headers=forwarded,
        json={"username": username, "password": "motdepasse8"},
        timeout=10,
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_inscription_creation_et_lecture_restent_filtrees_par_propriete(postgres_dsn):
    spec = """app PgAccess

entity User
    name: String

entity Note
    body: String

relation User hasMany Note
actor User selfRegister
rule Note.Read ownedBy User
workflow W for User
    Create Note
    Read Note
"""
    with _application(spec, postgres_dsn) as (_directory, base, _env):
        alice = _register(base, f"alice-{uuid4().hex[:8]}")
        bob = _register(base, f"bob-{uuid4().hex[:8]}")
        created = requests.post(f"{base}/note", headers=alice,
                                json={"body": "privé alice"}, timeout=10)
        assert created.status_code == 200, created.text
        note_id = created.json()["id"]

        own = requests.get(f"{base}/note", headers=alice, timeout=10)
        other = requests.get(f"{base}/note", headers=bob, timeout=10)
        assert own.status_code == 200 and own.json()["total"] == 1
        assert other.status_code == 200 and other.json()["total"] == 0
        assert requests.get(f"{base}/note/{note_id}", headers=bob,
                            timeout=10).status_code == 404


def test_les_trois_409_integrite_sont_distincts_sur_les_deux_moteurs(database_url):
    spec = """app PgErrors

entity User
    name: String

entity Entry
    label: String

entity Vote
    note: String

relation User hasMany Vote
relation Entry hasMany Vote
actor User selfRegister
rule Vote.Read ownedBy User
rule Vote.note unique
rule Vote.Create oncePer User, Entry
workflow W for User
    Create Vote
    Read Vote

seed Entry
    label: "première"
    label: "seconde"
"""
    with _application(spec, database_url) as (_directory, base, _env):
        user = _register(base, f"errors-{uuid4().hex[:8]}")
        first = requests.post(f"{base}/vote", headers=user,
                              json={"note": "note-1", "entry_id": 1}, timeout=10)
        assert first.status_code == 200, first.text

        once = requests.post(f"{base}/vote", headers=user,
                             json={"note": "note-2", "entry_id": 1}, timeout=10)
        unique = requests.post(f"{base}/vote", headers=user,
                               json={"note": "note-1", "entry_id": 2}, timeout=10)
        foreign = requests.post(f"{base}/vote", headers=user,
                                json={"note": "note-3", "entry_id": 999999}, timeout=10)
        assert once.status_code == 409 and "déjà été effectuée" in once.json()["detail"]
        assert unique.status_code == 409 and "note" in unique.json()["detail"]
        assert foreign.status_code == 409 and "Référence invalide" in foreign.json()["detail"]


def test_stock_concurrent_condition_et_ecriture_sont_une_instruction(postgres_dsn):
    spec = """app PgStock

entity User
    name: String

entity Product
    name: String
    stock: Integer

entity Order
    status: String

entity Line
    quantity: Integer

relation User hasMany Order
relation Order hasMany Line
relation Product hasMany Line
actor User selfRegister
rule Product.Read public
rule Product.stock min 0
rule Line.quantity required
rule Order.Read ownedBy User
rule Line.Read ownedBy Order
rule Line.Create decrements Product.stock by quantity
workflow W for User
    Create Order
    Read Order
    Create Line
    Read Line
    Read Product

seed Product
    name: "stock-unique", stock: 1
"""
    with _application(spec, postgres_dsn) as (_directory, base, env):
        alice = _register(base, f"stock-a-{uuid4().hex[:8]}")
        bob = _register(base, f"stock-b-{uuid4().hex[:8]}")
        catalogue = requests.get(f"{base}/product?limit=10", timeout=10)
        assert catalogue.status_code == 200, catalogue.text
        product_id = catalogue.json()["data"][0]["id"]
        orders = []
        for headers in (alice, bob):
            response = requests.post(f"{base}/order", headers=headers,
                                     json={"status": "panier"}, timeout=10)
            assert response.status_code == 200, response.text
            orders.append(response.json()["id"])

        def create_line(order_id):
            response = requests.post(
                f"{base}/line", headers=alice if order_id == orders[0] else bob,
                json={"quantity": 1, "order_id": order_id, "product_id": product_id},
                timeout=10,
            )
            return response.status_code, response.text

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create_line, orders))
        assert sorted(code for code, _text in results) == [200, 409], results

        psycopg = _psycopg()
        conn = psycopg.connect(env["MONL_DATABASE_URL"])
        try:
            stock = conn.execute('SELECT stock FROM "product" WHERE id = %s', (product_id,)).fetchone()[0]
            lines = conn.execute('SELECT COUNT(*) FROM "line"').fetchone()[0]
        finally:
            conn.close()
        assert stock == 0 and lines == 1


def test_numerotation_concurrent_preserve_une_sequence_unique(postgres_dsn):
    spec = """app PgNumber

entity User
    name: String

entity Order
    reference: String
    status: String

relation User hasMany Order
actor User selfRegister
rule Order.Read ownedBy User
rule Order.reference numbered "CMD-{YYYY}-{NNNN}"
workflow W for User
    Create Order
    Read Order
"""
    with _application(spec, postgres_dsn) as (_directory, base, env):
        headers = [_register(base, f"number-{uuid4().hex[:8]}") for _ in range(2)]

        def create_order(auth):
            response = requests.post(f"{base}/order", headers=auth,
                                     json={"status": "nouvelle"}, timeout=10)
            return response.status_code, response.json().get("id")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create_order, headers))
        assert [code for code, _order_id in results] == [200, 200], results
        references = []
        for (_code, order_id), auth in zip(results, headers, strict=True):
            read = requests.get(f"{base}/order/{order_id}", headers=auth, timeout=10)
            assert read.status_code == 200, read.text
            references.append(read.json()["data"]["reference"])
        assert all(re.fullmatch(r"CMD-\d{4}-\d{4}", value or "") for value in references)
        assert len(set(references)) == 2

        psycopg = _psycopg()
        conn = psycopg.connect(env["MONL_DATABASE_URL"])
        try:
            sequence = conn.execute(
                "SELECT dernier FROM _monl_sequences WHERE entite = 'Order' "
                "AND champ = 'reference' AND periode <> ''"
            ).fetchone()[0]
            indexes = conn.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'order' "
                "AND indexname = 'idx_unique_order_reference'"
            ).fetchall()
        finally:
            conn.close()
        assert sequence == 2
        assert indexes == [("idx_unique_order_reference",)]


def test_migration_additive_sur_base_postgresql_deja_peuplee(postgres_dsn):
    spec_v1 = """app PgMigration

entity User
    name: String

entity Note
    title: String

relation User hasMany Note
actor User selfRegister
rule Note.Read ownedBy User
workflow W for User
    Create Note
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String\n", "    title: String\n    body: Text\n")
    with tempfile.TemporaryDirectory(prefix="monl-pg-migration-") as directory:
        _compile(spec_v1, directory)
        env = os.environ.copy()
        env["MONL_DATABASE_URL"] = postgres_dsn
        env["MONL_JWT_SECRET"] = "postgres-migration-secret-32-bytes-min"
        env["MONL_TRUST_PROXY"] = "1"
        with uvicorn_server(directory, env=env) as base:
            username = f"migration-{uuid4().hex[:8]}"
            headers = _register(base, username)
            created = requests.post(f"{base}/note", headers=headers,
                                    json={"title": "avant"}, timeout=10)
            assert created.status_code == 200, created.text
            note_id = created.json()["id"]

        _compile(spec_v2, directory)
        with uvicorn_server(directory, env=env) as base:
            login = requests.post(f"{base}/login",
                                  json={"username": username, "password": "motdepasse8"},
                                  timeout=10)
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            read = requests.get(f"{base}/note/{note_id}", headers=headers, timeout=10)
            assert read.status_code == 200 and read.json()["data"]["body"] is None
            added = requests.post(f"{base}/note", headers=headers,
                                  json={"title": "après", "body": "nouvelle"}, timeout=10)
            assert added.status_code == 200, added.text

        psycopg = _psycopg()
        conn = psycopg.connect(postgres_dsn)
        try:
            columns = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'note'"
            ).fetchall()
        finally:
            conn.close()
        assert ("body",) in columns
