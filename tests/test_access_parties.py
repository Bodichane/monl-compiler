"""AJOUT (roadmap, écosystème de capacités -- brique "accès à deux parties") :
teste la règle 'rule Entite.Action accessibleBy col1, col2' sur l'exemple
canonique de la messagerie privée (exemples/19_private_messages.ml).

Deux volets :
  1. validations de compilation (sans serveur) : colonnes inconnues, mauvais
     type, action Create interdite, conflit avec 'ownedBy', parties non
     distinctes ;
  2. scénario réel (serveur uvicorn éphémère, compilé via --output dans un
     dossier temporaire) : l'expéditeur et le destinataire voient/suppriment
     le message, un tiers du même rôle est filtré de la liste et reçoit 403
     sur l'accès direct.
"""
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

# (spec e2e désormais autonome, voir E2E_SPEC plus bas)

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
    with pytest.raises(ASTValidationError, match="ni un champ déclaré"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Read",
                                   columns="user_id, colonne_inexistante", extra_rule=""))


def test_non_integer_column_is_rejected():
    with pytest.raises(ASTValidationError, match="type Integer"):
        _validate(BASE_SPEC.format(recipient_type="String", action="Read",
                                   columns="user_id, recipient_id", extra_rule=""))


def test_create_action_is_rejected():
    with pytest.raises(ASTValidationError, match="invalide"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Create",
                                   columns="user_id, recipient_id", extra_rule=""))


def test_conflict_with_ownedby_is_rejected():
    with pytest.raises(ASTValidationError, match=r"ownedBy.*accessibleBy|accessibleBy.*ownedBy"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Delete",
                                   columns="user_id, recipient_id",
                                   extra_rule="rule Message.Delete ownedBy User\n"))


def test_identical_parties_are_rejected():
    with pytest.raises(ASTValidationError, match="DISTINCTES"):
        _validate(BASE_SPEC.format(recipient_type="Integer", action="Read",
                                   columns="user_id, user_id", extra_rule=""))


# ---------------------------------------------------------------------------
# Volet 2 : scénario réel contre l'exemple canonique
# ---------------------------------------------------------------------------

def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


# Spec minimale autonome pour le scénario end-to-end (n'est plus liée à un
# fichier d'exemple, pour découpler le test de la consolidation des exemples).
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

            # Alice envoie un message privé à Bob.
            r = requests.post(f"{base}/message", headers=alice,
                              json={"content": "privé", "recipient_id": bob_id})
            assert r.status_code == 200, r.text
            msg_id = r.json()["id"]

            # Les deux parties voient le message dans leur liste, pas Carol.
            assert requests.get(f"{base}/message", headers=alice).json()["total"] == 1
            assert requests.get(f"{base}/message", headers=bob).json()["total"] == 1
            assert requests.get(f"{base}/message", headers=carol).json()["total"] == 0

            # Accès direct : parties OK, tiers 403 (même rôle User pourtant).
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
