"""Offensive audit replayed on EVERY example, against a real server (point 197).

Replaces `tests/test_exploit_all.py`, which defined no `test_` function:
pytest did not collect it, it swallowed compilation failures ("ignored") and
wrote into the repository root. Yet three documents promised CI replayed it —
the promise is now kept.

Three attacks, with the EXACT expected code (not ">= 400", which an invalid
body would be enough to satisfy):
  1. impersonation through a raw `x_actor` header   → 401;
  2. token signed with another key, allowed role     → 401;
  3. legitimate token of a role not allowed on a
     write reserved to others                        → 403.
The counter-proof comes FIRST: the same call with a legitimate token of the
allowed role does NOT get 401 — without it, a server closed to everything
would pass.
"""
import datetime
import glob
import json
import os

import jwt
import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "exemples")
EXEMPLES = sorted(glob.glob(os.path.join(EXEMPLES_DIR, "*.ml")))
MOT_DE_PASSE = "audit-offensif-197-solide"
VALEURS = {"Integer": 1, "Float": 1.0, "Money": 1.0, "Boolean": False}


def test_the_examples_are_found():
    # An empty list would make the parametrized test green without attacking
    # anything.
    assert len(EXEMPLES) >= 5, EXEMPLES


def _compiler(spec, sortie):
    compile_project(spec, str(sortie))
    from monl.ast_validator import MonlAST
    from monl.parser import parse_monl_file
    return MonlAST(parse_monl_file(spec), base_dir=EXEMPLES_DIR).validate_and_audit()


def _cibles(ast):
    securite = ast["security"]
    entites = ast["schema"]["entities"]
    publiques = set(securite.get("public", []))
    inscriptibles = set(securite.get("self_register_actors", []))

    creation = None
    for wf in securite["workflows"]:
        for action in wf["actions"]:
            cible = action["target"]
            if (action["type"] == "Create" and cible in entites
                    and f"{cible}.Create" not in publiques):
                prefere = wf["actor"] in inscriptibles
                if creation is None or (prefere and not creation["inscriptible"]):
                    creation = {"entite": cible, "acteur": wf["actor"],
                                "inscriptible": prefere}

    autorises = {}
    for wf in securite["workflows"]:
        for action in wf["actions"]:
            base = action["target"].split(".")[0]
            if action["type"] in ("Update", "Delete") and base in entites:
                autorises.setdefault((base, action["type"]), set()).add(wf["actor"])
    # A deletion first: without a body, nothing can answer 422 before the role
    # check (an update validates its body FIRST, measured).
    elevation = None
    for (entite, verbe), acteurs in sorted(autorises.items(),
                                           key=lambda c: (c[0][1] != "Delete", c[0])):
        adverses = sorted(a for a in inscriptibles if a not in acteurs)
        if adverses:
            elevation = {"entite": entite, "verbe": verbe, "acteur": adverses[0]}
            break
    return creation, elevation


def _corps_valide(projet, entite):
    """A body the SCHEMA accepts, read from the compiled contract: without it, a
    422 would answer before the role check and the attack would measure nothing."""
    contrat = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    return {
        champ["name"]: (champ["allowed_values"][0] if champ.get("allowed_values")
                        else VALEURS.get(champ["type"], "valeur-audit"))
        for champ in contrat["entities"][entite]["fields"]
        if not champ["server_generated"]
    }


def _token(base, identifiant, acteur):
    inscrit = requests.post(base + "/register", timeout=20, json={
        "username": identifiant, "password": MOT_DE_PASSE, "actor": acteur})
    assert inscrit.status_code == 200, inscrit.text
    connecte = requests.post(base + "/login", timeout=20, json={
        "username": identifiant, "password": MOT_DE_PASSE})
    assert connecte.status_code == 200, connecte.text
    return connecte.json()["access_token"]


@pytest.mark.parametrize("spec", EXEMPLES, ids=[os.path.basename(p) for p in EXEMPLES])
def test_the_offensive_audit_fails_on_every_example(spec, tmp_path):
    ast = _compiler(spec, tmp_path / "projet")
    creation, elevation = _cibles(ast)
    assert creation, "no protected creation: nothing to attack on this example"
    route = "/" + creation["entite"].lower()

    with uvicorn_server(str(tmp_path / "projet")) as base:
        if creation["inscriptible"]:
            legitime = _token(base, "legitime@example.test", creation["acteur"])
            accepte = requests.post(base + route, json={}, timeout=10,
                                    headers={"Authorization": f"Bearer {legitime}"})
            assert accepte.status_code != 401, accepte.text

        usurpe = requests.post(base + route, json={}, timeout=10,
                               headers={"x_actor": creation["acteur"]})
        assert usurpe.status_code == 401, usurpe.text

        forge = jwt.encode({
            "sub": "1", "user_id": 1, "actor": creation["acteur"],
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        }, "cle-etrangere-au-projet-197-de-32-octets", algorithm="HS256")
        refuse = requests.post(base + route, json={}, timeout=10,
                               headers={"Authorization": f"Bearer {forge}"})
        assert refuse.status_code == 401, refuse.text

        if elevation:
            jeton = _token(base, "adverse@example.test", elevation["acteur"])
            suppression = elevation["verbe"] == "Delete"
            methode = requests.delete if suppression else requests.put
            corps = None if suppression else _corps_valide(tmp_path / "projet", elevation["entite"])
            interdit = methode(f"{base}/{elevation['entite'].lower()}/1", json=corps,
                               timeout=10, headers={"Authorization": f"Bearer {jeton}"})
            assert interdit.status_code == 403, interdit.text
