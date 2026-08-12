"""Brique 12 (`sumOf`) éprouvée contre un vrai serveur — point 82.

Pourquoi ce fichier existe. `derivedFrom` (brique 10) calcule un montant depuis
UNE ligne liée : une commande ne pouvait donc porter qu'un seul article. La
propriété transitive (brique 11) a donné à la commande des lignes correctement
protégées, mais la commande ne savait toujours pas ce qu'elle coûtait — le total
restait un champ que le client écrivait, ou n'existait pas. `sumOf` ferme la
troisième et dernière brique du panier cadrée au point 80.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :

* le total suit les lignes dans les TROIS sens — ajout, modification,
  suppression. Recalculer à la création seulement laisserait la faille du
  point 77 revenir par la quantité, puis par le retrait d'un article ;
* un panier vidé retombe à 0 et non à NULL (qu'aucune interface n'affiche) ;
* le montant ENCAISSÉ est la somme, vérifié sur ce que le prestataire reçoit
  réellement — c'est la seule affirmation qui compte pour une boutique, et elle
  demande un faux Stripe, pas une lecture de la base ;
* le total d'un tiers ne bouge pas quand on tente d'ajouter une ligne à sa
  commande (composition avec la brique 11 : le 403 ne suffit pas, il faut que
  RIEN n'ait été recalculé) ;
* la somme est arrondie : additionner des flottants dérive, et c'est un montant.
"""
import contextlib
import json
import os
import sqlite3
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app BancAgregation

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
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
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_banc_agregation"
CLE_WEBHOOK = "whsec_banc_agregation"
# Prix CHOISIS pour que la somme dérive réellement en flottant :
# round(10.05*3, 2) + round(10.15*7, 2) == 101.19999999999999, et non 101.2.
# Mes premières valeurs (12.35 et 7.80) ne dérivaient pas, ce qui rendait le
# test d'arrondi tautologique : il passait avec ou sans le ROUND. Vérifié en
# Python avant d'être écrit ici.
PRIX_A, PRIX_B = 10.05, 10.15
# La quantité qui déclenche la dérive, utilisée par le test d'arrondi.
QTE_A, QTE_B = 3, 7


class _PrestataireFactice(BaseHTTPRequestHandler):
    """Même faux Stripe que tests/test_paiement.py : il DÉCODE le corps qu'on
    lui envoie, ce qui est la seule façon d'affirmer quel montant a réellement
    été demandé — lire la base ne dirait que ce que monl croit encaisser."""

    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append({
            "chemin": self.path,
            "champs": {c: v[0] for c, v
                       in urllib.parse.parse_qs(brut.decode()).items()},
        })
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
                            ("Article A", PRIX_A))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article B", PRIX_B))
            yield base, dossier


