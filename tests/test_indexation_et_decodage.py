"""Preuves réelles des index de recherche et du décodage unique.

Le banc compile une application, démarre son vrai serveur uvicorn, inspecte
la base SQLite créée au démarrage et trace les requêtes du processus serveur.
Les contre-épreuves compilent des variantes temporaires qui désarment chaque
correctif ; l'assertion métier est alors bien rouge, et le test vérifie que
cette rougeur a eu lieu sans la masquer par un saut ou un ``xfail``.
"""

import contextlib
import os
import re
import sqlite3

import pytest
import requests

from monl.cli import compile_project
from monl.generator import MonlSecureGenerator
from tests.support.server import uvicorn_server

SPEC = """app IndexDecodage

entity User
    display_name: String

entity Commande
    reference: String
    status: String
    author: String

relation User hasMany Commande

actor User selfRegister

rule Commande.reference unique
rule Commande.author generated
rule Commande.Read ownedBy User
rule Commande.Read filter status

workflow Commandes for User
    Create Commande
    Read Commande
"""

PASSWORD = "motdepasse123"


def _compile(directory):
    directory.mkdir(parents=True, exist_ok=True)
    spec = directory / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(directory))


def _database_indexes(directory):
    connection = sqlite3.connect(directory / "app.db")
    try:
        rows = connection.execute('PRAGMA index_list("commande")').fetchall()
        names = {row[1] for row in rows}
        columns = {
            name: [row[2] for row in connection.execute(
                f'PRAGMA index_info("{name}")').fetchall()]
            for name in names
        }
        definitions = dict(connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'commande'"))
        return names, columns, definitions
    finally:
        connection.close()


def _assert_lookup_layout(directory):
    names, columns, definitions = _database_indexes(directory)
    expected = {
        "idx_lookup_commande_user_id": "user_id",
        "idx_lookup_commande_status": "status",
    }
    for index, column in expected.items():
        assert index in names, f"index absent de PRAGMA index_list : {index}"
        assert columns[index] == [column], (index, columns[index])
        assert f'("{column}")' in definitions[index], definitions[index]

    assert "idx_unique_commande_reference" in names
    assert columns["idx_unique_commande_reference"] == ["reference"]
    assert "idx_lookup_commande_reference" not in names, (
        "une colonne unique reçoit un second index de recherche")


def _write_sitecustomize(trace_file, directory):
    trace_env = directory / "trace_env"
    trace_env.mkdir(exist_ok=True)
    (trace_env / "sitecustomize.py").write_text(
        """import os
import sqlite3

_real_connect = sqlite3.connect


def _trace(statement):
    path = os.environ.get("MONL_SQL_TRACE")
    if path:
        with open(path, "a", encoding="utf-8") as trace:
            trace.write(statement.replace("\\n", " ") + "\\n")


def connect(*args, **kwargs):
    connection = _real_connect(*args, **kwargs)
    connection.set_trace_callback(_trace)
    return connection


sqlite3.connect = connect
""",
        encoding="utf-8",
    )
    trace_file.touch()
    return trace_env


@contextlib.contextmanager
def _server(directory):
    trace_file = directory / "sql-trace.log"
    trace_env = _write_sitecustomize(trace_file, directory)
    environment = os.environ.copy()
    environment.pop("MONL_DATABASE_URL", None)
    environment["MONL_SQL_TRACE"] = str(trace_file)
    old_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(trace_env), old_pythonpath) if part)
    with uvicorn_server(str(directory), env=environment) as base:
        yield base, trace_file


def _authenticate(base, username="client@example.test"):
    registered = requests.post(
        f"{base}/register", timeout=10,
        json={"username": username, "password": PASSWORD, "actor": "User"},
    )
    assert registered.status_code == 200, registered.text
    logged = requests.post(
        f"{base}/login", timeout=10,
        json={"username": username, "password": PASSWORD},
    )
    assert logged.status_code == 200, logged.text
    return logged.json()["access_token"]


def _create_commande(base, token):
    response = requests.post(
        f"{base}/commande", timeout=10,
        headers={"Authorization": f"Bearer {token}"},
        json={"reference": "CMD-1", "status": "en_attente"},
    )
    assert response.status_code == 200, response.text


def _revocation_selects(trace_file):
    statements = trace_file.read_text(encoding="utf-8").splitlines()
    return [
        statement for statement in statements
        if re.match(r"\s*SELECT\b", statement, re.IGNORECASE)
        and "_monl_revoked_tokens" in statement
    ]


def _assert_one_revocation_lookup(trace_file):
    queries = _revocation_selects(trace_file)
    assert len(queries) == 1, queries


