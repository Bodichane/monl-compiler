"""Issue #73 : un statut après-paiement naît dans le premier état du oneOf."""

import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import free_port, uvicorn_server

SPEC = """app BancStatutInitial

entity Article
    prix: Money
    stock: Integer

entity Commande
    total: Money
    statut: String
    suivi: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister
actor Gestionnaire selfRegister

rule Article.Read public
rule Article.stock min 0
rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Commande.total sumOf Ligne.sousTotal
rule Commande.total payable
rule Commande.statut oneOf "panier", "expédiée", "annulée"
rule Commande.statut writableAfterPayment Gestionnaire
rule Commande.suivi writableAfterPayment Gestionnaire

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Read Article

workflow Gerer for Gestionnaire
    Update Commande.statut
    Update Commande.suivi
"""

MOT_DE_PASSE = "motdepasse123"
CLE_WEBHOOK = "whsec_statut_initial"


class _PrestataireFactice(BaseHTTPRequestHandler):
    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append(urllib.parse.parse_qs(brut.decode()))
        corps = json.dumps({
            "id": f"cs_statut_{len(self.server.recu)}",
            "url": "https://paiement.example/session",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def faux_stripe():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _PrestataireFactice)
    serveur.recu = []
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)


@contextlib.contextmanager
def _base(dossier):
    connexion = sqlite3.connect(Path(dossier) / "app.db")
    try:
        with connexion:
            yield connexion
    finally:
        connexion.close()


def _env_paiement(faux_stripe):
    hote, port = faux_stripe.server_address[:2]
    return {
        **os.environ,
        "STRIPE_SECRET_KEY": "sk_test_statut_initial",
        "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
        "MONL_STRIPE_BASE_URL": f"http://{hote}:{port}",
    }


def _inscrire(base, nom, acteur):
    reponse = requests.post(
        f"{base}/register",
        json={"username": nom, "password": MOT_DE_PASSE, "actor": acteur},
        timeout=10,
    )
    assert reponse.status_code == 200, reponse.text
    connexion = requests.post(
        f"{base}/login",
        json={"username": nom, "password": MOT_DE_PASSE},
        timeout=10,
    )
    assert connexion.status_code == 200, connexion.text
    return {"Authorization": "Bearer " + connexion.json()["access_token"]}


def _webhook(base, commande_id):
    corps = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_statut_1",
            "client_reference_id": f"Commande:{commande_id}",
        }},
    }).encode()
    horodatage = str(int(time.time()))
    signature = hmac.new(
        CLE_WEBHOOK.encode(), (horodatage + ".").encode() + corps,
        hashlib.sha256,
    ).hexdigest()
    return requests.post(
        f"{base}/paiement/webhook",
        data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={horodatage},v1={signature}"},
        timeout=10,
    )


@pytest.fixture(scope="module")
def application(faux_stripe):
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier, env=_env_paiement(faux_stripe)) as base:
            with _base(dossier) as connexion:
                connexion.execute(
                    "INSERT INTO article (prix, stock) VALUES (12.5, 10)")
            client = _inscrire(base, "cliente", "Client")
            gestionnaire = _inscrire(base, "gestionnaire", "Gestionnaire")
            yield base, dossier, client, gestionnaire


def test_creation_prend_le_premier_oneof_et_laisse_le_texte_vide(application):
    base, dossier, client, _gestionnaire = application
    creation = requests.post(f"{base}/commande", headers=client, json={}, timeout=10)
    assert creation.status_code == 200, creation.text
    identifiant = creation.json()["id"]

    lecture = requests.get(
        f"{base}/commande/{identifiant}", headers=client, timeout=10)
    assert lecture.status_code == 200, lecture.text
    assert lecture.json()["data"]["statut"] == "panier"
    assert lecture.json()["data"]["suivi"] is None
    with _base(dossier) as connexion:
        assert connexion.execute(
            "SELECT statut, suivi FROM commande WHERE id = ?", (identifiant,),
        ).fetchone() == ("panier", None)


