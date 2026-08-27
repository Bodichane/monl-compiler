"""SQLite schema and connection lifecycle for identities."""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path


class IdentityDatabaseMixin:
    def __init__(self, workspace: str | os.PathLike[str]):
        self.path = Path(workspace).resolve() / "platform.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Ouvre, valide (ou annule), puis FERME.

        `with sqlite3.connect(...)` valide la transaction mais ne ferme pas la
        connexion — et un objet `Connection` de CPython prend part à des cycles
        de références, donc il n'est rendu que par le ramasse-miettes
        cyclique, pas au retour de la méthode. Mesuré : 500 lectures laissaient
        **197 descripteurs** ouverts sur la base, tous rendus d'un coup par un
        `gc.collect()` manuel. Ce n'est pas une fuite éternelle, c'est pire à
        exploiter — un serveur sous charge peut atteindre sa limite de
        descripteurs avant qu'une collecte de génération 2 ne survienne, et
        l'incident ne ressemble alors à rien de connu.

        Deuxième conséquence, celle qui a révélé la première : tant qu'une
        connexion vit, SQLite ne rabat pas le journal WAL dans le fichier
        principal. La base restait à 4 096 octets avec 111 Ko de WAL à côté —
        et la restauration documentée dans `docs/EXPLOITATION.md` échouait sur
        un « disk I/O error » en remettant le fichier en place.

        Le `with connection:` interne conserve exactement l'ancienne sémantique
        (validation en sortie propre, annulation sur exception) ; seule la
        fermeture est ajoutée. Les deux appelants qui lisent `cursor.rowcount`
        APRÈS le bloc continuent de fonctionner : la valeur est figée à
        l'exécution, pas relue dans la connexion.
        """
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def ready(self) -> bool:
        try:
            with self._connect() as db:
                return db.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def _migrate(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash BLOB NOT NULL,
                password_salt BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                auth_provider TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS projects_user_created
                ON projects(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER,
                revoked_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS api_keys_user_created
                ON api_keys(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS recovery_codes (
                code_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS recovery_codes_user
                ON recovery_codes(user_id);
            CREATE TABLE IF NOT EXISTS rate_limits (
                scope TEXT NOT NULL,
                subject TEXT NOT NULL,
                window_start INTEGER NOT NULL,
                hits INTEGER NOT NULL,
                PRIMARY KEY (scope, subject)
            );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            if "expires_at" not in columns:
                db.execute("ALTER TABLE projects ADD COLUMN expires_at INTEGER")
            user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "auth_provider" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT")




