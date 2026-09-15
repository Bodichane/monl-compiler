"""Sonde de validité de la dernière sauvegarde du service Compose."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

BACKUP_DIRECTORY = Path("/backups")
MAX_AGE_ENV = "MONL_BACKUP_MAX_AGE_SECONDS"
DEFAULT_MAX_AGE = 172800


def _sqlite_valide(chemin: Path) -> bool:
    """Vérifie qu'une copie récente est réellement lisible par SQLite.

    `with sqlite3.connect(...)` valide la transaction mais ne FERME pas la
    connexion (point 141, identity_database.py) : un objet `Connection` de
    CPython prend part à des cycles de références, donc il n'est rendu qu'au
    ramasse-miettes cyclique. Cette sonde tourne toutes les 30 s dans le
    conteneur de sauvegarde — sans fermeture explicite, elle accumule un
    descripteur par appel jusqu'à heurter la limite du conteneur, moment où
    `sqlite3.connect` lève à son tour une erreur que ce bloc absorbe déjà :
    le healthcheck se déclarerait alors unhealthy pour une sauvegarde
    pourtant valide.
    """
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
    """Indique si le dossier contient une copie SQLite récente et intègre."""
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
