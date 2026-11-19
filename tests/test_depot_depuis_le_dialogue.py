"""File upload born from the DIALOGUE, exercised over real HTTP (point 173).

`tests/test_uploads.py` tests the brick on a hand-written spec. This bench
starts from the other end: a user's answers to the guided dialogue, the spec
it produces, the server that spec produces, and a real uploaded file.

It is the distinction this project relearns with every brick: **compiling
is not behaving**. The dialogue → spec → server chain had never been walked
in full for this brick, and its author had said so in plain words — "not
measured".
"""

import contextlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import requests

from monl.app_templates import TEMPLATES
from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server
from tests.test_app_templates import _run_template

# A tiny but VALID PNG: the backend checks the byte signature, not the
# extension nor the type the client announces.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8cfc00000030101003c2d0b0b0000000049454e"
    "44ae426082"
)


@pytest.fixture(scope="module")
def server_from_the_dialogue():
    """Compiles what the dialogue produces, and really runs it."""
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Personal expense tracking")
    with contextlib.redirect_stdout(io.StringIO()):
        spec = _run_template(index, "n", False, upload_pour="Expense")
    assert "rule Expense.photo upload max" in spec, spec

    with TemporaryDirectory(prefix="monl-depot-dialogue-") as dossier:
        with contextlib.redirect_stdout(io.StringIO()):
            ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
            MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        stockage = Path(dossier).parent / f"{Path(dossier).name}.uploads"
        env = os.environ.copy()
        env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "depot-dialogue-secret-32-octets-minimum"
        env["MONL_UPLOADS_DIR"] = str(stockage)
        with uvicorn_server(dossier, env=env) as base:
            yield base


def _compte(base, nom):
    inscription = requests.post(
        f"{base}/register",
        json={"username": nom, "password": "motdepasse8", "actor": "User"},
        timeout=10)
    assert inscription.status_code == 200, inscription.text
    connexion = requests.post(
        f"{base}/login",
        json={"username": nom, "password": "motdepasse8"}, timeout=10)
    assert connexion.status_code == 200, connexion.text
    return {"Authorization": f"Bearer {connexion.json()['access_token']}"}


@pytest.fixture(scope="module")
def two_accounts(server_from_the_dialogue):
    """TWO accounts, otherwise "is the file private?" does not arise.

    With one, the question becomes "can I read my own file?", which a server
    without any check would answer yes. It is the trap named at points 81, 90
    and 116.
    """
    base = server_from_the_dialogue
    return base, _compte(base, "alice"), _compte(base, "bob")


def _budget(base, entetes, nom):
    """An expense belongs to a budget: the foreign key is CLIENT-supplied.

    It is brick 11 (transitive ownership): the column is not deduced from the
    token, so the client provides it — and the server checks it.
    """
    reponse = requests.post(
        f"{base}/budget", json={"name": nom, "limit": 500.0, "spent": 0.0},
        headers=entetes, timeout=10)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _depense(base, entetes, libelle):
    budget = _budget(base, entetes, f"budget-{libelle}")
    reponse = requests.post(
        f"{base}/expense",
        json={"label": libelle, "amount": 12.5, "spentOn": "2026-08-31",
              "category": "Repas", "budget_id": budget},
        headers=entetes, timeout=10)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def test_a_receipt_is_uploaded_and_read_back(two_accounts):
    base, alice, _bob = two_accounts
    identifiant = _depense(base, alice, "Déjeuner client")

    depot = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("recu.png", PNG, "image/png")},
        headers=alice, timeout=10)
    assert depot.status_code in (200, 201), depot.text

    relecture = requests.get(
        f"{base}/expense/{identifiant}/photo", headers=alice, timeout=10)
    assert relecture.status_code == 200, relecture.text
    assert relecture.content == PNG, "les octets rendus ne sont pas ceux déposés"


def test_another_accounts_receipt_stays_inaccessible(two_accounts):
    """The promise announced by the dialogue's question, checked.

    The dialogue says "the file will be readable only by its owner". A sentence
    is not a guarantee: this refusal is.
    """
    base, alice, bob = two_accounts
    identifiant = _depense(base, alice, "Note d'hôtel")
    depot = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("recu.png", PNG, "image/png")},
        headers=alice, timeout=10)
    assert depot.status_code in (200, 201), depot.text

    vol = requests.get(
        f"{base}/expense/{identifiant}/photo", headers=bob, timeout=10)
    assert vol.status_code in (403, 404), vol.status_code
    assert PNG not in vol.content

    sans_compte = requests.get(f"{base}/expense/{identifiant}/photo", timeout=10)
    assert sans_compte.status_code == 401, sans_compte.status_code


def test_the_limits_declared_by_the_dialogue_really_bite(two_accounts):
    """5 MiB and two image types: written by the dialogue, enforced here.

    The type is determined by the BYTE SIGNATURE and never by the name nor the
    announced type — an SVG renamed `.png` must be refused.
    """
    base, alice, _bob = two_accounts
    identifiant = _depense(base, alice, "Taxi")

    trop_gros = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("gros.png", PNG + b"x" * (5 * 1024 * 1024), "image/png")},
        headers=alice, timeout=30)
    assert trop_gros.status_code == 413, trop_gros.status_code

    deguise = requests.post(
        f"{base}/expense/{identifiant}/photo",
        files={"photo": ("faux.png", b"<svg>x</svg>", "image/png")},
        headers=alice, timeout=10)
    assert deguise.status_code == 415, deguise.status_code


def test_the_upload_question_speaks_english():
    """The upload choices are read by the person being guided: each one says
    its field, its byte limit and its types in English. One label stayed
    "— champ photo, 5242880 octets" after the migration; nothing read the
    printed question, since every test discarded the dialogue's output."""
    index = next(i for i, t in enumerate(TEMPLATES, 1)
                 if t["name"] == "Personal expense tracking")
    questions = []
    with contextlib.redirect_stdout(io.StringIO()):
        _run_template(index, "n", False, upload_pour="Expense", prompts=questions)
    texte = next((q for q in questions if "Which file upload for Expense?" in q), "")
    assert texte, questions
    assert "— field photo, " in texte and " bytes, types " in texte, texte
    assert "octets" not in texte and "champ" not in texte
