"""Accounts, OAuth identities and browser sessions."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
import time
import uuid
from typing import Any

from .identity_primitives import SESSION_TTL, IdentityError


class IdentityAuthMixin:
    def register(self, email: Any, password: Any) -> dict[str, str]:
        normalized = self._email(email)
        secret = self._password(password)
        user_id, salt = uuid.uuid4().hex, secrets.token_bytes(16)
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO users "
                    "(id, email, password_hash, password_salt, created_at, auth_provider) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    (user_id, normalized, self._password_hash(secret, salt), salt,
                     int(time.time())),
                )
        except sqlite3.IntegrityError:
            raise IdentityError("An account already exists for this address.") from None
        return {"id": user_id, "email": normalized}

    def authenticate(self, email: Any, password: Any) -> dict[str, str] | None:
        normalized = self._login_identifier(email)
        if normalized is None:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT id, email, password_hash, password_salt, auth_provider "
                "FROM users WHERE email = ?", (normalized,)
            ).fetchone()
        if not row:
            # Similar cost to limit telling a missing account from a wrong
            # secret.
            self._password_hash(str(password or ""), b"monl-missing-user")
            return None
        # An OAuth account deliberately has a random hash and salt to respect
        # NOT NULL. They are not a fallback password: the refusal must come
        # BEFORE any computation and be exactly that of a wrong password.
        if row["auth_provider"] is not None:
            return None
        candidate = self._password_hash(str(password or ""), row["password_salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"]}

    def upsert_oauth_account(self, identifier, provider, display_name=None):
        """Creates or finds an OAuth identity without making up a password.

        ``identifier`` belongs to the provider's namespace (``github:4242`` or
        ``google:...``). The ``email`` column keeps this login identifier; the
        verified label is consumed by the OAuth layer that prepares the session,
        since the identity schema carries no separate display name.

        ``display_name`` stays an accepted argument so that migrating the old
        caller does not lose the verified label, but it is never used as an
        identifier: attaching this label to a password account would be precisely
        the takeover that was ruled out."""
        del display_name
        identifier = str(identifier).strip()
        provider = str(provider).strip()
        if not identifier or "\x00" in identifier:
            raise IdentityError("empty or invalid OAuth identifier")
        if not provider or "\x00" in provider:
            raise IdentityError("empty or invalid OAuth provider")
        with self._connect() as db:
            row = db.execute(
                "SELECT id, auth_provider FROM users WHERE email = ?", (identifier,)
            ).fetchone()
            if row is not None:
                if row["auth_provider"] != provider:
                    raise IdentityError("OAuth identity already attached to another provider")
                return row["id"], False
            user_id = uuid.uuid4().hex
            # These bytes are not a digest computed from a known secret. They
            # exist only to satisfy the registry's NOT NULLs.
            password_hash = secrets.token_bytes(32)
            password_salt = secrets.token_bytes(16)
            db.execute(
                "INSERT INTO users "
                "(id, email, password_hash, password_salt, created_at, auth_provider) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, identifier, password_hash, password_salt, int(time.time()), provider),
            )
            return user_id, True

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (self._token_hash(token), user_id, now + SESSION_TTL, now))
        return token

    def session_user(self, token: str | None) -> dict[str, str] | None:
        session = self.session_proof(token)
        return {"id": session["id"], "email": session["email"]} if session else None

    def session_proof(self, token: str | None) -> dict | None:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as db:
            row = db.execute(
                "SELECT users.id, users.email, users.auth_provider, "
                "sessions.created_at AS session_created_at FROM sessions JOIN users "
                "ON users.id = sessions.user_id WHERE token_hash = ? AND expires_at > ?",
                (self._token_hash(token), now),
            ).fetchone()
        return dict(row) if row else None

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))



