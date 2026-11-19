"""ADDED (long-term roadmap, migrations without data loss): checks that adding
fields to a spec then recompiling in the same folder preserves the data
already present and makes the new columns usable, without resetting the
database.

The test compiles a v1 spec, inserts a row through a real server, stops the
server, recompiles a v2 spec (two fields added to an entity + a new entity)
IN THE SAME FOLDER keeping app.db, restarts, and checks:
  - the v1 row is still there and correctly aligned (the column shift bug,
    where ADD COLUMN puts new columns at the end of the table while the read
    code assumed another order, is covered here);
  - the new columns exist and accept writes;
  - the new table is created.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

import requests

from monl.ast_validator import MonlAST
from monl.cli import compile_project
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port as _find_free_port

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "src"))


def _cli_env():
    return {**os.environ, "PYTHONPATH": SRC_DIR}

SPEC_V1 = """app MigApp

entity User
    name: String

entity Note
    title: String

relation User hasMany Note

actor User selfRegister

rule Note.title required

workflow W for User
    Create Note
    Read Note
"""

SPEC_V2 = """app MigApp

entity User
    name: String
    email: Email

entity Note
    title: String
    body: Text
    priority: Integer

entity Tag
    label: String

relation User hasMany Note

actor User selfRegister

rule Note.title required

workflow W for User
    Create Note
    Read Note
"""


def _wait(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def _compile(spec, workdir):
    ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=workdir).generate_all()


def _compile_cli(spec, workdir):
    spec_path = os.path.join(workdir, "spec.ml")
    with open(spec_path, "w", encoding="utf-8") as file:
        file.write(spec)
    compile_project(spec_path, workdir)


def _serve(workdir, port):
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
        cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert _wait(port), "le serveur n'a pas démarré"
    return proc


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _serve_expected_failure(workdir):
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(_find_free_port())],
        cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        output, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
        raise AssertionError("le serveur a démarré malgré le schéma non migré") from None
    return proc.returncode, output


def test_additive_migration_preserves_data():
    with tempfile.TemporaryDirectory() as workdir:
        # --- v1: insert a row ---
        _compile(SPEC_V1, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            base = f"http://127.0.0.1:{port}"
            requests.post(f"{base}/register",
                          json={"username": "u", "password": "motdepasse8", "actor": "User"})
            tok = requests.post(f"{base}/login",
                                json={"username": "u", "password": "motdepasse8"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {tok}"}
            r = requests.post(f"{base}/note", headers=headers, json={"title": "note v1"})
            assert r.status_code == 200, r.text
            note_id = r.json()["id"]
        finally:
            _stop(proc)

        # --- v2: recompile in the same folder, app.db kept ---
        assert os.path.exists(os.path.join(workdir, "app.db"))
        _compile(SPEC_V2, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            base = f"http://127.0.0.1:{port}"
            tok = requests.post(f"{base}/login",
                                json={"username": "u", "password": "motdepasse8"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {tok}"}

            # The v1 row survived, correctly aligned.
            r = requests.get(f"{base}/note/{note_id}", headers=headers)
            assert r.status_code == 200, r.text
            data = r.json()["data"]
            assert data["title"] == "note v1"       # champ d'origine intact
            assert data["user_id"] == 1              # FK correctly aligned (not shifted)
            assert data["body"] is None              # new column, NULL default
            assert data["priority"] is None

            # The new columns accept writes.
            r = requests.post(f"{base}/note", headers=headers,
                              json={"title": "note v2", "body": "corps", "priority": 5})
            assert r.status_code == 200, r.text
            new_id = r.json()["id"]
            data2 = requests.get(f"{base}/note/{new_id}", headers=headers).json()["data"]
            assert data2["body"] == "corps"
            assert data2["priority"] == 5
        finally:
            _stop(proc)

        history = sqlite3.connect(os.path.join(workdir, "app.db"))
        try:
            rows = history.execute(
                "SELECT migration_name, operation, direction, schema_fingerprint "
                "FROM _monl_migrations ORDER BY id"
            ).fetchall()
        finally:
            history.close()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            ("__auto_add_column__", "add_column", "up"),
            ("__auto_add_column__", "add_column", "up"),
            ("__auto_add_column__", "add_column", "up"),
        ]
        assert all(len(row[3]) == 64 for row in rows)


def test_non_additive_migration_is_named_refused_then_applied():
    spec_v1 = """app MigNonAdditive

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
    with tempfile.TemporaryDirectory() as workdir:
        _compile_cli(spec_v1, workdir)
        subprocess.run(
            [sys.executable, "-c", (
                "import app; app.init_db(); c=app._connect(); "
                "c.execute(\"INSERT INTO _monl_users "
                "(username,password_hash,salt,actor,anon_handle) "
                "VALUES (?,?,?,?,?)\", ('u','x','s','User','Anon#1111')); "
                "c.execute('INSERT INTO note (title,priority,legacy,user_id) "
                "VALUES (?,?,?,?)', ('avant','7','a garder',1)); c.commit(); c.close()"
            )], cwd=workdir, check=True,
        )
        _compile_cli(spec_v2, workdir)

        returncode, output = _serve_expected_failure(workdir)
        assert returncode != 0
        assert "Non-additive schema detected" in output
        assert "rename not applied" in output
        assert "type of note.priority" in output
        assert "column removed from the spec" in output
        assert "the database will not be served" in output

        migrate = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", workdir,
             "--name", "note_fields"],
            cwd="/tmp", env=_cli_env(),
            capture_output=True, text=True, check=False,
        )
        assert migrate.returncode == 0, migrate.stdout + migrate.stderr
        assert "Migration 'note_fields' (up) applied" in migrate.stdout

        subprocess.run(
            [sys.executable, "-c", (
                "import app; app.init_db(); c=app._connect(); "
                "assert c.execute('SELECT heading, priority FROM note').fetchone() == ('avant', 7); "
                "assert [r[1] for r in c.execute('PRAGMA table_info(\\\"note\\\")')] == "
                "['id','heading','priority','user_id']; "
                "h=c.execute('SELECT migration_name, operation_index, direction, schema_fingerprint "
                "FROM _monl_migrations ORDER BY id').fetchall(); "
                "assert len(h) == 3 and all(row[0] == 'note_fields' and row[2] == 'up' "
                "and len(row[3]) == 64 for row in h); c.close()"
            )], cwd=workdir, check=True,
        )
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
            assert response.status_code == 200
        finally:
            _stop(proc)


