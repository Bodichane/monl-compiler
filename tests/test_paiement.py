"""The `payable` brick tested against a real server and a fake Stripe.

CLAUDE.md says it bluntly: compiling is not behaving correctly, and "any NEW
brick must arrive with its server test". Payment is monl's first brick whose
defect is paid not in a wrong display but in money — it is also the first that
sends a request out of the generated backend. It cannot settle for compile
coverage.

The provider is replaced by a local HTTP server speaking its dialect
(`MONL_STRIPE_BASE_URL`, provided for this in the generated code). It is not
there to politely simulate: it **records what it is sent**, and that record
carries the central guarantee — the charged amount is the DATABASE's, never the
one the client chose to announce. A test bench that merely returned 200 would
let through exactly the bug that costs money.

Three families of guarantees, in order of what they cost if they fall:

* **The amount** — read from the database on every request, insensitive to the
  request body.
* **The webhook signature** — without it, a `curl` marks any order as paid. It
  is the only place in the generated backend where an unauthenticated third
  party can modify a row.
* **The refusals** — 403 for someone else's record, 409 for an already settled
  payment, 400 for a zero amount, 503 when the server has no key. A payment
  must refuse loudly, never fail silently.
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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.cases import check_each_case
from tests.support.server import uvicorn_server

SPEC_BOUTIQUE = """app Boutique

entity Client
    nom: String

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
    quantite: Integer
    total: Money

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

