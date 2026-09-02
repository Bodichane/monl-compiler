"""SQLite schema, migrations and shared store helpers."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

BUILD_STATES = ("en_attente", "en_cours", "reussie", "echouee")


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
        """Ouvre, valide (ou annule), puis ferme une connexion SQLite."""
        connection = sqlite3.connect(
            self.database, check_same_thread=False, timeout=30
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def close(self):
        """Compatibilité avec les appelants : aucune connexion ne persiste."""
        return None

    def _migrate(self):
        """Crée le schéma puis ajoute seulement les colonnes manquantes.

        Une exécution répétée est sans effet. Une évolution future doit
        ajouter une entrée à ``columns`` plutôt que supprimer ou renommer une
        colonne : c'est la discipline des migrations additives de monl.
        """
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
            self._armer_unicite_du_slug(db)
            db.execute("PRAGMA user_version = 2")

    @staticmethod
    def _armer_unicite_du_slug(db):
        """L'adresse d'un site est UNIQUE sur toute la plateforme.

        C'est un sous-domaine : deux projets qui la partagent rendent l'hôte
        ambigu, et `SiteManager.project_for_host` refuse alors de servir — il
        a raison de refuser, mais rien n'empêchait d'en arriver là.
        `UNIQUE(user_id, slug)` ne protégeait que d'un homonyme du MÊME compte.

        Un INDEX, et pas une vérification applicative : c'est lui qui tient
        aussi deux écritures concurrentes. Et `IF NOT EXISTS`, comme au
        point 85 — la migration additive du dépôt ajoute, elle ne réécrit pas.

        SUR UNE BASE DÉJÀ EN DOUBLON, la création échoue. On ne renomme PAS :
        changer l'adresse d'un site en ligne au démarrage serait pire que le
        défaut qu'on corrige. Les doublons sont COMPTÉS et NOMMÉS — même
        arbitrage qu'au point 89 pour les enregistrements sans horodatage —
        et l'exploitant tranche en supprimant les projets en trop.
        """
        try:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_builder_projects_slug "
                       "ON builder_projects(slug)")
            return
        except sqlite3.IntegrityError:
            pass
        doublons = [
            (ligne["slug"], ligne["combien"])
            for ligne in db.execute(
                "SELECT slug, COUNT(*) AS combien FROM builder_projects "
                "GROUP BY slug COLLATE NOCASE HAVING combien > 1 ORDER BY slug")
        ]
        details = ", ".join(f"{slug} ({combien})" for slug, combien in doublons)
        print(
            f"⚠️  {len(doublons)} adresse(s) de site portée(s) par plusieurs projets : "
            f"{details}. Ces sites ne peuvent pas être servis tant que le doublon "
            "dure — supprimez les projets en trop, l'unicité s'armera au "
            "redémarrage suivant."
        )

    @staticmethod
    def _reject_non_additive_project_schema(db, *, complete=True):
        """Refuse une ancienne forme qui demanderait reconstruction ou DROP.

        La tranche précédente a créé ``builder_projects.id`` et
        ``builder_projects.account_id``. SQLite ne permet pas de transformer
        honnêtement cette table en place : il faudrait déplacer des lignes et
        réécrire les clés étrangères. La migration additive du dépôt refuse
        donc le démarrage en nommant la procédure manuelle, tout en laissant
        intactes les données héritées.
        """
        builder = {
            row["name"]: (row["type"] or "").upper()
            for row in db.execute("PRAGMA table_info(builder_projects)")
        }
        builds = {
            row["name"]: (row["type"] or "").upper()
            for row in db.execute("PRAGMA table_info(builds)")
        }
        if not builder and not builds:
            return
        if "id" in builder or "account_id" in builder:
            raise RuntimeError(
                "migration non additive requise : builder_projects utilise encore "
                "id/account_id ; aucune conversion automatique n'est effectuée"
            )
        if builds and builds.get("project_id") != "TEXT":
            raise RuntimeError(
                "migration non additive requise : builds.project_id doit être TEXT ; "
                "aucune reconstruction automatique n'est effectuée"
            )
        if not complete:
            return
        builder_fks = {
            (row["from"], row["table"], row["on_delete"])
            for row in db.execute("PRAGMA foreign_key_list(builder_projects)")
        }
        if ("project_id", "projects", "CASCADE") not in builder_fks:
            raise RuntimeError(
                "schéma constructeur invalide : builder_projects.project_id doit "
                "référencer projects avec ON DELETE CASCADE"
            )
        build_fks = {
            (row["from"], row["table"], row["on_delete"])
            for row in db.execute("PRAGMA foreign_key_list(builds)")
        }
        if ("project_id", "builder_projects", "CASCADE") not in build_fks:
            raise RuntimeError(
                "schéma constructeur invalide : builds.project_id doit référencer "
                "builder_projects avec ON DELETE CASCADE"
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

    def _project_row(self, db, query, parameters=()):
        return self._project_values(self._row(db, query, parameters))

    def _project_rows(self, db, query, parameters=()):
        return [self._project_values(row) for row in self._rows(db, query, parameters)]

    def legacy_account_count(self):
        """Compte les lignes de l'ancien registre sans jamais les employer."""
        with self._lock, self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]