def test_index_de_cle_etrangere_filtre_et_dedoublonnage_contre_serveur(tmp_path):
    _compile(tmp_path)
    with _server(tmp_path) as (base, trace_file):
        token = _authenticate(base)
        trace_file.write_text("", encoding="utf-8")
        _create_commande(base, token)

        _assert_lookup_layout(tmp_path)
        _assert_one_revocation_lookup(trace_file)


def test_un_logout_revoque_toujours_le_jeton_utilise(tmp_path):
    _compile(tmp_path)
    with _server(tmp_path) as (base, _trace_file):
        token = _authenticate(base, "sortant@example.test")
        headers = {"Authorization": f"Bearer {token}"}
        logout = requests.post(f"{base}/logout", headers=headers, timeout=10)
        assert logout.status_code == 200, logout.text
        refused = requests.get(f"{base}/commande", headers=headers, timeout=10)
        assert refused.status_code == 401, refused.text


def test_contre_epreuve_les_index_manquants_font_rougir_le_temoins(
        tmp_path, monkeypatch):
    """Désarmer l'émission rend la preuve d'index effectivement rouge."""
    monkeypatch.setattr(MonlSecureGenerator, "_compute_lookup_indexes",
                        lambda _generator: [])
    _compile(tmp_path)
    with _server(tmp_path), pytest.raises(AssertionError, match="index absent"):
        _assert_lookup_layout(tmp_path)


def test_contre_epreuve_un_unique_recoit_un_second_index_si_dedoublonnage_desarme(
        tmp_path, monkeypatch):
    """Désarmer le dédoublonnage fait rougir son témoin dédié."""
    original = MonlSecureGenerator._compute_lookup_indexes

    def with_redundant_unique_index(generator):
        return [*original(generator),
                ("commande", "reference", "idx_lookup_commande_reference")]

    monkeypatch.setattr(MonlSecureGenerator, "_compute_lookup_indexes",
                        with_redundant_unique_index)
    _compile(tmp_path)
    with _server(tmp_path), pytest.raises(AssertionError, match="second index"):
        _assert_lookup_layout(tmp_path)


def _disarm_shared_token_dependency(app):
    replacements = (
        (
            "def verify_jwt_and_get_actor(payload: dict = Depends(_identite_du_jeton)) -> str:\n"
            "    return payload.get('actor')",
            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:\n"
            "    return _decode_and_verify_token(credentials).get('actor')",
        ),
        (
            "def get_current_user_id(payload: dict = Depends(_identite_du_jeton)) -> int:\n"
            "    return payload.get('user_id', 0)",
            "def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:\n"
            "    return _decode_and_verify_token(credentials).get('user_id', 0)",
        ),
        (
            "def get_current_anon_handle(payload: dict = Depends(_identite_du_jeton)) -> str:\n"
            "    return payload.get('anon_handle', '')",
            "def get_current_anon_handle(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:\n"
            "    return _decode_and_verify_token(credentials).get('anon_handle', '')",
        ),
    )
    for current, disarmed in replacements:
        assert current in app
        app = app.replace(current, disarmed)
    return app


def test_contre_epreuve_deux_dependances_distinctes_font_rougir_le_compteur(
        tmp_path):
    _compile(tmp_path)
    app = (tmp_path / "app.py").read_text(encoding="utf-8")
    (tmp_path / "app.py").write_text(_disarm_shared_token_dependency(app),
                                    encoding="utf-8")
    with _server(tmp_path) as (base, trace_file):
        token = _authenticate(base, "double@example.test")
        trace_file.write_text("", encoding="utf-8")
        _create_commande(base, token)
        assert len(_revocation_selects(trace_file)) == 3
        with pytest.raises(AssertionError):
            _assert_one_revocation_lookup(trace_file)


def test_contre_epreuve_sans_controle_de_revocation_fait_rougir_le_temoins(
        tmp_path):
    _compile(tmp_path)
    app = (tmp_path / "app.py").read_text(encoding="utf-8")
    start = app.index("    jti = payload.get('jti')")
    end = app.index("    return payload\n", start)
    (tmp_path / "app.py").write_text(app[:start] + app[end:],
                                    encoding="utf-8")

    with _server(tmp_path) as (base, _trace_file):
        token = _authenticate(base, "revocation-desarmee@example.test")
        headers = {"Authorization": f"Bearer {token}"}
        logout = requests.post(f"{base}/logout", headers=headers, timeout=10)
        assert logout.status_code == 200, logout.text
        with pytest.raises(AssertionError):
            refused = requests.get(f"{base}/commande", headers=headers, timeout=10)
            assert refused.status_code == 401, refused.text
