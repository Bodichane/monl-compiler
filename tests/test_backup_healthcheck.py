"""The backup probe checks the content, not only the file name."""

import os
import pathlib
import sqlite3
import time

import pytest

from monl_platform.backup_healthcheck import _sqlite_valide, sauvegarde_recente


def _copie_valide(chemin):
    # Explicit close (point 141): `with sqlite3.connect(...)` commits the
    # transaction but does not close — without `.close()`, this test helper
    # itself left a descriptor open on the file it had just created, skewing
    # the test below that counts the PROBE's.
    connexion = sqlite3.connect(chemin)
    try:
        with connexion:
            connexion.execute("CREATE TABLE preuve (id INTEGER PRIMARY KEY)")
    finally:
        connexion.close()


def test_a_recent_intact_sqlite_copy_is_healthy(tmp_path):
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    assert sauvegarde_recente(tmp_path, maintenant=time.time(), age_maximal=60)


def test_an_empty_or_corrupt_copy_is_unhealthy(tmp_path):
    (tmp_path / "base-vide.sqlite3").write_bytes(b"")
    (tmp_path / "base-corrompue.sqlite3").write_bytes(b"pas une base sqlite")

    assert not sauvegarde_recente(tmp_path, maintenant=time.time(), age_maximal=60)


def test_a_too_old_copy_is_unhealthy(tmp_path):
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    assert not sauvegarde_recente(tmp_path, maintenant=time.time() + 61, age_maximal=60)


def _descripteurs(chemin):
    """How many descriptors this process holds open on this file."""
    dossier = pathlib.Path("/proc") / str(os.getpid()) / "fd"
    total = 0
    for entree in dossier.iterdir():
        try:
            if str(chemin) in os.readlink(entree):
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
    chemin = tmp_path / "base-20260914-120000.sqlite3"
    _copie_valide(chemin)

    for _ in range(200):
        assert _sqlite_valide(chemin)

    ouverts = _descripteurs(chemin)
    assert ouverts == 0, f"{ouverts} descriptors stay open on the backup"
