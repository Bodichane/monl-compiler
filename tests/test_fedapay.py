"""Encaisser par mobile money — brique 2b, prestataire FedaPay.

Stripe n'opère pas en Afrique de l'Ouest, où l'argent passe par MTN MoMo, Moov
et Wave derrière un agrégateur. FedaPay est le premier ajouté.

**Ce qui est PROUVÉ ici** : que monl parle le protocole qu'on lui a décrit —
deux appels de création, une URL de paiement rendue au navigateur, et une
vérification de signature de webhook conforme à la recette du SDK officiel
(`Webhook.ts` : schéma `s`, message `timestamp + "." + corps brut`,
HMAC-SHA256 hexadécimal, tolérance de 300 secondes).

**Ce qui ne l'est PAS** : qu'un vrai FedaPay accepte ce corps de requête, et
surtout le CHEMIN JSON exact de la référence marchand dans l'événement de
webhook. La documentation publique établit que `merchant_reference` et
`custom_metadata` existent, mais n'imprime aucune charge utile complète. Le
code généré est donc *fail-closed* : référence introuvable ⇒ aucune écriture.
Ces deux points restent à confirmer sur un compte de bac à sable réel, et le
faux prestataire de ce fichier ne les remplace pas — il prouve monl, pas
FedaPay.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import ASTValidationError, MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server
from tests.test_paiement import SPEC_BOUTIQUE

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_fedapay"
CLE_WEBHOOK = "wh_test_fedapay"
ID_TRANSACTION = 778899

SPEC_FEDAPAY = SPEC_BOUTIQUE + """
capability payment
    provider: fedapay
    currency: XOF
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que le validateur refuse — et le refus qui explique au lieu de fermer
# --------------------------------------------------------------------------

def test_kkiapay_est_refuse_en_disant_pourquoi():
    """Refuser en NOMMANT la raison : « prestataire inconnu » enverrait
    chercher une faute de frappe dans un nom parfaitement correct.

    KKiaPay ne publie ni l'algorithme ni les données signées de son webhook.
    Le construire par analogie avec Stripe ou FedaPay ne serait pas une
    approximation : ce serait un trou de sécurité à l'unique endroit du
    backend généré où un tiers non authentifié écrit en base.
    """
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: kkiapay\n")
    message = str(refus.value)
    assert "kkiapay" in message
    assert "devinera pas" in message


def test_un_prestataire_inconnu_est_refuse():
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: banqueX\n")
    assert "inconnu" in str(refus.value)


def test_deux_prestataires_ne_compilent_pas():
    spec = (SPEC_BOUTIQUE + "\ncapability payment\n    provider: stripe\n"
            + "\ncapability payment\n    provider: fedapay\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "deux fois" in str(refus.value)


def test_un_prestataire_sans_rien_a_encaisser_est_refuse():
    sans = SPEC_BOUTIQUE.replace("rule Commande.total payable\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans + "\ncapability payment\n    provider: fedapay\n")
    assert "payable" in str(refus.value)


def test_une_spec_muette_reste_sur_stripe():
    """Témoin de non-régression : rien de déclaré, rien de changé."""
    assert _valide(SPEC_BOUTIQUE)["security"]["payment_provider"] is None


# --------------------------------------------------------------------- faux --
class _FedaPayFactice(BaseHTTPRequestHandler):
    """Parle le dialecte FedaPay et RETIENT ce qu'on lui a envoyé.

    Le corps est du JSON : le décoder ici plutôt que de faire confiance au code
    généré est ce qui permet d'affirmer quel montant a réellement été demandé.
    """

    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        corps = json.loads(brut or b"{}") if brut else {}
        self.server.recu.append({
            "chemin": self.path,
            "autorisation": self.headers.get("Authorization", ""),
            "corps": corps,
        })
        if self.path.endswith("/token"):
            charge = {"token": "tok_essai",
                      "url": "https://sandbox.fedapay/pay/tok_essai"}
        else:
            charge = {"v1/transaction": {"id": ID_TRANSACTION,
                                         "status": "pending"}}
        rendu = json.dumps(charge).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rendu)))
        self.end_headers()
        self.wfile.write(rendu)

    def log_message(self, *_):  # silence
        pass


@pytest.fixture(scope="module")
def faux_fedapay():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _FedaPayFactice)
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
def _application(faux, avec_cles=True):
    hote, port = faux.server_address[:2]
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_FEDAPAY)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        env = {**os.environ}
        for cle in ("MONL_FEDAPAY_SECRET_KEY", "MONL_FEDAPAY_WEBHOOK_SECRET",
                    "MONL_FEDAPAY_BASE_URL"):
            env.pop(cle, None)
        if avec_cles:
            env.update({"MONL_FEDAPAY_SECRET_KEY": CLE_SECRETE,
                        "MONL_FEDAPAY_WEBHOOK_SECRET": CLE_WEBHOOK,
                        "MONL_FEDAPAY_BASE_URL": f"http://{hote}:{port}"})
        with uvicorn_server(dossier, env=env) as base:
            yield base, dossier


