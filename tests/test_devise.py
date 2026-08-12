"""La devise d'encaissement et son EXPOSANT — brique 2a.

Le code figeait deux choses : la devise (`'eur'`) et le facteur de conversion
(`montant × 100`). Le second est le vrai danger. Un prestataire attend un
ENTIER dans l'unité mineure de la devise ; pour l'euro c'est le centime, donc
×100. **Le franc CFA n'a aucune sous-unité** : une commande de 5 000 FCFA
serait partie chez le prestataire pour 500 000 FCFA — cent fois le prix.

Ce défaut ne se voit ni à la lecture (le calcul est juste pour l'euro), ni dans
les tests existants (ils encaissent en euros), ni à l'exécution côté monl (le
serveur répond 200). Il se voit sur le relevé bancaire du client. C'est la
famille du point 77 — le montant que quelqu'un d'autre décide — par une porte
que personne n'avait ouverte : celle des UNITÉS.

**Le test qui porte la brique est une PAIRE** : la même commande de 5 000,
compilée en XOF puis en EUR, et ce que le faux prestataire a réellement reçu.
Pris seul, le cas XOF passerait avec un `×100` oublié quelque part si l'autre
moitié de la chaîne compensait ; pris seul, le cas EUR ne prouverait aucune
régression. Ensemble, ils épinglent le facteur.
"""
import contextlib
import os
import sqlite3
import tempfile
import threading
from http.server import ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server

# Le faux prestataire est celui du banc d'essai du paiement : il décode le
# corps `x-www-form-urlencoded` et RETIENT les champs reçus. Le réécrire ici
# donnerait deux prestataires factices à maintenir, et c'est exactement ce
# qu'un décodeur en double finit par masquer.
from tests.test_paiement import SPEC_BOUTIQUE, _PrestataireFactice

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_devise"

SPEC_XOF = SPEC_BOUTIQUE + """
capability payment
    currency: XOF
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que le validateur refuse — et pourquoi il refuse plutôt que de deviner
# --------------------------------------------------------------------------

def test_une_devise_inconnue_est_refusee_jamais_devinee():
    """Deviner « deux décimales » serait reprendre le bug qu'on ferme."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    currency: ZZZ\n")
    message = str(refus.value)
    assert "ZZZ" in message
    assert "multiplierait chaque montant par cent" in message


def test_une_devise_a_trois_decimales_est_refusee_en_le_disant():
    """Le dinar tunisien est un code parfaitement valide : le message ne doit
    pas envoyer chercher une faute de frappe."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    currency: TND\n")
    assert "trois décimales" in str(refus.value)


def test_la_devise_posee_sur_capability_auth_nomme_la_bonne_capacite():
    """La grammaire partage un seul jeu de propriétés entre les capacités : une
    ligne au mauvais endroit est l'erreur attendue, pas une faute de frappe."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability auth\n    currency: XOF\n")
    assert "capability payment" in str(refus.value)


def test_deux_devises_ne_compilent_pas():
    spec = (SPEC_BOUTIQUE + "\ncapability payment\n    currency: XOF\n"
            + "\ncapability payment\n    currency: EUR\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "deux fois" in str(refus.value)


def test_une_devise_sans_rien_a_encaisser_est_refusee():
    """Point 85 : une règle sans effet est refusée, jamais ignorée en silence —
    sinon l'auteur croit avoir configuré son application."""
    sans_paiement = SPEC_BOUTIQUE.replace("rule Commande.total payable\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans_paiement + "\ncapability payment\n    currency: XOF\n")
    assert "payable" in str(refus.value)


def test_une_spec_muette_garde_leuro_et_le_facteur_cent():
    """Le témoin de non-régression : rien de déclaré, rien de changé."""
    ast = _valide(SPEC_BOUTIQUE)
    assert ast["security"]["payment_currency"] is None


def test_la_devise_declaree_porte_son_exposant():
    devise = _valide(SPEC_XOF)["security"]["payment_currency"]
    assert devise == {"code": "XOF", "exponent": 0}


# --------------------------------------------------------------------------
# Ce que le prestataire reçoit VRAIMENT — la paire qui porte la brique
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def faux_prestataire():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _PrestataireFactice)
    serveur.recu = []
    serveur.refuser = False
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)


