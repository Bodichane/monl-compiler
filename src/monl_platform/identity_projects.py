"""Project ownership and lifecycle operations in the identity store."""

from __future__ import annotations

import time
from typing import Any

from .identity_primitives import PROJECT_TTL


class IdentityProjectsMixin:
    def add_project(self, user_id: str, project_id: str, name: str) -> None:
        now = int(time.time())
        with self._connect() as db:
            db.execute("INSERT INTO projects "
                       "(project_id, user_id, name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                       (project_id, user_id, name[:160], now, now + PROJECT_TTL))

    def owns_project(self, user_id: str, project_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM projects WHERE user_id = ? AND project_id = ? "
                             "AND (expires_at IS NULL OR expires_at > ?)",
                             (user_id, project_id, int(time.time()))).fetchone()
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

    def delete_user(self, user_id: str) -> list[str]:
        """Erases an account and returns the projects to remove from disk.

        Sessions, projects and keys go away through `ON DELETE CASCADE` — hence
        the importance of the `PRAGMA foreign_keys = ON` set on every connection:
        SQLite ignores foreign keys by default, and without it the `users` row
        would go away leaving everything else orphaned.

        The project identifiers are read BEFORE the deletion: afterwards, nothing
        says which folders to erase. Same reasoning as point 92 of the compiler,
        on returning stock."""
        with self._connect() as db:
            rows = db.execute("SELECT project_id FROM projects WHERE user_id = ?",
                              (user_id,)).fetchall()
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return [row["project_id"] for row in rows]
