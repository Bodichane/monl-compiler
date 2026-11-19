"""Field masking — `rule Entite.champ hidden` (brick 2, point 25).

This rule was implemented (src/parser.py `masking_rule`,
src/generator/routes.py) and **covered by nothing**: since
exemples/13_anon_forum_demo.yaml was removed in beta 3, the `hidden` keyword
appeared in no test and no example. Point 63's coverage measurement confirmed
it, CLAUDE.md already warned about it: a regression went through CI without a
sound.

What the rule promises, and what this file tests against a real server: the
field disappears from the LIST and the DETAIL, for everyone — but it stays
writable, and it stays in the database.
"""
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC_MASQUAGE = """app Registre

entity Note
    title: String
    internalNote: String

actor Admin selfRegister

rule Note.Read public
rule Note.internalNote hidden

workflow GererNote for Admin
    Create Note
    Read Note
    Update Note
    Delete Note
"""


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_MASQUAGE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            yield base, dossier


def _admin(base):
    requests.post(f"{base}/register",
                  json={"username": "chef", "password": "motdepasse123",
                        "actor": "Admin"})
    jeton = requests.post(f"{base}/login",
                          json={"username": "chef", "password": "motdepasse123"}).json()
    return {"Authorization": "Bearer " + jeton["access_token"]}


def test_the_hidden_field_disappears_from_reads_and_stays_stored(application):
    base, dossier = application
    entetes = _admin(base)

    cree = requests.post(f"{base}/note", headers=entetes,
                         json={"title": "Devis Aurora",
                               "internalNote": "marge 42%, ne pas divulguer"})
    assert cree.status_code in (200, 201), cree.text
    note_id = cree.json().get("id") or cree.json().get("data", {}).get("id")
    assert note_id, cree.text

    # 1. The LIST does not show the field — not even to the signed-in author.
    liste = requests.get(f"{base}/note", headers=entetes).json()
    lignes = liste["data"]
    assert lignes, liste
    for ligne in lignes:
        assert "title" in ligne
        assert "internalNote" not in ligne, f"champ masqué exposé en liste : {ligne}"

    # 2. Nor does the DETAIL.
    detail = requests.get(f"{base}/note/{note_id}", headers=entetes).json()
    corps = detail.get("data", detail)
    assert corps.get("title") == "Devis Aurora", detail
    assert "internalNote" not in corps, f"champ masqué exposé en détail : {detail}"

    # 3. Nor without an account (reading is public here): masking does not
    # depend on the caller, unlike ownedBy.
    anonyme = requests.get(f"{base}/note/{note_id}").json()
    assert "internalNote" not in anonyme.get("data", anonyme)

    # 4. The field stays WRITABLE — masking is not removing.
    maj = requests.put(f"{base}/note/{note_id}", headers=entetes,
                       json={"title": "Devis Aurora",
                             "internalNote": "marge revue à 38%"})
    assert maj.status_code == 200, maj.text

    # 5. And it is indeed in the database: hidden on read, not lost.
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:  # `with connect(...)` commits the transaction, it does not close.
        table = next(nom for (nom,) in cnx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
            if nom.lower().startswith("note"))
        valeur = cnx.execute(
            f'SELECT internalNote FROM "{table}" WHERE id = ?', (note_id,)).fetchone()
    finally:
        cnx.close()
    assert valeur and valeur[0] == "marge revue à 38%", valeur


def test_the_hidden_field_is_absent_from_the_read_contract(application):
    """The frontend contract describes what the routes return: announcing a field
    the server removes would send the interface AI drawing an always-empty
    column."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()
    texte = str(schema)
    assert "internalNote" in texte, "le champ doit exister en écriture"
    lecture = schema["paths"]["/note/{id}"]["get"]
    assert "internalNote" not in str(lecture), lecture
