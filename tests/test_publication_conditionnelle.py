"""Brick 27 (point 116): `publicWhen`, tested against a real server.

Compile coverage was not enough — it let through, for the brick's whole life,
a ONE-WAY moderation: the moderator hiding content could no longer list nor
reread it, and a draft's author never found their draft again. These tests
therefore start from a real server and THREE distinct accounts: with one,
"is hidden content hidden?" would pass even when it is hidden from everyone.
"""

import json
import subprocess
import sys

import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

SPEC = """app Communaute

entity Post
    content: Text
    status: String

actor Member selfRegister
actor Moderator

relation Member hasMany Post

rule Post.status oneOf "published", "hidden"
rule Post.Read publicWhen status "published"
rule Post.Read sharedBy Moderator
rule Post.Update sharedBy Member, Moderator

workflow Publier for Member
    Create Post
    Read Post
    Update Post

workflow Moderer for Moderator
    Read Post
    Update Post
"""

MOT_DE_PASSE = "MotDePasse123!"


@pytest.fixture(scope="module")
def application(tmp_path_factory):
    """Compiles the spec, provisions the moderator, and serves the application."""
    projet = tmp_path_factory.mktemp("publication_conditionnelle")
    spec = projet / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(projet))
    # The moderator is not 'selfRegister': it can only come from manage.py, and
    # that is precisely the boundary beta 3 protects.
    subprocess.run(
        [sys.executable, "manage.py", "adduser", "mod@x.co", "Moderator"],
        cwd=projet, input=f"{MOT_DE_PASSE}\n{MOT_DE_PASSE}\n",
        text=True, capture_output=True, check=True,
    )
    with uvicorn_server(str(projet)) as base_url:
        yield base_url


def _jeton(base_url, identifiant):
    reponse = requests.post(f"{base_url}/login", timeout=10, json={
        "username": identifiant, "password": MOT_DE_PASSE})
    reponse.raise_for_status()
    return reponse.json()["access_token"]


def _inscrire(base_url, identifiant):
    requests.post(f"{base_url}/register", timeout=10, json={
        "username": identifiant, "password": MOT_DE_PASSE, "actor": "Member"})
    return _jeton(base_url, identifiant)


def _entete(jeton):
    return {"Authorization": f"Bearer {jeton}"}


@pytest.fixture(scope="module")
def scene(application):
    """A hidden post, its author, a third member and a moderator."""
    auteur = _inscrire(application, "auteur@x.co")
    tiers = _inscrire(application, "tiers@x.co")
    moderateur = _jeton(application, "mod@x.co")
    cree = requests.post(f"{application}/post", timeout=10, headers=_entete(auteur),
                         json={"content": "Contenu litigieux", "status": "published"})
    identifiant = cree.json()["id"]
    requests.put(f"{application}/post/{identifiant}", timeout=10,
                 headers=_entete(moderateur),
                 json={"content": "Contenu litigieux", "status": "hidden"})
    return {"base_url": application, "auteur": auteur, "tiers": tiers,
            "moderateur": moderateur, "id": identifiant}


def _liste(scene, jeton=None):
    entetes = _entete(jeton) if jeton else {}
    reponse = requests.get(f"{scene['base_url']}/post", timeout=10, headers=entetes)
    assert reponse.status_code == 200
    return reponse.json()


def _detail(scene, jeton=None):
    entetes = _entete(jeton) if jeton else {}
    return requests.get(f"{scene['base_url']}/post/{scene['id']}",
                        timeout=10, headers=entetes)


def test_the_anonymous_user_does_not_see_hidden_content(scene):
    assert _liste(scene)["total"] == 0


def test_the_anonymous_user_cannot_reach_it_by_its_id_either(scene):
    """404 and never 403: telling them apart would let one count what was
    removed, on sequential identifiers."""
    assert _detail(scene).status_code == 404


def test_the_moderator_still_sees_what_they_hid(scene):
    """THE defect the brick had: hiding meant losing the content."""
    donnees = _liste(scene, scene["moderateur"])
    assert donnees["total"] == 1
    assert donnees["data"][0]["status"] == "hidden"


def test_the_moderator_can_reopen_the_hidden_record(scene):
    reponse = _detail(scene, scene["moderateur"])
    assert reponse.status_code == 200
    assert reponse.json()["data"]["status"] == "hidden"


def test_lauteur_retrouve_son_propre_contenu_masque(scene):
    """Otherwise a draft would be lost by the person who just wrote it."""
    assert _liste(scene, scene["auteur"])["total"] == 1
    assert _detail(scene, scene["auteur"]).status_code == 200


def test_a_third_member_stays_at_the_door(scene):
    """The exemption is DECLARED, never granted to whoever is merely signed in:
    otherwise "hidden" would mean nothing as soon as one has an account."""
    assert _liste(scene, scene["tiers"])["total"] == 0
    assert _detail(scene, scene["tiers"]).status_code == 404


def test_an_invalid_token_leaves_anonymous_without_401(scene):
    """A PUBLIC route must never answer 401: the optional identity can only grant
    rights, never make the request fail."""
    entetes = {"Authorization": "Bearer nimportequoi"}
    liste = requests.get(f"{scene['base_url']}/post", timeout=10, headers=entetes)
    assert liste.status_code == 200
    assert liste.json()["total"] == 0
    detail = requests.get(f"{scene['base_url']}/post/{scene['id']}",
                          timeout=10, headers=entetes)
    assert detail.status_code == 404


def test_published_content_stays_visible_to_all(scene):
    """Counter-proof: a condition hiding EVERYTHING would pass the tests above
    without doing anything right."""
    requests.post(f"{scene['base_url']}/post", timeout=10,
                  headers=_entete(scene["auteur"]),
                  json={"content": "Annonce ouverte", "status": "published"})
    contenus = [p["content"] for p in _liste(scene)["data"]]
    assert contenus == ["Annonce ouverte"]


def test_the_contract_announces_the_condition(tmp_path):
    """An interface AI must know the list is filtered by a state."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    contrat = json.loads(
        (tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contrat["business_rules"]["public_when"]["Post.Read"] == {
        "field": "status", "value": "published"}


def test_without_supervisor_or_owner_the_condition_stays_alone(tmp_path):
    """A spec with no possible exemption gains no identity dependency: the
    produced code stays the one from before point 116."""
    spec = tmp_path / "spec.ml"
    spec.write_text("""app Vitrine

entity Article
    titre: String
    status: String

actor Lecteur selfRegister

rule Article.Read publicWhen status "published"

workflow Lire for Lecteur
    Read Article
""", encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "get_optional_identity" not in genere
    assert 'WHERE "status" = ?' in genere
