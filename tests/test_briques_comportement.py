"""Briques 3, 4, 5 et 7 éprouvées contre un vrai serveur.

Sur les huit briques de l'écosystème de capacités, trois seulement étaient
exercées contre un serveur réel : `accessibleBy` (test_access_parties.py), le
filtrage de lecture d'`ownedBy` (test_lecture_privee.py) et `hidden`
(test_masquage_hidden.py, point 64). Les autres n'avaient que la couverture de
COMPILATION apportée par `exemples/03_reseau_social.ml` — or CLAUDE.md le dit
sans détour : compiler n'est pas se comporter correctement.

Ce fichier ferme l'écart pour les quatre briques dont la promesse est
comportementale, et qui portent chacune une garantie qu'une relecture ne
prouve pas :

* `generated` (brique 7) — le pseudonyme ne doit pas être forgeable depuis le
  corps de requête. C'est la seule des quatre dont un défaut est une faille
  d'intégrité et pas un affichage faux.
* `increments` / `decrements` (briques 3 et 4) — le compteur doit bouger, du
  montant déclaré, et sur le BON enregistrement. CLAUDE.md liste précisément
  « un mécanisme de clé étrangère qui décrémentait le mauvais enregistrement »
  parmi les bugs qui ne se sont jamais révélés à la lecture ; un témoin voisin
  l'attrape ici.
* `categorized` (brique 5) — la valeur numérique doit être remplacée, pas
  doublée, y compris à la borne exacte (`below N` est strict), et rester en
  base.

La spec assemble les quatre dans les rôles qu'elles occupent dans
`exemples/03_reseau_social.ml`, en réduit : c'est cet assemblage qui avait
révélé deux bugs réels au point 29, pas les briques prises isolément.
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

SPEC_BANC = """app BancEssai

entity Member
    name: String
    reputation: Integer

entity Post
    content: Text
    author: String
    likes: Integer

entity Like
    note: String

entity Report
    reason: String

relation Member hasMany Post
relation Post hasMany Like
relation Member hasMany Report

actor Member selfRegister

rule Post.Read public
rule Post.author generated
rule Post.likes categorized: "discret" below 10, "populaire" below 100, "viral" otherwise
rule Like.Create increments Post.likes by 1
rule Report.Create decrements Member.reputation by 10

workflow Inscrire for Member
    Create Member
    Read Member

workflow Publier for Member
    Create Post
    Read Post

workflow Reagir for Member
    Create Like
    Create Report
"""

MOT_DE_PASSE = "motdepasse123"


@pytest.fixture(scope="module")
def application():
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_BANC)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        with uvicorn_server(dossier) as base:
            yield base, dossier


@contextlib.contextmanager
def _base(dossier):
    """Ouvre app.db en validant ET en fermant à la sortie.

    `with sqlite3.connect(...)` seul ne ferme PAS la connexion — il ne fait que
    valider ou annuler la transaction. C'est le piège qui laissait la suite
    émettre des ResourceWarning ; les fermetures se faisaient à la merci du
    ramasse-miettes. Le code produit, lui, ferme explicitement (voir
    generator/runtime.py) : la fuite n'a jamais concerné que le banc d'essai.
    """
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


def _vider_quota(dossier):
    """Efface le compteur de tentatives (5 / 60 s / IP, points 13 et 33).

    Même geste qu'au point 67, pour la même raison : ce fichier ouvre un
    compte par test afin que les tests ne s'ordonnent pas implicitement les
    uns les autres, ce qui dépasse le quota. Vider une table de compteurs côté
    banc d'essai n'affaiblit rien du produit — desserrer le quota lui-même,
    si.
    """
    with _base(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")


def _entetes(application, identifiant):
    """Inscrit un compte et renvoie ses en-têtes d'authentification.

    Chaque test emploie ses propres identifiants : la base vit le temps du
    module, et des tests qui se partagent un compte s'ordonnent implicitement
    les uns les autres.
    """
    base, dossier = application
    _vider_quota(dossier)
    requests.post(f"{base}/register",
                  json={"username": identifiant, "password": MOT_DE_PASSE,
                        "actor": "Member"})
    jeton = requests.post(f"{base}/login",
                          json={"username": identifiant,
                                "password": MOT_DE_PASSE}).json()
    assert "access_token" in jeton, jeton
    return {"Authorization": "Bearer " + jeton["access_token"]}


def _cree(base, chemin, entetes, corps):
    reponse = requests.post(f"{base}/{chemin}", headers=entetes, json=corps)
    assert reponse.status_code in (200, 201), reponse.text
    identifiant = reponse.json().get("id")
    assert identifiant, reponse.text
    return identifiant


def _post(base, identifiant):
    detail = requests.get(f"{base}/post/{identifiant}").json()
    return detail.get("data", detail)


# --------------------------------------------------- brique 7 : generated --
def test_le_champ_generated_ne_peut_pas_etre_forge_par_le_client(application):
    """La promesse du point 30 : l'auteur vient du compte, jamais du corps de
    requête. Un client qui envoie quand même le champ ne doit pas voir sa
    valeur atterrir en base — sans quoi `generated` ne serait qu'une
    convention d'affichage."""
    base, dossier = application
    entetes = _entetes(application, "forgeuse")

    identifiant = _cree(base, "post", entetes,
                        {"content": "coucou", "author": "Administration",
                         "likes": 0})

    corps = _post(base, identifiant)
    assert corps["author"] != "Administration", (
        f"l'auteur fourni par le client a été retenu : {corps}")
    assert corps["author"].startswith("Anon#"), corps

    # Et pas seulement à l'affichage : la valeur forgée n'est pas non plus
    # en base, où un autre lecteur (export, requête directe) la trouverait.
    with _base(dossier) as cnx:
        en_base = cnx.execute("SELECT author FROM post WHERE id = ?",
                              (identifiant,)).fetchone()
    assert en_base and en_base[0] == corps["author"], en_base


