"""Brique 18 (verrou de l'enregistrement payé) éprouvée contre un vrai serveur —
point 91.

Pourquoi ce fichier existe. `payable` (brique 9) garantissait que le montant
encaissé venait de la BASE, jamais du client. Elle ne disait rien de ce qui se
passe APRÈS l'encaissement — et la réponse, mesurée sur une boutique réelle
avant d'écrire une ligne de code, était : tout. Une commande réglée 89 € gagnait
une paire à 149 €, affichait 238 € toujours marqués 'payee', puis 594 € en
portant la quantité à cinq. Vidée de ses lignes, elle se supprimait ; le 409 que
renvoyait alors la clé étrangère ne protégeait rien, il retardait.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :

* les cinq portes sont fermées, pas une : l'entité payable en modification et en
  suppression, et sa LIGNE en création, modification et suppression — c'est par
  la ligne que le total remontait, le verrou posé sur la seule commande aurait
  laissé le trou entier ;
* le total ne bouge pas d'un centime après un refus (un 409 rendu APRÈS le
  recalcul serait un verrou qui prévient au lieu d'empêcher) ;
* la CONTRE-ÉPREUVE : avant règlement, les cinq écritures passent toujours. Un
  verrou qui figerait tout ferait passer les cinq premiers tests sans rien
  garantir, et rendrait la boutique inutilisable ;
* un webhook signé mais VIEUX est refusé : l'horodatage était lu pour vérifier
  la signature et jamais daté, donc un appel capté restait rejouable ;
* le type `Email` refuse enfin une adresse qui n'en est pas une.
"""
import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
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
from tests.support.server import uvicorn_server

