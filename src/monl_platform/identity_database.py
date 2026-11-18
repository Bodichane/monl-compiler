"""SQLite schema and connection lifecycle for identities."""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .sqlite_database import activate_wal


class IdentityDatabaseMixin:
    def __init__(self, workspace: str | os.PathLike[str]):
        self.path = Path(workspace).resolve() / "platform.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Opens, commits (or rolls back), then CLOSES.

        `with sqlite3.connect(...)` commits the transaction but does not close the
        connection — and a CPython `Connection` object takes part in reference
        cycles, so it is only released by the cyclic garbage collector, not when
        the method returns. Measured: 500 reads left **197 descriptors** open on
        the database, all released at once by a manual `gc.collect()`. It is not
        an eternal leak, it is worse to operate — a server under load can reach
        its descriptor limit before a generation 2 collection happens, and the
        incident then looks like nothing known.

        Second consequence, the one that revealed the first: as long as a
        connection lives, SQLite does not fold the WAL journal back into the main
        file. The database stayed at 4,096 bytes with 111 KB of WAL next to it —
        and the restore documented in `docs/EXPLOITATION.md` failed with a "disk
        I/O error" when putting the file back.

        The inner `with connection:` keeps exactly the old semantics (commit on a
        clean exit, rollback on exception); only the close is added. The two
        callers that read `cursor.rowcount` AFTER the block keep working: the
        value is frozen at execution, not read back from the connection."""
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            activate_wal(connection)
            with connection:
                yield connection
        finally:
            connection.close()

    def ready(self) -> bool:
        try:
            with self._connect() as db:
                return db.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def _migrate(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash BLOB NOT NULL,
                password_salt BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                auth_provider TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS projects_user_created
                ON projects(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS api_keys_user_created
                ON api_keys(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS recovery_codes (
                code_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS recovery_codes_user
                ON recovery_codes(user_id);
            CREATE TABLE IF NOT EXISTS rate_limits (
                scope TEXT NOT NULL,
                subject TEXT NOT NULL,
                window_start INTEGER NOT NULL,
                hits INTEGER NOT NULL,
                PRIMARY KEY (scope, subject)
            );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            if "expires_at" not in columns:
                db.execute("ALTER TABLE projects ADD COLUMN expires_at INTEGER")
            user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "auth_provider" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT")




