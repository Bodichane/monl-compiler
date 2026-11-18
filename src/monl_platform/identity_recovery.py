"""Recovery-code creation and password recovery transactions."""

from __future__ import annotations

import secrets
import time
from typing import Any

from .identity_primitives import IdentityError


class IdentityRecoveryMixin:
    # ------------------------------------------------------------------
    # Recovery codes
    # ------------------------------------------------------------------
    #
    # Without email, a lost password made the account and its projects
    # permanently inaccessible. The remedy cannot be "we will send you a link":
    # monl sends nothing, and a "knowing how to send a message" brick would
    # open an SMTP server, a domain with a reputation and a network dependency
    # in a service that has none.
    #
    # A recovery code moves custody to the person: they receive codes ONCE,
    # they store them where they want. It is exactly the contract already made
    # for API keys — shown once, hashed afterwards — so neither a new promise
    # nor a new storage mode.

    NB_CODES = 8

    def create_recovery_codes(self, user_id: str, /, *, session: str | None = None,
                              revoke_access: bool = False) -> list[str]:
        """Replaces ALL of the account's codes and returns the new ones, in clear.

        Replacing rather than adding: someone who regenerates their codes often
        does so because they fear the old ones leaked. Accumulating them would
        keep alive exactly what they want to get rid of."""
        codes = [secrets.token_urlsafe(12) for _ in range(self.NB_CODES)]
        maintenant = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            compte = db.execute("SELECT auth_provider FROM users WHERE id = ?",
                                (user_id,)).fetchone()
            if compte and compte["auth_provider"] is not None:
                raise IdentityError("OAuth accounts cannot use recovery codes.")
            db.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
            db.executemany(
                "INSERT INTO recovery_codes VALUES (?, ?, ?)",
                [(self._token_hash(code), user_id, maintenant) for code in codes])
            if revoke_access:
                db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                db.execute("UPDATE api_keys SET revoked_at = ? WHERE user_id = ? "
                           "AND revoked_at IS NULL", (maintenant, user_id))
            elif session is not None:
                db.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                           (user_id, self._token_hash(session)))
        return codes

    def count_recovery_codes(self, user_id: str, /) -> int:
        with self._connect() as db:
            return db.execute(
                "SELECT COUNT(*) FROM recovery_codes WHERE user_id = ?",
                (user_id,)).fetchone()[0]

    def consume_recovery_code(self, email: Any, code: Any, password: Any
                              ) -> dict[str, str] | None:
        """Checks a code, changes the password, and returns the account.

        The code is CONSUMED in the same transaction as the password change:
        outside it, a failed write would leave a code burned for nothing, and the
        person would have lost one chance in eight without getting anything.

        All sessions go away. A password reset that kept open sessions alive
        would be useless in the case that matters — the one where someone else
        has already got in."""
        try:
            normalise = self._email(email)
            secret = self._password(password)
        except IdentityError:
            return None
        empreinte = self._token_hash(str(code or ""))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            ligne = db.execute(
                "SELECT users.id AS user_id, users.email FROM recovery_codes "
                "JOIN users ON users.id = recovery_codes.user_id "
                "WHERE recovery_codes.code_hash = ? AND users.email = ?",
                (empreinte, normalise)).fetchone()
            if not ligne:
                return None
            sel = secrets.token_bytes(16)
            db.execute("UPDATE users SET password_hash = ?, password_salt = ? "
                       "WHERE id = ?",
                       (self._password_hash(secret, sel), sel, ligne["user_id"]))
            db.execute("DELETE FROM recovery_codes WHERE code_hash = ?", (empreinte,))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (ligne["user_id"],))
            db.execute("UPDATE api_keys SET revoked_at = ? WHERE user_id = ? "
                       "AND revoked_at IS NULL", (int(time.time()), ligne["user_id"]))
        return {"id": ligne["user_id"], "email": ligne["email"]}
