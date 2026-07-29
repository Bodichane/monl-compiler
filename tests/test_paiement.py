"""La brique `payable` éprouvée contre un vrai serveur et un faux Stripe.

CLAUDE.md le dit sans détour : compiler n'est pas se comporter correctement,
et « toute NOUVELLE brique doit arriver avec son test contre serveur ». Le
paiement est la première brique de monl dont un défaut ne se paie pas en
affichage faux mais en argent — c'est aussi la première qui fait sortir une
requête du backend généré. Elle ne peut pas se contenter d'une couverture de
compilation.

Le prestataire est remplacé par un serveur HTTP local qui parle son dialecte
(`MONL_STRIPE_BASE_URL`, prévu pour cela dans le code généré). Il n'est pas là
pour simuler poliment : il **enregistre ce qu'on lui envoie**, et c'est cet
enregistrement qui porte la garantie centrale — le montant encaissé est celui
de la BASE, jamais celui que le client a bien voulu annoncer. Un banc d'essai
qui se contenterait de renvoyer 200 laisserait passer exactement le bug qui
coûte de l'argent.

Trois familles de garanties, dans l'ordre de ce qu'elles coûtent si elles
tombent :

* **Le montant** — lu en base à chaque demande, insensible au corps de requête.
* **La signature du webhook** — sans elle, un `curl` marque n'importe quelle
  commande comme payée. C'est le seul endroit du backend généré où un tiers
  non authentifié peut modifier une ligne.
* **Les refus** — 403 pour l'enregistrement d'autrui, 409 pour un règlement
  déjà encaissé, 400 pour un montant nul, 503 quand le serveur n'a pas de clé.
  Un paiement doit refuser bruyamment, jamais échouer en silence.
"""
import contextlib
import hashlib
import hmac
import json
import os
import socket
import sqlite3
import subprocess
import sys
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

SPEC_BOUTIQUE = """app Boutique

entity Client
    nom: String

entity Commande
    libelle: String
    total: Money

relation Client hasMany Commande

actor Client selfRegister

rule Commande.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
"""

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_bancdessai"
CLE_WEBHOOK = "whsec_bancdessai"


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------- le faux Stripe --
class _PrestataireFactice(BaseHTTPRequestHandler):
    """Parle le dialecte de Stripe et RETIENT ce qu'on lui a envoyé.

    Le corps est en `application/x-www-form-urlencoded`, comme la vraie API :
    le décoder ici plutôt que de faire confiance au code généré est ce qui
    permet d'affirmer quel montant a réellement été demandé.
    """

    def do_POST(self):  # nom imposé par BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append({
            "chemin": self.path,
            "autorisation": self.headers.get("Authorization", ""),
            "champs": {c: v[0] for c, v
                       in urllib.parse.parse_qs(brut.decode()).items()},
        })
        if self.server.refuser:
            # ensure_ascii=False comme la vraie API : c'est ce qui fait passer
            # le message par le `.decode('utf-8')` du code généré.
            corps = json.dumps({"error": {"message": "carte refusée"}},
                               ensure_ascii=False).encode()
            self.send_response(402)
        else:
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
    serveur.refuser = False
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)


# ------------------------------------------------ le serveur monl généré --
@contextlib.contextmanager
def _application_generee(env_supplementaire):
    """Compile SPEC_BOUTIQUE et démarre un uvicorn éphémère dans un dossier
    temporaire. L'environnement est explicite : les clés de paiement sont
    lues à l'import du module généré, un test ne peut donc pas les changer
    après coup — d'où deux serveurs distincts, avec et sans clés."""
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_BOUTIQUE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        port = _port_libre()
        env = {**os.environ}
        for cle in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                    "MONL_STRIPE_BASE_URL"):
            env.pop(cle, None)
        env.update(env_supplementaire)
        serveur = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port)],
            cwd=dossier, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(80):
                try:
                    requests.get(f"{base}/openapi.json", timeout=1)
                    break
                except requests.exceptions.ConnectionError:
                    time.sleep(0.25)
            else:
                pytest.skip("serveur non démarré")
            yield base, dossier
        finally:
            serveur.terminate()
            serveur.wait(timeout=10)


@pytest.fixture(scope="module")
def application(faux_stripe):
    hote, port = faux_stripe.server_address[:2]
    with _application_generee({
        "STRIPE_SECRET_KEY": CLE_SECRETE,
        "STRIPE_WEBHOOK_SECRET": CLE_WEBHOOK,
        "MONL_STRIPE_BASE_URL": f"http://{hote}:{port}",
    }) as ouvert:
        yield ouvert


