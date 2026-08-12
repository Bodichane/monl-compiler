"""AJOUT (roadmap long terme, migrations sans perte de données) : vérifie
qu'ajouter des champs à une spec puis recompiler dans le même dossier
préserve les données déjà présentes et rend les nouvelles colonnes
utilisables, sans réinitialiser la base.

Le test compile une spec v1, insère une donnée via un vrai serveur, arrête
le serveur, recompile une spec v2 (deux champs ajoutés à une entité + une
nouvelle entité) DANS LE MÊME DOSSIER en conservant app.db, redémarre, et
vérifie :
  - la donnée v1 est toujours là et correctement alignée (le bug de
    décalage de colonnes, où ADD COLUMN place les nouvelles colonnes en fin
    de table alors que le code de lecture supposait un autre ordre, est
    couvert ici) ;
  - les nouvelles colonnes existent et acceptent des écritures ;
  - la nouvelle table est créée.
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
        # --- v1 : insère une donnée ---
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

        # --- v2 : recompile dans le même dossier, app.db conservée ---
        assert os.path.exists(os.path.join(workdir, "app.db"))
        _compile(SPEC_V2, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            base = f"http://127.0.0.1:{port}"
            tok = requests.post(f"{base}/login",
                                json={"username": "u", "password": "motdepasse8"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {tok}"}

            # La donnée v1 a survécu, correctement alignée.
            r = requests.get(f"{base}/note/{note_id}", headers=headers)
            assert r.status_code == 200, r.text
            data = r.json()["data"]
            assert data["title"] == "note v1"       # champ d'origine intact
            assert data["user_id"] == 1              # FK correctement alignée (pas décalée)
            assert data["body"] is None              # nouvelle colonne, défaut NULL
            assert data["priority"] is None

            # Les nouvelles colonnes acceptent des écritures.
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


def test_migration_non_additive_est_nommee_refusee_puis_appliquee():
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
        assert "Schéma non additif détecté" in output
        assert "renommage non appliqué" in output
        assert "type de note.priority" in output
        assert "colonne retirée" in output
        assert "base ne sera pas servie" in output

        migrate = subprocess.run(
            [sys.executable, "-m", "monl.cli", "migrate", workdir,
             "--name", "note_fields"],
            cwd="/tmp", env=_cli_env(),
            capture_output=True, text=True, check=False,
        )
        assert migrate.returncode == 0, migrate.stdout + migrate.stderr
        assert "Migration 'note_fields' (up) appliquée" in migrate.stdout

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


def test_migration_reversible_retablit_le_schema_avant():
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
        # Recompiler la spec d'avant rend à nouveau la base servable.
        _compile_cli(spec_v1, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        _stop(proc)


def test_echec_de_migration_est_atomique_et_ne_sert_pas_un_moitie():
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
        assert "Précondition du changement de type" in failed.stdout
        subprocess.run(
            [sys.executable, "-c", (
                "import app; c=app._connect(); info=c.execute('PRAGMA table_info(\\\"note\\\")').fetchall(); "
                "assert [r[1] for r in info] == ['id','title','priority']; "
                "assert c.execute('SELECT title,priority FROM note').fetchone() == ('avant','7'); "
                "assert c.execute('SELECT COUNT(*) FROM _monl_migrations').fetchone()[0] == 0; c.close()"
            )], cwd=workdir, check=True,
        )
        returncode, output = _serve_expected_failure(workdir)
        assert returncode != 0 and "base ne sera pas servie" in output


def test_manage_py_nomme_le_remede_au_lieu_de_dechirer_une_trace():
    """Défaut trouvé en revue de A2. Sur une base qui attend une migration non
    additive, `manage.py` refuse d'écrire — c'est juste : provisionner un
    compte dans un schéma en attente le met au même risque que le servir. Mais
    il sortait sur un `RuntimeError` NON RATTRAPÉ : le diagnostic d'app.py,
    correct et précis, se retrouvait noyé sous quinze lignes de trace.

    Une trace n'apprend rien à qui doit décider quoi faire. C'est le reproche
    des points 97 et 105, sur un troisième point d'entrée : la sortie doit
    NOMMER le remède et le dossier concerné. `manage.py` est par ailleurs le
    SEUL chemin pour créer un compte à rôle privilégié, donc son message est
    celui que lit un exploitant bloqué."""
    with tempfile.TemporaryDirectory() as workdir:
        _compile_cli(SPEC_V2, workdir)
        port = _find_free_port()
        proc = _serve(workdir, port)
        try:
            _wait(port)
        finally:
            _stop(proc)

        # La spec v1 a un champ de moins que la base créée par la v2 :
        # c'est un retrait non additif, sans `migration` déclarée.
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