def test_reversible_migration_restores_the_earlier_schema():
    spec_v1 = """app MigDown

entity Note
    title: String
    priority: String

actor User selfRegister
workflow W for User
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String", "    heading: String")
    spec_v2 = spec_v2.replace("    priority: String", "    priority: Integer")
    spec_v2 += """
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
"""
    with tempfile.TemporaryDirectory() as workdir:
        _compile_cli(spec_v1, workdir)
        subprocess.run(
            [sys.executable, "-c", (
                "import app; app.init_db(); c=app._connect(); "
                "c.execute('INSERT INTO note (title,priority) VALUES (?,?)', ('avant','7')); "
                "c.commit(); c.close()"
            )], cwd=workdir, check=True,
        )
        _compile_cli(spec_v2, workdir)
        apply = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", workdir,
             "--name", "note_fields"], cwd="/tmp", env=_cli_env(), capture_output=True,
            text=True, check=False,
        )
        assert apply.returncode == 0, apply.stdout + apply.stderr
        down = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", workdir,
             "--name", "note_fields", "--down"], cwd="/tmp", env=_cli_env(),
            capture_output=True, text=True, check=False,
        )
        assert down.returncode == 0, down.stdout + down.stderr
        subprocess.run(
            [sys.executable, "-c", (
                "import app; c=app._connect(); info=c.execute('PRAGMA table_info(\\\"note\\\")').fetchall(); "
                "assert [r[1] for r in info] == ['id','title','priority']; "
                "assert dict((r[1],r[2]) for r in info)['priority'] == 'VARCHAR(255)'; "
                "assert c.execute('SELECT title,priority FROM note').fetchone() == ('avant','7'); "
                "h=c.execute('SELECT direction FROM _monl_migrations ORDER BY id').fetchall(); "
                "assert [r[0] for r in h] == ['up','up','down','down']; c.close()"
            )], cwd=workdir, check=True,
        )
        # Recompiling the earlier spec makes the database servable again.
        _compile_cli(spec_v1, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        _stop(proc)


def test_migration_failure_is_atomic_and_serves_no_half():
    spec_v1 = """app MigAtomic

