"""Opening a SQLite database in a test: commit AND close.

`with sqlite3.connect(path) as db:` only commits (or rolls back) the
transaction on exit: the connection stays OPEN until the garbage collector
runs. It is the trap of points 141 and 185, which cost descriptors and
-wal/-shm files in production; in the suite, it produced 72
`ResourceWarning: unclosed database` under Python 3.14.

`sqlite_db` keeps exactly the original `with` semantics (commit if the
block succeeds, rollback if it raises) and ALWAYS closes. It is the only form
allowed in `tests/`: `pyproject.toml` turns every `ResourceWarning` into an
error, and `test_architecture.py` refuses the bare pattern.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from os import PathLike


@contextlib.contextmanager
def sqlite_db(path: str | PathLike[str], **options) -> Iterator[sqlite3.Connection]:
    """Connection committed on leaving the block, then closed whatever happens."""
    login = sqlite3.connect(path, **options)
    try:
        with login:
            yield login
    finally:
        login.close()