def test_le_pseudonyme_est_stable_par_compte_et_distinct_entre_comptes(application):
    """« Stable par compte » est la moitié de la promesse qu'une seule
    création ne peut pas vérifier : deux posts du même compte, séparés par une
    reconnexion, doivent porter le même pseudonyme — et celui d'un autre
    compte doit en différer."""
    base, _dossier = application
    entetes = _entetes(application, "stable")

    premier = _cree(base, "post", entetes, {"content": "un", "likes": 0})
    second = _cree(base, "post", entetes, {"content": "deux", "likes": 0})
    assert _post(base, premier)["author"] == _post(base, second)["author"]

    # Reconnexion : le pseudonyme est fixé à l'inscription, pas tiré à chaque
    # session — un tirage par connexion casserait le fil d'un même auteur.
    rejeton = requests.post(f"{base}/login",
                            json={"username": "stable",
                                  "password": MOT_DE_PASSE}).json()
    apres = _cree(base, "post",
                  {"Authorization": "Bearer " + rejeton["access_token"]},
                  {"content": "trois", "likes": 0})
    assert _post(base, apres)["author"] == _post(base, premier)["author"]

    autre = _entetes(application, "voisine")
    ailleurs = _cree(base, "post", autre, {"content": "quatre", "likes": 0})
    assert _post(base, ailleurs)["author"] != _post(base, premier)["author"]


