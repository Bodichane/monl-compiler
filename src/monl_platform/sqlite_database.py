"""Shared SQLite journal initialization for platform stores."""

import sqlite3
import time


def activate_wal(connection):
    """Retry journal conversion within the connection's existing busy budget.

    SQLite can reject rollback-to-WAL conversion immediately despite its
    busy timeout. Disable the native wait during retries so even readers
    cannot extend our monotonic deadline; restore it for normal queries.
    """
    busy_ms = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    deadline = time.monotonic() + busy_ms / 1000
    connection.execute("PRAGMA busy_timeout = 0")
    try:
        while True:
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                return
            except sqlite3.OperationalError as error:
                code = getattr(error, "sqlite_errorcode", None)
                # sqlite_errorcode is unavailable on Python 3.10.
                transient = (code & 0xff in (5, 6) if code is not None
                             else str(error).lower() in ("database is locked", "database table is locked"))
                remaining = deadline - time.monotonic()
                if not transient or remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))
    finally:
        connection.execute(f"PRAGMA busy_timeout = {busy_ms}")
