"""Banc #121 : pytest tests/test_generated_specs.py -q -s (< 60 s).

MONL_LONG_BENCH=1 python3 -m pytest tests/test_generated_specs.py -q -s
ajoute hors suite ordinaire N=160,320,640. Graine fixe, graphe de degré borné,
3 répétitions entrelacées, médiane du temps mural du pipeline complet (lecture,
parse, validation, backend, contrat, empreintes et publication). Une chauffe
précède la mesure ; les sources sont préparées hors chronomètre.
La borne porte sur cette famille, pas sur tous les graphes DSL possibles.
"""

import contextlib
import io
import json
import math
import os
import random
import statistics
import time

import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server


def generated_spec(n):
    """Exactement N entités ; paires parent/enfant et propriétaire acteur."""
    if n < 2:
        raise ValueError("N doit être au moins 2")
    rng = random.Random(121)
    blocks = ["app GeneratedBench", "actor Member selfRegister",
              "actor Reader selfRegister"]
    for i in range(n):
        name = f"Record{i}"
        blocks.append(f"entity {name}\n    title: String\n    amount: Integer\n"
                      "    status: String\n    created: DateTime\n    events: Integer")
        blocks.append(f"relation Member hasMany {name}")
        if i % 2:
            blocks.append(f"relation Record{i-1} hasMany {name}")
            blocks.append(f"rule {name}.Create increments Record{i-1}.events by 1")
        blocks.extend([f"rule {name}.title required", f"rule {name}.title min 3",
                       f"rule {name}.title max {rng.randrange(30, 80)}",
                       f"rule {name}.amount min 1", f"rule {name}.amount max 100",
                       f'rule {name}.status oneOf "open", "closed"',
                       f"rule {name}.created timestamp",
                       f"rule {name}.Read filter status", f"rule {name}.Read sort amount"])
        for action in ("Read", "Update", "Delete"):
            blocks.append(f"rule {name}.{action} ownedBy Member")
        blocks.append(f"workflow Manage{i} for Member\n    Create {name}\n"
                      f"    Read {name}\n    Update {name}\n    Delete {name}")
    return "\n\n".join(blocks) + "\n"


def compile_quiet(spec, output):
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(output))


def growth_exponent(curve):
    x = [math.log(n) for n, _ in curve]
    y = [math.log(t) for _, t in curve]
    xm, ym = statistics.mean(x), statistics.mean(y)
    return sum((a-xm)*(b-ym) for a, b in zip(x, y, strict=True)) / sum((a-xm)**2 for a in x)


def test_compilation_growth(tmp_path):
    sizes = [5, 10, 20, 40, 80]
    if os.environ.get("MONL_LONG_BENCH") == "1":
        sizes += [160, 320, 640]
    sources = {}
    for n in sizes:
        folder = tmp_path / str(n)
        folder.mkdir()
        spec = folder / "spec.ml"
        spec.write_text(generated_spec(n), encoding="utf-8")
        sources[n] = spec
    compile_quiet(sources[5], tmp_path / "warm")
    samples = {n: [] for n in sizes}
    for repeat in range(3):
        for n in sizes if repeat % 2 == 0 else reversed(sizes):
            started = time.perf_counter()
            compile_quiet(sources[n], tmp_path / f"out-{n}-{repeat}")
            samples[n].append(time.perf_counter() - started)
    curve = [(n, statistics.median(samples[n])) for n in sizes]
    exponent = growth_exponent(curve)
    print(f"\ncompile curve={curve}; samples={samples}; exponent={exponent:.3f}")
    assert exponent < 1.5, f"croissance excessive : {exponent:.3f}, {curve}"


def checked(session, base, route, **kwargs):
    response = session.request(route["method"], base + route["path"], timeout=10, **kwargs)
    assert 200 <= response.status_code < 300, (
        route, response.status_code, response.text)
    return response.json()


def test_every_contract_route(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(generated_spec(20), encoding="utf-8")
    compile_quiet(spec, tmp_path)
    contract = json.loads((tmp_path / "frontend_contract.json").read_text())
    ids, bodies, visited = {}, {}, set()
    with uvicorn_server(tmp_path) as base, requests.Session() as session:
        auth = contract["api"]["auth"]
        # Décale réellement les ids de compte ; aucun id n'est supposé égal à 1.
        checked(session, base, auth["register"], json={
            "username": "reader", "password": "password121", "actor": "Reader"})
        checked(session, base, auth["register"], json={
            "username": "member", "password": "password121", "actor": "Member"})
        login = checked(session, base, auth["login"], json={
            "username": "member", "password": "password121"})
        session.headers["Authorization"] = "Bearer " + login["access_token"]
        routes = contract["routes"]
        assert len(routes) == 5 * 20, "chaque entité doit exposer ses cinq routes"
        # Créations dans l'ordre topologique réel, suppressions en ordre inverse.
        for route in routes:
            if route["action"] != "Create":
                continue
            entity = route["entity"]
            body = {"title": "valid title", "amount": 7, "status": "open", "events": 0}
            for field in route["request_fields"]:
                if field.endswith("_id"):
                    body[field] = ids[field[:-3]]
            body = {field: body[field] for field in route["request_fields"]}
            bodies[entity] = body
            result = checked(session, base, route, json=body)
            ids[entity.lower()] = result["id"]
            visited.add((route["method"], route["path"]))
        assert len(ids) == 20
        for route in routes:
            if route["action"] in ("Create", "Delete"):
                continue
            path = route["path"].replace("{id}", str(ids[route["entity"].lower()]))
            kwargs = {}
            if route["action"] == "Update":
                kwargs["json"] = bodies[route["entity"]]
            if route["action"] == "List":
                kwargs["params"] = {"status": "open", "sort": "amount", "direction": "desc"}
            result = checked(session, base, {**route, "path": path}, **kwargs)
            if route["action"] == "List":
                assert result["total"] == 1
                assert result["data"][0]["id"] == ids[route["entity"].lower()]
                assert result["data"][0]["created"]
                if int(route["entity"][6:]) % 2 == 0:
                    assert result["data"][0]["events"] == 1
            visited.add((route["method"], route["path"]))
        for route in reversed(routes):
            if route["action"] == "Delete":
                path = route["path"].replace("{id}", str(ids[route["entity"].lower()]))
                checked(session, base, {**route, "path": path})
                visited.add((route["method"], route["path"]))
        checked(session, base, auth["logout"])
        assert visited == {(r["method"], r["path"]) for r in routes}
        print(f"\n{len(visited)} routes métier + register/login/logout : toutes 2xx")


def test_generator_is_deterministic():
    assert generated_spec(20) == generated_spec(20)
    assert generated_spec(20).count("\nentity ") == 20
