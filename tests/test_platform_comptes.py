"""Preuves de la tranche 2 : identité unique, projets et héritage."""

import importlib
import sqlite3
import uuid

import pytest

from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore


def _projet(identity, platform, user, slug, name=None):
    project_id = uuid.uuid4().hex
    identity.add_project(user["id"], project_id, name or slug)
    platform.create_project(user["id"], project_id, slug)
    return project_id


def test_la_suppression_identite_cascade_le_projet(tmp_path):
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    user = identity.register("cascade@example.test", "MotDePasse-123")
    project_id = _projet(identity, platform, user, "boutique")

    with sqlite3.connect(platform.database) as db:
        assert {
            (row[3], row[2], row[6])
            for row in db.execute("PRAGMA foreign_key_list(builder_projects)")
        } >= {("user_id", "users", "CASCADE"), ("project_id", "projects", "CASCADE")}

    # La connexion brute ci-dessus montre la valeur SQLite par défaut (OFF) :
    # ce n'est pas celle des stores. La suppression passe par
    # IdentityStore._connect, qui l'active à chaque transaction.
    assert identity.delete_user(user["id"]) == [project_id]
    with sqlite3.connect(platform.database) as db:
        assert db.execute("SELECT COUNT(*) FROM projects WHERE project_id = ?",
                          (project_id,)).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM builder_projects WHERE project_id = ?", (project_id,)
        ).fetchone()[0] == 0

    with identity._connect() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_le_slug_est_unique_par_compte_et_non_global(tmp_path):
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    alice = identity.register("alice@example.test", "MotDePasse-123")
    bob = identity.register("bob@example.test", "MotDePasse-123")

    _projet(identity, platform, alice, "boutique")
    _projet(identity, platform, bob, "boutique")

    duplicate_id = uuid.uuid4().hex
    identity.add_project(alice["id"], duplicate_id, "Deuxième boutique")
    with pytest.raises(sqlite3.IntegrityError):
        platform.create_project(alice["id"], duplicate_id, "BOUTIQUE")

    assert len(platform.list_projects(alice["id"])) == 1
    assert len(platform.list_projects(bob["id"])) == 1


def test_un_oauth_refuse_le_mot_de_passe_exactement_comme_un_faux(tmp_path):
    identity = IdentityStore(tmp_path)
    oauth_id, created = identity.upsert_oauth_account(
        "github:4242", "github", "alice@example.test"
    )
    assert created is True
    with sqlite3.connect(identity.path) as db:
        password_hash, password_salt, provider = db.execute(
            "SELECT password_hash, password_salt, auth_provider FROM users WHERE id = ?",
            (oauth_id,),
        ).fetchone()
    assert provider == "github"
    assert len(password_hash) == 32 and len(password_salt) == 16

    faux_password = identity.authenticate("github:4242", "MotDePasse-123")
    absent_password = identity.authenticate("absent@example.test", "MotDePasse-123")
    assert faux_password == absent_password is None

    # Contre-épreuve de la garde « avant comparaison » : l'authentification
    # d'un compte OAuth ne doit même pas appeler le KDF.
    original = identity._password_hash
    appels = []

    def compter(password, salt):
        appels.append((password, salt))
        return original(password, salt)

    identity._password_hash = compter
    assert identity.authenticate("github:4242", "MotDePasse-123") is None
    assert appels == []


def test_les_comptes_herites_sont_comptes_et_restent_hors_users(tmp_path, monkeypatch):
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    with sqlite3.connect(platform.database) as db:
        db.execute(
            "INSERT INTO accounts(identifier, password_hash, created_at) "
            "VALUES (?, ?, ?)",
            ("ancien-compte", "hachage-ancienne-fonction", "2026-08-26T00:00:00+00:00"),
        )

    assert identity.comptes_herites() == 1
    assert platform.legacy_account_count() == 1
    with sqlite3.connect(identity.path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM users WHERE email = ?", ("ancien-compte",)
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
        ).fetchone()[0] == 1

    app_module = importlib.import_module("monl_platform.app")
    annonces = []
    monkeypatch.setattr(app_module, "anomalie", lambda nom, **champs: annonces.append((nom, champs)))
    app_module.create_app(workspace=tmp_path)
    assert annonces == [(
        "comptes_heritages_non_convertibles",
        {
            "nombre": 1,
            "raison": "hachage et identifiants du registre historique incompatibles",
        },
    )]
