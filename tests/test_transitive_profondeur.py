"""Brique 24 (propriété transitive à profondeur quelconque) — point 107.

La brique 11 (point 81) ne savait remonter qu'UN intermédiaire : une ligne
appartenait à sa commande, et la commande au client. Deux niveaux — une ligne
dans un bloc d'une commande — compilaient en filtrant sur le MAUVAIS maillon
(le défaut du point 80 rouvrait par la profondeur), donc le validateur les
refusait.

Cette brique étend la marche de la chaîne jusqu'à un ACTEUR, maillon par
maillon, quelle que soit la profondeur. Ce que ces tests exigent, et qu'une
relecture ne prouve pas :

* le validateur résout une chaîne de 2 et 3 maillons jusqu'au bon acteur ;
* un cycle, un cul-de-sac (aucun compte) et un maillon possédé par plusieurs
  entités sont REFUSÉS — la classe de défaut du point 80 ne reparaît pas par
  une profondeur ;
* sur un vrai serveur, la chaîne à 2 sauts filtre par la JOINTURE sur les
  quatre chemins (liste, détail, modification, suppression) et refuse de
  rattacher à un parent qui n'appartient pas à l'appelant.

Les identifiants sont volontairement DIVERGENTS (plusieurs commandes créées
avant les assertions), comme en brique 11.
"""

import contextlib
import os
import sqlite3
import tempfile

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server


