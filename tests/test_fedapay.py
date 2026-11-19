"""Charging by mobile money — brick 2b, FedaPay provider.

Stripe does not operate in West Africa, where money goes through MTN MoMo,
Moov and Wave behind an aggregator. FedaPay is the first one added.

**What is PROVEN here**: that monl speaks the protocol it was described — two
creation calls, a payment URL returned to the browser, and a webhook
signature check matching the official SDK's recipe (`Webhook.ts`: scheme `s`,
message `timestamp + "." + raw body`, hexadecimal HMAC-SHA256, 300-second
tolerance).

**What is NOT**: that a real FedaPay accepts this request body, and above all
the exact JSON PATH of the merchant reference in the webhook event. The
public documentation establishes that `merchant_reference` and
`custom_metadata` exist, but prints no complete payload. The generated code
is therefore *fail-closed*: reference not found ⇒ no write. These two points
remain to be confirmed on a real sandbox account, and this file's fake
provider does not replace them — it proves monl, not FedaPay.
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
from tests.support.cases import check_each_case
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
# What the validator refuses — and the refusal that explains instead of closing
# --------------------------------------------------------------------------

def test_kkiapay_is_refused_saying_why():
    """Refuse by NAMING the reason: "unknown provider" would send people looking
    for a typo in a perfectly correct name.

    KKiaPay publishes neither the algorithm nor the signed data of its webhook.
    Building it by analogy with Stripe or FedaPay would not be an approximation:
    it would be a security hole at the only place of the generated backend where
    an unauthenticated third party writes to the database.
    """
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: kkiapay\n")
    message = str(refus.value)
    assert "kkiapay" in message
    assert "is not implemented by monl, and this is intentional" in message


def test_an_unknown_provider_is_refused():
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: banqueX\n")
    assert "unknown payment provider" in str(refus.value)


def test_two_providers_do_not_compile():
    spec = (SPEC_BOUTIQUE + "\ncapability payment\n    provider: stripe\n"
            + "\ncapability payment\n    provider: fedapay\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "payment provider is declared twice" in str(refus.value)


def test_a_provider_with_nothing_to_charge_is_refused():
    sans = SPEC_BOUTIQUE.replace("rule Commande.total payable\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans + "\ncapability payment\n    provider: fedapay\n")
    assert "payable" in str(refus.value)


def test_a_silent_spec_stays_on_stripe():
    """Non-regression witness: nothing declared, nothing changed."""
    assert _valide(SPEC_BOUTIQUE)["security"]["payment_provider"] is None


# --------------------------------------------------------------------- faux --
class _FedaPayFactice(BaseHTTPRequestHandler):
    """Speaks the FedaPay dialect and KEEPS what it was sent.

    The body is JSON: decoding it here rather than trusting the generated code is
    what lets us state which amount was really requested.
    """

    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
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


def _order(base, dossier, montant, identifiant):
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
    """Reproduces EXACTLY the official SDK's recipe: HMAC-SHA256 of
    "timestamp.body", hexadecimal, under scheme `s`."""
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
# The real journey
# --------------------------------------------------------------------------

def test_both_calls_go_out_with_the_database_amount(faux_fedapay):
    """Creation then token: creation alone returns NO URL, stopping there would
    deliver a "Pay" button leading nowhere."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "awa@example.com")
        faux_fedapay.recu.clear()
        reglement = requests.post(f"{base}/commande/{identifiant}/paiement",
                                  headers=entetes, timeout=10)
        assert reglement.status_code == 200, reglement.text

        chemins = [a["chemin"] for a in faux_fedapay.recu]
        assert chemins == ["/v1/transactions",
                           f"/v1/transactions/{ID_TRANSACTION}/token"]

        creation = faux_fedapay.recu[0]
        assert creation["autorisation"] == f"Bearer {CLE_SECRETE}"
        # The CFA franc has no subunit (brick 2a): 5,000 goes out as 5,000,
        # never 500,000.
        assert creation["corps"]["amount"] == 5000
        assert creation["corps"]["currency"] == {"iso": "XOF"}
        # QUALIFIED reference (point 75): a bare id would be confused with
        # another payable entity's in the same application.
        assert creation["corps"]["merchant_reference"] == f"Commande:{identifiant}"
        assert (creation["corps"]["custom_metadata"]["monl_reference"]
                == f"Commande:{identifiant}")

        assert reglement.json()["url"] == "https://sandbox.fedapay/pay/tok_essai"
        assert reglement.json()["devise"] == "XOF"


def test_the_signed_webhook_marks_the_order_paid(faux_fedapay):
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "leo@example.com")
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


