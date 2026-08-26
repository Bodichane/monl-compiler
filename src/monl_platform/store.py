"""Persistance SQLite du socle de plateforme.

Le store ne connaît ni HTTP ni IA. Chaque opération ouvre une transaction
SQLite courte, ce qui convient à un worker et laisse SQLite jouer son rôle de
verrou entre plusieurs processus.
"""

import contextlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

BUILD_STATES = ("en_attente", "en_cours", "reussie", "echouee")


def normalize_slug(slug):
    """Forme canonique du slug, qui est l'ADRESSE du site.

    Le sous-domaine sert d'identifiant d'hébergement, et un navigateur met
    toujours le nom d'hôte en minuscules avant de l'envoyer. Sans forme
    canonique, « myOwn » et « myown » sont donc deux projets distincts pour la
    base et un seul pour le réseau : le site construit devient injoignable, et
    deux comptes peuvent se disputer la même adresse. Même raisonnement qu'au
    point 95 sur l'identifiant de compte — la substance n'est pas la
    validation, c'est la normalisation.
    """
    return str(slug).strip().lower()


def _now():
    return datetime.now(timezone.utc).isoformat()


class PlatformStore:
    """Store SQLite avec création et migration additive au démarrage.

    ``workspace`` est le dossier partagé avec :class:`IdentityStore`. Les
    connexions sont volontairement éphémères : garder une connexion du
    constructeur ouverte empêcherait le rabattement du WAL de la base
    commune.
    """

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
            db.execute("PRAGMA user_version = 2")

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

    def create_project(
        self, user_id, project_id, slug, *, model_routes=None, generate_images=False
    ):
        """Ajoute les métadonnées constructeur d'un projet déjà identitaire.

        Le projet lui-même doit d'abord être créé par
        ``IdentityStore.add_project(user_id, project_id, name)``. Les clés
        étrangères rendent cet ordre vérifiable et laissent l'identité
        posséder la suppression en cascade.
        """
        if not isinstance(user_id, str) or not user_id or "\x00" in user_id:
            raise ValueError("identifiant d'utilisateur invalide")
        if not isinstance(project_id, str) or not project_id or "\x00" in project_id:
            raise ValueError("identifiant de projet invalide")
        slug = normalize_slug(slug)
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            raise ValueError("slug de projet invalide : remontée de chemin refusée")
        if not isinstance(generate_images, bool):
            raise ValueError("generate_images doit être un booléen")
        routes = self._normalize_model_routes(model_routes)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, created_at, "
                "model_routes, generate_images) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, user_id, slug, _now(), json.dumps(routes, sort_keys=True),
                 int(generate_images)),
            )
            return project_id

    def discard_project(self, user_id, project_id):
        """Supprime un projet tout juste créé si son initialisation échoue.

        Cette primitive n'est pas une API utilisateur : elle sert de
        compensation à l'écriture de ``spec.ml`` dans la même requête HTTP.
        Un projet possédant déjà une construction ne peut pas être écarté.
        """
        if not isinstance(user_id, str) or not isinstance(project_id, str):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connect() as db:
            row = self._row(
                db,
                "SELECT project_id FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            if row is None:
                return False
            build = self._row(
                db,
                "SELECT id FROM builds WHERE project_id = ? LIMIT 1", (project_id,)
            )
            if build is not None:
                raise ValueError("projet déjà construit : suppression de compensation refusée")
            deleted = db.execute(
                "DELETE FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            return deleted.rowcount == 1

    def get_project(self, project_id):
        with self._lock, self._connect() as db:
            return self._project_row(
                db, "SELECT * FROM builder_projects WHERE project_id = ?", (project_id,)
            )

    def get_project_for_user(self, user_id, project_id):
        with self._lock, self._connect() as db:
            return self._project_row(
                db,
                "SELECT * FROM builder_projects WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )

    def list_projects(self, user_id):
        with self._lock, self._connect() as db:
            return self._project_rows(
                db,
                "SELECT * FROM builder_projects WHERE user_id = ? ORDER BY project_id",
                (user_id,),
            )

    def list_all_projects(self):
        with self._lock, self._connect() as db:
            return self._project_rows(
                db, "SELECT * FROM builder_projects ORDER BY project_id"
            )

    def list_projects_by_slug(self, slug):
        # COLLATE NOCASE, et pas seulement une comparaison sur la forme
        # canonique : les projets créés avant la normalisation portent encore
        # leur majuscule en base, et ce sont des sites déjà construits et déjà
        # payés. Une comparaison stricte les laisserait injoignables.
        with self._lock, self._connect() as db:
            return self._project_rows(
                db,
                "SELECT * FROM builder_projects WHERE slug = ? COLLATE NOCASE "
                "ORDER BY project_id",
                (normalize_slug(slug),),
            )

    def create_build(self, project_id):
        if isinstance(project_id, bool):
            raise ValueError("identifiant de projet invalide")
        with self._lock, self._connect() as db:
            if self._row(
                db, "SELECT project_id FROM builder_projects WHERE project_id = ?",
                (project_id,),
            ) is None:
                raise KeyError(f"projet introuvable : {project_id}")
            cursor = db.execute(
                "INSERT INTO builds(project_id, state, created_at) VALUES (?, ?, ?)",
                (project_id, "en_attente", _now()),
            )
            return cursor.lastrowid

    def start_build(self, build_id):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE builds SET state = ?, started_at = ? WHERE id = ?",
                ("en_cours", _now(), build_id),
            )

    def claim_next_build(self):
        """Réserve atomiquement la prochaine construction en attente."""
        with self._lock, self._connect() as db:
            build = self._row(
                db,
                "SELECT * FROM builds WHERE state = 'en_attente' ORDER BY id LIMIT 1"
            )
            if build is None:
                return None
            updated = db.execute(
                "UPDATE builds SET state = ?, started_at = ? "
                "WHERE id = ? AND state = 'en_attente'",
                ("en_cours", _now(), build["id"]),
            )
            if updated.rowcount != 1:
                return None
            build["state"] = "en_cours"
            build["started_at"] = self._row(
                db,
                "SELECT started_at FROM builds WHERE id = ?", (build["id"],)
            )["started_at"]
            return build

    def recover_in_progress_builds(self, message="construction interrompue au redémarrage"):
        """Ne laisse jamais une construction abandonnée mentir en ``en_cours``."""
        with self._lock, self._connect() as db:
            cursor = db.execute(
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
        with self._lock, self._connect() as db:
            db.execute(
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
        with self._lock, self._connect() as db:
            build = self._row(db, "SELECT * FROM builds WHERE id = ?", (build_id,))
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def get_build_for_project(self, project_id, build_id):
        with self._lock, self._connect() as db:
            build = self._row(
                db,
                "SELECT * FROM builds WHERE id = ? AND project_id = ?",
                (build_id, project_id),
            )
            if build is not None:
                build["total_tokens"] = build["tokens_consumed"]
            return build

    def list_builds(self, project_id):
        with self._lock, self._connect() as db:
            builds = self._rows(
                db,
                "SELECT * FROM builds WHERE project_id = ? ORDER BY id", (project_id,)
            )
            for build in builds:
                build["total_tokens"] = build["tokens_consumed"]
            return builds


Store = PlatformStore
