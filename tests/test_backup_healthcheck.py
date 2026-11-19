"""The backup probe checks the content, not only the file name."""

import os
import pathlib
import sqlite3
import time

import pytest

from monl_platform.backup_healthcheck import _sqlite_valid, backup_recent


def _copie_valid(path):
    # Explicit close (point 141): `with sqlite3.connect(...)` commits the
    # transaction but does not close — without `.close()`, this test helper
    # itself left a descriptor open on the file it had just created, skewing
    # the test below that counts the PROBE's.
    login = sqlite3.connect(path)
    try:
        with login:
            login.execute("CREATE TABLE preuve (id INTEGER PRIMARY KEY)")
    finally:
        login.close()


def test_a_recent_intact_sqlite_copy_is_healthy(tmp_path):
    path = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valid(path)

    assert backup_recent(tmp_path, now=time.time(), age_maximal=60)


def test_an_empty_or_corrupt_copy_is_unhealthy(tmp_path):
    (tmp_path / "base-vide.sqlite3").write_bytes(b"")
    (tmp_path / "base-corrompue.sqlite3").write_bytes(b"pas une base sqlite")

    assert not backup_recent(tmp_path, now=time.time(), age_maximal=60)


def test_a_too_old_copy_is_unhealthy(tmp_path):
    path = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valid(path)

    assert not backup_recent(tmp_path, now=time.time() + 61, age_maximal=60)


def _descriptors(path):
    """How many descriptors this process holds open on this file."""
    folder = pathlib.Path("/proc") / str(os.getpid()) / "fd"
    total = 0
    for entry in folder.iterdir():
        try:
            if str(path) in os.readlink(entry):
                total += 1
        except OSError:                       # descriptor closed in between
            continue
    return total


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"),
                    reason="descriptor counting requires /proc")
def test_the_probe_leaves_no_connection_open_behind_it(tmp_path):
    """`with sqlite3.connect(...)` commits the transaction, but does NOT CLOSE
    (point 141, identity_database.py) — a CPython `Connection` object takes
    part in reference cycles and is only released by the cyclic garbage
    collector. This probe runs every 30 s in the backup container: without an
    explicit close, it piles up one descriptor per call until it hits the
    container's limit.

    Reproduced and measured BEFORE the fix on this very file: 300 calls left
    260 descriptors open, 193 still there after a manual `gc.collect()`.
    """
    path = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valid(path)

    for _ in range(200):
        assert _sqlite_valid(path)

    open_ = _descriptors(path)
    assert open_ == 0, f"{open_} descriptors stay open on the backup"
