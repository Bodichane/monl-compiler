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
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.cli import compile_project
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port, uvicorn_server


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


@pytest.fixture
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


def _compile_cli(spec: str, directory: str) -> None:
    path = Path(directory) / "spec.ml"
    path.write_text(spec, encoding="utf-8")
    compile_project(str(path), directory)


def _server_expected_failure(directory: str, env: dict[str, str]):
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
        cwd=directory, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
    )
    try:
        output, _ = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
        raise AssertionError("PostgreSQL : le serveur a démarré malgré le schéma non migré") from None
    return process.returncode, output


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


def test_migrations_non_additives_postgresql_sont_detectees_et_historisees(postgres_dsn):
    spec_v1 = """app PgNonAdditive

entity User
    name: String

entity Note
    title: String
    priority: String
    legacy: String

relation User hasMany Note
actor User selfRegister
workflow W for User
    Create Note
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String\n", "    heading: String\n")
    spec_v2 = spec_v2.replace("    priority: String\n", "    priority: Integer\n")
    spec_v2 = spec_v2.replace("    legacy: String\n", "")
    spec_v2 += """
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
    drop Note.legacy
"""
    with tempfile.TemporaryDirectory(prefix="monl-pg-nonadditive-") as directory:
        _compile_cli(spec_v1, directory)
        env = os.environ.copy()
        env["MONL_DATABASE_URL"] = postgres_dsn
        env["MONL_JWT_SECRET"] = "postgres-nonadditive-secret-32-bytes-min"
        env["MONL_TRUST_PROXY"] = "1"
        with uvicorn_server(directory, env=env) as base:
            headers = _register(base, f"nonadditive-{uuid4().hex[:8]}")
            created = requests.post(
                f"{base}/note", headers=headers,
                json={"title": "avant", "priority": "7", "legacy": "vieux"},
                timeout=10,
            )
            assert created.status_code == 200, created.text
            note_id = created.json()["id"]

        _compile_cli(spec_v2, directory)
        returncode, output = _server_expected_failure(directory, env)
        assert returncode != 0
        assert "Schéma non additif détecté" in output
        assert "renommage non appliqué" in output
        assert "type de note.priority" in output
        assert "colonne retirée" in output
        assert "base ne sera pas servie" in output

        cli_env = {**env, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        applied = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", directory,
             "--name", "note_fields"], cwd="/tmp", env=cli_env,
            capture_output=True, text=True, check=False,
        )
        assert applied.returncode == 0, applied.stdout + applied.stderr
        assert "Migration 'note_fields' (up) appliquée" in applied.stdout

        with uvicorn_server(directory, env=env) as base:
            # L'état est vérifié directement en base ; le serveur prouve que
            # le lifespan sert bien après migration.
            read = requests.get(f"{base}/note/{note_id}", headers=headers, timeout=10)
            assert read.status_code == 200, read.text
            assert read.json()["data"]["heading"] == "avant"
            assert read.json()["data"]["priority"] == 7

        psycopg = _psycopg()
        conn = psycopg.connect(postgres_dsn)
        try:
            columns = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'note' "
                "ORDER BY ordinal_position"
            ).fetchall()
            history = conn.execute(
                "SELECT migration_name, operation_index, direction, schema_fingerprint "
                "FROM _monl_migrations ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert [row[0] for row in columns] == ["id", "heading", "priority", "user_id"]
        assert dict(columns)["priority"] == "integer"
        assert len(history) == 3 and all(
            row[0] == "note_fields" and row[2] == "up" and len(row[3]) == 64
            for row in history
        )

        refused_down = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", directory,
             "--name", "note_fields", "--down"], cwd="/tmp", env=cli_env,
            capture_output=True, text=True, check=False,
        )
        assert refused_down.returncode != 0
        assert "DROP irréversible" in refused_down.stdout


def test_migration_postgresql_echec_atomique_ne_sert_pas_une_moitie(postgres_dsn):
    spec_v1 = """app PgAtomic

