"""Ouvrir une base SQLite dans un test : valider ET fermer.

`with sqlite3.connect(chemin) as db:` ne fait que valider (ou annuler) la
transaction en sortie : la connexion reste OUVERTE jusqu'au passage du
ramasse-miettes. C'est le piège des points 141 et 185, qui coûtait des
descripteurs et des fichiers -wal/-shm en production ; dans la suite, il
produisait 72 `ResourceWarning: unclosed database` sous Python 3.14.

`base_sqlite` garde exactement la sémantique du `with` d'origine (validation
si le bloc réussit, annulation s'il lève) et ferme TOUJOURS. C'est la seule
forme admise dans `tests/` : `pyproject.toml` transforme tout
`ResourceWarning` en erreur, et `test_architecture.py` refuse le motif nu.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from os import PathLike


@contextlib.contextmanager
def base_sqlite(chemin: str | PathLike[str], **options) -> Iterator[sqlite3.Connection]:
    """Connexion validée en sortie de bloc, puis fermée quoi qu'il arrive."""
    connexion = sqlite3.connect(chemin, **options)
    try:
        with connexion:
            yield connexion
    finally:
        connexion.close()
