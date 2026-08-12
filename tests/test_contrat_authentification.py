"""Le contrat NOMME les champs que les routes d'authentification renvoient.

Trouvé en éprouvant la voie sans clé API : le serveur répond
`{'access_token': …, 'token_type': 'bearer'}`, mais le contrat disait seulement
« un token JWT » et le brief « POST /login → token JWT ». Ni l'un ni l'autre ne
nommait la clé JSON. Une IA d'interface devait donc deviner entre `token`,
`access_token` et `jwt`.

**Pourquoi c'est le pire cas de figure.** Une IA qui se trompe de nom lit
`undefined` et envoie `Authorization: Bearer undefined`. Il n'y a alors aucune
exception JavaScript à signaler, et aucun appel hors contrat à dénoncer : le
smoke test passe, `monl run` démarre, et personne ne peut se connecter. Un
défaut qui franchit le vérificateur est plus grave qu'un défaut bruyant.

Que ce soit un oubli et non un choix se lit dans le brief lui-même : la réponse
paginée y est nommée au caractère près depuis toujours
(`{status, total, limit, offset, data}`), et la brique B4 nomme son
`refresh_token`. Seule la réponse d'origine ne s'était jamais décrite.

Ces tests confrontent donc le contrat au VRAI serveur, jamais au code qui
l'écrit : les deux sont générés par le même fichier, et comparer un générateur
à lui-même ne prouverait rien.
"""
import json
import os

import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server

SPEC = """app ContratAuth

entity Note
    texte: String

relation Client hasMany Note

actor Client selfRegister

rule Note.Read ownedBy Client

workflow Ecrire for Client
    Create Note
    Read Note
"""

# Le même socle, plus les jetons de rafraîchissement (brique B4) : c'est la
# SEULE capacité qui change la forme de la réponse de `/login`.
SPEC_REFRESH = SPEC + """
capability auth
    refresh_tokens: 3600
"""

IDENTIFIANT = "cliente@example.com"
SECRET = "motdepasse1"


def _compiler(tmp_path, spec, nom="spec.ml"):
    chemin = tmp_path / nom
    chemin.write_text(spec, encoding="utf-8")
    sortie = tmp_path / "projet"
    compile_project(str(chemin), str(sortie))
    return sortie


def _contrat(sortie):
    with open(os.path.join(str(sortie), "frontend_contract.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def _brief(sortie):
    with open(os.path.join(str(sortie), "FRONTEND_PROMPT.md"),
              encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Ce que le contrat promet — confronté à ce que le serveur renvoie
# --------------------------------------------------------------------------

def test_le_contrat_nomme_les_champs_que_login_renvoie_vraiment(tmp_path):
    """Chaque clé annoncée par le contrat doit exister dans la vraie réponse.

    C'est le test qui aurait attrapé le défaut : avant correction, `login`
    n'avait aucune clé `response` du tout.
    """
    sortie = _compiler(tmp_path, SPEC)
    auth = _contrat(sortie)["api"]["auth"]

    assert "response" in auth["login"], (
        "le contrat doit décrire la forme de la réponse, pas seulement dire "
        "qu'il y a « un token »")

    with uvicorn_server(str(sortie)) as base:
        inscription = requests.post(
            base + "/register", timeout=10,
            json={"username": IDENTIFIANT, "password": SECRET, "actor": "Client"})
        assert inscription.status_code == 200, inscription.text
        connexion = requests.post(
            base + "/login", timeout=10,
            json={"username": IDENTIFIANT, "password": SECRET})
        assert connexion.status_code == 200, connexion.text

        reponse_reelle = connexion.json()
        for champ in auth["login"]["response"]:
            assert champ in reponse_reelle, (
                f"le contrat annonce le champ '{champ}' que /login ne renvoie "
                f"pas — reçu : {sorted(reponse_reelle)}")

        # Et le jeton annoncé doit RÉELLEMENT ouvrir une route protégée : une
        # clé présente mais vide passerait la boucle ci-dessus.
        jeton = reponse_reelle["access_token"]
        protegee = requests.get(base + "/note", timeout=10,
                                headers={"Authorization": f"Bearer {jeton}"})
        assert protegee.status_code == 200, protegee.text


def test_le_contrat_nomme_ce_que_register_renvoie(tmp_path):
    sortie = _compiler(tmp_path, SPEC)
    auth = _contrat(sortie)["api"]["auth"]
    assert "response" in auth["register"]

    with uvicorn_server(str(sortie)) as base:
        reponse = requests.post(
            base + "/register", timeout=10,
            json={"username": IDENTIFIANT, "password": SECRET, "actor": "Client"})
        assert reponse.status_code == 200, reponse.text
        for champ in auth["register"]["response"]:
            assert champ in reponse.json(), (
                f"'{champ}' annoncé par le contrat, absent de /register")


def test_avec_les_jetons_de_rafraichissement_la_reponse_gagne_un_champ(tmp_path):
    """La forme varie avec `capability refresh_tokens` — le contrat suit.

    C'est aussi la réponse à la question de `_contract_signature` : cette
    capacité est déjà hachée sous « authentification B4 », donc le delta
    rapporte le changement sans qu'un second témoin soit nécessaire.
    """
    sortie = _compiler(tmp_path, SPEC_REFRESH)
    reponse_contrat = _contrat(sortie)["api"]["auth"]["login"]["response"]
    assert "refresh_token" in reponse_contrat
    assert "pas un JWT" in reponse_contrat["refresh_token"], (
        "le contrat doit dire que ce jeton est OPAQUE : envoyé en "
        "'Authorization: Bearer', il serait refusé")

    with uvicorn_server(str(sortie)) as base:
        requests.post(base + "/register", timeout=10,
                      json={"username": IDENTIFIANT, "password": SECRET,
                            "actor": "Client"})
        connexion = requests.post(
            base + "/login", timeout=10,
            json={"username": IDENTIFIANT, "password": SECRET})
        assert connexion.status_code == 200, connexion.text
        for champ in reponse_contrat:
            assert champ in connexion.json(), (
                f"'{champ}' annoncé, absent de la vraie réponse")


def test_sans_la_capacite_aucun_refresh_token_nest_promis(tmp_path):
    """Le témoin inverse : une spec ordinaire ne doit rien annoncer de plus.

    Sans lui, un contrat qui promettrait `refresh_token` à tout le monde
    passerait les trois tests ci-dessus.
    """
    sortie = _compiler(tmp_path, SPEC)
    assert "refresh_token" not in _contrat(sortie)["api"]["auth"]["login"]["response"]


# --------------------------------------------------------------------------
# Le brief : c'est lui que l'IA lit, pas le JSON
# --------------------------------------------------------------------------

def test_le_brief_nomme_access_token(tmp_path):
    """Le contrat JSON ne suffit pas : l'IA d'interface travaille sur le brief."""
    brief = _brief(_compiler(tmp_path, SPEC))
    assert "access_token" in brief, (
        "le brief doit NOMMER le champ du jeton — sans lui, l'IA devine, et "
        "une mauvaise devinette produit un site où personne ne se connecte "
        "sans qu'aucun vérificateur ne s'en aperçoive")


@pytest.mark.parametrize("mot", ["status, user_id", "access_token, token_type"])
def test_le_brief_donne_la_forme_des_reponses_dauthentification(tmp_path, mot):
    assert mot in _brief(_compiler(tmp_path, SPEC))