@contextlib.contextmanager
def _application(spec, faux_prestataire):
    hote, port = faux_prestataire.server_address[:2]
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        env = {**os.environ}
        for cle in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                    "MONL_STRIPE_BASE_URL"):
            env.pop(cle, None)
        env.update({"STRIPE_SECRET_KEY": CLE_SECRETE,
                    "MONL_STRIPE_BASE_URL": f"http://{hote}:{port}"})
        with uvicorn_server(dossier, env=env) as base:
            yield base, dossier


def _regler_une_commande_de(spec, faux_prestataire, montant, identifiant):
    """Inscrit un compte, crée une commande de `montant`, la règle — et renvoie
    les champs que le prestataire a réellement reçus."""
    with _application(spec, faux_prestataire) as (base, dossier):
        cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
        try:
            with cnx:
                cnx.execute("DELETE FROM _monl_rate_limit")
                article = cnx.execute(
                    'INSERT INTO article (nom, prix) VALUES (?, ?)',
                    ("Sac", montant)).lastrowid
        finally:
            cnx.close()

        requests.post(f"{base}/register", timeout=10,
                      json={"username": identifiant, "password": MOT_DE_PASSE,
                            "actor": "Client"})
        jeton = requests.post(f"{base}/login", timeout=10,
                              json={"username": identifiant,
                                    "password": MOT_DE_PASSE}).json()
        entetes = {"Authorization": "Bearer " + jeton["access_token"]}

        commande = requests.post(f"{base}/commande", headers=entetes, timeout=10,
                                 json={"libelle": "Sac", "quantite": 1,
                                       "article_id": article})
        assert commande.status_code in (200, 201), commande.text
        identifiant_commande = commande.json()["id"]

        faux_prestataire.recu.clear()
        reglement = requests.post(
            f"{base}/commande/{identifiant_commande}/paiement",
            headers=entetes, timeout=10)
        assert reglement.status_code == 200, reglement.text
        assert faux_prestataire.recu, "le prestataire n'a rien reçu"
        return faux_prestataire.recu[-1]["champs"], reglement.json()


def test_en_franc_cfa_le_montant_part_tel_quel(faux_prestataire):
    """5 000 FCFA doivent partir pour 5 000, jamais 500 000."""
    champs, reponse = _regler_une_commande_de(
        SPEC_XOF, faux_prestataire, 5000, "awa@example.com")

    assert champs["line_items[0][price_data][currency]"] == "xof"
    assert champs["line_items[0][price_data][unit_amount]"] == "5000", (
        "le franc CFA n'a pas de sous-unité : multiplier par cent facturerait "
        "cent fois le prix")
    assert reponse["devise"] == "XOF"
    assert reponse["montant"] == 5000


def test_en_euro_le_montant_reste_en_centimes(faux_prestataire):
    """L'autre moitié de la paire : sans elle, un facteur 1 appliqué partout
    passerait le test ci-dessus tout en cassant l'euro."""
    champs, reponse = _regler_une_commande_de(
        SPEC_BOUTIQUE, faux_prestataire, 5000, "leo@example.com")

    assert champs["line_items[0][price_data][currency]"] == "eur"
    assert champs["line_items[0][price_data][unit_amount]"] == "500000"
    assert reponse["devise"] == "EUR"


def test_le_montant_lisible_accompagne_lunite_mineure(faux_prestataire):
    """`montant_centimes` GARDE son nom sur le fil (point 95 : renommer
    casserait le bouton « Payer » de tout projet existant), mais `devise` et
    `montant` sont désormais à côté — une interface n'a plus à diviser par
    cent au hasard."""
    _champs, reponse = _regler_une_commande_de(
        SPEC_XOF, faux_prestataire, 2500, "koffi@example.com")
    assert reponse["montant_centimes"] == 2500
    assert reponse["montant"] == 2500
    assert reponse["devise"] == "XOF"
