import sqlite3

import pytest

from monl_platform.identity import IdentityError, IdentityStore
from tests.support.sqlite import sqlite_db


def test_account_session_and_hashed_password(tmp_path):
    store = IdentityStore(tmp_path)
    user = store.register(" Alice@Example.COM ", "mot-de-passe-solide")
    assert user["email"] == "alice@example.com"
    assert store.authenticate("alice@example.com", "incorrect") is None
    assert store.authenticate("ALICE@example.com", "mot-de-passe-solide") == user

    token = store.create_session(user["id"])
    assert store.session_user(token) == user
    store.revoke_session(token)
    assert store.session_user(token) is None

    with sqlite_db(store.path) as db:
        password_hash, salt = db.execute(
            "SELECT password_hash, password_salt FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    assert b"mot-de-passe" not in password_hash
    assert len(password_hash) == 32 and len(salt) == 16


def test_duplicate_email_and_short_secret_are_refused(tmp_path):
    store = IdentityStore(tmp_path)
    with pytest.raises(IdentityError, match="10 characters"):
        store.register("a@example.com", "court")
    store.register("a@example.com", "assez-long-123")
    with pytest.raises(IdentityError, match="already exists"):
        store.register("A@EXAMPLE.COM", "autre-secret-123")


def test_projects_belong_to_a_single_account(tmp_path):
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
    with sqlite_db(store.path) as db:
        db.execute("UPDATE projects SET expires_at = 0 WHERE project_id = ?", ("a" * 32,))
    assert reopened.expired_projects() == ["a" * 32]
    assert reopened.projects(alice["id"]), "Selecting expired projects must not erase their owner"
    from monl_platform.app_lifecycle import _purger
    from monl_platform.service import CompilationService

    assert _purger(CompilationService(tmp_path), reopened) == 1
    assert reopened.projects(alice["id"]) == []


def test_api_key_shown_once_hashed_and_revocable(tmp_path):
    store = IdentityStore(tmp_path)
    user = store.register("mcp@example.com", "secret-mcp-12345")
    created = store.create_api_key(user["id"], "Codex portable")
    assert created["key"].startswith("monl_")
    listed = store.api_keys(user["id"])
    assert listed[0]["prefix"] == created["prefix"]
    assert "key" not in listed[0]

    with sqlite_db(store.path) as db:
        stored = db.execute("SELECT key_hash FROM api_keys").fetchone()[0]
    assert created["key"] not in stored
    assert store.api_key_user(created["key"]) == user
    assert store.api_keys(user["id"])[0]["last_used_at"] is not None
    assert store.revoke_api_key(user["id"], created["id"])
    assert store.api_key_user(created["key"]) is None


def test_persistent_and_atomic_rate_limit(tmp_path):
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
    # Another scope and another subject have independent counters.
    assert reopened.consume_limit("register", "127.0.0.1", limit=1, window=60, now=102) is None
    assert reopened.consume_limit("login", "127.0.0.2", limit=1, window=60, now=102) is None


@pytest.mark.parametrize("generated", [False, True], ids=["platform", "generated"])
def test_wal_waits_for_the_lock_on_a_new_database(tmp_path, monkeypatch, generated):
    import threading
    import time

    from monl_platform import identity_database

    activate = _wal_initializer(generated)
    entered = threading.Event()
    errors = []
    stores = []

    class ObservedConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement):
            try:
                return self.connection.execute(statement)
            except sqlite3.OperationalError:
                if statement == "PRAGMA journal_mode = WAL":
                    entered.set()
                raise

    def initialize(connection):
        activate(ObservedConnection(connection))

    monkeypatch.setattr(identity_database, "activate_wal", initialize)
    blocker = sqlite3.connect(tmp_path / "platform.sqlite3")
    assert blocker.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    blocker.execute("BEGIN IMMEDIATE")

    def construct():
        try:
            stores.append(IdentityStore(tmp_path))
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=construct)
    try:
        worker.start()
        assert entered.wait(2)
        time.sleep(0.5)
        blocker.rollback()
        worker.join(3)
        assert not worker.is_alive()
        assert errors == []
        assert len(stores) == 1
        with sqlite_db(tmp_path / "platform.sqlite3") as check:
            assert check.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        blocker.rollback()
        worker.join(3)
        blocker.close()


def test_wal_reports_the_lock_at_deadline(tmp_path, monkeypatch):
    """Platform: at the deadline, the error comes up like any other request."""
    import time

    from monl_platform import identity_database

    activate = _wal_initializer(False)
    observed = []

    def short_budget(connection):
        connection.execute("PRAGMA busy_timeout = 150")
        try:
            activate(connection)
        finally:
            observed.append(connection.execute("PRAGMA busy_timeout").fetchone()[0])

    monkeypatch.setattr(identity_database, "activate_wal", short_budget)
    blocker = sqlite3.connect(tmp_path / "platform.sqlite3")
    blocker.execute("BEGIN IMMEDIATE")
    try:
        start = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            IdentityStore(tmp_path)
        assert 0.1 <= time.monotonic() - start < 2
        assert observed == [150]
        assert blocker.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        blocker.rollback()
        blocker.close()



def test_generated_wal_gives_up_without_error_at_deadline(tmp_path):
    """Generated backend: at the deadline, it gives up WAL WITHOUT failing
    startup — the database stays on the default journal, no data lost."""
    import time

    activate = _wal_initializer(True)
    blocker = sqlite3.connect(tmp_path / "app.db")
    blocker.execute("CREATE TABLE t (x)")
    blocker.commit()
    blocker.execute("BEGIN IMMEDIATE")
    connection = sqlite3.connect(tmp_path / "app.db")
    try:
        connection.execute("PRAGMA busy_timeout = 150")
        start = time.monotonic()
        activate(connection)
        assert 0.1 <= time.monotonic() - start < 2
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 150
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        connection.close()
        blocker.rollback()
        blocker.close()

def _wal_initializer(generated):
    if not generated:
        from monl_platform.sqlite_database import activate_wal
        return activate_wal

    # Execute the emitted function itself, without starting the generated app.
    import time

    from monl.generator.runtime_preparation import PreparationRuntimeMixin

    lines = PreparationRuntimeMixin()._lignes_de_base([])
    source = "\n".join(lines[:lines.index("def _prepare_database(conn):")])
    namespace = {"sqlite3": sqlite3, "time": time}
    exec(source, namespace)
    return namespace["_activer_wal"]
