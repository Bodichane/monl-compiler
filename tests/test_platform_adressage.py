"""L'adresse d'un site : le slug est un nom d'HÔTE, pas une étiquette libre.

Un navigateur met toujours le nom d'hôte en minuscules avant de l'envoyer.
Un projet nommé « myOwn » était donc construit, payé, conservé en snapshot —
et introuvable, parce que la recherche comparait « myown » à « myOwn ».
"""

import sqlite3
import uuid

import pytest

from monl_platform.hosting import SiteManager
from monl_platform.identity import IdentityStore
from monl_platform.store import PlatformStore, normalize_slug


@pytest.fixture()
def store(tmp_path):
    return PlatformStore(tmp_path)


def _compte_et_projet(store, email, slug):
    identity = IdentityStore(store.workspace)
    user = identity.register(email, "MotDePasse-123")
    project_id = uuid.uuid4().hex
    identity.add_project(user["id"], project_id, slug)
    store.create_project(user["id"], project_id, slug)
    return user["id"], project_id


def test_un_slug_neuf_est_range_en_forme_canonique(store):
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "  myOwn  ")

    assert store.get_project(project_id)["slug"] == "myown"


def test_un_projet_deja_en_base_avec_une_majuscule_reste_joignable(store, tmp_path):
    """Le cas réel : la ligne existe déjà, le site est déjà construit."""
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "provisoire")
    # On remet la majuscule comme la faisait la version d'avant.
    raw = sqlite3.connect(store.database)
    raw.execute("UPDATE builder_projects SET slug = 'myOwn' WHERE project_id = ?", (project_id,))
    raw.commit()
    raw.close()

    trouves = store.list_projects_by_slug("myown")

    assert [row["project_id"] for row in trouves] == [project_id]


def test_l_hote_envoye_par_un_navigateur_designe_le_projet(store, tmp_path):
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "myOwn")
    sites = SiteManager(store, tmp_path / "projets", "localhost")

    project = sites.project_for_host("myown.localhost:8020")

    assert project is not None
    assert project["project_id"] == project_id
    # L'adresse affichée par la console doit être celle qui répond.
    assert sites.host_for(project) == "myown.localhost"


def test_deux_casses_du_meme_nom_ne_font_pas_deux_adresses(store):
    user_id, _first = _compte_et_projet(store, "a@monl.test", "myOwn")
    second = uuid.uuid4().hex
    IdentityStore(store.workspace).add_project(user_id, second, "autre")

    with pytest.raises(sqlite3.IntegrityError):
        store.create_project(user_id, second, "MYOWN")


def test_la_forme_canonique_est_nommee_et_partagee():
    assert normalize_slug("  MyOwn  ") == "myown"