@pytest.fixture(scope="module")
def application_sans_cles():
    """Le cas du serveur mis en ligne sans configurer le paiement. C'est la
    situation par défaut de tout projet monl fraîchement compilé — donc celle
    que le smoke test rencontre, et qui doit rester verte hors ligne."""
    with _application_generee({}) as ouvert:
        yield ouvert


# ------------------------------------------------------------- utilitaires --
@contextlib.contextmanager
def _base(dossier):
    """Ouvre app.db en validant ET en fermant à la sortie (voir point 71 :
    `with sqlite3.connect(...)` ne ferme pas la connexion)."""
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


def _entetes(application, identifiant):
    """Inscrit un compte et renvoie ses en-têtes d'authentification.

    Le compteur de tentatives est vidé au passage (5 / 60 s / IP, points 13
    et 33) : ce fichier ouvre un compte par test pour que les tests ne
    s'ordonnent pas implicitement les uns les autres.
    """
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


def _commande(base, entetes, libelle, total):
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle, "total": total})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _signer(corps, secret=CLE_WEBHOOK, horodatage="1700000000", version="v1"):
    """Reproduit la signature Stripe : HMAC-SHA256 de « horodatage.corps »."""
    empreinte = hmac.new(secret.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    return f"t={horodatage},{version}={empreinte}"


def _evenement(session_id, reference, type_evenement="checkout.session.completed"):
    return json.dumps({
        "type": type_evenement,
        "data": {"object": {"id": session_id,
                            "client_reference_id": str(reference)}},
    }).encode()


def _etat_en_base(dossier, identifiant):
    with _base(dossier) as cnx:
        return cnx.execute(
            "SELECT payment_status, payment_ref FROM commande WHERE id = ?",
            (identifiant,)).fetchone()


# =============================================== le montant vient de la base --
def test_le_montant_encaisse_vient_de_la_base_jamais_du_client(application, faux_stripe):
    """La garantie centrale de la brique. Un panier qui envoie son propre prix
    est un panier qu'on peut négocier — le test envoie donc un corps de requête
    qui annonce un tout autre montant, et vérifie ce que le prestataire a
    RÉELLEMENT reçu, pas ce que le serveur a répondu."""
    base, _dossier = application
    entetes = _entetes(application, "acheteuse")
    identifiant = _commande(base, entetes, "chaise", 42.50)

    avant = len(faux_stripe.recu)
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes,
                            json={"total": 1, "montant_centimes": 1,
                                  "unit_amount": 1})
    assert reponse.status_code == 200, reponse.text

    demande = faux_stripe.recu[avant]
    assert demande["champs"]["line_items[0][price_data][unit_amount]"] == "4250", (
        f"le montant annoncé par le client a été retenu : {demande['champs']}")
    assert reponse.json()["montant_centimes"] == 4250, reponse.text
    assert reponse.json()["url"] == "https://paiement.example/session"


def test_le_montant_suit_la_base_quand_elle_change(application, faux_stripe):
    """Corollaire du précédent, et il ne va pas de soi : le montant est relu à
    CHAQUE demande. Un montant figé à la création laisserait encaisser un prix
    périmé après une correction en base."""
    base, dossier = application
    entetes = _entetes(application, "revisee")
    identifiant = _commande(base, entetes, "table", 10.00)

    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    with _base(dossier) as cnx:
        cnx.execute("UPDATE commande SET total = 99.99 WHERE id = ?", (identifiant,))

    avant = len(faux_stripe.recu)
    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    assert faux_stripe.recu[avant]["champs"][
        "line_items[0][price_data][unit_amount]"] == "9999"


def test_la_session_porte_la_reference_et_la_cle_du_serveur(application, faux_stripe):
    """`client_reference_id` est le seul fil qui relie la session au règlement :
    c'est lui que le webhook relit pour savoir quelle ligne marquer payée. Sans
    lui, un paiement réussi n'atterrit sur aucune commande."""
    base, _dossier = application
    entetes = _entetes(application, "referencee")
    identifiant = _commande(base, entetes, "lampe", 7.00)

    avant = len(faux_stripe.recu)
    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    demande = faux_stripe.recu[avant]

    assert demande["chemin"] == "/v1/checkout/sessions"
    assert demande["champs"]["client_reference_id"] == str(identifiant)
    # La clé part en en-tête, jamais dans l'URL ni dans le corps.
    assert demande["autorisation"] == f"Bearer {CLE_SECRETE}"
    assert CLE_SECRETE not in demande["chemin"]