def test_apres_paiement_change_le_statut(application):
    base, dossier, client, gestionnaire = application
    commande = requests.post(
        f"{base}/commande", headers=client, json={}, timeout=10).json()["id"]
    ligne = requests.post(
        f"{base}/ligne", headers=client,
        json={"commande_id": commande, "article_id": 1, "quantite": 1},
        timeout=10,
    )
    assert ligne.status_code == 200, ligne.text
    paiement = requests.post(
        f"{base}/commande/{commande}/paiement", headers=client, timeout=10)
    assert paiement.status_code == 200, paiement.text
    assert _webhook(base, commande).status_code == 200

    modification = requests.put(
        f"{base}/commande/{commande}/apres-paiement",
        headers=gestionnaire, json={"statut": "expédiée"}, timeout=10)
    assert modification.status_code == 200, modification.text
    with _base(dossier) as connexion:
        assert connexion.execute(
            "SELECT statut FROM commande WHERE id = ?", (commande,),
        ).fetchone()[0] == "expédiée"


def test_premier_etat_de_liberation_est_refuse(capsys):
    spec = SPEC.replace(
        'rule Commande.statut oneOf "panier", "expédiée", "annulée"',
        'rule Commande.statut oneOf "annulée", "panier", "expédiée"',
    ).replace(
        "rule Commande.statut writableAfterPayment Gestionnaire",
        'rule Commande.statut "annulée" releases Ligne\n'
        "rule Ligne.Create decrements Article.stock by quantite\n"
        "rule Commande.statut writableAfterPayment Gestionnaire",
    )
    with pytest.raises(ASTValidationError) as refus:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    message = str(refus.value)
    assert "Commande.statut" in message
    assert "annulée" in message
    assert "Déclarer d'abord l'état initial" in message
    capsys.readouterr()


def _lancer_avec_journal(dossier, env):
    port = free_port()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=dossier, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        if processus.poll() is not None:
            sortie = processus.stdout.read().decode("utf-8", "replace")
            pytest.fail(sortie)
        try:
            if requests.get(base + "/openapi.json", timeout=1).status_code == 200:
                return processus
        except requests.RequestException:
            time.sleep(0.25)
    processus.terminate()
    pytest.fail("le serveur n'a jamais répondu")


def test_une_ancienne_ligne_null_est_comptee_sans_etre_rattrapee(
        tmp_path, faux_stripe):
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    env = _env_paiement(faux_stripe)
    with uvicorn_server(str(tmp_path), env=env), _base(tmp_path) as connexion:
        connexion.execute(
            "INSERT INTO commande (total, statut, suivi) VALUES (0, NULL, NULL)")

    processus = _lancer_avec_journal(str(tmp_path), env)
    processus.terminate()
    sortie, _ = processus.communicate(timeout=10)
    journal = sortie.decode("utf-8", "replace")
    assert '"commande"."statut" : 1 enregistrement(s)' in journal
    assert "valeur NULL hors du oneOf" in journal
    with _base(tmp_path) as connexion:
        assert connexion.execute(
            "SELECT statut FROM commande WHERE id = 1").fetchone()[0] is None


def test_exemple_boutique_cree_une_commande_au_statut_panier(tmp_path):
    racine = Path(__file__).parents[1]
    compile_project(str(racine / "exemples" / "02_boutique.ml"), str(tmp_path))
    with uvicorn_server(str(tmp_path)) as base:
        client = _inscrire(base, "boutique@example.com", "Customer")
        creation = requests.post(
            f"{base}/order", headers=client, json={}, timeout=10)
        assert creation.status_code == 200, creation.text
        lecture = requests.get(
            f"{base}/order/{creation.json()['id']}", headers=client, timeout=10)
        assert lecture.status_code == 200, lecture.text
        assert lecture.json()["data"]["status"] == "panier"
