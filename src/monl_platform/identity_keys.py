"""MCP API-key lifecycle for identity accounts."""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from .identity_primitives import IdentityError


class IdentityKeysMixin:
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




