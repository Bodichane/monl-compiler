"""Validity probe of the Compose service's latest backup."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

BACKUP_DIRECTORY = Path("/backups")
MAX_AGE_ENV = "MONL_BACKUP_MAX_AGE_SECONDS"
DEFAULT_MAX_AGE = 172800


def _sqlite_valide(chemin: Path) -> bool:
    """Checks that a recent copy is really readable by SQLite.

    `with sqlite3.connect(...)` commits the transaction but does NOT CLOSE the
    connection (point 141, identity_database.py): a CPython `Connection`
    object takes part in reference cycles, so it is only released by the
    cyclic garbage collector. This probe runs every 30 s in the backup
    container — without an explicit close, it accumulates one descriptor per
    call until it hits the container's limit, at which point
    `sqlite3.connect` itself raises an error this block already swallows: the
    healthcheck would then declare itself unhealthy for a backup that is
    valid."""
    try:
        connexion = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        return False
    try:
        with connexion:
            return connexion.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    except (OSError, sqlite3.Error):
        return False
    finally:
        connexion.close()


def sauvegarde_recente(
    directory: Path = BACKUP_DIRECTORY,
    *,
    maintenant: float | None = None,
    age_maximal: int = DEFAULT_MAX_AGE,
) -> bool:
    """Says whether the folder contains a recent and intact SQLite copy."""
    instant = time.time() if maintenant is None else maintenant
    try:
        candidates = sorted(
            (
                chemin
                for chemin in directory.glob("base-*.sqlite3")
                if chemin.is_file() and not chemin.is_symlink() and chemin.stat().st_size > 0
            ),
            key=lambda chemin: chemin.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return False

    for chemin in candidates:
        try:
            recente = instant - chemin.stat().st_mtime <= age_maximal
        except OSError:
            continue
        if recente and _sqlite_valide(chemin):
            return True
    return False


def main() -> int:
    try:
        age_maximal = int(os.environ.get(MAX_AGE_ENV, str(DEFAULT_MAX_AGE)))
    except ValueError:
        return 1
    return 0 if sauvegarde_recente(age_maximal=max(0, age_maximal)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
