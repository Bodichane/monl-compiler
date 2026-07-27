"""Étanchéité des lectures entre comptes (bêta 3).

Défaut corrigé : 'ownedBy' ne protégeait que l'écriture. Sur une application
de suivi de dépenses, deux comptes distincts se lisaient mutuellement —
'GET /expense' renvoyait tout, et 'GET /expense/{id}' répondait 200 sur
l'enregistrement d'autrui. Seul 'PUT' était refusé.

Le test lance une vraie application générée et rejoue le scénario complet.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ast_validator import MonlAST
from generator import MonlSecureGenerator
from parser import parse_monl_string

SPEC_PRIVEE = """app Depenses

entity Expense
    label: String
    amount: Money

entity User
    displayName: String

relation User hasMany Expense

actor User selfRegister
actor Auditor

rule Expense.Read ownedBy User
rule Expense.Update ownedBy User
rule Expense.Delete ownedBy User

workflow MesDepenses for User
    Create Expense
    Read Expense
    Update Expense
    Delete Expense

workflow Controle for Auditor
    Read Expense
"""


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _compte(base, nom):
    requests.post(f"{base}/register",
                  json={"username": nom, "password": "motdepasse123", "actor": "User"})
    jeton = requests.post(f"{base}/login",
                          json={"username": nom, "password": "motdepasse123"}).json()
    return {"Authorization": "Bearer " + jeton["access_token"]}


@pytest.fixture(scope="module")
def application():
    """Compile la spec, démarre le serveur, le rend à l'appelant."""
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_PRIVEE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        port = _port_libre()
        serveur = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=dossier, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(80):
                try:
                    requests.get(f"{base}/openapi.json", timeout=1)
                    break
                except requests.exceptions.ConnectionError:
                    time.sleep(0.25)
            else:
                pytest.skip("serveur non démarré")
            yield base, dossier
        finally:
            serveur.terminate()
            serveur.wait(timeout=10)


def test_un_compte_ne_lit_pas_les_donnees_d_un_autre(application):
    base, dossier = application
    alice, bob = _compte(base, "alice"), _compte(base, "bob")
    cree = requests.post(f"{base}/expense", headers=alice,
                         json={"label": "Consultation", "amount": 120.0})
    assert cree.status_code == 200
    id_alice = cree.json()["id"]
    requests.post(f"{base}/expense", headers=bob, json={"label": "Courses", "amount": 42.0})

    # Liste : Bob ne voit que la sienne, et le total ne compte que la sienne.
    vue_bob = requests.get(f"{base}/expense", headers=bob).json()
    assert vue_bob["total"] == 1, vue_bob
    assert [d["label"] for d in vue_bob["data"]] == ["Courses"]

    # Accès direct : 404 et non 403 — un 403 confirmerait l'existence de
    # l'enregistrement d'autrui, donc permettrait de le compter par énumération.
    assert requests.get(f"{base}/expense/{id_alice}", headers=bob).status_code == 404
    # L'écriture reste refusée elle aussi (comportement historique conservé).
    assert requests.put(f"{base}/expense/{id_alice}", headers=bob,
                        json={"label": "x", "amount": 1.0}).status_code in (403, 404)
    # Le propriétaire, lui, accède bien à la sienne.
    assert requests.get(f"{base}/expense/{id_alice}", headers=alice).status_code == 200


def test_un_role_tiers_autorise_continue_de_tout_voir(application):
    """Le filtre vise l'acteur propriétaire, pas les autres rôles autorisés.

    Sans cette nuance, le gestionnaire d'une boutique ne verrait aucune
    commande et le contrôle de propriété casserait les applications qu'il est
    censé protéger.
    """
    base, dossier = application
    subprocess.run([sys.executable, "manage.py", "adduser", "inspecteur", "Auditor"],
                   cwd=dossier, input="motdepasse123\nmotdepasse123\n",
                   capture_output=True, text=True)
    jeton = requests.post(f"{base}/login",
                          json={"username": "inspecteur", "password": "motdepasse123"}).json()
    auditeur = {"Authorization": "Bearer " + jeton["access_token"]}
    vue = requests.get(f"{base}/expense", headers=auditeur).json()
    assert vue["total"] >= 2, vue


def test_ownedby_sur_create_est_refuse_a_la_compilation():
    """Une règle sans effet doit échouer, pas être ignorée en silence."""
    from ast_validator import ASTValidationError
    spec = SPEC_PRIVEE.replace("rule Expense.Read ownedBy User",
                               "rule Expense.Create ownedBy User")
    with pytest.raises(ASTValidationError, match="Create"):
        MonlAST(parse_monl_string(spec)).validate_and_audit()
