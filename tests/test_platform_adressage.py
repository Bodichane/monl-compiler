"""L'adresse d'un site : le slug est un nom d'HÔTE, pas une étiquette libre.

Un navigateur met toujours le nom d'hôte en minuscules avant de l'envoyer.
Un projet nommé « myOwn » était donc construit, payé, conservé en snapshot —
et introuvable, parce que la recherche comparait « myown » à « myOwn ».
"""

import sqlite3

import pytest

from monl_platform.hosting import SiteManager
from monl_platform.store import PlatformStore, normalize_slug


@pytest.fixture()
def store(tmp_path):
    return PlatformStore(tmp_path / "plateforme.db")


def test_un_slug_neuf_est_range_en_forme_canonique(store):
    store.create_account("a@monl.test", "MotDePasse-123")
    project_id = store.create_project("a@monl.test", "  myOwn  ")

    assert store.get_project(project_id)["slug"] == "myown"


def test_un_projet_deja_en_base_avec_une_majuscule_reste_joignable(store, tmp_path):
    """Le cas réel : la ligne existe déjà, le site est déjà construit."""
    store.create_account("a@monl.test", "MotDePasse-123")
    project_id = store.create_project("a@monl.test", "provisoire")
    # On remet la majuscule comme la faisait la version d'avant.
    raw = sqlite3.connect(store.database)
    raw.execute("UPDATE projects SET slug = 'myOwn' WHERE id = ?", (project_id,))
    raw.commit()
    raw.close()

    trouves = store.list_projects_by_slug("myown")

    assert [row["id"] for row in trouves] == [project_id]


def test_l_hote_envoye_par_un_navigateur_designe_le_projet(store, tmp_path):
    store.create_account("a@monl.test", "MotDePasse-123")
    project_id = store.create_project("a@monl.test", "myOwn")
    sites = SiteManager(store, tmp_path / "projets", "localhost")

    project = sites.project_for_host("myown.localhost:8020")

    assert project is not None
    assert project["id"] == project_id
    # L'adresse affichée par la console doit être celle qui répond.
    assert sites.host_for(project) == "myown.localhost"


def test_deux_casses_du_meme_nom_ne_font_pas_deux_adresses(store):
    store.create_account("a@monl.test", "MotDePasse-123")
    store.create_project("a@monl.test", "myOwn")

    with pytest.raises(sqlite3.IntegrityError):
        store.create_project("a@monl.test", "MYOWN")


def test_la_forme_canonique_est_nommee_et_partagee():
    assert normalize_slug("  MyOwn  ") == "myown"
