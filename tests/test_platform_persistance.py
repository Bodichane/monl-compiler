"""Preuves de la persistance commune des deux parties de la plateforme."""

import os
import sqlite3

import pytest

from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore


def _descripteurs_sur(chemin):
    dossier = "/proc/self/fd"
    if not os.path.isdir(dossier):
        pytest.skip("le décompte de descripteurs demande /proc")
    chemin = str(chemin)
    ouverts = 0
    with os.scandir(dossier) as entrees:
        for entree in entrees:
            try:
                if chemin in os.readlink(entree.path):
                    ouverts += 1
            except OSError:
                continue
    return ouverts


def _fermer(connexion):
    connexion.close()


def test_la_sauvegarde_couvre_identite_et_constructeur(tmp_path):
    identities = IdentityStore(tmp_path)
    identities.register("alice@example.test", "MotDePasse-123")
    platform = PlatformStore(tmp_path)
    assert platform.database == str(identities.path)
    account = platform.create_account("alice@example.test")
    project = platform.create_project(account, "atelier")
    build = platform.create_build(project)

    copie = identities.sauvegarder(tmp_path / "sauvegardes" / "base.sqlite3")
    connexion = sqlite3.connect(copie)
    try:
        assert connexion.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert connexion.execute(
            "SELECT COUNT(*) FROM builder_projects WHERE id = ?", (project,)
        ).fetchone()[0] == 1
        assert connexion.execute(
            "SELECT COUNT(*) FROM builds WHERE id = ?", (build,)
        ).fetchone()[0] == 1
    finally:
        _fermer(connexion)


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="/proc requis")
def test_les_lectures_du_constructeur_ferment_leurs_connexions(tmp_path):
    platform = PlatformStore(tmp_path)
    account = platform.create_account("lecteur@example.test")
    project = platform.create_project(account, "atelier")
    avant = _descripteurs_sur(platform.database)

    for _ in range(500):
        assert platform.get_project(project)["id"] == project

    apres = _descripteurs_sur(platform.database)
    assert apres - avant == 0, (
        f"{apres - avant} descripteur(s) restent ouverts après 500 lectures"
    )


def test_identity_et_constructeur_cohabitent_sur_la_meme_base(tmp_path):
    identities = IdentityStore(tmp_path)
    platform = PlatformStore(tmp_path)

    for numero in range(3):
        email = f"compte-{numero}@example.test"
        user = identities.register(email, "MotDePasse-123")
        account = platform.create_account(email)
        project = platform.create_project(account, f"site-{numero}")
        identities.add_project(user["id"], f"{numero:032x}", f"Site {numero}")
        build = platform.create_build(project)

        assert identities.projects(user["id"])[0]["name"] == f"Site {numero}"
        assert platform.get_build(build)["project_id"] == project

    connexion = sqlite3.connect(platform.database)
    try:
        tables = {
            row[0]
            for row in connexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        _fermer(connexion)

    assert {"users", "projects", "accounts", "builder_projects", "builds"} <= tables
    assert len(platform.list_all_projects()) == 3
    assert len(identities.tous_les_projets()) == 3
