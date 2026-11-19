"""ADDED (roadmap, capability ecosystem -- "two-party access" brick): tests
the rule 'rule Entite.Action accessibleBy col1, col2' on the canonical
private messaging example (exemples/19_private_messages.ml).

Two parts:
  1. compile-time validations (no server): unknown columns, wrong type,
     forbidden Create action, conflict with 'ownedBy', non-distinct parties;
  2. real scenario (ephemeral uvicorn server, compiled through --output into
     a temporary folder): sender and recipient see/delete the message, a
     third party with the same role is filtered out of the list and gets 403
     on direct access.
"""
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port as _find_free_port

# (e2e spec now self-contained, see E2E_SPEC below)

BASE_SPEC = """app T

entity User
    name: String

entity Message
    content: Text
    recipient_id: {recipient_type}

relation User hasMany Message

actor User selfRegister

rule Message.{action} accessibleBy {columns}
{extra_rule}
workflow M for User
    Create Message
    Read Message
    Delete Message
"""


def _validate(spec):
    raw = parse_monl_string(spec)
    return MonlAST(raw).validate_and_audit()


def test_valid_spec_exports_access_parties():
    ast = _validate(BASE_SPEC.format(recipient_type="Integer", action="Read",
                                     columns="user_id, recipient_id", extra_rule=""))
    assert ast["security"]["access_parties"] == {"Message.Read": ["user_id", "recipient_id"]}


def test_unknown_column_is_rejected():
    with pytest.raises(ASTValidationError, match="neither a declared field"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Read",
                                   columns="user_id, colonne_inexistante", extra_rule=""))


def test_non_integer_column_is_rejected():
    with pytest.raises(ASTValidationError, match="type Integer"):
        _validate(BASE_SPEC.format(recipient_type="String", action="Read",
                                   columns="user_id, recipient_id", extra_rule=""))


def test_create_action_is_rejected():
    with pytest.raises(ASTValidationError, match="invalid action"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Create",
                                   columns="user_id, recipient_id", extra_rule=""))


def test_conflict_with_ownedby_is_rejected():
    with pytest.raises(ASTValidationError, match=r"ownedBy.*accessibleBy|accessibleBy.*ownedBy"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Delete",
                                   columns="user_id, recipient_id",
                                   extra_rule="rule Message.Delete ownedBy User\n"))


def test_identical_parties_are_rejected():
    with pytest.raises(ASTValidationError, match="distinct columns"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Read",
                                   columns="user_id, user_id", extra_rule=""))


# ---------------------------------------------------------------------------
# Part 2: real scenario against the canonical example
# ---------------------------------------------------------------------------

