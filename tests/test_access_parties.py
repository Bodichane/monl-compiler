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


# ---------------------------------------------------------------------------
# AJOUT (brique 23, point 106) : rôle superviseur au-dessus d'accessibleBy.
# Un role nomme via 'sharedBy' sur la MEME reference transperce le controle
# par colonnes : il lit / modifie / supprime TOUS les enregistrements d'une
# action regie par 'accessibleBy'. C'est pour accessibleBy le pendant du
# superviseur deja acquis pour ownedBy au point 88.
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
    # La suppression est regie par deux acteurs (User et Moderator) : grace a
    # l'exemption 'accessibleBy' (miroir de 'ownedBy'), pas de CRITICAL_COLLISION.
    assert "Message.Delete" in ast["security"]["access_parties"]


def test_supervisor_must_be_a_declared_actor():
    with pytest.raises(ASTValidationError, match="pas un acteur"):
        _validate(SUPER_SPEC.replace("rule Message.Read sharedBy Moderator",
                                     "rule Message.Read sharedBy Spectateur"))


def test_supervisor_from_sharedby_not_party_access():
    """Un 'sharedBy' porte sur une action SANS 'accessibleBy' ne produit
    aucun superviseur — c'est le partage de privilege historique, inchangé."""
    # E2E_SPEC ne declare aucun 'sharedBy' : aucun superviseur, partout.
    ast = _validate(E2E_SPEC)
    assert ast["security"]["access_supervisors"] == {}


# Spec e2e autonome du superviseur.
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
    """Insere un compte Moderator dans app.db, meme hachage pbkdf2 que
    manage.py adduser — le seul moyen de creer un role non-selfRegister."""
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

            # Le moderateur voit TOUT (le filtre de parties est transperce).
            assert requests.get(f"{base}/message", headers=mod).json()["total"] == 1
            assert requests.get(f"{base}/message/{msg_id}", headers=mod).status_code == 200

            # Carol, tier du meme role User, reste confinee : 0 en liste, 403 en direct.
            assert requests.get(f"{base}/message", headers=carol).json()["total"] == 0
            assert requests.get(f"{base}/message/{msg_id}", headers=carol).status_code == 403

            # Le moderateur supprime ce qu'il n'expedie ni ne recoit.
            assert requests.delete(f"{base}/message/{msg_id}", headers=mod).status_code == 200
            assert requests.get(f"{base}/message", headers=mod).json()["total"] == 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
