"""Un champ obligatoire né du DIALOGUE refuse aussi la chaîne VIDE.

`required` dit qu'un champ est PRÉSENT dans le corps de requête, jamais qu'il
est REMPLI — c'est le point 85 lu à la lettre, et personne ne l'avait lu ainsi
depuis le dialogue guidé. Mesuré sur une archive téléchargée par le
mainteneur : une fiche de catalogue au titre `""` entrait en base en 200, et
le site affichait une carte sans nom.

Ce banc part du CHEMIN USAGER — les réponses au dialogue, la spec qui en sort,
le serveur qu'elle produit — et il vérifie les DEUX sens : la chaîne vide est
refusée, et ce qui est légitime passe encore. Un instrument qui refuse tout
est aussi inutile qu'un instrument qui accepte tout, et il a l'air plus
sérieux (point 168).
"""

import contextlib
import io
import os
from tempfile import TemporaryDirectory

import pytest
import requests

from monl.app_templates import TEMPLATES
from monl.ast_validator import MonlAST
from monl.ast_validator.champs import ChampsMixin
from monl.dialogue_engine.emission_parts import TYPES_TEXTE, emit_base_rules
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server
from tests.test_app_templates import _run_template

#: Le modèle « Boutique en ligne » porte les DEUX cas dans une seule spec :
#: `Customer.displayName` est du texte (borné), `Order.total` est un nombre
#: (jamais borné). Un seul serveur suffit donc à éprouver la règle et sa
#: limite.
BOUTIQUE = next(i for i, t in enumerate(TEMPLATES, 1)
                if t["name"] == "Boutique en ligne")


def _spec(index, reponse="n", seed=False):
    with contextlib.redirect_stdout(io.StringIO()):
        return _run_template(index, reponse, want_seed=seed)


def _premiers_champs(index, reponse, seed):
    """Le PREMIER champ de chaque entité, avec son type — c'est lui que le
    dialogue rend obligatoire (`emit_base_rules`)."""
    with contextlib.redirect_stdout(io.StringIO()):
        spec = _run_template(index, reponse, want_seed=seed)
        ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
    regles = {ligne.strip() for ligne in spec.splitlines()}
    premiers = {}
    for nom, champs in ast["schema"]["entities"].items():
        if champs:
            premier = next(iter(champs))
            premiers[(nom, premier)] = champs[premier]
    return spec, regles, premiers


@pytest.fixture(scope="module")
def boutique():
    """Compile ce que le dialogue produit pour la boutique, et le fait tourner."""
    spec = _spec(BOUTIQUE)
    with TemporaryDirectory(prefix="monl-texte-non-vide-") as dossier:
        with contextlib.redirect_stdout(io.StringIO()):
            ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
            MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        env = os.environ.copy()
        env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "texte-non-vide-secret-de-32-octets-au-moins"
        with uvicorn_server(dossier, env=env) as base:
            yield base


@pytest.fixture(scope="module")
def entete(boutique):
    inscription = requests.post(
        f"{boutique}/register",
        json={"username": "acheteuse", "password": "motdepasse8",
              "actor": "Customer"}, timeout=10)
    assert inscription.status_code == 200, inscription.text
    connexion = requests.post(
        f"{boutique}/login",
        json={"username": "acheteuse", "password": "motdepasse8"}, timeout=10)
    assert connexion.status_code == 200, connexion.text
    return {"Authorization": f"Bearer {connexion.json()['access_token']}"}


# --- ce que le dialogue ÉCRIT ------------------------------------------------

def test_tout_champ_texte_obligatoire_est_aussi_borne():
    """Sur les dix modèles, dans les deux sens : un premier champ TEXTE rendu
    obligatoire porte `min 1`. C'est la règle, balayée là où elle s'applique."""
    manquants = []
    for index, modele in enumerate(TEMPLATES, 1):
        for reponse, seed in (("n", False), ("o", True)):
            _spec_, regles, premiers = _premiers_champs(index, reponse, seed)
            for (entite, champ), type_ in premiers.items():
                obligatoire = f"rule {entite}.{champ} required" in regles
                borne = f"rule {entite}.{champ} min 1" in regles
                if obligatoire and type_ in TYPES_TEXTE and not borne:
                    manquants.append(f"{modele['name']} ({reponse}) : "
                                     f"{entite}.{champ} ({type_})")
    assert not manquants, (
        "un champ texte obligatoire sans plancher accepte la chaîne vide :\n  "
        + "\n  ".join(manquants))


