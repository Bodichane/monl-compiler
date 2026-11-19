"""Proofs of the shared persistence of the platform's two parts."""

import os
import sqlite3
import uuid

import pytest

from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore


def _descriptors_on(path):
    folder = "/proc/self/fd"
    if not os.path.isdir(folder):
        pytest.skip("descriptor counting requires /proc")
    path = str(path)
    open_ = 0
    with os.scandir(folder) as entrees:
        for entry in entrees:
            try:
                if path in os.readlink(entry.path):
                    open_ += 1
            except OSError:
                continue
    return open_


def _close(login):
    login.close()


def test_the_backup_covers_identity_and_builder(tmp_path):
    identities = IdentityStore(tmp_path)
    user = identities.register("alice@example.test", "MotDePasse-123")
    platform = PlatformStore(tmp_path)
    assert platform.database == str(identities.path)
    project = uuid.uuid4().hex
    identities.add_project(user["id"], project, "Atelier")
    platform.create_project(user["id"], project, "atelier")

    copy = identities.back_up(tmp_path / "sauvegardes" / "base.sqlite3")
    login = sqlite3.connect(copy)
    try:
        assert login.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert login.execute(
            "SELECT COUNT(*) FROM builder_projects WHERE project_id = ?", (project,)
        ).fetchone()[0] == 1
    finally:
        _close(login)


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="/proc requis")
def test_the_builder_reads_close_their_connections(tmp_path):
    identities = IdentityStore(tmp_path)
    user = identities.register("lecteur@example.test", "MotDePasse-123")
    platform = PlatformStore(tmp_path)
    project = uuid.uuid4().hex
    identities.add_project(user["id"], project, "Atelier")
    platform.create_project(user["id"], project, "atelier")
    before = _descriptors_on(platform.database)

    for _ in range(500):
        assert platform.get_project(project)["project_id"] == project

    apres = _descriptors_on(platform.database)
    assert apres - before == 0, (
        f"{apres - before} descriptor(s) stay open after 500 reads"
    )


def test_identity_and_builder_share_the_same_database(tmp_path):
    identities = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)

    for number in range(3):
        email = f"compte-{number}@example.test"
        user = identities.register(email, "MotDePasse-123")
        project = f"{number:032x}"
        identities.add_project(user["id"], project, f"Site {number}")
        platform.create_project(user["id"], project, f"site-{number}")

        assert identities.projects(user["id"])[0]["name"] == f"Site {number}"
        assert platform.get_project(project)["project_id"] == project

    login = sqlite3.connect(platform.database)
    try:
        tables = {
            row[0]
            for row in login.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        _close(login)

    assert {"users", "projects", "accounts", "builder_projects", "builds"} <= tables
    assert len(platform.list_all_projects()) == 3
    assert len(identities.all_the_projects()) == 3