def _wait_for_server(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


def _register_and_login(base_url, username):
    r = requests.post(f"{base_url}/register",
                      json={"username": username, "password": "motdepasse8", "actor": "User"})
    assert r.status_code == 200, r.text
    user_id = r.json()["user_id"]
    r = requests.post(f"{base_url}/login",
                      json={"username": username, "password": "motdepasse8"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


# Minimal self-contained spec for the end-to-end scenario (no longer tied to an
# example file, to decouple the test from the examples' consolidation).
E2E_SPEC = """app Msg

entity User
    name: String

entity Message
    content: Text
    recipient_id: Integer

relation User hasMany Message

actor User selfRegister

rule Message.content required
rule Message.Read accessibleBy user_id, recipient_id
rule Message.Delete accessibleBy user_id, recipient_id

workflow M for User
    Create Message
    Read Message
    Delete Message
"""


def test_private_messaging_end_to_end():
    with tempfile.TemporaryDirectory() as workdir:
        raw = parse_monl_string(E2E_SPEC)
        ast = MonlAST(raw).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            assert _wait_for_server(port), "le serveur n'a pas démarré"
            base = f"http://127.0.0.1:{port}"

            alice_id, alice = _register_and_login(base, "alice")
            bob_id, bob = _register_and_login(base, "bob")
            carol_id, carol = _register_and_login(base, "carol")

            # Alice sends Bob a private message.
            r = requests.post(f"{base}/message", headers=alice,
                              json={"content": "privé", "recipient_id": bob_id})
            assert r.status_code == 200, r.text
            msg_id = r.json()["id"]

            # Both parties see the message in their list, Carol does not.
            assert requests.get(f"{base}/message", headers=alice).json()["total"] == 1
            assert requests.get(f"{base}/message", headers=bob).json()["total"] == 1
            assert requests.get(f"{base}/message", headers=carol).json()["total"] == 0

            # Direct access: parties OK, third party 403 (same User role,
            # though).
            assert requests.get(f"{base}/message/{msg_id}", headers=bob).status_code == 200
            assert requests.get(f"{base}/message/{msg_id}", headers=alice).status_code == 200
            assert requests.get(f"{base}/message/{msg_id}", headers=carol).status_code == 403

            # Suppression : tiers 403, destinataire OK.
            assert requests.delete(f"{base}/message/{msg_id}", headers=carol).status_code == 403
            assert requests.delete(f"{base}/message/{msg_id}", headers=bob).status_code == 200
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


# ---------------------------------------------------------------------------
# ADDED (brick 23, point 106): supervisor role above accessibleBy. A role named
# through 'sharedBy' on the SAME reference pierces the column check: it reads /
# updates / deletes ALL records of an action governed by 'accessibleBy'. It is,
# for accessibleBy, the counterpart of the supervisor already acquired for
# ownedBy at point 88.
# ---------------------------------------------------------------------------

SUPER_SPEC = """app T

entity User
    name: String

entity Message
    content: Text
    recipient_id: Integer

relation User hasMany Message

actor User selfRegister
actor Moderator

rule Message.content required
rule Message.Read accessibleBy user_id, recipient_id
rule Message.Read sharedBy Moderator
rule Message.Delete accessibleBy user_id, recipient_id
rule Message.Delete sharedBy Moderator

workflow M for User
    Create Message
    Read Message
    Delete Message

workflow Moderate for Moderator
    Read Message
    Delete Message
"""


def test_supervisor_exported_without_collision():
    ast = _validate(SUPER_SPEC)
    assert ast["security"]["access_supervisors"] == {
        "Message.Read": ["Moderator"],
        "Message.Delete": ["Moderator"],
    }
    # Deletion is governed by two actors (User and Moderator): thanks to the
    # 'accessibleBy' exemption (mirror of 'ownedBy'), no CRITICAL_COLLISION.
    assert "Message.Delete" in ast["security"]["access_parties"]


def test_supervisor_must_be_a_declared_actor():
    with pytest.raises(ASTValidationError, match="not a declared actor"):
        _validate(SUPER_SPEC.replace("rule Message.Read sharedBy Moderator",
                                     "rule Message.Read sharedBy Spectateur"))


def test_supervisor_from_sharedby_not_party_access():
    """A 'sharedBy' on an action WITHOUT 'accessibleBy' produces no supervisor —
    it is the historical privilege sharing, unchanged."""
    # E2E_SPEC declares no 'sharedBy': no supervisor, anywhere.
    ast = _validate(E2E_SPEC)
    assert ast["security"]["access_supervisors"] == {}


# Self-contained e2e spec of the supervisor.
SUPER_E2E_SPEC = """app MsgMod

entity User
    name: String

entity Message
    content: Text
    recipient_id: Integer

relation User hasMany Message

actor User selfRegister
actor Moderator

rule Message.content required
rule Message.Read accessibleBy user_id, recipient_id
rule Message.Read sharedBy Moderator
rule Message.Delete accessibleBy user_id, recipient_id
rule Message.Delete sharedBy Moderator

workflow M for User
    Create Message
    Read Message
    Delete Message

workflow Moderate for Moderator
    Read Message
    Delete Message
"""


def _login(base_url, username, password):
    r = requests.post(f"{base_url}/login",
                      json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _provision_moderator(workdir, username="mod", password="moderateur8"):
    """Inserts a Moderator account into app.db, same pbkdf2 hash as manage.py
    adduser — the only way to create a non-selfRegister role."""
    salt_hex = "6d6f6e6c2d746573742d73616c742d00"
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000).hex()
    conn = sqlite3.connect(os.path.join(workdir, "app.db"))
    conn.execute(
        "INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) "
        "VALUES (?, ?, ?, ?, ?)",
        (username, pwd_hash, salt_hex, "Moderator", "Anon#7777"))
    conn.commit()
    conn.close()


def test_supervisor_moderates_private_messages_end_to_end():
    with tempfile.TemporaryDirectory() as workdir:
        raw = parse_monl_string(SUPER_E2E_SPEC)
        ast = MonlAST(raw).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=workdir).generate_all()

        port = _find_free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            assert _wait_for_server(port), "le serveur n'a pas démarré"
            base = f"http://127.0.0.1:{port}"

            alice_id, alice = _register_and_login(base, "alice")
            bob_id, bob = _register_and_login(base, "bob")
            _, carol = _register_and_login(base, "carol")
            _provision_moderator(workdir)
            mod = _login(base, "mod", "moderateur8")

            # Alice ecrit a Bob.
            r = requests.post(f"{base}/message", headers=alice,
                              json={"content": "privé", "recipient_id": bob_id})
            assert r.status_code == 200, r.text
            msg_id = r.json()["id"]

            # The moderator sees EVERYTHING (the parties filter is pierced).
            assert requests.get(f"{base}/message", headers=mod).json()["total"] == 1
            assert requests.get(f"{base}/message/{msg_id}", headers=mod).status_code == 200

            # Carol, a third party with the same User role, stays confined: 0
            # in the list, 403 directly.
            assert requests.get(f"{base}/message", headers=carol).json()["total"] == 0
            assert requests.get(f"{base}/message/{msg_id}", headers=carol).status_code == 403

            # The moderator deletes what they neither send nor receive.
            assert requests.delete(f"{base}/message/{msg_id}", headers=mod).status_code == 200
            assert requests.get(f"{base}/message", headers=mod).json()["total"] == 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
