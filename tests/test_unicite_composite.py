"""Brick 28 (point 116): `oncePer`, tested against a real server.

The test-bench trap: with ONE account and ONE target, "is the second vote
refused?" would pass even if the rule refused every second vote, wherever it
came from. These tests therefore use TWO accounts and TWO targets, and check
the three combinations — the one that must be refused, and the two that must
pass.
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
    """Two participants, two entries: the minimum to settle the rule."""
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


def test_the_first_vote_passes(scene):
    assert _voter(scene, "p1", 1, "n-p1-e1").status_code == 200


def test_the_same_accounts_second_vote_on_the_same_target_is_refused(scene):
    reponse = _voter(scene, "p1", 1, "n-p1-e1-bis")
    assert reponse.status_code == 409
    assert "already" in reponse.json()["detail"]


def test_the_same_account_votes_another_target(scene):
    """Counter-proof: a rule freezing everything would pass the test above."""
    assert _voter(scene, "p1", 2, "n-p1-e2").status_code == 200


def test_another_account_votes_the_same_target(scene):
    """Second counter-proof, on the pair's other column."""
    assert _voter(scene, "p2", 1, "n-p2-e1").status_code == 200


def test_the_counter_only_counts_accepted_votes(scene):
    """The refusal must cancel the INCREMENT as well as the insertion: without
    the shared transaction, a re-vote would inflate the score without leaving a
    vote."""
    entrees = requests.get(f"{scene['base_url']}/entry", timeout=10).json()["data"]
    scores = {e["titre"]: e["score"] for e in entrees}
    assert scores == {"Photo A": 2, "Photo B": 1}


def test_a_unique_field_duplicate_keeps_its_own_message(scene):
    """POINT 116: `oncePer` had stolen `unique`'s sentence — a plain duplicate
    field, on ANOTHER target and ANOTHER account, was answered "you already did
    it for this target". It is the defect point 85 had closed, reopened by the
    next brick."""
    reponse = _voter(scene, "p2", 2, "n-p1-e1")
    assert reponse.status_code == 409
    assert "note must be unique" in reponse.json()["detail"]


def test_the_composite_index_really_exists_in_the_database(scene):
    """Uniqueness rests on a SQLite index, not an application check: it is the
    index that also protects two concurrent requests."""
    connexion = sqlite3.connect(scene["projet"] / "app.db")
    index = {ligne[0] for ligne in connexion.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'")}
    connexion.close()
    assert "idx_once_per_vote_participant_id_entry_id" in index


def test_the_contract_announces_the_rule(scene):
    """Without it, an interface AI draws a "vote" button that collects a 409
    nothing had announced."""
    import json
    contrat = json.loads(
        (scene["projet"] / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contrat["business_rules"]["once_per"] == [
        {"trigger_entity": "Vote", "parents": ["Participant", "Entry"]}]
