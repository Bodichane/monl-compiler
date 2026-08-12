"""Brique 27 (point 116) : `publicWhen`, éprouvé contre un vrai serveur.

La couverture de compilation ne suffisait pas — elle a laissé passer, pendant
toute la vie de la brique, une modération À SENS UNIQUE : le modérateur qui
masquait un contenu ne pouvait plus ni le lister ni le relire, et l'auteur d'un
brouillon ne retrouvait jamais son brouillon. Ces tests-là partent donc d'un
serveur réel et de TROIS comptes distincts : avec un seul, « le contenu masqué
est-il caché ? » passerait même quand il est caché à tout le monde.
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
    """Compile la spec, provisionne le modérateur, et sert l'application."""
    projet = tmp_path_factory.mktemp("publication_conditionnelle")
    spec = projet / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(projet))
    # Le modérateur n'est pas 'selfRegister' : il ne peut venir que de
    # manage.py, et c'est précisément la frontière que la bêta 3 protège.
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
    """Un post masqué, son auteur, un membre tiers et un modérateur."""
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


def test_lanonyme_ne_voit_pas_le_contenu_masque(scene):
    assert _liste(scene)["total"] == 0


def test_lanonyme_ne_latteint_pas_non_plus_par_son_identifiant(scene):
    """404 et jamais 403 : distinguer les deux laisserait dénombrer ce qui a
    été retiré, sur des identifiants séquentiels."""
    assert _detail(scene).status_code == 404


def test_le_moderateur_voit_encore_ce_quil_a_masque(scene):
    """LE défaut que la brique avait : masquer, c'était perdre le contenu."""
    donnees = _liste(scene, scene["moderateur"])
    assert donnees["total"] == 1
    assert donnees["data"][0]["status"] == "hidden"


def test_le_moderateur_peut_rouvrir_la_fiche_masquee(scene):
    reponse = _detail(scene, scene["moderateur"])
    assert reponse.status_code == 200
    assert reponse.json()["data"]["status"] == "hidden"


def test_lauteur_retrouve_son_propre_contenu_masque(scene):
    """Sans quoi un brouillon serait perdu par celui qui vient de l'écrire."""
    assert _liste(scene, scene["auteur"])["total"] == 1
    assert _detail(scene, scene["auteur"]).status_code == 200


def test_un_membre_tiers_reste_devant_la_porte(scene):
    """L'exemption est DÉCLARÉE, jamais accordée à qui est simplement connecté :
    sinon « masqué » ne voudrait plus rien dire dès qu'on a un compte."""
    assert _liste(scene, scene["tiers"])["total"] == 0
    assert _detail(scene, scene["tiers"]).status_code == 404


def test_un_jeton_invalide_laisse_anonyme_sans_401(scene):
    """Une route PUBLIQUE ne doit jamais répondre 401 : l'identité facultative
    ne peut que donner des droits, jamais faire échouer la requête."""
    entetes = {"Authorization": "Bearer nimportequoi"}
    liste = requests.get(f"{scene['base_url']}/post", timeout=10, headers=entetes)
    assert liste.status_code == 200
    assert liste.json()["total"] == 0
    detail = requests.get(f"{scene['base_url']}/post/{scene['id']}",
                          timeout=10, headers=entetes)
    assert detail.status_code == 404


def test_le_contenu_publie_reste_visible_de_tous(scene):
    """Contre-épreuve : une condition qui cacherait TOUT passerait les tests
    ci-dessus sans rien faire de juste."""
    requests.post(f"{scene['base_url']}/post", timeout=10,
                  headers=_entete(scene["auteur"]),
                  json={"content": "Annonce ouverte", "status": "published"})
    contenus = [p["content"] for p in _liste(scene)["data"]]
    assert contenus == ["Annonce ouverte"]


def test_le_contrat_annonce_la_condition(tmp_path):
    """Une IA d'interface doit savoir que la liste est filtrée par un état."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    contrat = json.loads(
        (tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contrat["business_rules"]["public_when"]["Post.Read"] == {
        "field": "status", "value": "published"}


def test_sans_superviseur_ni_proprietaire_la_condition_reste_seule(tmp_path):
    """Une spec sans exemption possible ne gagne aucune dépendance d'identité :
    le code produit reste celui d'avant le point 116."""
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
