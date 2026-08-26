import sqlite3

import pytest

from monl_platform.identity import IdentityError, IdentityStore


def test_compte_session_et_mot_de_passe_hache(tmp_path):
    store = IdentityStore(tmp_path)
    user = store.register(" Alice@Example.COM ", "mot-de-passe-solide")
    assert user["email"] == "alice@example.com"
    assert store.authenticate("alice@example.com", "incorrect") is None
    assert store.authenticate("ALICE@example.com", "mot-de-passe-solide") == user

    token = store.create_session(user["id"])
    assert store.session_user(token) == user
    store.revoke_session(token)
    assert store.session_user(token) is None

    with sqlite3.connect(store.path) as db:
        password_hash, salt = db.execute(
            "SELECT password_hash, password_salt FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    assert b"mot-de-passe" not in password_hash
    assert len(password_hash) == 32 and len(salt) == 16


def test_email_duplique_et_secret_court_sont_refuses(tmp_path):
    store = IdentityStore(tmp_path)
    with pytest.raises(IdentityError, match="10 caractères"):
        store.register("a@example.com", "court")
    store.register("a@example.com", "assez-long-123")
    with pytest.raises(IdentityError, match="existe déjà"):
        store.register("A@EXAMPLE.COM", "autre-secret-123")


def test_projets_appartiennent_a_un_seul_compte(tmp_path):
    store = IdentityStore(tmp_path)
    alice = store.register("alice@example.com", "secret-alice-123")
    bob = store.register("bob@example.com", "secret-bob-12345")
    store.add_project(alice["id"], "a" * 32, "Boutique")
    assert store.owns_project(alice["id"], "a" * 32)
    assert not store.owns_project(bob["id"], "a" * 32)
    assert store.projects(alice["id"])[0]["name"] == "Boutique"
    assert store.projects(bob["id"]) == []
    reopened = IdentityStore(tmp_path)
    assert reopened.projects(alice["id"])[0]["project_id"] == "a" * 32
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE projects SET expires_at = 0 WHERE project_id = ?", ("a" * 32,))
    assert reopened.expired_projects() == ["a" * 32]
    assert reopened.projects(alice["id"]) == []


def test_cle_api_affichee_une_fois_hachee_et_revocable(tmp_path):
    store = IdentityStore(tmp_path)
    user = store.register("mcp@example.com", "secret-mcp-12345")
    created = store.create_api_key(user["id"], "Codex portable")
    assert created["key"].startswith("monl_")
    listed = store.api_keys(user["id"])
    assert listed[0]["prefix"] == created["prefix"]
    assert "key" not in listed[0]

    with sqlite3.connect(store.path) as db:
        stored = db.execute("SELECT key_hash FROM api_keys").fetchone()[0]
    assert created["key"] not in stored
    assert store.api_key_user(created["key"]) == user
    assert store.api_keys(user["id"])[0]["last_used_at"] is not None
    assert store.revoke_api_key(user["id"], created["id"])
    assert store.api_key_user(created["key"]) is None


def test_limite_de_debit_persistante_et_atomique(tmp_path):
    store = IdentityStore(tmp_path)
    assert store.consume_limit("login", "127.0.0.1", limit=2, window=60, now=100) is None
    assert store.consume_limit("login", "127.0.0.1", limit=2, window=60, now=101) is None
    assert store.consume_limit("login", "127.0.0.1", limit=2, window=60, now=102) == 58

    reopened = IdentityStore(tmp_path)
    assert reopened.consume_limit(
        "login", "127.0.0.1", limit=2, window=60, now=120
    ) == 40
    assert reopened.consume_limit(
        "login", "127.0.0.1", limit=2, window=60, now=160
    ) is None
    # Une autre portée et un autre sujet disposent de compteurs indépendants.
    assert reopened.consume_limit("register", "127.0.0.1", limit=1, window=60, now=102) is None
    assert reopened.consume_limit("login", "127.0.0.2", limit=1, window=60, now=102) is None