def test_un_premier_champ_numerique_ne_recoit_aucun_plancher():
    """La limite de la règle, exercée sur son PRODUCTEUR.

    Un balayage des dix modèles ne saurait pas la mesurer : `min 1` y est
    aussi émis, à dessein, sur les quantités d'un mouvement de stock — par
    une décision distincte (un mouvement de zéro unité ne veut rien dire).
    Lire le texte de la spec confondrait les deux producteurs ; c'est
    `emit_base_rules` qui porte la règle, donc c'est elle qu'on interroge."""
    for type_ in ("Integer", "Float", "Money"):
        lignes = []
        emit_base_rules(lignes, {"Commande": [("total", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Commande": ["Admin"]},
                        calculated=set())
        assert "rule Commande.total required" in lignes, type_
        assert "rule Commande.total min 1" not in lignes, (
            f"un plancher sur du {type_} interdirait la valeur zéro : {lignes}")


def test_un_premier_champ_texte_recoit_son_plancher():
    """La contre-épreuve du témoin ci-dessus : sans elle, une fonction qui
    n'émettrait plus jamais de plancher les rendrait tous les deux verts."""
    for type_ in TYPES_TEXTE:
        lignes = []
        emit_base_rules(lignes, {"Fiche": [("titre", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Fiche": ["Admin"]},
                        calculated=set())
        assert "rule Fiche.titre min 1" in lignes, (type_, lignes)


def test_la_boutique_borne_son_nom_et_pas_son_total():
    """Les deux cas côte à côte dans une spec RÉELLE, celle qui fait tourner
    le serveur de ce fichier."""
    regles = {ligne.strip() for ligne in _spec(BOUTIQUE).splitlines()}
    assert "rule Customer.displayName min 1" in regles
    assert "rule Order.total required" in regles
    assert "rule Order.total min 1" not in regles


def test_la_liste_des_types_texte_vient_du_compilateur():
    """Elle n'est pas recopiée : une seconde liste finirait par diverger, et
    le dialogue émettrait une règle que le compilateur refuse — le pire
    résultat pour qui est guidé (point 173)."""
    assert TYPES_TEXTE is ChampsMixin.BORNES_TEXTE


# --- ce que le SERVEUR fait --------------------------------------------------

def test_le_serveur_refuse_un_champ_texte_vide(boutique, entete):
    """Le défaut mesuré sur l'archive du mainteneur, à sa source."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": ""}, timeout=10)
    assert reponse.status_code == 422, reponse.text


def test_le_serveur_refuse_aussi_un_champ_qui_n_a_que_des_espaces(
        boutique, entete):
    """Une chaîne d'espaces n'est pas vide au sens de la longueur — et une
    fiche nommée « " " » est aussi illisible qu'une fiche sans nom. Ce que
    monl fait ici est ÉNONCÉ plutôt que supposé : il ne le refuse PAS."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": "   "}, timeout=10)
    assert reponse.status_code == 200, reponse.text


def test_le_serveur_accepte_toujours_une_fiche_nommee(boutique, entete):
    """La contre-épreuve qui distingue un plancher juste d'un plancher qui
    refuse tout."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": "Naya"}, timeout=10)
    assert reponse.status_code == 200, reponse.text
    # Relu EN BASE : un code de retour dit que la route a répondu, jamais que
    # la valeur est arrivée.
    fiche = requests.get(f"{boutique}/customer/{reponse.json()['id']}",
                         headers=entete, timeout=10)
    assert fiche.status_code == 200, fiche.text
    assert fiche.json()["data"]["displayName"] == "Naya"


def test_un_total_a_zero_reste_accepte(boutique, entete):
    """La limite, éprouvée contre le serveur et pas seulement dans la spec :
    un panier vide vaut zéro, et le refuser casserait la boutique."""
    reponse = requests.post(f"{boutique}/order", headers=entete,
                            json={"total": 0, "status": "nouvelle"}, timeout=10)
    assert reponse.status_code == 200, reponse.text