entity User
    name: String

entity Note
    title: String
    priority: String

relation User hasMany Note
actor User selfRegister
workflow W for User
    Create Note
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String\n", "    heading: String\n")
    spec_v2 = spec_v2.replace("    priority: String\n", "    priority: Float\n")
    spec_v2 += """
migration broken
    rename Note.title to heading
    alter Note.priority from Integer to Float
"""
    with tempfile.TemporaryDirectory(prefix="monl-pg-atomic-") as directory:
        _compile_cli(spec_v1, directory)
        env = os.environ.copy()
        env["MONL_DATABASE_URL"] = postgres_dsn
        env["MONL_JWT_SECRET"] = "postgres-atomic-secret-32-bytes-min"
        env["MONL_TRUST_PROXY"] = "1"
        with uvicorn_server(directory, env=env) as base:
            headers = _register(base, f"atomic-{uuid4().hex[:8]}")
            created = requests.post(
                f"{base}/note", headers=headers,
                json={"title": "avant", "priority": "7"}, timeout=10,
            )
            assert created.status_code == 200, created.text

        _compile_cli(spec_v2, directory)
        cli_env = {**env, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        failed = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", directory,
             "--name", "broken"], cwd="/tmp", env=cli_env,
            capture_output=True, text=True, check=False,
        )
        assert failed.returncode != 0
        assert "Précondition du changement de type" in failed.stdout

        psycopg = _psycopg()
        conn = psycopg.connect(postgres_dsn)
        try:
            columns = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'note' "
                "ORDER BY ordinal_position"
            ).fetchall()
            row = conn.execute("SELECT title, priority FROM note").fetchone()
            history_count = conn.execute("SELECT COUNT(*) FROM _monl_migrations").fetchone()[0]
        finally:
            conn.close()
        assert [row[0] for row in columns] == ["id", "title", "priority", "user_id"]
        assert row == ("avant", "7")
        assert history_count == 0

        returncode, output = _server_expected_failure(directory, env)
        assert returncode != 0 and "base ne sera pas servie" in output


def test_migration_postgresql_down_retablit_noms_types_et_donnees(postgres_dsn):
    spec_v1 = """app PgDown

entity Note
    title: String
    priority: String

actor User selfRegister
workflow W for User
    Create Note
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String", "    heading: String")
    spec_v2 = spec_v2.replace("    priority: String", "    priority: Integer")
    spec_v2 += """
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
"""
    with tempfile.TemporaryDirectory(prefix="monl-pg-down-") as directory:
        _compile_cli(spec_v1, directory)
        env = os.environ.copy()
        env["MONL_DATABASE_URL"] = postgres_dsn
        env["MONL_JWT_SECRET"] = "postgres-down-secret-32-bytes-min"
        with uvicorn_server(directory, env=env) as base:
            headers = _register(base, f"down-{uuid4().hex[:8]}")
            created = requests.post(
                f"{base}/note", headers=headers,
                json={"title": "avant", "priority": "7"}, timeout=10,
            )
            assert created.status_code == 200, created.text

        _compile_cli(spec_v2, directory)
        cli_env = {**env, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        for extra in ([], ["--down"]):
            result = subprocess.run(
                [sys.executable, "-m", "monl.cli", "migrate", directory,
                 "--name", "note_fields", *extra], cwd="/tmp", env=cli_env,
                capture_output=True, text=True, check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr

        psycopg = _psycopg()
        conn = psycopg.connect(postgres_dsn)
        try:
            columns = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'note' "
                "ORDER BY ordinal_position"
            ).fetchall()
            row = conn.execute("SELECT title, priority FROM note").fetchone()
        finally:
            conn.close()
        assert [item[0] for item in columns] == ["id", "title", "priority"]
        assert dict(columns)["priority"] == "character varying"
        assert row == ("avant", "7")

        _compile_cli(spec_v1, directory)
        with uvicorn_server(directory, env=env) as base:
            assert requests.get(f"{base}/health", timeout=10).status_code == 200
