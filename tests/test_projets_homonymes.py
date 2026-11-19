"""Two projects with the same name must have two addresses, not a collision.

BOTH DEFECTS, MEASURED BEFORE WRITING A LINE. The slug — the hosting
address — was derived from the application NAME alone, without ever checking
that it was free:

  (a) SAME account, two projects with the same name → `IntegrityError` on
      `UNIQUE(user_id, slug)`. `_ensure_builder_project` only catches
      `OSError` and `ValueError`: the error therefore came out as a **500**,
      and the second project could never start its API.

  (b) TWO accounts, same name → accepted, then `project_for_host` refuses to
      serve, saying "designates several projects". A stranger naming their
      project like yours made your site unreachable. The slug lookup is
      GLOBAL — it is a subdomain, it cannot be per account.

The remedy is the same for both: the slug is chosen FREE at creation, under
the store lock, and global uniqueness is held by an index rather than an
application check — a check lets two concurrent writes through, an index
does not.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from monl_platform.hosting import SiteManager
from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore


@pytest.fixture
def plateforme(tmp_path):
    store = PlatformStore(tmp_path)
    identites = IdentityStore(store.workspace)
    sites = SiteManager(store, tmp_path / "projets", "localhost")
    return store, identites, sites


def _projet(store, identites, user_id, nom):
    """Creates a project the way the platform does, and returns the slug kept."""
    project_id = uuid.uuid4().hex
    identites.add_project(user_id, project_id, nom)
    slug = store.create_project(user_id, project_id, nom.lower())
    return project_id, slug


def test_one_account_can_name_two_projects_alike(plateforme):
    """(a) The second must no longer make the write fail.

    Three passes through the dialogue with the same name is the REAL case that
    brought the defect up: three "AtelierVitrine" rows in the console.
    """
    store, identites, _ = plateforme
    compte = identites.register("un@monl.test", "MotDePasse-123")

    slugs = [_projet(store, identites, compte["id"], "AtelierVitrine")[1]
             for _ in range(3)]

    assert len(set(slugs)) == 3, f"deux projets partagent une adresse : {slugs}"
    assert slugs[0] == "ateliervitrine", (
        "le PREMIER doit garder l'adresse que son nom annonce")


def test_two_accounts_do_not_steal_an_address(plateforme):
    """(b) The most serious defect: it comes from someone else."""
    store, identites, sites = plateforme
    a = identites.register("a@monl.test", "MotDePasse-123")
    b = identites.register("b@monl.test", "MotDePasse-123")

    _, slug_a = _projet(store, identites, a["id"], "AtelierVitrine")
    _, slug_b = _projet(store, identites, b["id"], "AtelierVitrine")

    assert slug_a != slug_b, "un inconnu a pris l'adresse du premier"
    for slug in (slug_a, slug_b):
        projet = sites.project_for_host(f"{slug}.localhost")
        assert projet is not None, f"{slug} ne désigne aucun projet"


def test_hosting_stays_unambiguous(plateforme):
    """Each address designates ONE project, and the right one.

    Without this check we would know the slugs differ, never that they lead to
    the right place — two distinct addresses pointing to the same row would pass
    the previous witness.
    """
    store, identites, sites = plateforme
    compte = identites.register("route@monl.test", "MotDePasse-123")

    attendu = {}
    for _ in range(3):
        project_id, slug = _projet(store, identites, compte["id"], "Boutique")
        attendu[slug] = project_id

    for slug, project_id in attendu.items():
        projet = sites.project_for_host(f"{slug}.localhost")
        assert projet["project_id"] == project_id, (
            f"{slug}.localhost mène au mauvais projet")


def test_lunicite_globale_tient_meme_a_deux_ecritures_concurrentes(plateforme):
    """The guarantee lives in an INDEX, never in a prior check.

    A check "is this slug free?" followed by a write lets through two
    simultaneous calls that both read "free". We therefore force the direct
    write a race would produce, and the database must refuse it by itself.
    """
    store, identites, _ = plateforme
    a = identites.register("c1@monl.test", "MotDePasse-123")
    b = identites.register("c2@monl.test", "MotDePasse-123")
    _, slug = _projet(store, identites, a["id"], "Course")

    autre = uuid.uuid4().hex
    identites.add_project(b["id"], autre, "Course")
    with pytest.raises(sqlite3.IntegrityError), store._connect() as db:
        db.execute(
            "INSERT INTO builder_projects(project_id, user_id, slug, "
            "created_at, model_routes, generate_images) "
            "VALUES (?, ?, ?, datetime('now'), '{}', 0)",
            (autre, b["id"], slug),
        )


def test_a_database_already_with_duplicates_does_not_block_startup(tmp_path, capsys):
    """EARLIER databases already carry duplicates — ours has three.

    Point 85 word for word: the index cannot be created on a database with
    duplicates, and refusing to start would immobilize a working service.
    Duplicates are COUNTED and NAMED, never silently rewritten: renaming would
    change the address of a site already online.
    """
    store = PlatformStore(tmp_path)
    identites = IdentityStore(store.workspace)
    a = identites.register("v1@monl.test", "MotDePasse-123")
    b = identites.register("v2@monl.test", "MotDePasse-123")

    # We build the BEFORE state: two accounts, one slug.
    for compte in (a, b):
        project_id = uuid.uuid4().hex
        identites.add_project(compte["id"], project_id, "Ancien")
        with store._connect() as db:
            db.execute("DROP INDEX IF EXISTS idx_builder_projects_slug")
            db.execute(
                "INSERT INTO builder_projects(project_id, user_id, slug, "
                "created_at, model_routes, generate_images) "
                "VALUES (?, ?, 'ancien', datetime('now'), '{}', 0)",
                (project_id, compte["id"]),
            )

    capsys.readouterr()
    rouvert = PlatformStore(tmp_path)
    sortie = capsys.readouterr().out
    assert rouvert.list_all_projects(), "la plateforme refuse de démarrer"
    assert "ancien" in sortie.lower(), (
        f"le doublon n'est pas NOMMÉ au démarrage :\n{sortie}")
