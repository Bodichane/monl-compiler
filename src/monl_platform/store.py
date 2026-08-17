"""Persistance SQLite du socle de plateforme.

Le store ne connaît ni HTTP ni IA. Les opérations ouvrent une transaction
SQLite courte, ce qui convient à un worker et laisse SQLite jouer son rôle de
verrou entre plusieurs processus.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

BUILD_STATES = ("en_attente", "en_cours", "reussie", "echouee")


def _now():
    return datetime.now(timezone.utc).isoformat()


class PlatformStore:
    """Store SQLite avec création et migration additive au démarrage."""

    def __init__(self, database):
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database, check_same_thread=False, timeout=30
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self):
        with self._lock:
            self._connection.close()

    def _migrate(self):
        """Crée le schéma puis ajoute seulement les colonnes manquantes.

        Une exécution répétée est sans effet. Une évolution future doit
        ajouter une entrée à ``columns`` plutôt que supprimer ou renommer une
        colonne : c'est la discipline des migrations additives de monl.
        """
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    identifier TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    slug TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(account_id, slug)
                );
                CREATE TABLE IF NOT EXISTS builds (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id),
                    state TEXT NOT NULL DEFAULT 'en_attente',
                    run_id TEXT,
                    tokens_consumed INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost REAL,
                    currency TEXT,
                    price_status TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_account
                    ON projects(account_id);
                CREATE INDEX IF NOT EXISTS idx_builds_project
                    ON builds(project_id);
                """
            )
            columns = {
                "accounts": {
                    "identifier": "TEXT",
                    "created_at": "TEXT",
                },
                "projects": {
                    "account_id": "INTEGER",
                    "slug": "TEXT",
                    "created_at": "TEXT",
                },
                "builds": {
                    "project_id": "INTEGER",
                    "state": "TEXT NOT NULL DEFAULT 'en_attente'",
                    "run_id": "TEXT",
                    "tokens_consumed": "INTEGER",
                    "input_tokens": "INTEGER",
                    "output_tokens": "INTEGER",
                    "cost": "REAL",
                    "currency": "TEXT",
                    "price_status": "TEXT",
                    "started_at": "TEXT",
                    "finished_at": "TEXT",
                    "error_message": "TEXT",
                    "created_at": "TEXT",
                },
            }
            for table, expected in columns.items():
                present = {
                    row["name"]
                    for row in self._connection.execute(f"PRAGMA table_info({table})")
                }
                for name, definition in expected.items():
                    if name not in present:
                        self._connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        )
            self._connection.execute("PRAGMA user_version = 1")

    def _row(self, query, parameters=()):
        row = self._connection.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None

    def _rows(self, query, parameters=()):
        return [dict(row) for row in self._connection.execute(query, parameters)]

    def _account_id(self, account):
        if isinstance(account, bool):
            raise ValueError("identifiant de compte invalide")
        if isinstance(account, int):
            row = self._row("SELECT id FROM accounts WHERE id = ?", (account,))
        else:
            row = self._row("SELECT id FROM accounts WHERE identifier = ?", (str(account),))
        if row is None:
            raise KeyError(f"compte introuvable : {account}")
        return row["id"]

    def resolve_account_id(self, account):
        with self._lock:
            return self._account_id(account)

    def create_account(self, identifier):
        identifier = str(identifier).strip()
        if not identifier or "\x00" in identifier:
            raise ValueError("identifiant de compte vide ou invalide")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO accounts(identifier, created_at) VALUES (?, ?)",
                (identifier, _now()),
            )
            return cursor.lastrowid

    def get_account(self, account):
        with self._lock:
            account_id = self._account_id(account)
            return self._row("SELECT * FROM accounts WHERE id = ?", (account_id,))

    def create_project(self, account, slug):
        slug = str(slug).strip()
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise ValueError("slug de projet invalide : remontée de chemin refusée")
        with self._lock, self._connection:
            account_id = self._account_id(account)
            cursor = self._connection.execute(
                "INSERT INTO projects(account_id, slug, created_at) VALUES (?, ?, ?)",
                (account_id, slug, _now()),
            )
            return cursor.lastrowid

    def get_project(self, project_id):
        with self._lock:
            return self._row("SELECT * FROM projects WHERE id = ?", (project_id,))

    def get_project_for_account(self, account, project_id):
        with self._lock:
            account_id = self._account_id(account)
            return self._row(
                "SELECT * FROM projects WHERE id = ? AND account_id = ?",
                (project_id, account_id),
            )

    def list_projects(self, account):
        with self._lock:
            account_id = self._account_id(account)
            return self._rows(
                "SELECT * FROM projects WHERE account_id = ? ORDER BY id", (account_id,)
            )

    def create_build(self, project_id):
        if isinstance(project_id, bool):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connection:
            if self._row("SELECT id FROM projects WHERE id = ?", (project_id,)) is None:
                raise KeyError(f"projet introuvable : {project_id}")
            cursor = self._connection.execute(
                "INSERT INTO builds(project_id, state, created_at) VALUES (?, ?, ?)",
                (project_id, "en_attente", _now()),
            )
            return cursor.lastrowid

    def start_build(self, build_id):
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE builds SET state = ?, started_at = ? WHERE id = ?",
                ("en_cours", _now(), build_id),
            )

    def finish_build(
        self,
        build_id,
        state,
        *,
        run_id=None,
        tokens_consumed=None,
        input_tokens=None,
        output_tokens=None,
        cost=None,
        currency=None,
        price_status=None,
        error_message=None,
    ):
        if state not in {"reussie", "echouee"}:
            raise ValueError(f"état terminal invalide : {state}")
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE builds SET state = ?, run_id = ?, tokens_consumed = ?,
                   input_tokens = ?, output_tokens = ?, cost = ?, currency = ?,
                   price_status = ?, finished_at = ?, error_message = ? WHERE id = ?""",
                (
                    state,
                    run_id,
                    tokens_consumed,
                    input_tokens,
                    output_tokens,
                    cost,
                    currency,
                    price_status,
                    _now(),
                    error_message,
                    build_id,
                ),
            )

    def get_build(self, build_id):
        with self._lock:
            build = self._row("SELECT * FROM builds WHERE id = ?", (build_id,))
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def list_builds(self, project_id):
        with self._lock:
            builds = self._rows(
                "SELECT * FROM builds WHERE project_id = ? ORDER BY id", (project_id,)
            )
            for build in builds:
                build["total_tokens"] = build["tokens_consumed"]
            return builds


Store = PlatformStore