def test_le_champ_generated_est_absent_du_schema_de_creation(application):
    """Le contrat public dit la même chose que le serveur : le modèle d'entrée
    de la création n'expose pas le champ, alors qu'il expose ses voisins.

    On interroge le composant réellement référencé par la requête plutôt que
    le texte de la route : `author` absent d'une chaîne prouverait aussi bien
    que le champ a disparu qu'il n'a jamais été cherché au bon endroit. Les
    routes de LECTURE, elles, ne déclarent aucun `response_model` — leur
    contenu se vérifie contre le serveur (tests ci-dessus), pas dans OpenAPI.
    """
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()

    reference = schema["paths"]["/post"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["$ref"]
    modele = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    proprietes = modele["properties"]
    assert "content" in proprietes and "likes" in proprietes, proprietes
    assert "author" not in proprietes, (
        f"le champ 'generated' est proposé en entrée : {proprietes}")


# ----------------------------------- briques 3 et 4 : compteurs transactionnels --
def test_increments_touche_le_bon_enregistrement_et_lui_seul(application):
    """Le témoin voisin est l'objet du test. Un compteur qui monte prouve
    seulement qu'un UPDATE a eu lieu ; c'est le post NON visé, resté à sa
    valeur, qui prouve que la clé étrangère désigne le bon."""
    base, dossier = application
    entetes = _entetes(application, "likeuse")

    vise = _cree(base, "post", entetes, {"content": "visé", "likes": 41})
    temoin = _cree(base, "post", entetes, {"content": "témoin", "likes": 41})

    _cree(base, "like", entetes, {"note": "bravo", "post_id": vise})

    with _base(dossier) as cnx:
        valeurs = dict(cnx.execute(
            "SELECT id, likes FROM post WHERE id IN (?, ?)", (vise, temoin)))
    assert valeurs[vise] == 42, valeurs
    assert valeurs[temoin] == 41, f"le voisin a bougé : {valeurs}"


def test_decrements_retire_le_montant_declare_a_la_cible(application):
    """`by 10` doit retirer 10, pas 1 : le montant est déclaré dans la spec et
    c'est le générateur qui l'inscrit dans l'UPDATE."""
    base, _dossier = application
    entetes = _entetes(application, "signaleuse")

    membre = _cree(base, "member", entetes, {"name": "cible", "reputation": 100})
    temoin = _cree(base, "member", entetes, {"name": "témoin", "reputation": 100})

    _cree(base, "report", entetes, {"reason": "spam", "member_id": membre})

    lu = requests.get(f"{base}/member/{membre}", headers=entetes).json()
    assert lu["data"]["reputation"] == 90, lu
    intact = requests.get(f"{base}/member/{temoin}", headers=entetes).json()
    assert intact["data"]["reputation"] == 100, intact


def test_une_cible_inexistante_annule_toute_la_creation(application):
    """Atomicité (bêta 1) : création et effet de compteur tiennent dans une
    seule transaction. Une clé étrangère qui ne pointe sur rien est refusée en
    409 — et l'enregistrement déclencheur ne doit PAS subsister, sinon la base
    garderait un like orphelin dont le compteur n'a jamais bougé."""
    base, dossier = application
    entetes = _entetes(application, "fantome")

    with _base(dossier) as cnx:
        avant = cnx.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]

    refus = requests.post(f"{base}/like", headers=entetes,
                          json={"note": "sur du vide", "post_id": 999_999})
    assert refus.status_code == 409, refus.text

    with _base(dossier) as cnx:
        apres = cnx.execute('SELECT COUNT(*) FROM "like"').fetchone()[0]
        orphelin = cnx.execute(
            'SELECT COUNT(*) FROM "like" WHERE note = ?', ("sur du vide",)
        ).fetchone()[0]
    assert apres == avant, f"{apres - avant} ligne(s) laissée(s) par un refus"
    assert orphelin == 0


# ------------------------------------------------- brique 5 : categorized --
def test_categorized_remplace_la_valeur_en_liste_et_en_detail(application):
    """Substitution, pas addition : la valeur exacte disparaît des deux routes
    de lecture. La laisser à côté du libellé rendrait la brique inutile — son
    objet est justement de ne pas publier le score."""
    base, _dossier = application
    entetes = _entetes(application, "categorisee")

    identifiant = _cree(base, "post", entetes, {"content": "chiffres", "likes": 137})

    detail = _post(base, identifiant)
    assert detail["likes_category"] == "viral", detail
    assert "likes" not in detail, f"la valeur exacte fuit en détail : {detail}"

    ligne = next(r for r in requests.get(f"{base}/post").json()["data"]
                 if r["id"] == identifiant)
    assert ligne["likes_category"] == "viral", ligne
    assert "likes" not in ligne, f"la valeur exacte fuit en liste : {ligne}"


def test_categorized_traite_below_comme_une_borne_stricte(application):
    """`below 10` exclut 10. La borne est le seul endroit où une chaîne
    if/elif générée peut se décaler d'un cran sans que rien ne le signale ;
    9, 10 et 100 l'encadrent des deux côtés."""
    base, _dossier = application
    entetes = _entetes(application, "bornes")

    attendus = {9: "discret", 10: "populaire", 99: "populaire", 100: "viral"}
    for valeur, libelle in attendus.items():
        identifiant = _cree(base, "post", entetes,
                            {"content": f"likes={valeur}", "likes": valeur})
        assert _post(base, identifiant)["likes_category"] == libelle, (
            f"{valeur} classé {_post(base, identifiant)['likes_category']}, "
            f"attendu {libelle}")


def test_categorized_ne_touche_pas_a_la_valeur_stockee(application):
    """Comme `hidden`, la brique agit à la lecture : le nombre reste en base,
    intact — c'est lui que `increments` continue de faire monter."""
    base, dossier = application
    entetes = _entetes(application, "stockage")

    identifiant = _cree(base, "post", entetes, {"content": "en base", "likes": 137})

    with _base(dossier) as cnx:
        stocke = cnx.execute("SELECT likes FROM post WHERE id = ?",
                             (identifiant,)).fetchone()
    assert stocke and stocke[0] == 137, stocke
