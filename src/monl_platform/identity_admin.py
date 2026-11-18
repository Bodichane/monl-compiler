"""Offline administration reads, backups and expiry handling."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .identity_primitives import IdentityError


class IdentityAdminMixin:
    def comptes_sans_codes(self) -> int:
        """How many accounts have no recovery code.

        EARLIER accounts have none: the additive migration catches up a table,
        never its content (point 89, word for word). Making some for them at
        startup would be worse — they would have to be displayed, and nobody
        would read them. They are therefore COUNTED and named, and the account
        page offers to generate some."""
        with self._connect() as db:
            return db.execute(
                "SELECT COUNT(*) FROM users WHERE id NOT IN "
                "(SELECT DISTINCT user_id FROM recovery_codes)").fetchone()[0]

    def comptes_herites(self) -> int:
        """Counts the old ``accounts`` rows without converting them.

        The old registry used another hash and integer identifiers. No password
        can be guessed or made up to transfer them honestly into ``users``; the
        table therefore stays intact and startup only names the number of
        accounts not carried over."""
        with self._connect() as db:
            existe = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
            ).fetchone()
            if existe is None:
                return 0
            return db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    count_legacy_accounts = comptes_herites

    # ------------------------------------------------------------------
    # Reads and operational actions
    # ------------------------------------------------------------------
    #
    # These methods have NO HTTP route. Every intervention on an account went
    # through `sqlite3` by hand, with the server stopped: workable at ten
    # accounts, not at a hundred, and each action risked a mistyped query with
    # no trace of who made it.
    #
    # Choosing a command line rather than a web panel is not laziness. A panel
    # would require its own authentication and a privilege column, and would
    # become the service's most interesting target. Whoever owns the shell
    # already owns the database: the command line therefore adds NO attack
    # surface, it only makes safe and traceable actions that were already done.

    def comptes(self) -> list[dict[str, Any]]:
        """All accounts, with enough to decide without another query."""
        with self._connect() as db:
            lignes = db.execute("""
                SELECT users.id, users.email, users.created_at,
                       (SELECT COUNT(*) FROM projects WHERE user_id = users.id) AS projets,
                       (SELECT COUNT(*) FROM api_keys
                        WHERE user_id = users.id AND revoked_at IS NULL) AS cles,
                       (SELECT COUNT(*) FROM recovery_codes
                        WHERE user_id = users.id) AS codes
                FROM users ORDER BY users.created_at DESC
            """).fetchall()
        return [dict(ligne) for ligne in lignes]

    def compte_par_adresse(self, email: Any) -> dict[str, str] | None:
        """Finds an account by its address, without a password.

        The address is NORMALIZED as at registration: otherwise, the operator
        would type the address as it was dictated to them and find nothing, while
        the account exists."""
        try:
            normalise = self._email(email)
        except IdentityError:
            return None
        with self._connect() as db:
            ligne = db.execute("SELECT id, email FROM users WHERE email = ?",
                               (normalise,)).fetchone()
        return {"id": ligne["id"], "email": ligne["email"]} if ligne else None

    def tous_les_projets(self, user_id: str | None = None) -> list[dict[str, Any]]:
        requete = ("SELECT projects.*, users.email FROM projects "
                   "JOIN users ON users.id = projects.user_id ")
        parametres: tuple = ()
        if user_id:
            requete += "WHERE projects.user_id = ? "
            parametres = (user_id,)
        with self._connect() as db:
            lignes = db.execute(requete + "ORDER BY projects.created_at DESC",
                                parametres).fetchall()
        return [dict(ligne) for ligne in lignes]

    def deplacer_echeance(self, project_id: str, secondes: int | None) -> bool:
        """Pushes back (or brings forward) a project's expiry. `None` = never.

        Counted from NOW and not from the current due date: "keep it thirty more
        days" is said after the fact, often on an already expired project, and
        restarting from the old date would extend nothing."""
        echeance = None if secondes is None else int(time.time()) + secondes
        with self._connect() as db:
            curseur = db.execute("UPDATE projects SET expires_at = ? WHERE project_id = ?",
                                 (echeance, project_id))
        return curseur.rowcount == 1

    def revoquer_cle_par_id(self, key_id: str) -> dict[str, str] | None:
        """Revokes a key without knowing its owner.

        `revoke_api_key` requires the account identifier, because an HTTP route
        must only touch the caller's keys. The operator, however, has in front of
        them a key prefix read in a log and not much else."""
        with self._connect() as db:
            ligne = db.execute(
                "SELECT api_keys.id, api_keys.name, users.email FROM api_keys "
                "JOIN users ON users.id = api_keys.user_id "
                "WHERE api_keys.id = ? AND api_keys.revoked_at IS NULL",
                (key_id,)).fetchone()
            if not ligne:
                return None
            db.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?",
                       (int(time.time()), key_id))
        return dict(ligne)

    def cles_du_compte(self, user_id: str) -> list[dict[str, Any]]:
        return self.api_keys(user_id)

    def sauvegarder(self, destination: str | os.PathLike[str]) -> Path:
        """Copies the database through SQLite's online backup API.

        A `cp` on an open database can yield a TORN file: the platform writes in
        WAL, so the `.sqlite3` alone does not contain the transactions still in
        the journal. `Connection.backup()` takes a consistent copy while the
        server keeps serving — it is the only reason for this method rather than
        a shell line.

        `backup()` also copies the source's page 1 HEADER, which carries the
        journal mode: the copy therefore inherits WAL and sqlite3 leaves it its
        `-wal`/`-shm` sidecar files when closing it. Measured under real
        conditions (podman compose, backups every 20 s for 18 h): **719 orphan
        `-wal`/`-shm` pairs** for 14 `.sqlite3` files — `_rotation`
        (`__main__.py`) only filters on `cible.suffix` (`.sqlite3`), which matches
        neither `.sqlite3-wal` nor `.sqlite3-shm`: these sidecars are NEVER purged,
        whatever `--garder`. A backup service without effective rotation fills the
        disk — the backup becomes the outage it was meant to prevent. Switching
        the copy back to DELETE before closing it forces a full checkpoint and
        makes both files disappear: a backup must be a single portable file, never
        a pair that only makes sense together."""
        cible = Path(destination).resolve()
        cible.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path, timeout=30)
        copie = sqlite3.connect(cible)
        try:
            source.backup(copie)
            copie.execute("PRAGMA journal_mode = DELETE")
        finally:
            copie.close()
            source.close()
        return cible

    def expired_projects(self) -> list[str]:
        now = int(time.time())
        with self._connect() as db:
            rows = db.execute("SELECT project_id FROM projects "
                              "WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchall()
        return [row["project_id"] for row in rows]



