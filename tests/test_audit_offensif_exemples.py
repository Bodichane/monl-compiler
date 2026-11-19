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

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "exemples")
EXAMPLES = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.ml")))
PASSWORD = "audit-offensif-197-solide"
VALUES = {"Integer": 1, "Float": 1.0, "Money": 1.0, "Boolean": False}


def test_the_examples_are_found():
    # An empty list would make the parametrized test green without attacking
    # anything.
    assert len(EXAMPLES) >= 5, EXAMPLES


def _compiler(spec, output):
    compile_project(spec, str(output))
    from monl.ast_validator import MonlAST
    from monl.parser import parse_monl_file
    return MonlAST(parse_monl_file(spec), base_dir=EXAMPLES_DIR).validate_and_audit()


def _targets(ast):
    security = ast["security"]
    entities = ast["schema"]["entities"]
    public = set(security.get("public", []))
    writable = set(security.get("self_register_actors", []))

    creation = None
    for wf in security["workflows"]:
        for action in wf["actions"]:
            target = action["target"]
            if (action["type"] == "Create" and target in entities
                    and f"{target}.Create" not in public):
                preferred = wf["actor"] in writable
                if creation is None or (preferred and not creation["inscriptible"]):
                    creation = {"entite": target, "acteur": wf["actor"],
                                "inscriptible": preferred}

    allowed = {}
    for wf in security["workflows"]:
        for action in wf["actions"]:
            base = action["target"].split(".")[0]
            if action["type"] in ("Update", "Delete") and base in entities:
                allowed.setdefault((base, action["type"]), set()).add(wf["actor"])
    # A deletion first: without a body, nothing can answer 422 before the role
    # check (an update validates its body FIRST, measured).
    elevation = None
    for (entity, verb), actors in sorted(allowed.items(),
                                           key=lambda c: (c[0][1] != "Delete", c[0])):
        adverse = sorted(a for a in writable if a not in actors)
        if adverse:
            elevation = {"entite": entity, "verbe": verb, "acteur": adverse[0]}
            break
    return creation, elevation


def _body_valid(project, entity):
    """A body the SCHEMA accepts, read from the compiled contract: without it, a
    422 would answer before the role check and the attack would measure nothing."""
    contract = json.loads((project / "frontend_contract.json").read_text(encoding="utf-8"))
    return {
        field["name"]: (field["allowed_values"][0] if field.get("allowed_values")
                        else VALUES.get(field["type"], "valeur-audit"))
        for field in contract["entities"][entity]["fields"]
        if not field["server_generated"]
    }


def _token(base, identifier, actor):
    registered = requests.post(base + "/register", timeout=20, json={
        "username": identifier, "password": PASSWORD, "actor": actor})
    assert registered.status_code == 200, registered.text
    connected = requests.post(base + "/login", timeout=20, json={
        "username": identifier, "password": PASSWORD})
    assert connected.status_code == 200, connected.text
    return connected.json()["access_token"]


@pytest.mark.parametrize("spec", EXAMPLES, ids=[os.path.basename(p) for p in EXAMPLES])
def test_the_offensive_audit_fails_on_every_example(spec, tmp_path):
    ast = _compiler(spec, tmp_path / "projet")
    creation, elevation = _targets(ast)
    assert creation, "no protected creation: nothing to attack on this example"
    route = "/" + creation["entite"].lower()

    with uvicorn_server(str(tmp_path / "projet")) as base:
        if creation["inscriptible"]:
            legitimate = _token(base, "legitime@example.test", creation["acteur"])
            accepted = requests.post(base + route, json={}, timeout=10,
                                    headers={"Authorization": f"Bearer {legitimate}"})
            assert accepted.status_code != 401, accepted.text

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
            token = _token(base, "adverse@example.test", elevation["acteur"])
            deletion = elevation["verbe"] == "Delete"
            method = requests.delete if deletion else requests.put
            body = None if deletion else _body_valid(tmp_path / "projet", elevation["entite"])
            forbidden = method(f"{base}/{elevation['entite'].lower()}/1", json=body,
                               timeout=10, headers={"Authorization": f"Bearer {token}"})
            assert forbidden.status_code == 403, forbidden.text
