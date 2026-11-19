"""SQLite schema, migrations and shared store helpers."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .sqlite_database import activate_wal

BUILD_STATES = ("en_attente", "en_cours", "reussie", "echouee")


def _types_of_columns(db, table):
    """{column: uppercase TYPE} of a table, empty if it does not exist. `table`
    is an internal constant, never a received value."""
    return {
        row["name"]: (row["type"] or "").upper()
        for row in db.execute(f"PRAGMA table_info({table})")
    }


def normalize_slug(slug):
    """Return the canonical, case-insensitive site slug."""
    return str(slug).strip().lower()


def _now():
    return datetime.now(timezone.utc).isoformat()


class StoreCoreMixin:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.database = str(self.workspace / "platform.sqlite3")
        self._lock = threading.RLock()
        self._migrate()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Opens, commits (or rolls back), then closes a SQLite connection."""
        connection = sqlite3.connect(
            self.database, check_same_thread=False, timeout=30
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            activate_wal(connection)
            with connection:
                yield connection
        finally:
            connection.close()

    def close(self):
        """Compatibility with callers: no connection persists."""
        return None

    def _migrate(self):
        """Creates the schema then adds only the missing columns.

        A repeated run has no effect. A future change must add an entry to
        ``columns`` rather than delete or rename a column: it is the discipline of
        monl's additive migrations."""
        with self._lock, self._connect() as db:
            self._reject_non_additive_project_schema(db, complete=False)
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    identifier TEXT NOT NULL UNIQUE,
                    password_hash TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS builder_projects (
                    project_id TEXT PRIMARY KEY REFERENCES projects(project_id)
                        ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    slug TEXT NOT NULL,
                    model_routes TEXT NOT NULL DEFAULT '{}',
                    generate_images INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, slug)
                );
                CREATE TABLE IF NOT EXISTS builds (
                    id INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES builder_projects(project_id)
                        ON DELETE CASCADE,
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
                    warning_message TEXT,
                    snapshot_path TEXT,
                    snapshot_sha256 TEXT,
                    snapshot_bytes INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_builder_projects_user
                    ON builder_projects(user_id);
                CREATE INDEX IF NOT EXISTS idx_builds_project
                    ON builds(project_id);
                """
            )
            self._reject_non_additive_project_schema(db)
            columns = {
                "accounts": {
                    "identifier": "TEXT",
                    "password_hash": "TEXT",
                    "created_at": "TEXT",
                },
                "builder_projects": {
                    "project_id": "TEXT",
                    "user_id": "TEXT",
                    "slug": "TEXT",
                    "created_at": "TEXT",
                    "model_routes": "TEXT NOT NULL DEFAULT '{}'",
                    "generate_images": "INTEGER NOT NULL DEFAULT 0",
                },
                "builds": {
                    "project_id": "TEXT",
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
                    "warning_message": "TEXT",
                    "snapshot_path": "TEXT",
                    "snapshot_sha256": "TEXT",
                    "snapshot_bytes": "INTEGER",
                    "created_at": "TEXT",
                },
            }
            for table, expected in columns.items():
                present = {
                    row["name"]
                    for row in db.execute(f"PRAGMA table_info({table})")
                }
                for name, definition in expected.items():
                    if name not in present:
                        db.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        )
            self._arm_uniqueness_of_slug(db)
            db.execute("PRAGMA user_version = 2")

    @staticmethod
    def _arm_uniqueness_of_slug(db):
        """A site's address is UNIQUE across the whole platform.

        It is a subdomain: two projects sharing it make the host ambiguous, and
        `SiteManager.project_for_host` then refuses to serve — it is right to
        refuse, but nothing prevented getting there. `UNIQUE(user_id, slug)` only
        protected against a namesake in the SAME account.

        An INDEX, and not an application check: it is what also holds two
        concurrent writes. And `IF NOT EXISTS`, as in point 85 — the repository's
        additive migration adds, it does not rewrite.

        ON A DATABASE ALREADY HOLDING DUPLICATES, the creation fails. We do NOT
        rename: changing a live site's address at startup would be worse than the
        defect being fixed. The duplicates are COUNTED and NAMED — the same
        trade-off as point 89 for records without a timestamp — and the operator
        decides by deleting the extra projects."""
        try:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_builder_projects_slug "
                       "ON builder_projects(slug)")
            return
        except sqlite3.IntegrityError:
            pass
        duplicates = [
            (line["slug"], line["combien"])
            for line in db.execute(
                "SELECT slug, COUNT(*) AS combien FROM builder_projects "
                "GROUP BY slug COLLATE NOCASE HAVING combien > 1 ORDER BY slug")
        ]
        details = ", ".join(f"{slug} ({how_many})" for slug, how_many in duplicates)
        print(
            f"⚠️  {len(duplicates)} site address(es) carried by several projects: "
            f"{details}. These sites cannot be served while the duplicate "
            "lasts — delete the extra projects; uniqueness will be enforced at the "
            "next restart."
        )

    @staticmethod
    def _reject_non_additive_project_schema(db, *, complete=True):
        """Refuses an old shape that would require a rebuild or a DROP.

        The previous slice created ``builder_projects.id`` and
        ``builder_projects.account_id``. SQLite does not allow honestly
        transforming this table in place: rows would have to be moved and foreign
        keys rewritten. The repository's additive migration therefore refuses to
        start, naming the manual procedure, while leaving the inherited data
        intact."""
        builder = _types_of_columns(db, "builder_projects")
        builds = _types_of_columns(db, "builds")
        if not builder and not builds:
            return
        if "id" in builder or "account_id" in builder:
            raise RuntimeError(
                "non-additive migration required: builder_projects still uses "
                "id/account_id; no automatic conversion is performed"
            )
        if builds and builds.get("project_id") != "TEXT":
            raise RuntimeError(
                "non-additive migration required: builds.project_id must be TEXT; "
                "no automatic rebuild is performed"
            )
        if not complete:
            return
        builder_fks = {
            (row["from"], row["table"], row["on_delete"])
            for row in db.execute("PRAGMA foreign_key_list(builder_projects)")
        }
        if ("project_id", "projects", "CASCADE") not in builder_fks:
            raise RuntimeError(
                "invalid builder schema: builder_projects.project_id must "
                "reference projects with ON DELETE CASCADE"
            )
        build_fks = {
            (row["from"], row["table"], row["on_delete"])
            for row in db.execute("PRAGMA foreign_key_list(builds)")
        }
        if ("project_id", "builder_projects", "CASCADE") not in build_fks:
            raise RuntimeError(
                "invalid builder schema: builds.project_id must reference "
                "builder_projects with ON DELETE CASCADE"
            )

    @staticmethod
    def _row(db, query, parameters=()):
        row = db.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _rows(db, query, parameters=()):
        return [dict(row) for row in db.execute(query, parameters)]

    @staticmethod
    def _normalize_model_routes(routes):
        """Validates the shape, leaving the targets to the compiler."""
        if routes is None:
            return {}
        if isinstance(routes, dict):
            declarations = routes.items()
        elif isinstance(routes, list):
            parsed = []
            for declaration in routes:
                if not isinstance(declaration, str):
                    raise ValueError("model_routes must contain TARGET=MODEL strings")
                target, separator, model = declaration.partition("=")
                if not separator:
                    raise ValueError(
                        f"invalid model routing: {declaration!r} — "
                        "the expected form is TARGET=MODEL."
                    )
                parsed.append((target, model))
            declarations = parsed
        else:
            raise ValueError("model_routes must be a TARGET: MODEL object")

        normalized = {}
        for target, model in declarations:
            if not isinstance(target, str) or not isinstance(model, str):
                raise ValueError("model_routes must contain TARGET: MODEL strings")
            target = target.strip().replace("\\", "/")
            model = model.strip()
            if not target or not model:
                raise ValueError("invalid model routing: target and model required")
            if target in normalized:
                raise ValueError(f"target repeated in the model routing: {target!r}")
            normalized[target] = model
        return normalized

    @staticmethod
    def _project_values(project):
        if project is None:
            return None
        project = dict(project)
        try:
            routes = json.loads(project.get("model_routes") or "{}")
        except (TypeError, json.JSONDecodeError):
            routes = {}
        project["model_routes"] = routes if isinstance(routes, dict) else {}
        project["generate_images"] = bool(project.get("generate_images", 0))
        return project

    def _project_row(self, db, query, parameters=()):
        return self._project_values(self._row(db, query, parameters))

    def _project_rows(self, db, query, parameters=()):
        return [self._project_values(row) for row in self._rows(db, query, parameters)]

    def legacy_account_count(self):
        """Counts the rows of the old registry without ever using them."""
        with self._lock, self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]



