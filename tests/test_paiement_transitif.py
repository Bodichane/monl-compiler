"""Encaisser une entité possédée TRANSITIVEMENT — point 87.

Pourquoi ce fichier existe. Le point 81 refusait `payable` sur toute entité
possédée à travers un intermédiaire, avec ce motif : « la route de règlement
identifie le payeur par une clé étrangère de COMPTE, qu'une chaîne transitive ne
fournit pas ». C'était exact du code d'alors, et faux de la brique : la
propriété transitive livrait DÉJÀ, dans `_owner_lookup_sql`, la jointure qui
rend l'id de compte. Le refus protégeait d'une comparaison fausse — pas d'une
impossibilité.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :

* **le tiers est refusé.** C'est LA raison d'être du refus levé. Si la route
  comparait encore `current_user_id` à la clé étrangère de l'intermédiaire, le
  verdict serait tiré au sort — laisser payer le mauvais compte, ou bloquer le
  bon. Les identifiants du banc sont donc volontairement DIVERGENTS : sans
  cette précaution la sonde du point 81 n'avait rien montré, parce que
  « utilisateur 1 » et « commande 1 » coïncidaient ;
* **le montant est vérifié sur ce que le PRESTATAIRE reçoit**, pas sur ce que
  la base contient : c'est la seule affirmation qui compte pour une boutique ;
* **une ligne orpheline répond 404**, jamais « payable par quiconque » — la
  jointure ne rend aucun résultat, et c'est la bonne réponse ;
* **le contrôle et le montant sortent de la MÊME lecture.** L'invariant du
  point 74 ne devait pas être payé pour obtenir la jointure : deux requêtes
  rouvriraient la fenêtre entre le contrôle d'accès et le calcul du montant.
"""
import contextlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

# La LIGNE est encaissable, pas la commande : c'est exactement ce que le
# point 81 refusait. Le cas n'est pas artificiel — une facture rattachée à un
# contrat, une prestation rattachée à un dossier ont la même forme.
SPEC = """app BancTransitif

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

entity Client
    nom: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne
relation Client hasMany Client

actor Client selfRegister

rule Article.nom required
rule Commande.libelle required
rule Client.nom required
rule Ligne.quantite required
rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Ligne.sousTotal payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
    Create Client
    Read Client
    Read Article
"""

CLE_SECRETE = "sk_test_banc_transitif"
CLE_WEBHOOK = "whsec_banc_transitif"
PRIX = 42.5
QUANTITE = 3


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _PrestataireFactice(BaseHTTPRequestHandler):
    """Il DÉCODE le corps reçu : c'est la seule façon d'affirmer quel montant a
    réellement été demandé. Lire la base ne dirait que ce que monl croit."""

    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append(
            {c: v[0] for c, v in urllib.parse.parse_qs(brut.decode()).items()})
        corps = json.dumps({"id": f"cs_{len(self.server.recu)}",
                            "url": "https://paiement.example/s"}).encode()
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
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


@pytest.fixture(scope="module")
def application(faux_stripe):
    hote, port_stripe = faux_stripe.server_address[:2]
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        port = _port_libre()
        env = {**os.environ, "STRIPE_SECRET_KEY": CLE_SECRETE,
               "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
               "MONL_STRIPE_BASE_URL": f"http://{hote}:{port_stripe}"}
        serveur = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=dossier, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            with _base(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article", PRIX))
            yield base, dossier
        finally:
            serveur.terminate()
            serveur.wait(timeout=10)


def _compte(application, identifiant):
    base, dossier = application
    with _base(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register", json={"username": identifiant,
                                            "password": "motdepasse1",
                                            "actor": "Client"}, timeout=10)
    reponse = requests.post(f"{base}/login", json={"username": identifiant,
                                                   "password": "motdepasse1"},
                            timeout=10)
    entetes = {"Authorization": f"Bearer {reponse.json()['access_token']}"}
    requests.post(f"{base}/client", json={"nom": identifiant},
                  headers=entetes, timeout=10)
    return entetes


@pytest.fixture(scope="module")
def alice(application):
    return _compte(application, "alice")


@pytest.fixture(scope="module")
def bob(application):
    return _compte(application, "bob")


def _ligne_de(base, entetes, libelle):
    """Une commande et sa ligne, et l'identifiant des deux."""
    commande = requests.post(f"{base}/commande", json={"libelle": libelle},
                             headers=entetes, timeout=10).json()["id"]
    article = requests.get(f"{base}/article?limit=1", timeout=10).json()["data"][0]["id"]
    ligne = requests.post(f"{base}/ligne",
                          json={"quantite": QUANTITE, "commande_id": commande,
                                "article_id": article},
                          headers=entetes, timeout=10).json()["id"]
    return commande, ligne