# ============================================================ les refus ======
def test_payer_l_enregistrement_d_un_autre_compte_est_refuse(application):
    """La commande d'autrui n'est pas seulement illisible : elle n'est pas
    payable non plus. Sans ce contrôle, un tiers pourrait ouvrir des sessions
    de règlement sur des lignes qu'il ne verra jamais — et découvrir leur
    montant par la réponse."""
    base, _dossier = application
    proprietaire = _entetes(application, "proprietaire")
    identifiant = _commande(base, proprietaire, "vélo", 300.00)

    intruse = _entetes(application, "intruse")
    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=intruse)
    assert refus.status_code == 403, refus.text
    assert "appartient" in refus.json()["detail"]


def test_un_enregistrement_inexistant_donne_404(application):
    base, _dossier = application
    entetes = _entetes(application, "fantome")
    refus = requests.post(f"{base}/commande/999999/paiement", headers=entetes)
    assert refus.status_code == 404, refus.text


def test_un_montant_nul_n_est_pas_encaisse(application, faux_stripe):
    """Zéro n'est pas un prix. Laisser passer produirait chez le prestataire
    une session à 0, refusée de son côté — donc une erreur incompréhensible,
    loin de sa cause."""
    base, _dossier = application
    entetes = _entetes(application, "gratuite")
    identifiant = _commande(base, entetes, "échantillon", 0)

    avant = len(faux_stripe.recu)
    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=entetes)
    assert refus.status_code == 400, refus.text
    assert len(faux_stripe.recu) == avant, (
        "une session a été ouverte pour un montant nul")


def test_une_demande_sans_jeton_est_refusee(application):
    """La route de règlement n'est jamais publique : le validateur refuse
    d'ailleurs `payable` sur une création `public`, faute d'identité à qui
    rattacher le paiement."""
    base, _dossier = application
    entetes = _entetes(application, "anonyme")
    identifiant = _commande(base, entetes, "livre", 15.00)
    refus = requests.post(f"{base}/commande/{identifiant}/paiement")
    assert refus.status_code in (401, 403), refus.text


def test_le_refus_du_prestataire_remonte_en_502_avec_son_message(application, faux_stripe):
    """Quand le prestataire dit non, monl ne doit ni prétendre que tout va
    bien ni masquer la raison : 502 et le message reçu. C'est la seule
    information dont dispose celui qui débogue."""
    base, _dossier = application
    entetes = _entetes(application, "recalee")
    identifiant = _commande(base, entetes, "canapé", 800.00)

    faux_stripe.refuser = True
    try:
        refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                              headers=entetes)
    finally:
        faux_stripe.refuser = False
    assert refus.status_code == 502, refus.text
    assert "carte refusée" in refus.json()["detail"]


def test_sans_cle_le_serveur_refuse_bruyamment_en_nommant_la_variable(
        application_sans_cles):
    """Un projet monl fraîchement compilé n'a aucune clé : la route existe
    quand même, et dit laquelle manque. Le silence — ou un 500 — obligerait à
    lire le code généré pour comprendre qu'il n'y a rien à configurer
    d'autre."""
    base, _dossier = application_sans_cles
    entetes = _entetes(application_sans_cles, "sansclef")
    identifiant = _commande(base, entetes, "étagère", 55.00)

    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=entetes)
    assert refus.status_code == 503, refus.text
    assert "STRIPE_SECRET_KEY" in refus.json()["detail"]

    # Le webhook aussi, avec SA variable : les deux se configurent séparément.
    refus_webhook = requests.post(f"{base}/paiement/webhook", data=b"{}")
    assert refus_webhook.status_code == 503, refus_webhook.text
    assert "STRIPE_WEBHOOK_SECRET" in refus_webhook.json()["detail"]


def test_le_serveur_sans_cle_demarre_et_sert_le_reste(application_sans_cles):
    """Le corollaire qui compte pour le smoke test : l'absence de clé de
    paiement n'empêche RIEN d'autre. Un backend qui refuserait de démarrer
    rendrait `monl run` impossible hors ligne."""
    base, _dossier = application_sans_cles
    entetes = _entetes(application_sans_cles, "ordinaire")
    identifiant = _commande(base, entetes, "tabouret", 20.00)
    lu = requests.get(f"{base}/commande/{identifiant}", headers=entetes)
    assert lu.status_code == 200, lu.text