def _commande(base, dossier, montant, identifiant):
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
    reponse = requests.post(f"{base}/commande", headers=entetes, timeout=10,
                            json={"libelle": "Sac", "quantite": 1,
                                  "article_id": article})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"], entetes


def _signer(corps, secret=CLE_WEBHOOK, horodatage=None):
    """Reproduit EXACTEMENT la recette du SDK officiel : HMAC-SHA256 de
    « horodatage.corps », hexadécimal, sous le schéma `s`."""
    t = str(int(horodatage if horodatage is not None else time.time()))
    signature = hmac.new(secret.encode(), (t + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    return f"t={t},s={signature}"


def _etat(dossier, identifiant):
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        return cnx.execute("SELECT payment_status FROM commande WHERE id = ?",
                           (identifiant,)).fetchone()[0]
    finally:
        cnx.close()


def _reference(dossier, identifiant):
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        return cnx.execute("SELECT payment_ref FROM commande WHERE id = ?",
                           (identifiant,)).fetchone()[0]
    finally:
        cnx.close()


# --------------------------------------------------------------------------
# Le parcours réel
# --------------------------------------------------------------------------

def test_les_deux_appels_partent_avec_le_montant_de_la_base(faux_fedapay):
    """Création puis jeton : la création seule ne rend AUCUNE URL, s'y arrêter
    livrerait un bouton « Payer » qui ne mène nulle part."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "awa@example.com")
        faux_fedapay.recu.clear()
        reglement = requests.post(f"{base}/commande/{identifiant}/paiement",
                                  headers=entetes, timeout=10)
        assert reglement.status_code == 200, reglement.text

        chemins = [a["chemin"] for a in faux_fedapay.recu]
        assert chemins == ["/v1/transactions",
                           f"/v1/transactions/{ID_TRANSACTION}/token"]

        creation = faux_fedapay.recu[0]
        assert creation["autorisation"] == f"Bearer {CLE_SECRETE}"
        # Le franc CFA n'a pas de sous-unité (brique 2a) : 5 000 partent
        # pour 5 000, jamais 500 000.
        assert creation["corps"]["amount"] == 5000
        assert creation["corps"]["currency"] == {"iso": "XOF"}
        # Référence QUALIFIÉE (point 75) : un id nu se confondrait avec celui
        # d'une autre entité payable de la même application.
        assert creation["corps"]["merchant_reference"] == f"Commande:{identifiant}"
        assert (creation["corps"]["custom_metadata"]["monl_reference"]
                == f"Commande:{identifiant}")

        assert reglement.json()["url"] == "https://sandbox.fedapay/pay/tok_essai"
        assert reglement.json()["devise"] == "XOF"


def test_le_webhook_signe_marque_la_commande_payee(faux_fedapay):
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "leo@example.com")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        assert _etat(dossier, identifiant) == "en_attente"

        corps = json.dumps({
            "name": "transaction.approved",
            "entity": {"id": ID_TRANSACTION,
                       "merchant_reference": f"Commande:{identifiant}"},
        }).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": _signer(corps)})
        assert reponse.status_code == 200, reponse.text
        assert _etat(dossier, identifiant) == "payee"


@pytest.mark.parametrize("entete", [
    "",
    "t=1,s=deadbeef",
    "s=deadbeef",
])
def test_un_webhook_mal_signe_ne_paie_rien(faux_fedapay, entete):
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, f"x{len(entete)}@e.fr")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        corps = json.dumps({"name": "transaction.approved",
                            "entity": {"id": ID_TRANSACTION,
                                       "merchant_reference": f"Commande:{identifiant}"}}).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": entete})
        assert reponse.status_code == 400, reponse.text
        assert _etat(dossier, identifiant) == "en_attente"


def test_une_signature_datee_du_futur_est_refusee(faux_fedapay):
    """monl est PLUS STRICT que le SDK officiel, délibérément.

    `Webhook.ts` ne teste que `timestampAge > tolerance` : un horodatage dans
    le FUTUR y passe. monl refuse `abs(maintenant - t) > 300`, parce qu'un
    horodatage qu'on ne contrôle pas dans les deux sens n'est plus une
    protection contre le rejeu (point 91).
    """
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "futur@example.com")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        corps = json.dumps({"name": "transaction.approved",
                            "entity": {"id": ID_TRANSACTION,
                                       "merchant_reference": f"Commande:{identifiant}"}}).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": _signer(corps,
                                                    horodatage=time.time() + 3600)})
        assert reponse.status_code == 400
        assert _etat(dossier, identifiant) == "en_attente"


def test_une_charge_utile_de_forme_inconnue_nécrit_rien(faux_fedapay):
    """FAIL-CLOSED. Le chemin JSON de la référence n'est pas prouvé par la
    documentation publique : si la forme reçue n'est pas celle attendue, le
    serveur n'écrit RIEN plutôt que de deviner. Se tromper coûte alors un
    règlement non enregistré, pas le mauvais enregistrement marqué payé."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "forme@example.com")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        corps = json.dumps({"name": "transaction.approved",
                            "inattendu": {"reference": f"Commande:{identifiant}"}}).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": _signer(corps)})
        assert reponse.status_code == 200
        assert reponse.json()["status"] == "ignored"
        assert _etat(dossier, identifiant) == "en_attente"


