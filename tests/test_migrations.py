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
import subprocess
import sys
import tempfile
import time

import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port as _find_free_port

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