# Since point 79, `payable` REQUIRES the amount to be calculated by the server:
# the creator of an order becomes its owner, hence the payer, and an amount
# they can write is an amount they can negotiate.
rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
"""

MOT_DE_PASSE = "motdepasse123"
CLE_SECRETE = "sk_test_bancdessai"
CLE_WEBHOOK = "whsec_bancdessai"


# ---------------------------------------------------------- the fake Stripe --
class _PrestataireFactice(BaseHTTPRequestHandler):
    """Speaks Stripe's dialect and KEEPS what it was sent.

    The body is `application/x-www-form-urlencoded`, like the real API: decoding
    it here rather than trusting the generated code is what lets us state which
    amount was really requested.
    """

    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.recu.append({
            "chemin": self.path,
            "autorisation": self.headers.get("Authorization", ""),
            "champs": {c: v[0] for c, v
                       in urllib.parse.parse_qs(brut.decode()).items()},
        })
        if self.server.refuser:
            # ensure_ascii=False like the real API: that is what makes the
            # message go through the generated code's `.decode('utf-8')`.
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


# ------------------------------------------------ the generated monl server --
@contextlib.contextmanager
def _application_generee(env_supplementaire):
    """Compiles SPEC_BOUTIQUE and starts an ephemeral uvicorn in a temporary
    folder. The environment is explicit: payment keys are read when the generated
    module is imported, so a test cannot change them afterwards — hence two
    distinct servers, with and without keys."""
    with tempfile.TemporaryDirectory() as dossier:
        ast = MonlAST(parse_monl_string(SPEC_BOUTIQUE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=dossier).generate_all()
        env = {**os.environ}
        for cle in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                    "MONL_STRIPE_BASE_URL"):
            env.pop(cle, None)
        env.update(env_supplementaire)
        with uvicorn_server(dossier, env=env) as base:
            yield base, dossier


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
def application_without_keys():
    """The case of a server put online without configuring payment. It is the
    default situation of every freshly compiled monl project — hence the one the
    smoke test meets, and which must stay green offline."""
    with _application_generee({}) as ouvert:
        yield ouvert


# ------------------------------------------------------------- utilitaires --
@contextlib.contextmanager
def _base_spec(dossier):
    """Opens app.db, committing AND closing on exit (see point 71:
    `with sqlite3.connect(...)` does not close the connection)."""
    cnx = sqlite3.connect(os.path.join(dossier, "app.db"))
    try:
        with cnx:
            yield cnx
    finally:
        cnx.close()


def _entetes(application, identifiant):
    """Registers an account and returns its authentication headers.

    The attempt counter is cleared on the way (5 / 60 s / IP, points 13 and 33):
    this file opens one account per test so that the tests do not implicitly
    order each other.
    """
    base, dossier = application
    with _base_spec(dossier) as cnx:
        cnx.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register",
                  json={"username": identifiant, "password": MOT_DE_PASSE,
                        "actor": "Client"})
    jeton = requests.post(f"{base}/login",
                          json={"username": identifiant,
                                "password": MOT_DE_PASSE}).json()
    assert "access_token" in jeton, jeton
    return {"Authorization": "Bearer " + jeton["access_token"]}


def _order(application, entetes, libelle, total):
    """Creates an order whose DERIVED amount equals `total`.

    Since point 79, `payable` requires a server-calculated amount: the client can
    no longer send it, so this file can no longer set it directly. The test bench
    inserts an item at the wanted price and orders one unit — the resulting amount
    is the same as before, and the sixteen calls of this file keep exactly the
    meaning they had.

    The item is inserted in the database rather than through a route: the bench
    spec opens no administration workflow, and adding one for the test's needs
    would widen the tested surface without proving anything more.
    """
    base, dossier = application
    with _base_spec(dossier) as cnx:
        curseur = cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                              (libelle, total))
        article = curseur.lastrowid
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": libelle, "quantite": 1,
                                  "article_id": article})
    assert reponse.status_code in (200, 201), reponse.text
    return reponse.json()["id"]


def _signer(corps, secret=CLE_WEBHOOK, horodatage=None, version="v1"):
    """Reproduces Stripe's signature: HMAC-SHA256 of "timestamp.body".

    POINT 91: the timestamp now defaults to the CURRENT time, like the one the
    real provider sends. It was frozen at '1700000000' — a November 2023 date — and
    the tests passed because the server never dated it. It is precisely the replay
    freshness closes: a signed call captured once stayed valid forever."""
    if horodatage is None:
        horodatage = str(int(time.time()))
    empreinte = hmac.new(secret.encode(),
                         (horodatage + ".").encode() + corps,
                         hashlib.sha256).hexdigest()
    return f"t={horodatage},{version}={empreinte}"


def _evenement(session_id, reference, type_evenement="checkout.session.completed"):
    # The reference is qualified by the entity ('Commande:id'): it is what the
    # server now sends, so that the webhook never confuses an id of one payable
    # entity with ANOTHER's, in an app declaring several.
    return json.dumps({
        "type": type_evenement,
        "data": {"object": {"id": session_id,
                            "client_reference_id": f"Commande:{reference}"}},
    }).encode()


def _state_in_database(dossier, identifiant):
    with _base_spec(dossier) as cnx:
        return cnx.execute(
            "SELECT payment_status, payment_ref FROM commande WHERE id = ?",
            (identifiant,)).fetchone()


# ======================================= the amount comes from the database --
def test_the_charged_amount_comes_from_the_database_never_the_client(application, faux_stripe):
    """The brick's central guarantee. A cart that sends its own price is a cart
    one can negotiate — the test therefore sends a request body announcing a
    completely different amount, and checks what the provider REALLY received, not
    what the server answered."""
    base, _dossier = application
    entetes = _entetes(application, "acheteuse")
    identifiant = _order(application, entetes, "chaise", 42.50)

    avant = len(faux_stripe.recu)
    reponse = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes,
                            json={"total": 1, "montant_centimes": 1,
                                  "unit_amount": 1})
    assert reponse.status_code == 200, reponse.text

    demande = faux_stripe.recu[avant]
    assert demande["champs"]["line_items[0][price_data][unit_amount]"] == "4250", (
        f"the amount announced by the client was kept: {demande['champs']}")
    assert reponse.json()["montant_centimes"] == 4250, reponse.text
    assert reponse.json()["url"] == "https://paiement.example/session"


def test_the_amount_follows_the_database_when_it_changes(application, faux_stripe):
    """Corollary of the previous one, and it does not go without saying: the
    amount is reread on EVERY request. An amount frozen at creation would let a
    stale price be charged after a correction in the database."""
    base, dossier = application
    entetes = _entetes(application, "revisee")
    identifiant = _order(application, entetes, "table", 10.00)

    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    with _base_spec(dossier) as cnx:
        cnx.execute("UPDATE commande SET total = 99.99 WHERE id = ?", (identifiant,))

    avant = len(faux_stripe.recu)
    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    assert faux_stripe.recu[avant]["champs"][
        "line_items[0][price_data][unit_amount]"] == "9999"


def test_the_session_carries_the_reference_and_the_server_key(application, faux_stripe):
    """`client_reference_id` is the only thread linking the session to the
    payment: it is what the webhook rereads to know which row to mark paid.
    Without it, a successful payment lands on no order."""
    base, _dossier = application
    entetes = _entetes(application, "referencee")
    identifiant = _order(application, entetes, "lampe", 7.00)

    avant = len(faux_stripe.recu)
    requests.post(f"{base}/commande/{identifiant}/paiement", headers=entetes)
    demande = faux_stripe.recu[avant]

    assert demande["chemin"] == "/v1/checkout/sessions"
    assert demande["champs"]["client_reference_id"] == f"Commande:{identifiant}"
    # The key goes in a header, never in the URL nor the body.
    assert demande["autorisation"] == f"Bearer {CLE_SECRETE}"
    assert CLE_SECRETE not in demande["chemin"]


# ========================================================= the refusals ======
def test_paying_another_accounts_record_is_refused(application):
    """Someone else's order is not only unreadable: it is not payable either.
    Without this check, a third party could open payment sessions on rows they
    will never see — and discover their amount through the response."""
    base, _dossier = application
    proprietaire = _entetes(application, "proprietaire")
    identifiant = _order(application, proprietaire, "vélo", 300.00)

    intruse = _entetes(application, "intruse")
    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=intruse)
    assert refus.status_code == 403, refus.text
    assert "belong to you" in refus.json()["detail"]


def test_a_nonexistent_record_gives_404(application):
    base, _dossier = application
    entetes = _entetes(application, "fantome")
    refus = requests.post(f"{base}/commande/999999/paiement", headers=entetes)
    assert refus.status_code == 404, refus.text


def test_a_zero_amount_is_not_charged(application, faux_stripe):
    """Zero is not a price. Letting it through would produce a 0 session at the
    provider, refused on its side — hence an incomprehensible error, far from its
    cause."""
    base, _dossier = application
    entetes = _entetes(application, "gratuite")
    identifiant = _order(application, entetes, "échantillon", 0)

    avant = len(faux_stripe.recu)
    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=entetes)
    assert refus.status_code == 400, refus.text
    assert len(faux_stripe.recu) == avant, (
        "a session was opened for a zero amount")


def test_a_request_without_token_is_refused(application):
    """The payment route is never public: the validator also refuses `payable` on
    a `public` creation, for lack of an identity to attach the payment to."""
    base, _dossier = application
    entetes = _entetes(application, "anonyme")
    identifiant = _order(application, entetes, "livre", 15.00)
    refus = requests.post(f"{base}/commande/{identifiant}/paiement")
    assert refus.status_code in (401, 403), refus.text


def test_the_provider_refusal_comes_up_as_502_with_its_message(application, faux_stripe):
    """When the provider says no, monl must neither pretend everything is fine
    nor hide the reason: 502 and the received message. It is the only information
    whoever debugs has."""
    base, _dossier = application
    entetes = _entetes(application, "recalee")
    identifiant = _order(application, entetes, "canapé", 800.00)

    faux_stripe.refuser = True
    try:
        refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                              headers=entetes)
    finally:
        faux_stripe.refuser = False
    assert refus.status_code == 502, refus.text
    assert "carte refusée" in refus.json()["detail"]


def test_without_key_the_server_refuses_loudly_naming_the_variable(
        application_without_keys):
    """A freshly compiled monl project has no key: the route exists anyway, and
    says which one is missing. Silence — or a 500 — would force reading the
    generated code to understand there is nothing else to configure."""
    base, _dossier = application_without_keys
    entetes = _entetes(application_without_keys, "sansclef")
    identifiant = _order(application_without_keys, entetes, "étagère", 55.00)

    refus = requests.post(f"{base}/commande/{identifiant}/paiement",
                          headers=entetes)
    assert refus.status_code == 503, refus.text
    assert "STRIPE_SECRET_KEY" in refus.json()["detail"]

    # The webhook too, with ITS variable: the two are configured separately.
    refus_webhook = requests.post(f"{base}/paiement/webhook", data=b"{}")
    assert refus_webhook.status_code == 503, refus_webhook.text
    assert "STRIPE_WEBHOOK_SECRET" in refus_webhook.json()["detail"]


def test_the_server_without_key_starts_and_serves_the_rest(application_without_keys):
    """The corollary that counts for the smoke test: the absence of a payment key
    prevents NOTHING else. A backend refusing to start would make `monl run`
    impossible offline."""
    base, _dossier = application_without_keys
    entetes = _entetes(application_without_keys, "ordinaire")
    identifiant = _order(application_without_keys, entetes, "tabouret", 20.00)
    lu = requests.get(f"{base}/commande/{identifiant}", headers=entetes)
    assert lu.status_code == 200, lu.text


# ====================================================== the signature ========
def test_the_signed_webhook_marks_the_record_paid(application):
    """The full journey: order, session, signed notification. It is the only path
    through which `payment_status` changes — no business write route touches it."""
    base, dossier = application
    entetes = _entetes(application, "reglee")
    identifiant = _order(application, entetes, "bureau", 120.00)

    session = requests.post(f"{base}/commande/{identifiant}/paiement",
                            headers=entetes).json()
    corps = _evenement(session["session_id"], identifiant)
    recu = requests.post(f"{base}/paiement/webhook", data=corps,
                         headers={"stripe-signature": _signer(corps)})
    assert recu.status_code == 200, recu.text
    assert recu.json()["status"] == "success"

    etat, reference = _state_in_database(dossier, identifiant)
    assert etat == "payee", etat
    assert reference == session["session_id"], reference

    # And the read says so: without it, the interface could not tell a settled
    # order from a pending one.
    lu = requests.get(f"{base}/commande/{identifiant}", headers=entetes).json()
    assert lu["data"]["payment_status"] == "payee", lu


def test_an_oversized_webhook_is_refused_with_or_without_content_length(
        application):
    """Both HTTP encodings stop before signature parsing."""
    base, _dossier = application
    corps = b"x" * (256 * 1024 + 1)

    annonce = requests.post(f"{base}/paiement/webhook", data=corps, timeout=10)
    morceaux = (corps[i:i + 8192] for i in range(0, len(corps), 8192))
    decoupe = requests.post(
        f"{base}/paiement/webhook", data=morceaux,
        headers={"stripe-signature": "invalide"}, timeout=10,
    )

    assert annonce.status_code == 413, annonce.text
    assert decoupe.status_code == 413, decoupe.text


def test_a_badly_signed_webhook_pays_nothing(application):
    """THE brick's security test. Without signature verification, anyone marks
    any order as paid with a plain `curl` — it is the only place in the generated
    backend where an unauthenticated third party writes to the database. Each form
    of invalid signature is tried separately: a single parsing branch letting it
    through is enough to open the door."""
    table = [
        None,
        "",
        "t=1700000000",
        "v1=" + "0" * 64,
        "t=1700000000,v1=" + "0" * 64,
    ]
    noms = ["absente", "vide", "sans-signature", "sans-horodatage", "forgée"]

    def cas(entete):
        base, dossier = application
        entetes = _entetes(application, f"tentative{abs(hash(str(entete))) % 10000}")
        identifiant = _order(application, entetes, "coffre", 60.00)

        corps = _evenement("cs_forge", identifiant)
        envoi = {} if entete is None else {"stripe-signature": entete}
        refus = requests.post(f"{base}/paiement/webhook", data=corps, headers=envoi)

        assert refus.status_code == 400, refus.text
        assert _state_in_database(dossier, identifiant)[0] == "en_attente", (
            "an invalid signature was enough to mark the order paid")

    check_each_case([(valeur,) for valeur in table], cas, ids=noms)


def test_a_signature_valid_for_another_body_is_refused(application):
    """The case a naive comparison would let through: the signature is authentic,
    but it covers another message. That is how one order's reference would be
    substituted for another."""
    base, dossier = application
    entetes = _entetes(application, "substituee")
    cible = _order(application, entetes, "armoire", 200.00)

    autre_corps = _evenement("cs_autre", 1)
    signature_valide = _signer(autre_corps)
    corps_substitue = _evenement("cs_autre", cible)

    refus = requests.post(f"{base}/paiement/webhook", data=corps_substitue,
                          headers={"stripe-signature": signature_valide})
    assert refus.status_code == 400, refus.text
    assert _state_in_database(dossier, cible)[0] == "en_attente"


def test_a_signature_made_with_another_key_is_refused(application):
    """The signature is well formed and does cover this body — but it was
    produced with a secret the server does not know. It is exactly what someone
    who read the generated code without having the key can forge."""
    base, dossier = application
    entetes = _entetes(application, "mauvaiseclef")
    identifiant = _order(application, entetes, "buffet", 90.00)

    corps = _evenement("cs_pirate", identifiant)
    refus = requests.post(
        f"{base}/paiement/webhook", data=corps,
        headers={"stripe-signature": _signer(corps, secret="whsec_pirate")})
    assert refus.status_code == 400, refus.text
    assert _state_in_database(dossier, identifiant)[0] == "en_attente"


def test_an_event_of_another_type_is_ignored_without_changing_anything(application):
    """Stripe sends dozens of event types to the same endpoint. Treating
    everything as a payment would mark paid an order whose session merely expired."""
    base, dossier = application
    entetes = _entetes(application, "expiree")
    identifiant = _order(application, entetes, "miroir", 30.00)

    corps = _evenement("cs_expiree", identifiant,
                       type_evenement="checkout.session.expired")
    recu = requests.post(f"{base}/paiement/webhook", data=corps,
                         headers={"stripe-signature": _signer(corps)})
    assert recu.status_code == 200, recu.text
    assert recu.json()["status"] == "ignored"
    assert _state_in_database(dossier, identifiant)[0] == "en_attente"


def test_settling_the_same_record_twice_is_refused(application, faux_stripe):
    """Once the order is paid, no more session opens: without this lock, a double
    click on a payment link charges twice."""
    base, _dossier = application
    entetes = _entetes(application, "doublee")
    identifiant = _order(application, entetes, "fauteuil", 250.00)

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
        "a second session was opened on an already settled order")


# ============================== the tracking columns are not for the client --
def test_the_client_cannot_declare_itself_paid_on_creation(application):
    """`payment_status` belongs to the server, like a `generated` field. A client
    sending it anyway must not see its value land in the database — otherwise the
    whole brick is bypassed through a JSON field."""
    base, dossier = application
    entetes = _entetes(application, "autoproclamee")

    with _base_spec(dossier) as cnx:
        article = cnx.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                              ("gratuite", 500.00)).lastrowid
    # `total` is sent too, and also ignored since point 79: the body tries the
    # three fields the server keeps for itself.
    reponse = requests.post(f"{base}/commande", headers=entetes,
                            json={"libelle": "gratuite", "quantite": 1,
                                  "article_id": article, "total": 0.01,
                                  "payment_status": "payee",
                                  "payment_ref": "cs_invente"})
    identifiant = reponse.json()["id"]
    assert _state_in_database(dossier, identifiant) == ("en_attente", None), (
        _state_in_database(dossier, identifiant))
    with _base_spec(dossier) as cnx:
        assert cnx.execute("SELECT total FROM commande WHERE id = ?",
                           (identifiant,)).fetchone()[0] == 500.00


def test_an_update_cannot_change_the_payment_state(application):
    """Same guarantee on the other write route. `Update` is in the workflow
    precisely to test it: a settled order that can be put back "pending" — or the
    reverse — empties the lock of its meaning."""
    base, dossier = application
    entetes = _entetes(application, "modifiee")
    identifiant = _order(application, entetes, "commode", 75.00)

    with _base_spec(dossier) as cnx:
        article = cnx.execute('SELECT article_id FROM commande WHERE id = ?',
                              (identifiant,)).fetchone()[0]
    modif = requests.put(f"{base}/commande/{identifiant}", headers=entetes,
                         json={"libelle": "commode restaurée", "quantite": 1,
                               "article_id": article, "total": 0.01,
                               "payment_status": "payee",
                               "payment_ref": "cs_invente"})
    assert modif.status_code in (200, 201), modif.text
    assert _state_in_database(dossier, identifiant) == ("en_attente", None)
    # The amount cannot be rewritten through this route either (point 79).
    with _base_spec(dossier) as cnx:
        assert cnx.execute("SELECT total FROM commande WHERE id = ?",
                           (identifiant,)).fetchone()[0] == 75.00


def test_the_tracking_columns_are_absent_from_input_schemas(application):
    """The public contract says the same thing as the server: these columns are
    readable but never offered as input. We query the component really referenced
    by the request rather than the route's text — their absence from a string
    would just as well prove we searched badly.

    Since point 79, `total` has joined this list: it is CALCULATED by the server,
    hence absent from input too. The witness becomes `quantite` — one is needed,
    otherwise an empty schema would pass the test."""
    base, _dossier = application
    schema = requests.get(f"{base}/openapi.json").json()

    for methode, chemin in (("post", "/commande"), ("put", "/commande/{id}")):
        reference = schema["paths"][chemin][methode]["requestBody"]["content"][
            "application/json"]["schema"]["$ref"]
        proprietes = schema["components"]["schemas"][
            reference.rsplit("/", 1)[-1]]["properties"]
        assert "quantite" in proprietes, proprietes
        for reserve in ("total", "payment_status", "payment_ref"):
            assert reserve not in proprietes, (methode, reserve, proprietes)


# ==================================== the brick does not prevent monl run ====
def test_a_payable_project_passes_the_smoke_test_without_any_key(tmp_path, monkeypatch):
    """Found by running `monl run`, not by rereading the code — and it is exactly
    the kind of defect rereading does not give.

    The smoke test requires a non-public route to refuse a request without a
    token, with 401 or 403. `/paiement/webhook` is indeed protected, but by the
    provider's SIGNATURE, not by a JWT: without a configured key it answers 503,
    with a key 400. The smoke test therefore failed it, and every project declaring
    `payable` failed at launch — on a route that was doing exactly its job.

    The fix tells the two regimes apart by what the contract already says: a
    protected route with no allowed actor is not a token route. What stays true in
    both cases, and that is what is checked here, is that a bare request is
    refused.
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
