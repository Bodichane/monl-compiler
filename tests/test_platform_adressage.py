"""A site's address: the slug is a HOST name, not a free label.

A browser always lowercases the host name before sending it. A project
named "myOwn" was therefore built, paid for, kept as a snapshot — and
unreachable, because the lookup compared "myown" with "myOwn".
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


def test_a_new_slug_is_stored_in_canonical_form(store):
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "  myOwn  ")

    assert store.get_project(project_id)["slug"] == "myown"


def test_a_stored_project_with_a_capital_stays_reachable(store, tmp_path):
    """The real case: the row already exists, the site is already built."""
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "provisoire")
    # We put the capital back the way the previous version did.
    raw = sqlite3.connect(store.database)
    raw.execute("UPDATE builder_projects SET slug = 'myOwn' WHERE project_id = ?", (project_id,))
    raw.commit()
    raw.close()

    trouves = store.list_projects_by_slug("myown")

    assert [row["project_id"] for row in trouves] == [project_id]


def test_the_host_a_browser_sends_designates_the_project(store, tmp_path):
    _user_id, project_id = _compte_et_projet(store, "a@monl.test", "myOwn")
    sites = SiteManager(store, tmp_path / "projets", "localhost")

    project = sites.project_for_host("myown.localhost:8020")

    assert project is not None
    assert project["project_id"] == project_id
    # The address the console shows must be the one that answers.
    assert sites.host_for(project) == "myown.localhost"


def test_two_cases_of_one_name_do_not_make_two_addresses(store):
    """"myOwn" and "MYOWN" target the same host: the second must step aside.

    This witness used to require an `IntegrityError` here. That was the defect:
    the second project could never be created and the error came out as a 500.
    It now gets a FREE address. The invariant this file guards is UNCHANGED —
    a difference in case does not make the same address twice — only the
    outcome changes: step aside instead of refusing.
    """
    user_id, _first = _compte_et_projet(store, "a@monl.test", "myOwn")
    second = uuid.uuid4().hex
    IdentityStore(store.workspace).add_project(user_id, second, "autre")

    retenu = store.create_project(user_id, second, "MYOWN")

    assert retenu == "myown-2", (
        f"la casse a refabriqué une adresse déjà prise : {retenu!r}")
    assert len(store.list_projects_by_slug("myown")) == 1, (
        "l'hôte myown désigne deux projets : il ne serait plus servi du tout")


def test_an_address_already_in_capitals_is_seen_as_taken(store):
    """The free-address lookup ignores case IN THE DATABASE, not only in what it
    is given.

    `create_project` lowercases its argument before anything else: the
    case-insensitive comparison would therefore never be tested by the call. An
    EARLIER row, written when the slug kept its capital, tests it — the real
    case of the witness
    `test_a_stored_project_with_a_capital_stays_reachable`.
    """
    user_id, premier = _compte_et_projet(store, "a@monl.test", "provisoire")
    raw = sqlite3.connect(store.database)
    raw.execute("UPDATE builder_projects SET slug = 'myOwn' WHERE project_id = ?",
                (premier,))
    raw.commit()
    raw.close()

    second = uuid.uuid4().hex
    IdentityStore(store.workspace).add_project(user_id, second, "autre")
    retenu = store.create_project(user_id, second, "myown")

    assert retenu == "myown-2", (
        f"la ligne 'myOwn' n'a pas été vue comme prise : {retenu!r}")


def test_the_canonical_form_is_named_and_shared():
    assert normalize_slug("  MyOwn  ") == "myown"