def _vider_quota(dossier):
    with _base(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")


def _entetes(application, identifiant):
    base, dossier = application
    _vider_quota(dossier)
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


@pytest.fixture(scope="module")
def bob(application):
    return _entetes(application, "bob")


def _id_article(dossier, prix):
    with _base(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (prix,)).fetchone()[0]


def _commande(base, entetes, libelle):
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _ligne(base, entetes, commande_id, article_id, quantite):
    return requests.post(f"{base}/ligne", headers=entetes,
                         json={"commande_id": commande_id,
                               "article_id": article_id,
                               "quantite": quantite})


def _total(base, entetes, commande_id):
    reponse = requests.get(f"{base}/commande/{commande_id}", headers=entetes)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()["data"]["total"]


# --------------------------------------------------------------------------
# Le total sort des corps de requête
# --------------------------------------------------------------------------

def test_le_total_n_est_pas_un_champ_de_requete(application):
    base, _ = application
    champs = requests.get(f"{base}/openapi.json").json()[
        "components"]["schemas"]["CommandeSchema"]["properties"]
    assert "total" not in champs, (
        "le client pourrait écrire le total d'un panier — la faille du point 77 "
        "revenue par le panier")
    assert "libelle" in champs  # témoin : le schéma n'est pas vide


def test_une_commande_naît_a_zero_et_non_a_null(application, alice):
    """NULL n'est pas 0 : aucune interface ne sait afficher « null € », et une
    somme partant de NULL resterait NULL en SQLite."""
    base, _ = application
    commande = _commande(base, alice, "panier vide")
    assert _total(base, alice, commande) == 0


def test_le_total_envoye_par_le_client_est_ignore(application, alice):
    base, dossier = application
    commande = _commande(base, alice, "tentative")
    article = _id_article(dossier, PRIX_A)
    _ligne(base, alice, commande, article, 1)
    # Le champ n'existe pas dans le schéma : Pydantic l'ignore en silence.
    requests.put(f"{base}/commande/{commande}", headers=alice,
                 json={"libelle": "tentative", "total": 0.01})
    assert _total(base, alice, commande) == pytest.approx(PRIX_A)


# --------------------------------------------------------------------------
# Le total suit les lignes dans les trois sens
# --------------------------------------------------------------------------

def test_le_total_est_la_somme_de_plusieurs_articles(application, alice):
    """Le cœur de la brique : ce que `derivedFrom` ne savait pas faire."""
    base, dossier = application
    commande = _commande(base, alice, "deux articles")
    assert _ligne(base, alice, commande, _id_article(dossier, PRIX_A),
                  2).status_code in (200, 201)
    assert _total(base, alice, commande) == pytest.approx(PRIX_A * 2)

    assert _ligne(base, alice, commande, _id_article(dossier, PRIX_B),
                  3).status_code in (200, 201)
    attendu = round(PRIX_A * 2 + PRIX_B * 3, 2)
    assert _total(base, alice, commande) == pytest.approx(attendu)


def test_le_total_suit_la_quantite_modifiee(application, alice):
    """Sans recalcul au PUT, la faille se déplacerait de la ligne vers la
    quantité : ajouter un article à 1 puis passer à 10."""
    base, dossier = application
    commande = _commande(base, alice, "modification")
    article = _id_article(dossier, PRIX_A)
    ligne = _ligne(base, alice, commande, article, 1).json()["id"]
    assert _total(base, alice, commande) == pytest.approx(PRIX_A)

    requests.put(f"{base}/ligne/{ligne}", headers=alice,
                 json={"quantite": 10, "commande_id": commande,
                       "article_id": article})
    assert _total(base, alice, commande) == pytest.approx(PRIX_A * 10)


def test_le_total_redescend_quand_une_ligne_est_supprimee(application, alice):
    """Le sens qu'on oublie : sans lui, retirer un article du panier laisserait
    payer un article rendu."""
    base, dossier = application
    commande = _commande(base, alice, "suppression")
    ligne_a = _ligne(base, alice, commande, _id_article(dossier, PRIX_A),
                     1).json()["id"]
    _ligne(base, alice, commande, _id_article(dossier, PRIX_B), 1)
    assert _total(base, alice, commande) == pytest.approx(
        round(PRIX_A + PRIX_B, 2))

    assert requests.delete(f"{base}/ligne/{ligne_a}",
                           headers=alice).status_code == 200
    assert _total(base, alice, commande) == pytest.approx(PRIX_B)


def test_un_panier_vide_de_ses_lignes_retombe_a_zero(application, alice):
    base, dossier = application
    commande = _commande(base, alice, "à vider")
    ligne = _ligne(base, alice, commande, _id_article(dossier, PRIX_A),
                   2).json()["id"]
    requests.delete(f"{base}/ligne/{ligne}", headers=alice)
    assert _total(base, alice, commande) == 0, "un panier vidé doit valoir 0"


def test_la_somme_est_arrondie(application, alice):
    """Additionner des flottants dérive. Sur un montant, un centime de dérive
    est un centime encaissé en trop ou en moins."""
    base, dossier = application
    commande = _commande(base, alice, "arrondi")
    _ligne(base, alice, commande, _id_article(dossier, PRIX_A), QTE_A)
    _ligne(base, alice, commande, _id_article(dossier, PRIX_B), QTE_B)
    total = _total(base, alice, commande)
    # Ces quantités-là dérivent : la somme brute vaut 101.19999999999999. Le
    # test ne prouverait rien avec des valeurs qui tombent juste.
    brute = round(PRIX_A * QTE_A, 2) + round(PRIX_B * QTE_B, 2)
    assert brute != round(brute, 2), (
        "les prix du banc ne dérivent plus : ce test redevient tautologique")
    assert total == round(brute, 2), f"total non arrondi : {total!r}"


# --------------------------------------------------------------------------
# Composition avec la brique 11 : le total d'un tiers
# --------------------------------------------------------------------------

def test_le_total_d_autrui_ne_bouge_pas(application, alice, bob):
    """Le 403 de la brique 11 ne suffit pas à l'affirmer : il faut vérifier que
    RIEN n'a été recalculé sur la commande visée."""
    base, dossier = application
    commande = _commande(base, alice, "privée")
    _ligne(base, alice, commande, _id_article(dossier, PRIX_A), 1)
    avant = _total(base, alice, commande)

    refuse = _ligne(base, bob, commande, _id_article(dossier, PRIX_B), 100)
    assert refuse.status_code == 403, refuse.text
    assert _total(base, alice, commande) == pytest.approx(avant)


# --------------------------------------------------------------------------
# Ce qui est réellement encaissé
# --------------------------------------------------------------------------

def test_le_montant_encaisse_est_la_somme_du_panier(application, alice, faux_stripe):
    """L'affirmation qui compte pour une boutique. Elle porte sur ce que le
    PRESTATAIRE reçoit, décodé de son corps de requête — pas sur ce que la base
    contient, ni sur ce que monl croit envoyer.

    C'est aussi la preuve que la chaîne complète tient : brique 10 calcule
    chaque ligne, brique 11 la rattache et la protège, brique 12 les somme,
    brique 9 encaisse le résultat."""
    base, dossier = application
    commande = _commande(base, alice, "à régler")
    _ligne(base, alice, commande, _id_article(dossier, PRIX_A), 2)
    _ligne(base, alice, commande, _id_article(dossier, PRIX_B), 3)
    attendu_centimes = str(round(round(PRIX_A * 2 + PRIX_B * 3, 2) * 100))

    avant = len(faux_stripe.recu)
    reglement = requests.post(f"{base}/commande/{commande}/paiement",
                              headers=alice)
    assert reglement.status_code == 200, reglement.text
    assert len(faux_stripe.recu) == avant + 1, "aucun appel au prestataire"

    demande = faux_stripe.recu[avant]
    assert demande["champs"][
        "line_items[0][price_data][unit_amount]"] == attendu_centimes, (
        f"montant encaissé faux : {demande['champs']}")
    # La référence reste qualifiée par l'entité (point 75).
    assert demande["champs"]["client_reference_id"] == f"Commande:{commande}"


def test_le_montant_encaisse_suit_une_ligne_retiree(application, alice, faux_stripe):
    """Le cas qui distingue « recalculé » de « calculé une fois » : on ne doit
    pas encaisser un article rendu avant le règlement."""
    base, dossier = application
    commande = _commande(base, alice, "panier corrigé")
    ligne_a = _ligne(base, alice, commande, _id_article(dossier, PRIX_A),
                     4).json()["id"]
    _ligne(base, alice, commande, _id_article(dossier, PRIX_B), 1)
    requests.delete(f"{base}/ligne/{ligne_a}", headers=alice)

    avant = len(faux_stripe.recu)
    assert requests.post(f"{base}/commande/{commande}/paiement",
                         headers=alice).status_code == 200
    assert faux_stripe.recu[avant]["champs"][
        "line_items[0][price_data][unit_amount]"] == str(round(PRIX_B * 100))
