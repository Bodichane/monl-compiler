"""Brick B1: final upload, file ACL and storage outside artifacts.

This test's client is deliberately as narrow as a frontend produced from the
contract: the multipart field, the 16-byte limit and the MIME types are
hard-coded here. A change to the rule must therefore break this smoke test,
as it would break a real checking client.
"""

from __future__ import annotations

import contextlib
import copy
import os
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import _contract_signature
from monl.frontend_contract import build_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app UploadSmoke

entity User
    name: String

entity Profile
    label: String
    avatar: Upload

relation User hasMany Profile
actor User selfRegister

rule Profile.Read ownedBy User
rule Profile.Update ownedBy User
rule Profile.Delete ownedBy User
rule Profile.avatar upload max 16 types "image/png", "image/jpeg"

workflow UserFlow for User
    Create Profile
    Read Profile
    Update Profile
    Delete Profile
"""

MAX_BYTES = 16
FIELD_NAME = "avatar"
ACCEPTED_TYPES = ("image/png", "image/jpeg")
PNG = b"\x89PNG\r\n\x1a\nsmoke"
PNG_REPLACEMENT = b"\x89PNG\r\n\x1a\nsecond"


@pytest.fixture(params=["sqlite", "postgres"])
def upload_database_url(request):
    if request.param == "sqlite":
        yield None
        return
    base = os.environ.get("MONL_TEST_DATABASE_URL", "").strip()
    if not base:
        pytest.skip("MONL_TEST_DATABASE_URL missing: integration PostgreSQL not requested")
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg absent : installer l'extra optionnel .[postgres]")
    schema = f"monl_upload_{uuid4().hex[:12]}"
    admin = psycopg.connect(base)
    try:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
    finally:
        admin.close()
    pieces = urlsplit(base)
    params = dict(parse_qsl(pieces.query, keep_blank_values=True))
    params["options"] = f"-c search_path={schema}"
    dsn = urlunsplit(pieces._replace(query=urlencode(params, quote_via=quote)))
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
def application(database_url):
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="monl-upload-") as directory:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=directory).generate_all()
        storage = Path(directory).parent / f"{Path(directory).name}.uploads"
        env = os.environ.copy()
        env.pop("MONL_DATABASE_URL", None)
        if database_url:
            env["MONL_DATABASE_URL"] = database_url
        env["MONL_JWT_SECRET"] = "upload-smoke-secret-32-bytes-minimum"
        env["MONL_UPLOADS_DIR"] = str(storage)
        with uvicorn_server(directory, env=env) as base:
            yield Path(directory), storage, base


def _account(base, name):
    response = requests.post(
        f"{base}/register", json={"username": name, "password": "motdepasse8", "actor": "User"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    response = requests.post(
        f"{base}/login", json={"username": name, "password": "motdepasse8"}, timeout=10,
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_the_upload_form_is_distinct_and_complete(capsys):
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    assert ast["schema"]["entities"]["Profile"][FIELD_NAME] == "Upload"
    assert ast["security"]["upload_fields"] == [{
        "entity": "Profile", "field": FIELD_NAME, "max_bytes": MAX_BYTES,
        "accepted_types": list(ACCEPTED_TYPES),
    }]
    capsys.readouterr()


def test_an_upload_without_rule_makes_no_false_promise(capsys):
    spec = SPEC.replace(
        'rule Profile.avatar upload max 16 types "image/png", "image/jpeg"\n', "")
    with pytest.raises(ASTValidationError, match="has no upload rule"):
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    capsys.readouterr()


def test_the_frontend_signature_sees_the_limit_and_types(capsys):
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    generator = MonlSecureGenerator(ast)
    contract = build_contract(ast, generator)
    initial = _contract_signature(contract)
    changed = copy.deepcopy(contract)
    changed["entities"]["Profile"]["fields"][1]["upload"]["max_bytes"] = 17
    assert _contract_signature(changed)[6] != initial[6]
    capsys.readouterr()


def test_html_and_svg_are_not_accepted_upload_types(capsys):
    spec = SPEC.replace(
        'rule Profile.avatar upload max 16 types "image/png", "image/jpeg"',
        'rule Profile.avatar upload max 16 types "text/html"',
    )
    with pytest.raises(
            ASTValidationError,
            match="Executable HTML and SVG are rejected by design"):
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    capsys.readouterr()


def test_real_upload_acl_bytes_limit_type_name_and_deletion(upload_database_url):
    with application(upload_database_url) as (directory, storage, base):
        alice = _account(base, f"alice-upload-{uuid4().hex[:8]}")
        bob = _account(base, f"bob-upload-{uuid4().hex[:8]}")
        created = requests.post(
            f"{base}/profile", headers=alice, json={"label": "privé"}, timeout=10,
        )
        assert created.status_code == 200, created.text
        profile_id = created.json()["id"]

        accepted = requests.post(
            f"{base}/profile/{profile_id}/{FIELD_NAME}",
            headers=alice,
            files={FIELD_NAME: ("../../etc/passwd\n", PNG, "text/html")},
            timeout=10,
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["content_type"] == ACCEPTED_TYPES[0]

        row = requests.get(f"{base}/profile/{profile_id}", headers=alice, timeout=10)
        assert row.status_code == 200, row.text
        reference = row.json()["data"][FIELD_NAME]
        assert len(reference) == 64 and all(c in "0123456789abcdef" for c in reference)
        stored = storage / "profile" / str(profile_id) / FIELD_NAME / reference
        assert stored.is_file() and ".." not in str(stored) and "\n" not in str(stored)

        replay = requests.get(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice, timeout=10,
        )
        assert replay.status_code == 200
        assert replay.content == PNG
        assert replay.headers["content-type"] == "application/octet-stream"
        assert replay.headers["x-content-type-options"] == "nosniff"

        other = requests.get(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=bob, timeout=10,
        )
        assert other.status_code == 404

        too_big = requests.post(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice,
            files={FIELD_NAME: ("valid.png", PNG + b"x" * (MAX_BYTES + 1), "image/png")},
            timeout=10,
        )
        assert too_big.status_code == 413
        forbidden = requests.post(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice,
            files={FIELD_NAME: ("looks.png", b"<svg>x</svg>", "image/png")},
            timeout=10,
        )
        assert forbidden.status_code == 415
        replay_after_refusals = requests.get(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice, timeout=10,
        )
        assert replay_after_refusals.content == PNG

        replaced = requests.post(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice,
            files={FIELD_NAME: ("normal.png", PNG_REPLACEMENT, "image/png")}, timeout=10,
        )
        assert replaced.status_code == 200, replaced.text
        new_reference = requests.get(
            f"{base}/profile/{profile_id}", headers=alice, timeout=10,
        ).json()["data"][FIELD_NAME]
        new_stored = storage / "profile" / str(profile_id) / FIELD_NAME / new_reference
        assert new_reference != reference and not stored.exists() and new_stored.is_file()

        direct = requests.get(
            f"{base}/.monl_uploads/profile/{profile_id}/{FIELD_NAME}/{new_reference}",
            timeout=10,
        )
        assert direct.status_code == 404

        deleted = requests.delete(
            f"{base}/profile/{profile_id}", headers=alice, timeout=10,
        )
        assert deleted.status_code == 200, deleted.text
        assert not new_stored.exists()
        assert requests.get(
            f"{base}/profile/{profile_id}/{FIELD_NAME}", headers=alice, timeout=10,
        ).status_code == 404