SPEC = """app BancVerrou

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
    courriel: Email
    total: Money

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client

rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite

rule Commande.total sumOf Ligne.sousTotal
rule Commande.total payable

workflow Acheter for Client
    Read Article
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_banc_verrou"
CLE_WEBHOOK = "whsec_banc_verrou"
PRIX = 89.00
PRIX_CHER = 149.00


class _PrestataireFactice(BaseHTTPRequestHandler):
    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append(
            {c: v[0] for c, v in urllib.parse.parse_qs(brut.decode()).items()})
        corps = json.dumps({
            "id": f"cs_test_{len(self.server.recu)}",
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
        env = {**os.environ,
               "STRIPE_SECRET_KEY": CLE_SECRETE,
               "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
               "MONL_STRIPE_BASE_URL": f"http://{hote}:{port_stripe}"}
        with uvicorn_server(dossier, env=env) as base:
            with _base(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Deck", PRIX))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Halo", PRIX_CHER))
            yield base, dossier


def _entetes(application, identifiant):
    base, dossier = application
    with _base(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register",
                  json={"username": identifiant, "password": MOT_DE_PASSE,
                        "actor": "Client"})
    jeton = requests.post(f"{base}/login",
                          json={"username": identifiant,
                                "password": MOT_DE_PASSE}).json()
    assert "access_token" in jeton, jeton
    return {"Authorization": "Bearer " + jeton["access_token"]}


@pytest.fixture(scope="module")
def alice(application):
    return _entetes(application, "alice")


def _article(dossier, prix):
    with _base(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (prix,)).fetchone()[0]


def _commande(base, entetes, libelle="panier"):
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle,
                                  "courriel": "acheteuse@exemple.fr"})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _ligne(base, entetes, commande_id, article_id, quantite=1):
    return requests.post(f"{base}/ligne", headers=entetes,
                         json={"commande_id": commande_id,
                               "article_id": article_id,
                               "quantite": quantite})


def _total(base, entetes, commande_id):
    return requests.get(f"{base}/commande/{commande_id}",
                        headers=entetes).json()["data"]["total"]


def _etat(dossier, commande_id):
    with _base(dossier) as cnx:
        ligne = cnx.execute(
            'SELECT payment_status FROM commande WHERE id = ?',
            (commande_id,)).fetchone()
    return ligne[0] if ligne else None


def _webhook(base, commande_id, decalage=0, session="cs_test_1"):
    """Signe et poste un événement de règlement. `decalage` en secondes sert au
    test de rejeu : c'est le seul paramètre qui change entre un appel légitime
    et un appel capté puis rejoué plus tard."""
    corps = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"id": session,
                            "client_reference_id": f"Commande:{commande_id}"}},
    }).encode()
    horodatage = str(int(time.time()) + decalage)
    signature = hmac.new(CLE_WEBHOOK.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    return requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t={horodatage},v1={signature}"},
        timeout=10)


def _commande_reglee(application, entetes):
    """Une commande d'une ligne à 89 €, réellement passée par la route de
    règlement puis par le webhook signé du prestataire."""
    base, dossier = application
    identifiant = _commande(base, entetes)
    assert _ligne(base, entetes, identifiant,
                  _article(dossier, PRIX)).status_code in (200, 201)
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes)
    assert reponse.status_code == 200, reponse.text
    assert _webhook(base, identifiant).status_code == 200
    assert _etat(dossier, identifiant) == "payee"
    return identifiant


# ---------------------------------------------------------------- le verrou

def test_une_commande_reglee_refuse_la_modification(application, alice):
    base, dossier = application
    identifiant = _commande_reglee(application, alice)

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=alice,
                           json={"libelle": "renommée",
                                 "courriel": "acheteuse@exemple.fr"})

    assert reponse.status_code == 409, reponse.text
    assert "réglé" in reponse.json()["detail"]
    with _base(dossier) as cnx:
        assert cnx.execute('SELECT libelle FROM commande WHERE id = ?',
                           (identifiant,)).fetchone()[0] == "panier"


def test_une_commande_reglee_refuse_la_suppression(application, alice):
    """Supprimer effaçait la trace d'un encaissement. Le 409 que rendait la clé
    étrangère ne tenait que tant qu'il restait une ligne : ce test vide d'abord
    la commande, ce qui est exactement le chemin par lequel elle disparaissait."""
    base, dossier = application
    identifiant = _commande_reglee(application, alice)
    lignes = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    ligne = next(li for li in lignes if li["commande_id"] == identifiant)

    retrait = requests.delete(f"{base}/ligne/{ligne['id']}", headers=alice)
    suppression = requests.delete(f"{base}/commande/{identifiant}", headers=alice)

    assert retrait.status_code == 409, retrait.text
    assert suppression.status_code == 409, suppression.text
    with _base(dossier) as cnx:
        assert cnx.execute('SELECT COUNT(*) FROM commande WHERE id = ?',
                           (identifiant,)).fetchone()[0] == 1


def test_une_ligne_ne_s_ajoute_plus_a_une_commande_reglee(application, alice):
    """Le trou d'origine, dans le sens où il a été exploité : 89 € encaissés,
    puis une paire à 149 € ajoutée, et 238 € affichés toujours 'payee'."""
    base, dossier = application
    identifiant = _commande_reglee(application, alice)

    ajout = _ligne(base, alice, identifiant, _article(dossier, PRIX_CHER))

    assert ajout.status_code == 409, ajout.text
    # Le total ne doit pas avoir bougé d'un centime : un refus rendu APRÈS le
    # recalcul préviendrait au lieu d'empêcher.
    assert float(_total(base, alice, identifiant)) == PRIX


def test_la_quantite_d_une_ligne_reglee_ne_change_plus(application, alice):
    base, dossier = application
    identifiant = _commande_reglee(application, alice)
    lignes = requests.get(f"{base}/ligne?limit=100", headers=alice).json()["data"]
    ligne = next(li for li in lignes if li["commande_id"] == identifiant)

    modif = requests.put(f"{base}/ligne/{ligne['id']}", headers=alice,
                         json={"quantite": 5, "commande_id": identifiant,
                               "article_id": ligne["article_id"]})

    assert modif.status_code == 409, modif.text
    assert float(_total(base, alice, identifiant)) == PRIX


# ---------------------------------------------------------- la contre-épreuve

def test_avant_reglement_les_cinq_ecritures_passent_toujours(application, alice):
    """SANS ce test, un verrou qui figerait tout ferait passer les précédents en
    ne garantissant rien — et rendrait la boutique inutilisable."""
    base, dossier = application
    identifiant = _commande(base, alice, "en cours")

    ajout = _ligne(base, alice, identifiant, _article(dossier, PRIX))
    ligne_id = ajout.json()["id"]
    modif_ligne = requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                               json={"quantite": 3, "commande_id": identifiant,
                                     "article_id": _article(dossier, PRIX)})
    total_apres_modif = float(_total(base, alice, identifiant))
    modif_commande = requests.put(f"{base}/commande/{identifiant}", headers=alice,
                                  json={"libelle": "renommée",
                                        "courriel": "acheteuse@exemple.fr"})
    retrait = requests.delete(f"{base}/ligne/{ligne_id}", headers=alice)
    suppression = requests.delete(f"{base}/commande/{identifiant}", headers=alice)

    assert ajout.status_code in (200, 201), ajout.text
    assert modif_ligne.status_code == 200, modif_ligne.text
    assert total_apres_modif == round(PRIX * 3, 2)
    assert modif_commande.status_code == 200, modif_commande.text
    assert retrait.status_code == 200, retrait.text
    assert suppression.status_code == 200, suppression.text


def test_le_verrou_ne_deborde_pas_sur_la_commande_d_a_cote(application, alice):
    """Une commande réglée ne fige qu'elle-même : le verrou lit le parent de la
    ligne, pas « une commande payée existe quelque part »."""
    base, dossier = application
    _commande_reglee(application, alice)
    voisine = _commande(base, alice, "voisine")

    ajout = _ligne(base, alice, voisine, _article(dossier, PRIX))

    assert ajout.status_code in (200, 201), ajout.text
    assert float(_total(base, alice, voisine)) == PRIX


# ------------------------------------------------------------ rejeu du webhook

def test_un_webhook_signe_mais_vieux_est_refuse(application, alice):
    """Fraîcheur de la signature : l'horodatage servait à VÉRIFIER la signature
    sans jamais être daté, donc un appel légitime capté restait rejouable
    indéfiniment. Dix minutes suffisent à le montrer."""
    base, dossier = application
    identifiant = _commande(base, alice, "rejeu")
    _ligne(base, alice, identifiant, _article(dossier, PRIX))

    reponse = _webhook(base, identifiant, decalage=-600)

    assert reponse.status_code == 400, reponse.text
    assert "expirée" in reponse.json()["detail"]
    assert _etat(dossier, identifiant) == "en_attente"


def test_un_horodatage_illisible_ne_passe_pas_pour_frais(application, alice):
    base, dossier = application
    identifiant = _commande(base, alice, "horodatage")
    corps = json.dumps({"type": "checkout.session.completed",
                        "data": {"object": {"id": "cs_x",
                                            "client_reference_id":
                                            f"Commande:{identifiant}"}}}).encode()
    signature = hmac.new(CLE_WEBHOOK.encode(), b"jamais." + corps,
                         hashlib.sha256).hexdigest()

    reponse = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"Content-Type": "application/json",
                 "stripe-signature": f"t=jamais,v1={signature}"}, timeout=10)

    assert reponse.status_code == 400, reponse.text
    assert _etat(dossier, identifiant) == "en_attente"


# ------------------------------------------------------------------- courriel

@pytest.mark.parametrize("adresse", [
    "pas-un-courriel", "sans@point", "espace @exemple.fr", "@exemple.fr",
    "deux@@exemple.fr",
])
def test_le_type_email_refuse_une_adresse_qui_n_en_est_pas_une(application,
                                                               alice, adresse):
    """POINT 91 : le type ne fixait qu'une longueur. 'pas-un-courriel' entrait
    en base avec un 200 — une adresse à laquelle aucun colis ne part."""
    base, _dossier = application

    reponse = requests.post(f"{base}/commande", headers=alice,
                            json={"libelle": "adresse", "courriel": adresse})

    assert reponse.status_code == 422, reponse.text


@pytest.mark.parametrize("adresse", [
    "acheteuse@exemple.fr", "prenom.nom+etiquette@sous.domaine.co.uk",
])
def test_une_adresse_valide_reste_acceptee(application, alice, adresse):
    """La contre-épreuve du refus : un motif trop strict ferait passer le test
    précédent en rejetant aussi les vraies adresses."""
    base, _dossier = application

    reponse = requests.post(f"{base}/commande", headers=alice,
                            json={"libelle": "adresse", "courriel": adresse})

    assert reponse.status_code in (200, 201), reponse.text