def test_a_badly_signed_webhook_pays_nothing(faux_fedapay):
    table = [
        "",
        "t=1,s=deadbeef",
        "s=deadbeef",
    ]

    def cas(entete):
        with _application(faux_fedapay) as (base, dossier):
            identifiant, entetes = _order(base, dossier, 5000, f"x{len(entete)}@e.fr")
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

    check_each_case([(valeur,) for valeur in table], cas)


def test_a_signature_dated_in_the_future_is_refused(faux_fedapay):
    """monl is STRICTER than the official SDK, on purpose.

    `Webhook.ts` only tests `timestampAge > tolerance`: a timestamp in the FUTURE
    gets through. monl refuses `abs(now - t) > 300`, because a timestamp not
    checked in both directions is no longer a protection against replay (point
    91).
    """
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "futur@example.com")
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


def test_a_payload_of_unknown_shape_writes_nothing(faux_fedapay):
    """FAIL-CLOSED. The reference's JSON path is not proven by the public
    documentation: if the received shape is not the expected one, the server
    writes NOTHING rather than guessing. Being wrong then costs an unrecorded
    payment, not the wrong record marked paid."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "forme@example.com")
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


def test_without_key_the_server_refuses_naming_the_variable(faux_fedapay):
    """Point 74's invariant: 503 naming the missing variable, and the rest of the
    server intact — `monl run` and the smoke test stay green offline."""
    with _application(faux_fedapay, avec_cles=False) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "sanscle@example.com")
        reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                                headers=entetes, timeout=10)
        assert reponse.status_code == 503
        assert "MONL_FEDAPAY_SECRET_KEY" in reponse.text
        # The rest of the server answers anyway: that is the invariant's other
        # half, and it keeps `monl run` and the smoke test green offline. The
        # customer's order is still readable.
        assert requests.get(f"{base}/commande", headers=entetes,
                            timeout=10).status_code == 200


# --------------------------------------------------------------------------
# The currency the provider really charges
# --------------------------------------------------------------------------

def test_fedapay_refuses_a_currency_it_does_not_charge():
    """FedaPay settles ONLY IN XOF — its own documentation says so, and its
    official Odoo module declares only that. Without this refusal, the spec
    compiles and the author only learns it at the first real charge, with a 502,
    in front of a customer who wanted to pay."""
    with pytest.raises(ASTValidationError) as erreur:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n"
                "    provider: fedapay\n    currency: EUR\n")
    message = str(erreur.value)
    assert "XOF" in message and "EUR" in message
    # The message must say WHAT TO WRITE: "incompatible" would leave people
    # searching.
    assert "currency: XOF" in message


def test_fedapay_without_declared_currency_is_refused():
    """The EFFECTIVE currency is compared, not only the declared one. Without a
    `currency` line, the default is the euro: `provider: fedapay` alone therefore
    went charging in euros at a provider that accepts none."""
    with pytest.raises(ASTValidationError) as erreur:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    provider: fedapay\n")
    assert "XOF" in str(erreur.value)


def test_stripe_is_bound_to_no_currency():
    """The table only says `None` where monl does not KNOW — and knowing nothing
    does not allow forbidding. The previous refusal's witness: without it, a too
    broad guard would break every euro spec."""
    assert _valide(SPEC_BOUTIQUE + "\ncapability payment\n"
                   "    provider: stripe\n    currency: EUR\n"
                   )["security"]["payment_provider"] == "stripe"


# --------------------------------------------------------------------------
# Matching the webhook by the provider's identifier
# --------------------------------------------------------------------------

def test_the_provider_reference_is_memorized_at_opening(faux_fedapay):
    """Without this memorization, the webhook fallback has nothing to compare."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "memo@example.com")
        assert _reference(dossier, identifiant) in (None, "")
        requests.post(f"{base}/commande/{identifiant}/paiement",
                      headers=entetes, timeout=10)
        assert _reference(dossier, identifiant) == str(ID_TRANSACTION)
        # Remembering is NOT charging: `payment_status` says whether it is
        # paid, and the contract now says so in plain words.
        assert _etat(dossier, identifiant) == "en_attente"


def test_a_webhook_without_merchant_reference_is_matched_by_id(faux_fedapay):
    """The path FedaPay's official Odoo plugin uses: finding the row by the
    transaction id memorized at creation. It is the only one of the two
    established by code in production — `merchant_reference` is documented on the
    transaction, never on the webhook payload."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "repli@example.com")
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


def test_an_unknown_transaction_id_matches_nothing(faux_fedapay):
    """The fallback's witness: it must recognize ONLY what it memorized. A
    fallback marking the first comer paid would be worse than no fallback at all —
    fail-closed is what holds the whole brick."""
    with _application(faux_fedapay) as (base, dossier):
        identifiant, entetes = _order(base, dossier, 5000, "inconnu@example.com")
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
