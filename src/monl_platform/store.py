"""Persistance SQLite du socle de plateforme.

Le store ne connaît ni HTTP ni IA. Les opérations ouvrent une transaction
SQLite courte, ce qui convient à un worker et laisse SQLite jouer son rôle de
verrou entre plusieurs processus.
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

BUILD_STATES = ("en_attente", "en_cours", "reussie", "echouee")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _password_hash(password):
    if not isinstance(password, str) or not password:
        raise ValueError("mot de passe vide ou invalide")
    iterations = 310_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _password_matches(password, encoded):
    if not isinstance(password, str) or not encoded:
        return False
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(digest, expected)


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
                    password_hash TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    slug TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    model_routes TEXT NOT NULL DEFAULT '{}',
                    generate_images INTEGER NOT NULL DEFAULT 0,
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
                    warning_message TEXT,
                    snapshot_path TEXT,
                    snapshot_sha256 TEXT,
                    snapshot_bytes INTEGER,
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
                    "password_hash": "TEXT",
                    "created_at": "TEXT",
                },
                "projects": {
                    "account_id": "INTEGER",
                    "slug": "TEXT",
                    "created_at": "TEXT",
                    "model_routes": "TEXT NOT NULL DEFAULT '{}'",
                    "generate_images": "INTEGER NOT NULL DEFAULT 0",
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
                    for row in self._connection.execute(f"PRAGMA table_info({table})")
                }
                for name, definition in expected.items():
                    if name not in present:
                        self._connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        )
            self._connection.execute("PRAGMA user_version = 2")

    def _row(self, query, parameters=()):
        row = self._connection.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None

    def _rows(self, query, parameters=()):
        return [dict(row) for row in self._connection.execute(query, parameters)]

    @staticmethod
    def _normalize_model_routes(routes):
        """Valide la forme, en laissant les cibles au compilateur."""
        if routes is None:
            return {}
        if isinstance(routes, dict):
            declarations = routes.items()
        elif isinstance(routes, list):
            parsed = []
            for declaration in routes:
                if not isinstance(declaration, str):
                    raise ValueError("model_routes doit contenir des chaînes CIBLE=MODELE")
                target, separator, model = declaration.partition("=")
                if not separator:
                    raise ValueError(
                        f"routage de modèle invalide : {declaration!r} — "
                        "la forme attendue est CIBLE=MODELE."
                    )
                parsed.append((target, model))
            declarations = parsed
        else:
            raise ValueError("model_routes doit être un objet CIBLE: MODELE")

        normalized = {}
        for target, model in declarations:
            if not isinstance(target, str) or not isinstance(model, str):
                raise ValueError("model_routes doit contenir des chaînes CIBLE: MODELE")
            target = target.strip().replace("\\", "/")
            model = model.strip()
            if not target or not model:
                raise ValueError("routage de modèle invalide : cible et modèle requis")
            if target in normalized:
                raise ValueError(f"cible répétée dans le routage des modèles : {target!r}")
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

    def _project_row(self, query, parameters=()):
        return self._project_values(self._row(query, parameters))

    def _project_rows(self, query, parameters=()):
        return [self._project_values(row) for row in self._rows(query, parameters)]

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

    def create_account(self, identifier, password=None):
        identifier = str(identifier).strip()
        if not identifier or "\x00" in identifier:
            raise ValueError("identifiant de compte vide ou invalide")
        password_hash = _password_hash(password) if password is not None else None
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO accounts(identifier, password_hash, created_at) VALUES (?, ?, ?)",
                (identifier, password_hash, _now()),
            )
            return cursor.lastrowid

    def authenticate_account(self, identifier, password):
        identifier = str(identifier).strip()
        with self._lock:
            row = self._row(
                "SELECT id, password_hash FROM accounts WHERE identifier = ?",
                (identifier,),
            )
            if row is None or not _password_matches(password, row["password_hash"]):
                return None
            return row["id"]

    def get_account(self, account):
        with self._lock:
            account_id = self._account_id(account)
            return self._row("SELECT * FROM accounts WHERE id = ?", (account_id,))

    def create_project(self, account, slug, *, model_routes=None, generate_images=False):
        slug = str(slug).strip()
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise ValueError("slug de projet invalide : remontée de chemin refusée")
        if not isinstance(generate_images, bool):
            raise ValueError("generate_images doit être un booléen")
        routes = self._normalize_model_routes(model_routes)
        with self._lock, self._connection:
            account_id = self._account_id(account)
            cursor = self._connection.execute(
                "INSERT INTO projects(account_id, slug, created_at, model_routes, "
                "generate_images) VALUES (?, ?, ?, ?, ?)",
                (account_id, slug, _now(), json.dumps(routes, sort_keys=True),
                 int(generate_images)),
            )
            return cursor.lastrowid

    def discard_project(self, account, project_id):
        """Supprime un projet tout juste créé si son initialisation échoue.

        Cette primitive n'est pas une API utilisateur : elle sert de
        compensation à l'écriture de ``spec.ml`` dans la même requête HTTP.
        Un projet possédant déjà une construction ne peut pas être écarté.
        """
        if isinstance(project_id, bool) or not isinstance(project_id, int):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connection:
            account_id = self._account_id(account)
            row = self._row(
                "SELECT id FROM projects WHERE id = ? AND account_id = ?",
                (project_id, account_id),
            )
            if row is None:
                return False
            build = self._row(
                "SELECT id FROM builds WHERE project_id = ? LIMIT 1", (project_id,)
            )
            if build is not None:
                raise ValueError("projet déjà construit : suppression de compensation refusée")
            deleted = self._connection.execute(
                "DELETE FROM projects WHERE id = ? AND account_id = ?",
                (project_id, account_id),
            )
            return deleted.rowcount == 1

    def get_project(self, project_id):
        with self._lock:
            return self._project_row("SELECT * FROM projects WHERE id = ?", (project_id,))

    def get_project_for_account(self, account, project_id):
        with self._lock:
            account_id = self._account_id(account)
            return self._project_row(
                "SELECT * FROM projects WHERE id = ? AND account_id = ?",
                (project_id, account_id),
            )

    def list_projects(self, account):
        with self._lock:
            account_id = self._account_id(account)
            return self._project_rows(
                "SELECT * FROM projects WHERE account_id = ? ORDER BY id", (account_id,)
            )

    def list_all_projects(self):
        with self._lock:
            return self._project_rows("SELECT * FROM projects ORDER BY id")

    def list_projects_by_slug(self, slug):
        with self._lock:
            return self._project_rows(
                "SELECT * FROM projects WHERE slug = ? ORDER BY id", (str(slug),)
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

    def claim_next_build(self):
        """Réserve atomiquement la prochaine construction en attente."""
        with self._lock, self._connection:
            build = self._row(
                "SELECT * FROM builds WHERE state = 'en_attente' ORDER BY id LIMIT 1"
            )
            if build is None:
                return None
            updated = self._connection.execute(
                "UPDATE builds SET state = ?, started_at = ? "
                "WHERE id = ? AND state = 'en_attente'",
                ("en_cours", _now(), build["id"]),
            )
            if updated.rowcount != 1:
                return None
            build["state"] = "en_cours"
            build["started_at"] = self._row(
                "SELECT started_at FROM builds WHERE id = ?", (build["id"],)
            )["started_at"]
            return build

    def recover_in_progress_builds(self, message="construction interrompue au redémarrage"):
        """Ne laisse jamais une construction abandonnée mentir en ``en_cours``."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE builds SET state = ?, finished_at = ?, error_message = ?, "
                "warning_message = NULL "
                "WHERE state = 'en_cours'",
                ("echouee", _now(), message),
            )
            return cursor.rowcount

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
        warning_message=None,
        snapshot_path=None,
        snapshot_sha256=None,
        snapshot_bytes=None,
    ):
        if state not in {"reussie", "echouee"}:
            raise ValueError(f"état terminal invalide : {state}")
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE builds SET state = ?, run_id = ?, tokens_consumed = ?,
                   input_tokens = ?, output_tokens = ?, cost = ?, currency = ?,
                   price_status = ?, finished_at = ?, error_message = ?,
                   warning_message = ?, snapshot_path = ?, snapshot_sha256 = ?,
                   snapshot_bytes = ? WHERE id = ?""",
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
                    warning_message,
                    snapshot_path,
                    snapshot_sha256,
                    snapshot_bytes,
                    build_id,
                ),
            )

    def get_build(self, build_id):
        with self._lock:
            build = self._row("SELECT * FROM builds WHERE id = ?", (build_id,))
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def get_build_for_project(self, project_id, build_id):
        with self._lock:
            build = self._row(
                "SELECT * FROM builds WHERE id = ? AND project_id = ?",
                (build_id, project_id),
            )
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
