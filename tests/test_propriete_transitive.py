"""Brique 11 (propriété transitive) éprouvée contre un vrai serveur — point 81.

Pourquoi ce fichier existe. Un panier multi-articles a besoin d'une entité
« ligne de commande », et une ligne n'appartient à personne directement : elle
appartient à qui possède sa commande. Jusqu'au point 80, `ownedBy` ne savait
désigner qu'un ACTEUR ; nommer une entité compilait en silence et produisait un
rattachement faux — l'identifiant du compte appelant écrit à la place de la
commande demandée.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :

* la clé étrangère stockée est bien la COMMANDE désignée, jamais l'identifiant
  du compte appelant (le défaut exact du point 80, qui compilait sans un mot) ;
* rattacher une ligne à la commande d'autrui est refusé — sans cette
  vérification, la brique ouvrirait un trou plus large que celui qu'elle ferme,
  puisque la clé étrangère n'est plus déduite du jeton mais fournie par le
  client ;
* les quatre chemins de lecture/écriture filtrent par la JOINTURE (liste,
  détail, modification, suppression), pas par une comparaison de colonne ;
* la composition avec `derivedFrom` tient : le montant de la ligne reste calculé
  par le serveur.

Les identifiants sont volontairement DIVERGENTS (plusieurs commandes créées
avant celles qui servent aux assertions) : le premier essai de la sonde n'avait
rien montré parce que « utilisateur 1 » et « commande 1 » coïncidaient, et une
comparaison fausse passait pour juste.
"""
import contextlib
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

SPEC = """app BancTransitif

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Admin
actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client

# La brique : une ligne appartient à qui possède sa commande.
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite

workflow GererArticle for Admin
    Create Article
    Read Article

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
PRIX_CHER, PRIX_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base(dossier):
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            with _base(dossier) as cnx:
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article cher", PRIX_CHER))
                cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                            ("Article bon marché", PRIX_BON_MARCHE))
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
    entetes = _entetes(application, "alice")
    # Trois commandes avant toute assertion : les identifiants de commande
    # cessent ainsi de coïncider avec ceux des comptes. Sans cet écart, une
    # comparaison qui confond « id de commande » et « id de compte » passe pour
    # juste — c'est précisément ce qui a masqué le défaut du point 80.
    base, _ = application
    for libelle in ("brouillon", "abandonnée", "en cours"):
        _commande(base, entetes, libelle)
    return entetes


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


def _id_compte(dossier, identifiant):
    with _base(dossier) as cnx:
        return cnx.execute("SELECT id FROM _monl_users WHERE username = ?",
                           (identifiant,)).fetchone()[0]


# --------------------------------------------------------------------------
# Ce que la brique doit produire dans le contrat d'entrée
# --------------------------------------------------------------------------

def test_le_client_designe_la_commande_dans_le_corps(application):
    """La clé étrangère du parent propriétaire est FOURNIE par le client.

    C'est le renversement de la brique : en propriété directe, cette colonne
    est déduite du jeton et n'apparaît pas dans le schéma. Ici, sans elle, le
    client ne pourrait rattacher sa ligne à aucune commande."""
    base, _ = application
    schema = requests.get(f"{base}/openapi.json").json()
    champs = schema["components"]["schemas"]["LigneSchema"]["properties"]
    assert "commande_id" in champs
    assert "article_id" in champs
    # Composition avec la brique 10 : le montant reste calculé par le serveur.
    assert "sousTotal" not in champs


# --------------------------------------------------------------------------
# Le défaut du point 80, en test de non-régression
# --------------------------------------------------------------------------

def test_la_commande_stockee_est_celle_qui_a_ete_demandee(application, alice):
    """Le défaut exact du point 80 : le rattachement demandé était ignoré et
    remplacé par l'identifiant du compte appelant, en silence."""
    base, dossier = application
    commande = _commande(base, alice, "panier réel")
    article = _id_article(dossier, PRIX_CHER)
    reponse = _ligne(base, alice, commande, article, 2)
    assert reponse.status_code in (200, 201), reponse.text
    ligne_id = reponse.json()["id"]

    with _base(dossier) as cnx:
        stocke = cnx.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (ligne_id,)).fetchone()[0]
    compte = _id_compte(dossier, "alice")
    assert stocke == commande, "la commande désignée n'a pas été enregistrée"
    # L'assertion qui compte : les deux valeurs DIVERGENT, donc l'égalité
    # ci-dessus ne peut pas être un hasard.
    assert commande != compte, "identifiants confondus : le test ne prouve rien"
    assert stocke != compte


def test_le_montant_de_la_ligne_est_calcule_par_le_serveur(application, alice):
    """Composition brique 10 + brique 11 : neuf briques testées une par une ne
    testent pas leurs paires (leçon du point 78)."""
    base, dossier = application
    commande = _commande(base, alice, "calcul")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande, article, 3).json()["id"]
    detail = requests.get(f"{base}/ligne/{ligne_id}", headers=alice).json()
    assert detail["data"]["sousTotal"] == pytest.approx(PRIX_CHER * 3)


# --------------------------------------------------------------------------
# Écriture : rattacher une ligne à la commande d'autrui
# --------------------------------------------------------------------------