entity Note
    title: String
    priority: String

actor User selfRegister
workflow W for User
    Read Note
"""
    spec_v2 = spec_v1.replace("    title: String", "    heading: String")
    spec_v2 = spec_v2.replace("    priority: String", "    priority: Float")
    spec_v2 += """
migration broken
    rename Note.title to heading
    alter Note.priority from Integer to Float
"""
    with tempfile.TemporaryDirectory() as workdir:
        _compile_cli(spec_v1, workdir)
        subprocess.run(
            [sys.executable, "-c", (
                "import app; app.init_db(); c=app._connect(); "
                "c.execute('INSERT INTO note (title,priority) VALUES (?,?)', ('avant','7')); "
                "c.commit(); c.close()"
            )], cwd=workdir, check=True,
        )
        _compile_cli(spec_v2, workdir)
        failed = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", workdir,
             "--name", "broken"], cwd="/tmp", env=_cli_env(), capture_output=True,
            text=True, check=False,
        )
        assert failed.returncode != 0
        assert "Precondition of the type change" in failed.stdout
        subprocess.run(
            [sys.executable, "-c", (
                "import app; c=app._connect(); info=c.execute('PRAGMA table_info(\\\"note\\\")').fetchall(); "
                "assert [r[1] for r in info] == ['id','title','priority']; "
                "assert c.execute('SELECT title,priority FROM note').fetchone() == ('avant','7'); "
                "assert c.execute('SELECT COUNT(*) FROM _monl_migrations').fetchone()[0] == 0; c.close()"
            )], cwd=workdir, check=True,
        )
        returncode, output = _serve_expected_failure(workdir)
        assert returncode != 0 and "the database will not be served" in output


def test_manage_py_names_the_remedy_instead_of_dumping_a_trace():
    """Defect found while reviewing A2. On a database awaiting a non-additive
    migration, `manage.py` refuses to write — rightly: provisioning an account in
    a pending schema puts it at the same risk as serving it. But it exited on an
    UNCAUGHT `RuntimeError`: app.py's diagnostic, correct and precise, was
    drowned under fifteen lines of traceback.

    A traceback teaches nothing to whoever must decide what to do. It is the
    complaint of points 97 and 105, on a third entry point: the output must NAME
    the remedy and the folder concerned. `manage.py` is moreover the ONLY path to
    create a privileged-role account, so its message is the one a blocked
    operator reads."""
    with tempfile.TemporaryDirectory() as workdir:
        _compile_cli(SPEC_V2, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            _wait(port)
        finally:
            _stop(proc)

        # The v1 spec has one field fewer than the database created by v2: it
        # is a non-additive removal, without a declared `migration`.
        _compile_cli(SPEC_V1, workdir)
        resultat = subprocess.run(
            [sys.executable, os.path.join(workdir, "manage.py"), "users"],
            cwd=tempfile.gettempdir(), env=_cli_env(),
            capture_output=True, text=True,
        )

    sortie = resultat.stdout + resultat.stderr
    assert resultat.returncode != 0, "administrer une base en attente doit échouer"
    assert "Traceback" not in sortie, f"trace brute au lieu d'un diagnostic :\n{sortie}"
    assert "monl migrate" in sortie, "la sortie doit nommer le remède"
    assert workdir in sortie, "la sortie doit nommer le dossier concerné"