# ======================================================= la signature ========
def test_le_webhook_signe_marque_l_enregistrement_paye(application):
    """Le parcours complet : commande, session, notification signée. C'est le
    seul chemin par lequel `payment_status` change — aucune route d'écriture
    métier ne le touche."""
    base, dossier = application
    entetes = _entetes(application, "reglee")
    identifiant = _commande(base, entetes, "bureau", 120.00)

    session = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes).json()
    corps = _evenement(session["session_id"], identifiant)
    recu = requests.post(f"{base}/paiement/webhook", data=corps,
                         headers={"stripe-signature": _signer(corps)})
    assert recu.status_code == 200, recu.text
    assert recu.json()["status"] == "success"

    etat, reference = _etat_en_base(dossier, identifiant)
    assert etat == "payee", etat
    assert reference == session["session_id"], reference

    # Et la lecture le dit : sans cela, l'interface ne pourrait pas distinguer
    # une commande réglée d'une commande en attente.
    lu = requests.get(f"{base}/commande/{identifiant}", headers=entetes).json()
    assert lu["data"]["payment_status"] == "payee", lu


@pytest.mark.parametrize("entete", [
    None,
    "",
    "t=1700000000",
    "v1=" + "0" * 64,
    "t=1700000000,v1=" + "0" * 64,
], ids=["absente", "vide", "sans-signature", "sans-horodatage", "forgée"])
def test_un_webhook_mal_signe_ne_paie_rien(application, entete):
    """LE test de sécurité de la brique. Sans vérification de signature,
    n'importe qui marque n'importe quelle commande comme payée avec un simple
    `curl` — c'est le seul endroit du backend généré où un tiers non
    authentifié écrit en base. Chaque forme de signature invalide est essayée
    séparément : une seule branche de l'analyse qui laisserait passer suffit à
    ouvrir la porte."""
    base, dossier = application
    entetes = _entetes(application, f"tentative{abs(hash(str(entete))) % 10000}")
    identifiant = _commande(base, entetes, "coffre", 60.00)

    corps = _evenement("cs_forge", identifiant)
    envoi = {} if entete is None else {"stripe-signature": entete}
    refus = requests.post(f"{base}/paiement/webhook", data=corps, headers=envoi)

    assert refus.status_code == 400, refus.text
    assert _etat_en_base(dossier, identifiant)[0] == "en_attente", (
        "une signature invalide a suffi à marquer la commande payée")


def test_une_signature_valide_pour_un_autre_corps_est_refusee(application):
    """Le cas qu'une comparaison naïve laisserait passer : la signature est
    authentique, mais elle couvre un autre message. C'est ainsi qu'on
    substituerait la référence d'une commande à une autre."""
    base, dossier = application
    entetes = _entetes(application, "substituee")
    cible = _commande(base, entetes, "armoire", 200.00)

    autre_corps = _evenement("cs_autre", 1)
    signature_valide = _signer(autre_corps)
    corps_substitue = _evenement("cs_autre", cible)

    refus = requests.post(f"{base}/paiement/webhook", data=corps_substitue,
                          headers={"stripe-signature": signature_valide})
    assert refus.status_code == 400, refus.text
    assert _etat_en_base(dossier, cible)[0] == "en_attente"


def test_une_signature_faite_avec_une_autre_cle_est_refusee(application):
    """La signature est bien formée et couvre bien ce corps — mais elle a été
    produite avec un secret que le serveur ne connaît pas. C'est exactement ce
    que peut fabriquer quelqu'un qui a lu le code généré sans avoir la clé."""
    base, dossier = application
    entetes = _entetes(application, "mauvaiseclef")
    identifiant = _commande(base, entetes, "buffet", 90.00)

    corps = _evenement("cs_pirate", identifiant)
    refus = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"stripe-signature": _signer(corps, secret="whsec_pirate")})
    assert refus.status_code == 400, refus.text
    assert _etat_en_base(dossier, identifiant)[0] == "en_attente"


def test_un_evenement_d_un_autre_type_est_ignore_sans_rien_changer(application):
    """Stripe envoie des dizaines de types d'événements sur le même point de
    terminaison. Tout traiter comme un règlement marquerait payée une commande
    dont la session a seulement expiré."""
    base, dossier = application
    entetes = _entetes(application, "expiree")
    identifiant = _commande(base, entetes, "miroir", 30.00)

    corps = _evenement("cs_expiree", identifiant,
                       type_evenement="checkout.session.expired")
    recu = requests.post(f"{base}/paiement/webhook", data=corps,
                         headers={"stripe-signature": _signer(corps)})
    assert recu.status_code == 200, recu.text
    assert recu.json()["status"] == "ignored"
    assert _etat_en_base(dossier, identifiant)[0] == "en_attente"