def test_sans_cle_le_serveur_refuse_en_nommant_la_variable(faux_fedapay):
    """Invariant du point 74 : 503 en nommant la variable absente, et le reste
    du serveur intact — `monl run` et le smoke test restent verts hors ligne."""
    with _application(faux_fedapay, avec_cles=False) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "sanscle@example.com")
        reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                                headers=entetes, timeout=10)
        assert reponse.status_code == 503
        assert "MONL_FEDAPAY_SECRET_KEY" in reponse.text
        # Le reste du serveur répond quand même : c'est la moitié de
        # l'invariant, et c'est elle qui garde `monl run` et le smoke test
        # verts hors ligne. La commande du client se lit toujours.
        assert requests.get(f"{base}/commande", headers=entetes,
                            timeout=10).status_code == 200


# --------------------------------------------------------------------------
# La devise que le prestataire encaisse réellement
# --------------------------------------------------------------------------

def test_fedapay_refuse_une_devise_quil_nencaisse_pas():
    """FedaPay ne règle QU'EN XOF — sa propre documentation le dit, et son
    module Odoo officiel ne déclare que ça. Sans ce refus, la spec compile et
    l'auteur ne l'apprend qu'au premier vrai encaissement, en 502, devant un
    client qui voulait payer."""
    with pytest.raises(ASTValidationError) as erreur:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n"
                "    provider: fedapay\n    currency: EUR\n")
    message = str(erreur.value)
    assert "XOF" in message and "EUR" in message
    # Le message doit dire QUOI ÉCRIRE : « incompatible » laisserait chercher.
    assert "currency: XOF" in message


def test_fedapay_sans_devise_declaree_est_refuse():
    """La devise EFFECTIVE est comparée, pas seulement la déclarée. Sans ligne
    `currency`, le défaut est l'euro : `provider: fedapay` tout seul partait
    donc encaisser en euros chez un prestataire qui n'en accepte pas."""
    with pytest.raises(ASTValidationError) as erreur:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: fedapay\n")
    assert "XOF" in str(erreur.value)


def test_stripe_nest_contraint_a_aucune_devise():
    """La table ne dit `None` que là où monl ne SAIT pas — et ne rien savoir
    n'autorise pas à interdire. Le témoin du refus précédent : sans lui, une
    garde trop large casserait toutes les specs en euros."""
    assert _valide(SPEC_BOUTIQUE + "\ncapability payment\n"
                   "    provider: stripe\n    currency: EUR\n"
                   )["security"]["payment_provider"] == "stripe"


# --------------------------------------------------------------------------
# L'appariement du webhook par l'identifiant du prestataire
# --------------------------------------------------------------------------

def test_la_reference_du_prestataire_est_memorisee_des_louverture(faux_fedapay):
    """Sans cette mémorisation, le repli du webhook n'a rien à comparer."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "memo@example.com")
        assert _reference(dossier, identifiant) in (None, "")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        assert _reference(dossier, identifiant) == str(ID_TRANSACTION)
        # Mémoriser n'est PAS encaisser : c'est `payment_status` qui dit si
        # c'est payé, et le contrat le dit désormais en toutes lettres.
        assert _etat(dossier, identifiant) == "en_attente"


def test_un_webhook_sans_reference_marchande_est_apparie_par_lidentifiant(faux_fedapay):
    """La voie que le plugin Odoo officiel de FedaPay emploie : retrouver la
    ligne par l'id de transaction mémorisé à la création. C'est la seule des
    deux qui soit établie par du code en production — `merchant_reference` est
    documenté sur la transaction, jamais sur la charge utile du webhook."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "repli@example.com")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        corps = json.dumps({
            "name": "transaction.approved",
            "entity": {"id": ID_TRANSACTION, "status": "approved"},
        }).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": _signer(corps)})
        assert reponse.status_code == 200, reponse.text
        assert _etat(dossier, identifiant) == "payee"


def test_un_identifiant_de_transaction_inconnu_napparie_rien(faux_fedapay):
    """Le témoin du repli : il ne doit reconnaître QUE ce qu'il a mémorisé.
    Un repli qui marquerait payé le premier venu serait pire que pas de repli
    du tout — c'est le fail-closed qui tient toute la brique."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _commande(base, dossier, 5000, "inconnu@example.com")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        corps = json.dumps({
            "name": "transaction.approved",
            "entity": {"id": ID_TRANSACTION + 1234, "status": "approved"},
        }).encode()
        reponse = requests.post(
            f"{base}/paiement/webhook", data=corps, timeout=10,
            headers={"Content-Type": "application/json",
                     "x-fedapay-signature": _signer(corps)})
        assert reponse.status_code == 200
        assert reponse.json()["status"] == "ignored"
        assert _etat(dossier, identifiant) == "en_attente"