def test_rattacher_une_ligne_a_la_commande_d_autrui_est_refuse(application, alice, bob):
    """Sans cette vérification, la brique ouvrirait un trou plus large que
    celui qu'elle ferme : la clé étrangère n'est plus déduite du jeton."""
    base, dossier = application
    commande_alice = _commande(base, alice, "privée")
    article = _id_article(dossier, PRIX_CHER)
    reponse = _ligne(base, bob, commande_alice, article, 1)
    assert reponse.status_code == 403, reponse.text

    with _base(dossier) as cnx:
        compte = cnx.execute(
            'SELECT COUNT(*) FROM ligne WHERE commande_id = ?',
            (commande_alice,)).fetchone()[0]
    assert compte == 0, "la ligne a été écrite malgré le refus"


def test_une_commande_inexistante_donne_la_meme_reponse(application, bob):
    """Distinguer « n'existe pas » de « pas à vous » permettrait d'énumérer les
    commandes des autres — même raison que le 404 de la lecture détail."""
    base, dossier = application
    article = _id_article(dossier, PRIX_CHER)
    reponse = _ligne(base, bob, 99999, article, 1)
    assert reponse.status_code == 403, reponse.text


# --------------------------------------------------------------------------
# Lecture : la jointure filtre-t-elle vraiment ?
# --------------------------------------------------------------------------

def test_la_liste_ne_montre_que_ses_propres_lignes(application, alice, bob):
    base, dossier = application
    article = _id_article(dossier, PRIX_CHER)
    commande_alice = _commande(base, alice, "liste alice")
    ligne_alice = _ligne(base, alice, commande_alice, article, 1).json()["id"]
    commande_bob = _commande(base, bob, "liste bob")
    ligne_bob = _ligne(base, bob, commande_bob, article, 1).json()["id"]

    vues_bob = [ligne["id"] for ligne
                in requests.get(f"{base}/ligne", headers=bob).json()["data"]]
    assert ligne_bob in vues_bob
    assert ligne_alice not in vues_bob

    vues_alice = [ligne["id"] for ligne
                  in requests.get(f"{base}/ligne", headers=alice).json()["data"]]
    assert ligne_alice in vues_alice
    assert ligne_bob not in vues_alice


def test_le_detail_d_une_ligne_d_autrui_est_indiscernable_d_une_absence(
        application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "détail")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande, article, 1).json()["id"]

    assert requests.get(f"{base}/ligne/{ligne_id}",
                        headers=alice).status_code == 200
    refuse = requests.get(f"{base}/ligne/{ligne_id}", headers=bob)
    assert refuse.status_code == 404, refuse.text


# --------------------------------------------------------------------------
# Modification et suppression
# --------------------------------------------------------------------------

def test_modifier_la_ligne_d_autrui_est_refuse(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "put")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande, article, 1).json()["id"]

    refuse = requests.put(f"{base}/ligne/{ligne_id}", headers=bob,
                          json={"quantite": 50, "commande_id": commande,
                                "article_id": article})
    assert refuse.status_code == 403, refuse.text
    with _base(dossier) as cnx:
        quantite = cnx.execute('SELECT quantite FROM ligne WHERE id = ?',
                               (ligne_id,)).fetchone()[0]
    assert quantite == 1, "la ligne a été modifiée malgré le refus"


def test_supprimer_la_ligne_d_autrui_est_refuse(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "delete")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande, article, 1).json()["id"]

    refuse = requests.delete(f"{base}/ligne/{ligne_id}", headers=bob)
    assert refuse.status_code == 403, refuse.text
    with _base(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 1, "la ligne a été supprimée malgré le refus"


def test_le_proprietaire_modifie_et_supprime_sa_propre_ligne(application, alice):
    """Le pendant indispensable des trois refus ci-dessus : une brique qui
    refuse tout le monde passerait ces tests sans rien permettre."""
    base, dossier = application
    commande = _commande(base, alice, "à moi")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande, article, 1).json()["id"]

    modifie = requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                           json={"quantite": 4, "commande_id": commande,
                                 "article_id": article})
    assert modifie.status_code == 200, modifie.text
    detail = requests.get(f"{base}/ligne/{ligne_id}", headers=alice).json()
    assert detail["data"]["quantite"] == 4
    # Le montant suit la quantité : sinon la faille du point 77 se déplacerait
    # simplement du montant vers la quantité.
    assert detail["data"]["sousTotal"] == pytest.approx(PRIX_CHER * 4)

    assert requests.delete(f"{base}/ligne/{ligne_id}",
                           headers=alice).status_code == 200
    with _base(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 0


def test_deplacer_sa_ligne_vers_la_commande_d_autrui_est_impossible(
        application, alice, bob):
    """La route Update de monl n'écrit pas les clés étrangères. Ce test fige ce
    comportement : s'il changeait, un client pourrait déposer une ligne dans le
    panier d'un tiers en passant par la modification."""
    base, dossier = application
    commande_bob = _commande(base, bob, "cible")
    commande_alice = _commande(base, alice, "source")
    article = _id_article(dossier, PRIX_CHER)
    ligne_id = _ligne(base, alice, commande_alice, article, 1).json()["id"]

    requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                 json={"quantite": 2, "commande_id": commande_bob,
                       "article_id": article})
    with _base(dossier) as cnx:
        stocke = cnx.execute('SELECT commande_id FROM ligne WHERE id = ?',
                             (ligne_id,)).fetchone()[0]
    assert stocke == commande_alice
    assert requests.get(f"{base}/ligne/{ligne_id}",
                        headers=bob).status_code == 404
