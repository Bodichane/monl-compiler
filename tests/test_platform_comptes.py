"""Proofs of slice 2: unique identity, projects and legacy."""

import importlib
import uuid

from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore
from tests.support.sqlite import base_sqlite


def _projet(identity, platform, user, slug, name=None):
    project_id = uuid.uuid4().hex
    identity.add_project(user["id"], project_id, name or slug)
    platform.create_project(user["id"], project_id, slug)
    return project_id


def test_identity_deletion_cascades_to_the_project(tmp_path):
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    user = identity.register("cascade@example.test", "MotDePasse-123")
    project_id = _projet(identity, platform, user, "boutique")

    with base_sqlite(platform.database) as db:
        assert {
            (row[3], row[2], row[6])
            for row in db.execute("PRAGMA foreign_key_list(builder_projects)")
        } >= {("user_id", "users", "CASCADE"), ("project_id", "projects", "CASCADE")}

    # The raw connection above shows SQLite's default value (OFF): it is not
    # the stores'. Deletion goes through IdentityStore._connect, which enables
    # it on every transaction.
    assert identity.delete_user(user["id"]) == [project_id]
    with base_sqlite(platform.database) as db:
        assert db.execute("SELECT COUNT(*) FROM projects WHERE project_id = ?",
                          (project_id,)).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM builder_projects WHERE project_id = ?", (project_id,)
        ).fetchone()[0] == 0

    with identity._connect() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_the_slug_is_GLOBALLY_unique_and_homonyms_step_aside(tmp_path):
    """The address is a SUBDOMAIN: its uniqueness cannot be per account.

    This witness required the opposite, and that was the defect. Two accounts
    could carry "boutique"; after which `project_for_host` refused to serve BOTH
    ("the host designates several projects"), so a stranger made your site
    unreachable just by naming theirs like yours. And on the SAME account, the
    second identical name came out as a 500.

    The details of both defects are in tests/test_projets_homonymes.py; what is
    kept here is that each account still only sees its own.
    """
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    alice = identity.register("alice@example.test", "MotDePasse-123")
    bob = identity.register("bob@example.test", "MotDePasse-123")

    premier = _projet(identity, platform, alice, "boutique")
    vole = _projet(identity, platform, bob, "boutique")

    duplicate_id = uuid.uuid4().hex
    identity.add_project(alice["id"], duplicate_id, "Deuxième boutique")
    troisieme = platform.create_project(alice["id"], duplicate_id, "BOUTIQUE")

    assert platform.get_project(premier)["slug"] == "boutique", (
        "le premier a perdu l'adresse que son nom annonce")
    assert platform.get_project(vole)["slug"] == "boutique-2"
    assert troisieme == "boutique-3"

    assert len(platform.list_projects(alice["id"])) == 2
    assert len(platform.list_projects(bob["id"])) == 1


def test_an_oauth_account_refuses_a_password_exactly_like_a_wrong_one(tmp_path):
    identity = IdentityStore(tmp_path)
    oauth_id, created = identity.upsert_oauth_account(
        "github:4242", "github", "alice@example.test"
    )
    assert created is True
    with base_sqlite(identity.path) as db:
        password_hash, password_salt, provider = db.execute(
            "SELECT password_hash, password_salt, auth_provider FROM users WHERE id = ?",
            (oauth_id,),
        ).fetchone()
    assert provider == "github"
    assert len(password_hash) == 32 and len(password_salt) == 16

    faux_password = identity.authenticate("github:4242", "MotDePasse-123")
    absent_password = identity.authenticate("absent@example.test", "MotDePasse-123")
    assert faux_password == absent_password is None

    # Counter-proof of the "before comparison" guard: authenticating an OAuth
    # account must not even call the KDF.
    original = identity._password_hash
    appels = []

    def compter(password, salt):
        appels.append((password, salt))
        return original(password, salt)

    identity._password_hash = compter
    assert identity.authenticate("github:4242", "MotDePasse-123") is None
    assert appels == []


def test_legacy_accounts_are_counted_and_stay_out_of_users(tmp_path, monkeypatch):
    identity = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)
    with base_sqlite(platform.database) as db:
        db.execute(
            "INSERT INTO accounts(identifier, password_hash, created_at) "
            "VALUES (?, ?, ?)",
            ("ancien-compte", "hachage-ancienne-fonction", "2026-08-26T00:00:00+00:00"),
        )

    assert identity.comptes_herites() == 1
    assert platform.legacy_account_count() == 1
    with base_sqlite(identity.path) as db:
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
            "raison": "legacy registry hashes and identifiers are incompatible",
        },
    )]
