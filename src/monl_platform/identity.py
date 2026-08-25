"""Persistent identities, browser sessions, projects and MCP API keys.

Secrets are never stored verbatim: passwords use scrypt, while high-entropy
session and API tokens use SHA-256 fingerprints suitable for exact lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SESSION_TTL = 30 * 24 * 3600
PROJECT_TTL = int(os.environ.get("MONL_PROJECT_RETENTION_DAYS", "30")) * 24 * 3600


class IdentityError(ValueError):
    pass


class IdentityStore:
    def __init__(self, workspace: str | os.PathLike[str]):
        self.path = Path(workspace).resolve() / "platform.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

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
                created_at INTEGER NOT NULL
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

    @staticmethod
    def _email(value: Any) -> str:
        email = str(value or "").strip().lower()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise IdentityError("Saisissez une adresse email valide.")
        return email

    @staticmethod
    def _password(value: Any) -> str:
        password = str(value or "")
        if len(password) < 10:
            raise IdentityError("Le mot de passe doit contenir au moins 10 caractères.")
        if len(password.encode("utf-8")) > 1024:
            raise IdentityError("Le mot de passe est trop long.")
        return password

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def register(self, email: Any, password: Any) -> dict[str, str]:
        normalized = self._email(email)
        secret = self._password(password)
        user_id, salt = uuid.uuid4().hex, secrets.token_bytes(16)
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                    (user_id, normalized, self._password_hash(secret, salt), salt, int(time.time())),
                )
        except sqlite3.IntegrityError:
            raise IdentityError("Un compte existe déjà pour cette adresse.") from None
        return {"id": user_id, "email": normalized}

    def authenticate(self, email: Any, password: Any) -> dict[str, str] | None:
        try:
            normalized = self._email(email)
        except IdentityError:
            return None
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (normalized,)).fetchone()
        if not row:
            # Coût similaire pour limiter la distinction compte absent / mauvais secret.
            self._password_hash(str(password or ""), b"monl-missing-user")
            return None
        candidate = self._password_hash(str(password or ""), row["password_salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"]}

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (self._token_hash(token), user_id, now + SESSION_TTL, now))
        return token

    def session_user(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                "SELECT users.id, users.email FROM sessions JOIN users "
                "ON users.id = sessions.user_id WHERE token_hash = ? AND expires_at > ?",
                (self._token_hash(token), now),
            ).fetchone()
        return {"id": row["id"], "email": row["email"]} if row else None

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))

    def add_project(self, user_id: str, project_id: str, name: str) -> None:
        now = int(time.time())
        with self._connect() as db:
            db.execute("INSERT INTO projects "
                       "(project_id, user_id, name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                       (project_id, user_id, name[:160], now, now + PROJECT_TTL))

    def owns_project(self, user_id: str, project_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM projects WHERE user_id = ? AND project_id = ?",
                             (user_id, project_id)).fetchone()
        return bool(row)

    def projects(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT project_id, name, created_at, expires_at FROM projects "
                "WHERE user_id = ? "
                "ORDER BY created_at DESC", (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_project(self, user_id: str, project_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM projects WHERE user_id = ? AND project_id = ?",
                                (user_id, project_id))
        return cursor.rowcount == 1

    def expired_projects(self) -> list[str]:
        now = int(time.time())
        with self._connect() as db:
            rows = db.execute("SELECT project_id FROM projects "
                              "WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchall()
            db.executemany("DELETE FROM projects WHERE project_id = ?",
                           [(row["project_id"],) for row in rows])
        return [row["project_id"] for row in rows]

    def create_api_key(self, user_id: str, name: Any) -> dict[str, Any]:
        label = str(name or "").strip()
        if not 1 <= len(label) <= 80:
            raise IdentityError("Le nom de la clé doit contenir entre 1 et 80 caractères.")
        raw = "monl_" + secrets.token_urlsafe(32)
        key_id, now = uuid.uuid4().hex, int(time.time())
        with self._connect() as db:
            db.execute("INSERT INTO api_keys VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
                       (key_id, user_id, label, raw[:13], self._token_hash(raw), now))
        return {"id": key_id, "name": label, "prefix": raw[:13], "key": raw,
                "created_at": now, "last_used_at": None, "revoked_at": None}

    def api_keys(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, name, prefix, created_at, last_used_at, revoked_at FROM api_keys "
                "WHERE user_id = ? ORDER BY created_at DESC", (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND user_id = ? "
                "AND revoked_at IS NULL", (int(time.time()), key_id, user_id),
            )
        return cursor.rowcount == 1

    def api_key_user(self, raw: str | None) -> dict[str, str] | None:
        if not raw or not raw.startswith("monl_"):
            return None
        digest, now = self._token_hash(raw), int(time.time())
        with self._connect() as db:
            row = db.execute(
                "SELECT api_keys.id AS key_id, users.id, users.email FROM api_keys "
                "JOIN users ON users.id = api_keys.user_id "
                "WHERE key_hash = ? AND revoked_at IS NULL", (digest,),
            ).fetchone()
            if row:
                db.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                           (now, row["key_id"]))
        return {"id": row["id"], "email": row["email"]} if row else None

    def consume_limit(self, scope: str, subject: str, *, limit: int,
                      window: int, now: int | None = None) -> int | None:
        """Consume one quota unit, returning retry seconds when exhausted.

        The counter lives in SQLite so multiple application workers share the
        same limit. ``BEGIN IMMEDIATE`` serialises the small read/update pair
        and prevents two simultaneous requests from both accepting the final
        unit.
        """
        timestamp = int(time.time()) if now is None else now
        safe_subject = self._token_hash(subject) if subject else "anonymous"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT window_start, hits FROM rate_limits "
                "WHERE scope = ? AND subject = ?", (scope, safe_subject),
            ).fetchone()
            if not row or timestamp >= row["window_start"] + window:
                db.execute(
                    "INSERT INTO rate_limits VALUES (?, ?, ?, 1) "
                    "ON CONFLICT(scope, subject) DO UPDATE SET "
                    "window_start = excluded.window_start, hits = 1",
                    (scope, safe_subject, timestamp),
                )
                return None
            if row["hits"] >= limit:
                return max(1, row["window_start"] + window - timestamp)
            db.execute(
                "UPDATE rate_limits SET hits = hits + 1 "
                "WHERE scope = ? AND subject = ?", (scope, safe_subject),
            )
        return None
