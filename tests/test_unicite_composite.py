"""Brique 28 (point 116) : `oncePer`, éprouvé contre un vrai serveur.

Le piège du banc d'essai : avec UN seul compte et UNE seule cible, « le second
vote est-il refusé ? » passerait même si la règle refusait tout second vote,
d'où qu'il vienne. Ces tests emploient donc DEUX comptes et DEUX cibles, et
vérifient les trois combinaisons — celle qui doit être refusée, et les deux qui
doivent passer.
"""

import sqlite3

import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

SPEC = """app Concours

entity Entry
    titre: String
    score: Integer

entity Vote
    note: String

actor Participant selfRegister

relation Participant hasMany Vote
relation Entry hasMany Vote

rule Vote.Create oncePer Participant, Entry
rule Vote.Create increments Entry.score by 1
rule Vote.note unique
rule Entry.Read public

workflow Voter for Participant
    Create Entry
    Create Vote
    Read Vote
    Read Entry
"""

MOT_DE_PASSE = "MotDePasse123!"


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    """Deux participants, deux entrées : le minimum pour départager la règle."""
    projet = tmp_path_factory.mktemp("unicite_composite")
    spec = projet / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(projet))
    with uvicorn_server(str(projet)) as base_url:
        jetons = {}
        for nom in ("p1", "p2"):
            requests.post(f"{base_url}/register", timeout=10, json={
                "username": f"{nom}@x.co", "password": MOT_DE_PASSE,
                "actor": "Participant"})
            reponse = requests.post(f"{base_url}/login", timeout=10, json={
                "username": f"{nom}@x.co", "password": MOT_DE_PASSE})
            jetons[nom] = reponse.json()["access_token"]
        for titre in ("Photo A", "Photo B"):
            requests.post(f"{base_url}/entry", timeout=10,
                          headers={"Authorization": f"Bearer {jetons['p1']}"},
                          json={"titre": titre, "score": 0})
        yield {"base_url": base_url, "jetons": jetons, "projet": projet}


def _voter(scene, compte, entry_id, note):
    return requests.post(
        f"{scene['base_url']}/vote", timeout=10,
        headers={"Authorization": f"Bearer {scene['jetons'][compte]}"},
        json={"note": note, "entry_id": entry_id})


def test_le_premier_vote_passe(scene):
    assert _voter(scene, "p1", 1, "n-p1-e1").status_code == 200


def test_le_second_vote_du_meme_compte_sur_la_meme_cible_est_refuse(scene):
    reponse = _voter(scene, "p1", 1, "n-p1-e1-bis")
    assert reponse.status_code == 409
    assert "déjà" in reponse.json()["detail"]


def test_le_meme_compte_vote_une_autre_cible(scene):
    """Contre-épreuve : une règle qui figerait tout passerait le test ci-dessus."""
    assert _voter(scene, "p1", 2, "n-p1-e2").status_code == 200


def test_un_autre_compte_vote_la_meme_cible(scene):
    """Seconde contre-épreuve, sur l'autre colonne de la paire."""
    assert _voter(scene, "p2", 1, "n-p2-e1").status_code == 200


def test_le_compteur_ne_compte_que_les_votes_acceptes(scene):
    """Le refus doit annuler l'INCRÉMENT autant que l'insertion : sans la
    transaction commune, un revote gonflerait le score sans laisser de vote."""
    entrees = requests.get(f"{scene['base_url']}/entry", timeout=10).json()["data"]
    scores = {e["titre"]: e["score"] for e in entrees}
    assert scores == {"Photo A": 2, "Photo B": 1}


def test_le_doublon_de_champ_unique_garde_son_propre_message(scene):
    """POINT 116 : `oncePer` avait volé la phrase de `unique` — un simple
    doublon de champ, sur une AUTRE cible et un AUTRE compte, s'entendait
    répondre « vous l'avez déjà fait pour cette cible ». C'est le défaut que le
    point 85 avait fermé, rouvert par la brique suivante."""
    reponse = _voter(scene, "p2", 2, "n-p1-e1")
    assert reponse.status_code == 409
    assert "note doit être unique" in reponse.json()["detail"]


def test_lindex_compose_existe_reellement_en_base(scene):
    """L'unicité tient à un index SQLite, pas à une vérification applicative :
    c'est lui qui protège aussi deux requêtes concurrentes."""
    connexion = sqlite3.connect(scene["projet"] / "app.db")
    index = {ligne[0] for ligne in connexion.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}
    connexion.close()
    assert "idx_once_per_vote_participant_id_entry_id" in index


def test_le_contrat_annonce_la_regle(scene):
    """Sans ça, une IA d'interface dessine un bouton « voter » qui récolte un
    409 que rien n'avait annoncé."""
    import json
    contrat = json.loads(
        (scene["projet"] / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contrat["business_rules"]["once_per"] == [
        {"trigger_entity": "Vote", "parents": ["Participant", "Entry"]}]
