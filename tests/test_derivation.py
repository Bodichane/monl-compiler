"""Brique 10 (`derivedFrom`) éprouvée contre un vrai serveur — point 77.

Pourquoi ce fichier existe. `payable` (point 74) promet que le montant encaissé
vient de la BASE et jamais du corps de requête. C'est vrai, et ça ne protégeait
rien : personne n'avait demandé **qui écrit le montant en base**. La réponse
était le client, par deux chemins — la création, et la modification (le
propriétaire a le droit de faire un `PUT`). Deux exploits de trois requêtes,
qu'aucun des 24 tests de `test_paiement.py` ne couvrait : ils vérifiaient que la
ROUTE ignore le corps qu'on lui donne, sans jamais remonter à la source de la
valeur qu'elle relit.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :

* le montant envoyé par le client est **ignoré**, à la création comme à la
  modification (le champ n'existe pas dans le schéma Pydantic) ;
* le montant **suit** la quantité : sans recalcul au `PUT`, la faille se
  déplacerait simplement du montant vers la quantité (créer à 1, modifier à 5) ;
* le montant est calculé sur la ligne liée **stockée**, jamais sur celle que le
  corps déclare. Les deux sens ont été essayés : calculer depuis `data.<fk>`
  laissait un client facturer 89 € un article à 189 € en déclarant un article
  bon marché qu'il ne pointait pas. C'est le seul défaut de la brique que
  l'exécution a trouvé et que la relecture avait laissé passer.
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

SPEC = """app BancDerivation

entity Article
    nom: String
    prix: Money

entity Commande
    quantite: Integer
    total: Money
    libelle: String

entity Client
    displayName: String

relation Client hasMany Commande
relation Article hasMany Commande
relation Client hasMany Client

actor Admin
actor Client selfRegister

rule Commande.quantite required
rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client

rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total payable

workflow GererArticle for Admin
    Create Article
    Read Article
    Update Article

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande

workflow Profil for Client
    Create Client
    Read Client
"""

MOT_DE_PASSE = "motdepasse123"
PRIX_CHER, PRIX_BON_MARCHE = 189.0, 89.0


@contextlib.contextmanager
def _base(dossier):
    # Comme dans test_briques_comportement.py : `with connect(...)` valide la
    # transaction mais ne FERME pas — d'où les ResourceWarning du banc d'essai.
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
            # Deux articles de prix différents : le témoin voisin est ce qui
            # permet d'affirmer que le bon a été lu (leçon du point 70, où un
            # compteur décrémentait le mauvais enregistrement).
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


def _id_article_cher(dossier):
    with _base(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (PRIX_CHER,)).fetchone()[0]


def _id_article_bon_marche(dossier):
    with _base(dossier) as cnx:
        return cnx.execute('SELECT id FROM article WHERE prix = ?',
                           (PRIX_BON_MARCHE,)).fetchone()[0]


def _commande(base, entetes, corps):
    reponse = requests.post(f"{base}/commande", headers=entetes, json=corps)
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _lire(base, entetes, identifiant):
    detail = requests.get(f"{base}/commande/{identifiant}",
                          headers=entetes).json()
    return detail.get("data", detail)


# ---------------------------------------------------- le champ n'est pas là --

def test_le_champ_calcule_est_absent_du_schema_d_entree(application):
    """Le contrat de la brique commence là : le client ne peut pas même TENTER
    de fournir le montant. C'est la même mécanique que `generated` (brique 7),
    et le schéma Pydantic est partagé entre création et modification — c'est ce
    qui ferme les deux chemins d'un coup."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()
    champs = schema["components"]["schemas"]["CommandeSchema"]["properties"]
    assert "total" not in champs, champs
    # Le multiplicateur et la référence de l'article, eux, viennent du client.
    assert "quantite" in champs and "article_id" in champs


# ------------------------------------------------------------- la création --

def test_le_total_envoye_a_la_creation_est_ignore(application):
    """L'exploit d'origine, rejoué : 5 articles à 189 € commandés en déclarant
    un total de 1 centime. Avant la brique, la base retenait 0.01 et `payable`
    encaissait un centime pour 945 € de marchandise."""
    base, dossier = application
    entetes = _entetes(application, "cree_ignore")
    identifiant = _commande(base, entetes, {
        "quantite": 5, "article_id": _id_article_cher(dossier),
        "libelle": "5x cher", "total": 0.01})
    assert _lire(base, entetes, identifiant)["total"] == PRIX_CHER * 5


def test_le_total_est_calcule_sur_le_bon_article(application):
    """Le témoin voisin : deux articles de prix différents existent, et c'est
    celui que le client a désigné qui doit être lu. Un défaut de clé étrangère
    donnerait un montant plausible mais faux — exactement le bug que CLAUDE.md
    cite comme invisible à la relecture."""
    base, dossier = application
    entetes = _entetes(application, "cree_bon_article")
    identifiant = _commande(base, entetes, {
        "quantite": 2, "article_id": _id_article_bon_marche(dossier),
        "libelle": "2x bon marché"})
    assert _lire(base, entetes, identifiant)["total"] == PRIX_BON_MARCHE * 2


