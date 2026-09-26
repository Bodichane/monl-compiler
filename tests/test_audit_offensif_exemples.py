"""Audit offensif rejoué sur CHAQUE exemple, contre un vrai serveur (point 197).

Remplace `tests/test_exploit_all.py`, qui ne définissait aucune fonction
`test_` : pytest ne le collectait pas, il avalait les échecs de compilation
(« ignoré ») et écrivait dans la racine du dépôt. Trois documents promettaient
pourtant que la CI le rejouait — la promesse est désormais tenue.

Trois attaques, avec le code EXACT attendu (et non « >= 400 », qu'un corps
invalide suffirait à satisfaire) :
  1. usurpation par en-tête brut `x_actor`          → 401 ;
  2. jeton signé avec une autre clé, rôle autorisé  → 401 ;
  3. jeton légitime d'un rôle non autorisé sur une
     écriture réservée à d'autres                   → 403.
La contre-épreuve vient AVANT : le même appel avec un jeton légitime du rôle
autorisé ne reçoit PAS 401 — sans elle, un serveur fermé à tout passerait.
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


def test_les_exemples_sont_trouves():
    # Une liste vide rendrait le test paramétré vert sans rien attaquer.
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
    # Une suppression d'abord : sans corps, rien ne peut répondre 422 avant le
    # contrôle du rôle (une modification valide son corps AVANT, mesuré).
    elevation = None
    for (entite, verbe), acteurs in sorted(autorises.items(),
                                           key=lambda c: (c[0][1] != "Delete", c[0])):
        adverses = sorted(a for a in inscriptibles if a not in acteurs)
        if adverses:
            elevation = {"entite": entite, "verbe": verbe, "acteur": adverses[0]}
            break
    return creation, elevation


def _corps_valide(projet, entite):
    """Un corps que le SCHÉMA accepte, lu sur le contrat compilé : sans lui, un
    422 répondrait avant le contrôle du rôle et l'attaque ne mesurerait rien."""
    contrat = json.loads((projet / "frontend_contract.json").read_text(encoding="utf-8"))
    return {
        champ["name"]: (champ["allowed_values"][0] if champ.get("allowed_values")
                        else VALEURS.get(champ["type"], "valeur-audit"))
        for champ in contrat["entities"][entite]["fields"]
        if not champ["server_generated"]
    }


def _jeton(base, identifiant, acteur):
    inscrit = requests.post(base + "/register", timeout=20, json={
        "username": identifiant, "password": MOT_DE_PASSE, "actor": acteur})
    assert inscrit.status_code == 200, inscrit.text
    connecte = requests.post(base + "/login", timeout=20, json={
        "username": identifiant, "password": MOT_DE_PASSE})
    assert connecte.status_code == 200, connecte.text
    return connecte.json()["access_token"]


@pytest.mark.parametrize("spec", EXEMPLES, ids=[os.path.basename(p) for p in EXEMPLES])
def test_l_audit_offensif_echoue_sur_chaque_exemple(spec, tmp_path):
    ast = _compiler(spec, tmp_path / "projet")
    creation, elevation = _cibles(ast)
    assert creation, "aucune création protégée : rien à attaquer sur cet exemple"
    route = "/" + creation["entite"].lower()

    with uvicorn_server(str(tmp_path / "projet")) as base:
        if creation["inscriptible"]:
            legitime = _jeton(base, "legitime@example.test", creation["acteur"])
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
            jeton = _jeton(base, "adverse@example.test", elevation["acteur"])
            suppression = elevation["verbe"] == "Delete"
            methode = requests.delete if suppression else requests.put
            corps = None if suppression else _corps_valide(tmp_path / "projet", elevation["entite"])
            interdit = methode(f"{base}/{elevation['entite'].lower()}/1", json=corps,
                               timeout=10, headers={"Authorization": f"Bearer {jeton}"})
            assert interdit.status_code == 403, interdit.text
