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

SPEC_MASKING = """app Registre

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
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC_MASKING)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        with uvicorn_server(folder) as base:
            yield base, folder


def _admin(base):
    requests.post(f"{base}/register",
                  json={"username": "chef", "password": "motdepasse123",
                        "actor": "Admin"})
    token = requests.post(f"{base}/login",
                          json={"username": "chef", "password": "motdepasse123"}).json()
    return {"Authorization": "Bearer " + token["access_token"]}


def test_the_hidden_field_disappears_from_reads_and_stays_stored(application):
    base, folder = application
    headers = _admin(base)

    created = requests.post(f"{base}/note", headers=headers,
                         json={"title": "Devis Aurora",
                               "internalNote": "marge 42%, ne pas divulguer"})
    assert created.status_code in (200, 201), created.text
    note_id = created.json().get("id") or created.json().get("data", {}).get("id")
    assert note_id, created.text

    # 1. The LIST does not show the field — not even to the signed-in author.
    list_ = requests.get(f"{base}/note", headers=headers).json()
    lines = list_["data"]
    assert lines, list_
    for line in lines:
        assert "title" in line
        assert "internalNote" not in line, f"hidden field exposed in list: {line}"

    # 2. Nor does the DETAIL.
    detail = requests.get(f"{base}/note/{note_id}", headers=headers).json()
    body = detail.get("data", detail)
    assert body.get("title") == "Devis Aurora", detail
    assert "internalNote" not in body, f"hidden field exposed in detail: {detail}"

    # 3. Nor without an account (reading is public here): masking does not
    # depend on the caller, unlike ownedBy.
    anonymous = requests.get(f"{base}/note/{note_id}").json()
    assert "internalNote" not in anonymous.get("data", anonymous)

    # 4. The field stays WRITABLE — masking is not removing.
    maj = requests.put(f"{base}/note/{note_id}", headers=headers,
                       json={"title": "Devis Aurora",
                             "internalNote": "marge revue à 38%"})
    assert maj.status_code == 200, maj.text

    # 5. And it is indeed in the database: hidden on read, not lost.
    conn = sqlite3.connect(os.path.join(folder, "app.db"))
    try:  # `with connect(...)` commits the transaction, it does not close.
        table = next(name for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
            if name.lower().startswith("note"))
        valeur = conn.execute(
            f'SELECT internalNote FROM "{table}" WHERE id = ?', (note_id,)).fetchone()
    finally:
        conn.close()
    assert valeur and valeur[0] == "marge revue à 38%", valeur


def test_the_hidden_field_is_missing_from_the_read_contract(application):
    """The frontend contract describes what the routes return: announcing a field
    the server removes would send the interface AI drawing an always-empty
    column."""
    base, _folder = application
    schema = requests.get(f"{base}/openapi.json").json()
    text = str(schema)
    assert "internalNote" in text, "the field must exist for writing"
    lecture = schema["paths"]["/note/{id}"]["get"]
    assert "internalNote" not in str(lecture), lecture