# --------------------------------------------------------------------------

def test_le_proprietaire_transitif_peut_payer(application, alice, faux_stripe):
    """Ce que le point 81 interdisait. Le montant est vérifié sur ce que le
    PRESTATAIRE reçoit — pas sur ce que la base contient."""
    base, _dossier = application
    _commande, ligne = _ligne_de(base, alice, "panier alice")

    avant = len(faux_stripe.recu)
    reponse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)
    assert reponse.status_code == 200, reponse.text
    assert len(faux_stripe.recu) == avant + 1

    demande = faux_stripe.recu[-1]
    attendu = str(round(PRIX * QUANTITE * 100))
    assert demande["line_items[0][price_data][unit_amount]"] == attendu, demande
    # La référence est qualifiée par le nom de l'entité (point 75) : sans quoi
    # le webhook confondrait l'id de deux tables payables.
    assert demande.get("client_reference_id") == f"Ligne:{ligne}"


def test_un_tiers_ne_peut_pas_payer(application, alice, bob):
    """LE test qui justifie le refus levé.

    Si la route comparait encore `current_user_id` à la clé étrangère de
    l'intermédiaire — un id de COMMANDE — le verdict serait tiré au sort. Les
    identifiants sont volontairement divergents pour que la confusion se voie."""
    base, dossier = application
    commande, ligne = _ligne_de(base, alice, "panier privé")

    with _base(dossier) as cnx:
        compte_alice = cnx.execute(
            "SELECT id FROM _monl_users WHERE username = 'alice'").fetchone()[0]
    assert commande != compte_alice, "identifiants confondus : le test ne prouve rien"
    assert ligne != compte_alice, "identifiants confondus : le test ne prouve rien"

    refuse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=bob, timeout=15)
    assert refuse.status_code == 403, refuse.text
    # Et le propriétaire, lui, passe : un 403 pour tout le monde « réussirait »
    # ce test sans rien prouver.
    assert requests.post(f"{base}/ligne/{ligne}/paiement",
                         headers=alice, timeout=15).status_code == 200


def test_une_ligne_orpheline_est_introuvable(application, alice):
    """La jointure ne rend aucun résultat : la ligne n'appartient à personne.
    404 — surtout pas « payable par quiconque »."""
    base, dossier = application
    _commande, ligne = _ligne_de(base, alice, "panier à orpheliner")
    with _base(dossier) as cnx:
        cnx.execute('UPDATE "ligne" SET "commande_id" = 999999 WHERE id = ?', (ligne,))
    reponse = requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)
    assert reponse.status_code == 404, reponse.text


def test_le_webhook_marque_la_ligne_payee(application, alice, faux_stripe):
    """La chaîne complète : la référence qualifiée revient du prestataire et
    désigne la bonne table."""
    import hashlib
    import hmac

    base, dossier = application
    _commande, ligne = _ligne_de(base, alice, "panier réglé")
    requests.post(f"{base}/ligne/{ligne}/paiement", headers=alice, timeout=15)

    corps = json.dumps({"type": "checkout.session.completed",
                        "data": {"object": {"client_reference_id": f"Ligne:{ligne}",
                                            "id": "cs_x"}}}).encode()
    # POINT 91 : l'heure COURANTE, comme le prestataire réel — la signature est
    # désormais datée, et un horodatage figé serait refusé pour rejeu.
    horodatage = str(int(time.time()))
    signature = hmac.new(CLE_WEBHOOK.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    reponse = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={horodatage},v1={signature}"}, timeout=10)
    assert reponse.status_code == 200, reponse.text

    with _base(dossier) as cnx:
        etat = cnx.execute('SELECT payment_status FROM "ligne" WHERE id = ?',
                           (ligne,)).fetchone()[0]
    assert etat == "payee"


def test_le_controle_et_le_montant_sortent_de_la_meme_lecture(tmp_path):
    """Invariant du point 74, à ne pas payer pour obtenir la jointure : deux
    requêtes séparées rouvriraient la fenêtre entre le contrôle d'accès et le
    calcul du montant. La route ne doit donc contenir qu'UN seul execute."""
    ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    # Découpe sur le décorateur suivant : « \ndef » attraperait aussi le
    # webhook, dont l'execute est légitime et fausserait le compte.
    corps = genere.split("def payer_ligne(")[1].split("@app.post")[0]
    assert corps.count("cursor.execute(") == 1, corps
    # La jointure est bien DANS ce seul SELECT.
    assert "JOIN" in corps and "commande" in corps