def test_regler_deux_fois_le_meme_enregistrement_est_refuse(application, faux_stripe):
    """Une fois la commande payée, plus aucune session ne s'ouvre : sans ce
    verrou, un double clic sur un lien de règlement encaisse deux fois."""
    base, _dossier = application
    entetes = _entetes(application, "doublee")
    identifiant = _commande(base, entetes, "fauteuil", 250.00)

    session = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes).json()
    corps = _evenement(session["session_id"], identifiant)
    requests.post(f"{base}/paiement/webhook", data=corps,
                  headers={"stripe-signature": _signer(corps)})

    avant = len(faux_stripe.recu)
    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=entetes)
    assert refus.status_code == 409, refus.text
    assert len(faux_stripe.recu) == avant, (
        "une seconde session a été ouverte sur une commande déjà réglée")


# ============================== les colonnes de suivi ne sont pas au client ==
def test_le_client_ne_peut_pas_se_declarer_paye_a_la_creation(application):
    """`payment_status` est au serveur, comme un champ `generated`. Un client
    qui l'envoie quand même ne doit pas voir sa valeur atterrir en base —
    sinon la brique entière se contourne par un champ JSON."""
    base, dossier = application
    entetes = _entetes(application, "autoproclamee")

    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": "gratuite", "total": 500.00,
                                  "payment_status": "payee",
                                  "payment_ref": "cs_invente"})
    identifiant = reponse.json()["id"]
    assert _etat_en_base(dossier, identifiant) == ("en_attente", None), (
        _etat_en_base(dossier, identifiant))


def test_une_mise_a_jour_ne_peut_pas_changer_l_etat_de_paiement(application):
    """Même garantie sur l'autre route d'écriture. `Update` est dans le
    workflow précisément pour l'éprouver : une commande réglée qu'on peut
    remettre « en attente » — ou l'inverse — vide le verrou de son sens."""
    base, dossier = application
    entetes = _entetes(application, "modifiee")
    identifiant = _commande(base, entetes, "commode", 75.00)

    modif = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                         json={"libelle": "commode restaurée", "total": 75.00,
                               "payment_status": "payee",
                               "payment_ref": "cs_invente"})
    assert modif.status_code in (200, 201), modif.text
    assert _etat_en_base(dossier, identifiant) == ("en_attente", None)


def test_les_colonnes_de_suivi_sont_absentes_des_schemas_d_entree(application):
    """Le contrat public dit la même chose que le serveur : les deux colonnes
    sont lisibles mais jamais proposées en entrée. On interroge le composant
    réellement référencé par la requête plutôt que le texte de la route — leur
    absence d'une chaîne prouverait aussi bien qu'on a mal cherché."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()

    for methode, chemin in (("post", "/commande"), ("put", "/commande/{id}")):
        reference = schema["paths"][chemin][methode]["requestBody"]["content"][
            "application/json"]["schema"]["$ref"]
        proprietes = schema["components"]["schemas"][
            reference.rsplit("/", 1)[-1]]["properties"]
        assert "total" in proprietes, proprietes
        assert "payment_status" not in proprietes, (methode, proprietes)
        assert "payment_ref" not in proprietes, (methode, proprietes)


# ==================================== la brique n'empêche pas 'monl run' ====
def test_un_projet_payable_passe_le_smoke_test_sans_aucune_cle(tmp_path, monkeypatch):
    """Trouvé en exécutant `monl run`, pas en relisant le code — et c'est
    exactement le genre de défaut que la relecture ne donne pas.

    Le smoke test exige qu'une route non publique refuse une requête sans
    jeton, en 401 ou 403. `/paiement/webhook` est bien protégée, mais par la
    SIGNATURE du prestataire, pas par un JWT : sans clé configurée elle répond
    503, avec clé 400. Le smoke test la recalait donc, et tout projet déclarant
    `payable` échouait au lancement — sur une route qui faisait pourtant
    exactement son travail.

    La correction distingue les deux régimes par ce que le contrat dit déjà :
    une route protégée sans aucun acteur autorisé n'est pas une route à jeton.
    Ce qui reste vrai dans les deux cas, et c'est cela qui est vérifié ici,
    c'est qu'une requête nue est refusée.
    """
    from monl.cli import check_coherence, compile_project
    from monl.smoke_test import run_smoke_test

    for cle in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                "MONL_STRIPE_BASE_URL"):
        monkeypatch.delenv(cle, raising=False)

    projet = tmp_path / "boutique"
    projet.mkdir()
    (projet / "spec.ml").write_text(SPEC_BOUTIQUE, encoding="utf-8")
    compile_project(str(projet / "spec.ml"), str(projet))

    coherent, erreurs_coherence, _w = check_coherence(str(projet))
    assert coherent, erreurs_coherence
    ok, erreurs, _warnings = run_smoke_test(str(projet), say=lambda *_a, **_k: None)
    assert ok, erreurs
