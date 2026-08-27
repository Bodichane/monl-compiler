"""Persistent rate-limit accounting for identity operations."""

from __future__ import annotations

import time


class IdentityLimitsMixin:
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