def test_une_quantite_nulle_ou_negative_est_refusee(application):
    """Un montant nul n'est pas encaissable (`payable` le refuse déjà en 400) ;
    le refuser ici évite d'écrire en base une commande qui ne pourra jamais
    être réglée. La quantité négative, elle, produirait un montant négatif."""
    base, dossier = application
    entetes = _entetes(application, "quantite_nulle")
    article = _id_article_cher(dossier)
    for quantite in (0, -3):
        reponse = requests.post(f"{base}/commande", headers=entetes, json={
            "quantite": quantite, "article_id": article, "libelle": "vide"})
        assert reponse.status_code == 400, (quantite, reponse.text)


def test_un_article_inexistant_donne_409_et_ne_cree_rien(application):
    """Le 409 vaut mieux qu'un montant faux : une référence bidon doit arrêter
    la commande, pas la créer à zéro euro — donc gratuite."""
    base, dossier = application
    entetes = _entetes(application, "article_absent")
    with _base(dossier) as cnx:
        avant = cnx.execute("SELECT COUNT(*) FROM commande").fetchone()[0]
    reponse = requests.post(f"{base}/commande", headers=entetes, json={
        "quantite": 1, "article_id": 999999, "libelle": "fantôme"})
    assert reponse.status_code == 409, reponse.text
    with _base(dossier) as cnx:
        assert cnx.execute("SELECT COUNT(*) FROM commande").fetchone()[0] == avant


# --------------------------------------------------------- la modification --

def test_le_total_envoye_a_la_modification_est_ignore(application):
    """Le SECOND exploit, celui que corriger la création seule aurait laissé
    entier : une commande honnête, puis un `PUT` qui réécrit le montant.
    `ownedBy` donne bien ce droit au propriétaire — c'est son rôle — donc la
    protection ne peut pas venir du contrôle d'accès."""
    base, dossier = application
    entetes = _entetes(application, "put_ignore")
    article = _id_article_cher(dossier)
    identifiant = _commande(base, entetes, {
        "quantite": 1, "article_id": article, "libelle": "1x cher"})
    assert _lire(base, entetes, identifiant)["total"] == PRIX_CHER

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                           json={"quantite": 1, "article_id": article,
                                 "libelle": "1x cher", "total": 0.01})
    assert reponse.status_code == 200, reponse.text
    assert _lire(base, entetes, identifiant)["total"] == PRIX_CHER


def test_le_total_suit_la_quantite_modifiee(application):
    """Sans recalcul au `PUT`, la faille se déplacerait du montant vers la
    quantité : créer à 1 puis modifier à 5 donnerait cinq articles au prix d'un.
    Le montant doit donc SUIVRE, dans les deux sens."""
    base, dossier = application
    entetes = _entetes(application, "put_quantite")
    article = _id_article_cher(dossier)
    identifiant = _commande(base, entetes, {
        "quantite": 1, "article_id": article, "libelle": "1x"})

    for quantite in (5, 2):
        reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                               json={"quantite": quantite, "article_id": article,
                                     "libelle": f"{quantite}x"})
        assert reponse.status_code == 200, reponse.text
        assert _lire(base, entetes, identifiant)["total"] == PRIX_CHER * quantite


def test_declarer_un_autre_article_au_put_ne_baisse_pas_le_total(application):
    """Le défaut trouvé en éprouvant la brique, et le seul que la relecture
    avait laissé passer. La route `Update` de monl n'écrit PAS les colonnes de
    clé étrangère : la FK en base reste donc la seule vérité sur « quel
    article ». Une version intermédiaire calculait depuis `data.article_id` —
    un client facturait alors 89 € un article à 189 € en déclarant un article
    bon marché qu'il ne pointait pas."""
    base, dossier = application
    entetes = _entetes(application, "put_autre_article")
    cher, bon_marche = _id_article_cher(dossier), _id_article_bon_marche(dossier)
    identifiant = _commande(base, entetes, {
        "quantite": 1, "article_id": cher, "libelle": "1x cher"})

    reponse = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                           json={"quantite": 1, "article_id": bon_marche,
                                 "libelle": "1x cher"})
    assert reponse.status_code == 200, reponse.text
    ligne = _lire(base, entetes, identifiant)
    assert ligne["total"] == PRIX_CHER, (
        "le montant a suivi l'article DÉCLARÉ au lieu de l'article stocké")
    assert ligne["article_id"] == cher


# ------------------------------------------- ce que la brique rend à payable --

def test_le_montant_encaisse_est_desormais_celui_du_catalogue(application):
    """La boucle est fermée : `payable` relit en base un montant que le client
    n'a jamais pu écrire. Sans clé Stripe la route répond 503 (point 74), donc
    c'est la valeur EN BASE qu'on vérifie — c'est elle que la route relirait."""
    base, dossier = application
    entetes = _entetes(application, "encaisse")
    identifiant = _commande(base, entetes, {
        "quantite": 3, "article_id": _id_article_cher(dossier),
        "libelle": "3x cher", "total": 0.01})
    with _base(dossier) as cnx:
        en_base = cnx.execute('SELECT total, payment_status FROM commande '
                              'WHERE id = ?', (identifiant,)).fetchone()
    assert en_base[0] == PRIX_CHER * 3
    assert en_base[1] == "en_attente"
    # Et la route de règlement existe bien, sans clé configurée : 503.
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes)
    assert reponse.status_code == 503, reponse.text
    assert "STRIPE_SECRET_KEY" in reponse.text
