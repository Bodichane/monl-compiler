"""Masquage de champ — `rule Entite.champ hidden` (brique 2, point 25).

Cette règle était implémentée (src/parser.py `masking_rule`,
src/generator/routes.py) et **couverte par rien** : depuis la suppression de
exemples/13_anon_forum_demo.yaml en bêta 3, le mot-clé `hidden` n'apparaissait
dans aucun test ni aucun exemple. La mesure de couverture du point 63 l'a
confirmé, CLAUDE.md l'avertissait déjà : une régression passait la CI sans
bruit.

Ce que la règle promet, et que ce fichier éprouve contre un vrai serveur :
le champ disparaît de la LISTE et du DÉTAIL, pour tout le monde — mais il
reste écrivable, et il reste en base.
"""
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC_MASQUAGE = """app Registre

entity Note
    title: String
    internalNote: String

actor Admin selfRegister

rule Note.Read public
rule Note.internalNote hidden

workflow GererNote for Admin
    Create Note
    Read Note
    Update Note
    Delete Note
"""


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_MASQUAGE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            yield base, dossier


def _admin(base):
    requests.post(f"{base}/register",
                  json={"username": "chef", "password": "motdepasse123",
                        "actor": "Admin"})
    jeton = requests.post(f"{base}/login",
                          json={"username": "chef", "password": "motdepasse123"}).json()
    return {"Authorization": "Bearer " + jeton["access_token"]}


def test_le_champ_masque_disparait_de_la_lecture_et_reste_en_base(application):
    base, dossier = application
    entetes = _admin(base)

    cree = requests.post(f"{base}/note", headers=entetes,
                         json={"title": "Devis Aurora",
                               "internalNote": "marge 42%, ne pas divulguer"})
    assert cree.status_code in (200, 201), cree.text
    note_id = cree.json().get("id") or cree.json().get("data", {}).get("id")
    assert note_id, cree.text

    # 1. La LISTE ne montre pas le champ — y compris pour l'auteur connecté.
    liste = requests.get(f"{base}/note", headers=entetes).json()
    lignes = liste["data"]
    assert lignes, liste
    for ligne in lignes:
        assert "title" in ligne
        assert "internalNote" not in ligne, f"champ masqué exposé en liste : {ligne}"

    # 2. Le DÉTAIL non plus.
    detail = requests.get(f"{base}/note/{note_id}", headers=entetes).json()
    corps = detail.get("data", detail)
    assert corps.get("title") == "Devis Aurora", detail
    assert "internalNote" not in corps, f"champ masqué exposé en détail : {detail}"

    # 3. Sans compte non plus (la lecture est publique ici) : le masquage
    #    ne dépend pas de l'appelant, contrairement à ownedBy.
    anonyme = requests.get(f"{base}/note/{note_id}").json()
    assert "internalNote" not in anonyme.get("data", anonyme)

    # 4. Le champ reste ÉCRIVABLE — masquer n'est pas retirer.
    maj = requests.put(f"{base}/note/{note_id}", headers=entetes,
                       json={"title": "Devis Aurora",
                             "internalNote": "marge revue à 38%"})
    assert maj.status_code == 200, maj.text

    # 5. Et il est bien en base : masqué à la lecture, pas perdu.
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:  # `with connect(...)` valide la transaction, il ne ferme pas.
        table = next(nom for (nom,) in cnx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
            if nom.lower().startswith("note"))
        valeur = cnx.execute(
            f'SELECT internalNote FROM "{table}" WHERE id = ?', (note_id,)).fetchone()
    finally:
        cnx.close()
    assert valeur and valeur[0] == "marge revue à 38%", valeur


def test_le_champ_masque_est_absent_du_contrat_de_lecture(application):
    """Le contrat frontend décrit ce que les routes rendent : annoncer un
    champ que le serveur retire enverrait l'IA d'interface dessiner une
    colonne toujours vide."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()
    texte = str(schema)
    assert "internalNote" in texte, "le champ doit exister en écriture"
    lecture = schema["paths"]["/note/{id}"]["get"]
    assert "internalNote" not in str(lecture), lecture