def _validate(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


CADRE = """entity Commande
    libelle: String
entity Bloc
    note: String
entity Ligne
    quantite: Integer
relation Machin hasMany Ligne

"""

# ---------------------------------------------------------------------------
# Résolution de la chaîne — le cœur de la brique 24
# ---------------------------------------------------------------------------

def test_une_chaine_a_deux_maillons_est_resolue():
    spec = """app P2
""" + CADRE + """relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne
actor Client selfRegister
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client
rule Bloc.Read ownedBy Commande
rule Bloc.Update ownedBy Commande
rule Bloc.Delete ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc
workflow W for Client
    Create Commande
    Create Bloc
    Create Ligne
    Read Commande
    Read Bloc
    Read Ligne
    Update Commande
    Update Bloc
    Update Ligne
    Delete Commande
    Delete Bloc
    Delete Ligne
"""
    ast = _validate(spec)
    transitif = ast["security"]["transitive_ownership"]
    # La brique 11 (un saut) reste LA MÊME forme.
    assert transitif["Bloc"] == {"chain": ["Commande"], "actor": "Client"}
    # La brique 24 remonte toute la profondeur jusqu'à l'acteur.
    assert transitif["Ligne"] == {"chain": ["Bloc", "Commande"], "actor": "Client"}


def test_une_chaine_a_trois_maillons_est_resolue():
    spec = """app P3
entity Commande
    libelle: String
entity Palette
    ref: String
entity Carton
    ref: String
entity Bloc
    note: String
entity Ligne
    quantite: Integer
relation Client hasMany Commande
relation Commande hasMany Palette
relation Palette hasMany Carton
relation Carton hasMany Bloc
relation Bloc hasMany Ligne
actor Client selfRegister
rule Commande.Read ownedBy Client
rule Palette.Read ownedBy Commande
rule Carton.Read ownedBy Palette
rule Bloc.Read ownedBy Carton
rule Ligne.Read ownedBy Bloc
workflow W for Client
    Create Commande
    Create Palette
    Create Carton
    Create Bloc
    Create Ligne
    Read Commande
    Read Palette
    Read Carton
    Read Bloc
    Read Ligne
"""
    ast = _validate(spec)
    transitif = ast["security"]["transitive_ownership"]
    assert transitif["Ligne"] == {"chain": ["Bloc", "Carton", "Palette", "Commande"],
                                  "actor": "Client"}


def test_un_cycle_est_refuse():
    spec = """app Cyc
entity C1
    champ: Integer
entity C2
    champ: Integer
relation C1 hasMany C2
relation C2 hasMany C1
actor A selfRegister
rule C1.Read ownedBy C2
rule C2.Read ownedBy C1
workflow W for A
    Read C1
    Read C2
"""
    with pytest.raises(ASTValidationError, match="boucle"):
        _validate(spec)


def test_une_chaine_qui_n_aboutit_a_aucun_compte_est_refusee():
    spec = """app SansCompte
entity D1
    champ: Integer
entity D2
    champ: Integer
relation D2 hasMany D1
actor A selfRegister
rule D1.Read ownedBy D2
workflow W for A
    Read D1
"""
    with pytest.raises(ASTValidationError, match=r"aucun acteur|AUCUN acteur"):
        _validate(spec)


def test_un_maillon_possede_par_plusieurs_entites_est_ambigu():
    spec = """app Ambigu
entity X1
    champ: Integer
entity X2
    champ: Integer
entity A2
    champ: Integer
entity A3
    champ: Integer
relation X2 hasMany X1
relation A2 hasMany X2
relation A3 hasMany X2
actor A selfRegister
rule X1.Read ownedBy X2
rule X2.Read ownedBy A2
rule X2.Delete ownedBy A3
workflow W for A
    Read X1
    Read X2
    Delete X2
"""
    with pytest.raises(ASTValidationError, match="ambigu"):
        _validate(spec)



# ---------------------------------------------------------------------------
# E2E sur un vrai serveur : une chaîne à DEUX sauts
#   Ligne -> Bloc -> Commande -> Client
# ---------------------------------------------------------------------------

SPEC = """app Profondeur

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String

entity Bloc
    note: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne
relation Article hasMany Ligne

actor Admin
actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.Delete ownedBy Client
rule Bloc.Read ownedBy Commande
rule Bloc.Update ownedBy Commande
rule Bloc.Delete ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc

workflow GererArticle for Admin
    Create Article
    Read Article

workflow Acheter for Client
    Read Article
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
    Create Bloc
    Read Bloc
    Update Bloc
    Delete Bloc
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

MOT_DE_PASSE = "motdepasse123"
PRIX = 42.5


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
                            ("Article test", PRIX))
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
    entetes = _entetes(application, "alice_prof")
    base, _ = application
    # Plusieurs commandes ET blocs AVANT toute assertion : ni les identifiants
    # de commande ni ceux de bloc ne coïncident alors avec ceux des comptes
    # (leçon du point 80 — un maillon confondu avec un compte masquerait le
    # bug qu'on cherche à départager en profondeur 2).
    dernier = None
    for libelle in ("brouillon", "abandonnée", "en cours"):
        dernier = _commande(base, entetes, libelle)
    for _ in range(3):
        _bloc(base, entetes, dernier)
    return entetes


@pytest.fixture(scope="module")
def bob(application):
    return _entetes(application, "bob_prof")


def _commande(base, entetes, libelle):
    r = requests.post(f"{base}/commande", headers=entetes,
                      json={"libelle": libelle})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _bloc(base, entetes, commande_id):
    r = requests.post(f"{base}/bloc", headers=entetes,
                      json={"note": "bloc", "commande_id": commande_id})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _ligne(base, entetes, bloc_id, article_id, quantite):
    return requests.post(f"{base}/ligne", headers=entetes,
                         json={"bloc_id": bloc_id, "article_id": article_id,
                               "quantite": quantite})


def _id_article(dossier):
    with _base(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (PRIX,)).fetchone()[0]


def _id_compte(dossier, identifiant):
    with _base(dossier) as cnx:
        return cnx.execute("SELECT id FROM _monl_users WHERE username = ?",
                           (identifiant,)).fetchone()[0]


# ---------------------------------------------------------------------------
# La profondeur ouvre le schéma comme la profondeur 1 l'avait fait
# ---------------------------------------------------------------------------

def test_les_cles_etrangeres_de_la_chaine_sont_dans_le_schema(application):
    base, _ = application
    schema = requests.get(f"{base}/openapi.json").json()
    bloc = schema["components"]["schemas"]["BlocSchema"]["properties"]
    ligne = schema["components"]["schemas"]["LigneSchema"]["properties"]
    assert "commande_id" in bloc       # Bloc -> Commande
    assert "bloc_id" in ligne          # Ligne -> Bloc (le parent propriétaire)
    assert "article_id" in ligne       # la simple relation, elle aussi


# ---------------------------------------------------------------------------
# Le défaut du point 80, transposé à la profondeur 2
# ---------------------------------------------------------------------------

def test_le_maillon_stocke_est_celui_qui_a_ete_demande(application, alice):
    base, dossier = application
    commande = _commande(base, alice, "panier profond")
    bloc = _bloc(base, alice, commande)
    article = _id_article(dossier)
    reponse = _ligne(base, alice, bloc, article, 2)
    assert reponse.status_code in (200, 201), reponse.text
    ligne_id = reponse.json()["id"]

    with _base(dossier) as cnx:
        stocke = cnx.execute('SELECT bloc_id FROM ligne WHERE id = ?',
                             (ligne_id,)).fetchone()[0]
    compte = _id_compte(dossier, "alice_prof")
    assert stocke == bloc, "le maillon désigné n'a pas été enregistré"
    assert bloc != compte and stocke != compte, "maillon et compte confondus"


# ---------------------------------------------------------------------------
# Refus croisés : l'appelant ne touche pas à la ligne d'un autre client
# ---------------------------------------------------------------------------

def test_lire_la_ligne_d_autrui_repond_404(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "lire")
    bloc = _bloc(base, alice, commande)
    ligne_id = _ligne(base, alice, bloc, _id_article(dossier), 1).json()["id"]
    assert requests.get(f"{base}/ligne/{ligne_id}",
                        headers=bob).status_code == 404


def test_creer_dans_le_bloc_d_autrui_est_refuse(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "créer")
    bloc = _bloc(base, alice, commande)
    reponse = _ligne(base, bob, bloc, _id_article(dossier), 1)
    assert reponse.status_code == 403, reponse.text


def test_modifier_la_ligne_d_autrui_est_refuse(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "modifier")
    bloc = _bloc(base, alice, commande)
    ligne_id = _ligne(base, alice, bloc, _id_article(dossier), 1).json()["id"]
    refuse = requests.put(f"{base}/ligne/{ligne_id}", headers=bob,
                          json={"quantite": 50, "bloc_id": bloc,
                                "article_id": _id_article(dossier)})
    assert refuse.status_code == 403, refuse.text
    with _base(dossier) as cnx:
        quantite = cnx.execute('SELECT quantite FROM ligne WHERE id = ?',
                               (ligne_id,)).fetchone()[0]
    assert quantite == 1, "la ligne a été modifiée malgré le refus"


def test_supprimer_la_ligne_d_autrui_est_refuse(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "supprimer")
    bloc = _bloc(base, alice, commande)
    ligne_id = _ligne(base, alice, bloc, _id_article(dossier), 1).json()["id"]
    refuse = requests.delete(f"{base}/ligne/{ligne_id}", headers=bob)
    assert refuse.status_code == 403, refuse.text
    with _base(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 1, "la ligne a été supprimée malgré le refus"


def test_le_proprietaire_modifie_et_supprime_sa_ligne(application, alice):
    base, dossier = application
    commande = _commande(base, alice, "à moi")
    bloc = _bloc(base, alice, commande)
    ligne_id = _ligne(base, alice, bloc, _id_article(dossier), 1).json()["id"]

    modifie = requests.put(f"{base}/ligne/{ligne_id}", headers=alice,
                           json={"quantite": 4, "bloc_id": bloc,
                                 "article_id": _id_article(dossier)})
    assert modifie.status_code == 200, modifie.text
    detail = requests.get(f"{base}/ligne/{ligne_id}", headers=alice).json()
    assert detail["data"]["quantite"] == 4

    assert requests.delete(f"{base}/ligne/{ligne_id}",
                           headers=alice).status_code == 200
    with _base(dossier) as cnx:
        reste = cnx.execute('SELECT COUNT(*) FROM ligne WHERE id = ?',
                            (ligne_id,)).fetchone()[0]
    assert reste == 0


def test_la_liste_ne_montre_que_les_lignes_du_client(application, alice, bob):
    base, dossier = application
    commande = _commande(base, alice, "liste")
    bloc = _bloc(base, alice, commande)
    article = _id_article(dossier)
    ids_alice = {_ligne(base, alice, bloc, article, 1).json()["id"] for _ in range(2)}

    commande_bob = _commande(base, bob, "liste bob")
    bloc_bob = _bloc(base, bob, commande_bob)
    _ligne(base, bob, bloc_bob, article, 1)

    liste = requests.get(f"{base}/ligne", headers=alice).json()
    vus = {ligne["id"] for ligne in liste["data"]}
    assert ids_alice.issubset(vus)
    assert all(ligne["id"] not in vus
               for ligne in requests.get(f"{base}/ligne", headers=bob).json()["data"])
