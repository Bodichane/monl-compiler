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

PASSWORD = "motdepasse123"
KEY_SECRETE = "sk_test_bancdessai"
KEY_WEBHOOK = "whsec_bancdessai"


# ---------------------------------------------------------- the fake Stripe --
class _ProviderFake(BaseHTTPRequestHandler):
    """Speaks Stripe's dialect and KEEPS what it was sent.

    The body is `application/x-www-form-urlencoded`, like the real API: decoding
    it here rather than trusting the generated code is what lets us state which
    amount was really requested.
    """

    def do_POST(self):  # name imposed by BaseHTTPRequestHandler
        brut = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.received.append({
            "chemin": self.path,
            "autorisation": self.headers.get("Authorization", ""),
            "champs": {c: v[0] for c, v
                       in urllib.parse.parse_qs(brut.decode()).items()},
        })
        if self.server.refuse:
            # ensure_ascii=False like the real API: that is what makes the
            # message go through the generated code's `.decode('utf-8')`.
            body = json.dumps({"error": {"message": "carte refusée"}},
                               ensure_ascii=False).encode()
            self.send_response(402)
        else:
            body = json.dumps({
                "id": f"cs_test_{len(self.server.received)}",
                "url": "https://paiement.example/session",
            }).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture(scope="module")
def faux_stripe():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderFake)
    server.received = []
    server.refuse = False
    fil = threading.Thread(target=server.serve_forever, daemon=True)
    fil.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        fil.join(timeout=5)


# ------------------------------------------------ the generated monl server --
@contextlib.contextmanager
def _application_generated(env_extra):
    """Compiles SPEC_BOUTIQUE and starts an ephemeral uvicorn in a temporary
    folder. The environment is explicit: payment keys are read when the generated
    module is imported, so a test cannot change them afterwards — hence two
    distinct servers, with and without keys."""
    with tempfile.TemporaryDirectory() as folder:
        ast = MonlAST(parse_monl_string(SPEC_BOUTIQUE)).validate_and_audit()
        MonlSecureGenerator(ast, output_dir=folder).generate_all()
        env = {**os.environ}
        for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                    "MONL_STRIPE_BASE_URL"):
            env.pop(key, None)
        env.update(env_extra)
        with uvicorn_server(folder, env=env) as base:
            yield base, folder


@pytest.fixture(scope="module")
def application(faux_stripe):
    hote, port = faux_stripe.server_address[:2]
    with _application_generated({
        "STRIPE_SECRET_KEY": KEY_SECRETE,
        "STRIPE_WEBHOOK_SECRET": KEY_WEBHOOK,
        "MONL_STRIPE_BASE_URL": f"http://{hote}:{port}",
    }) as ouvert:
        yield ouvert


@pytest.fixture(scope="module")
def application_without_keys():
    """The case of a server put online without configuring payment. It is the
    default situation of every freshly compiled monl project — hence the one the
    smoke test meets, and which must stay green offline."""
    with _application_generated({}) as ouvert:
        yield ouvert


# ------------------------------------------------------------- utilitaires --
@contextlib.contextmanager
def _base_spec(folder):
    """Opens app.db, committing AND closing on exit (see point 71:
    `with sqlite3.connect(...)` does not close the connection)."""
    conn = sqlite3.connect(os.path.join(folder, "app.db"))
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _headers(application, identifier):
    """Registers an account and returns its authentication headers.

    The attempt counter is cleared on the way (5 / 60 s / IP, points 13 and 33):
    this file opens one account per test so that the tests do not implicitly
    order each other.
    """
    base, folder = application
    with _base_spec(folder) as conn:
        conn.execute("DELETE FROM _monl_rate_limit")
    requests.post(f"{base}/register",
                  json={"username": identifier, "password": PASSWORD,
                        "actor": "Client"})
    token = requests.post(f"{base}/login",
                          json={"username": identifier,
                                "password": PASSWORD}).json()
    assert "access_token" in token, token
    return {"Authorization": "Bearer " + token["access_token"]}


def _order(application, headers, label, total):
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
    base, folder = application
    with _base_spec(folder) as conn:
        cursor = conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                              (label, total))
        article = cursor.lastrowid
    response = requests.post(f"{base}/commande", headers=headers,
                            json={"libelle": label, "quantite": 1,
                                  "article_id": article})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _signer(body, secret=KEY_WEBHOOK, timestamp=None, version="v1"):
    """Reproduces Stripe's signature: HMAC-SHA256 of "timestamp.body".

    POINT 91: the timestamp now defaults to the CURRENT time, like the one the
    real provider sends. It was frozen at '1700000000' — a November 2023 date — and
    the tests passed because the server never dated it. It is precisely the replay
    freshness closes: a signed call captured once stayed valid forever."""
    if timestamp is None:
        timestamp = str(int(time.time()))
    fingerprint = hmac.new(secret.encode(),
                         (timestamp + ".").encode() + body,
                         hashlib.sha256).hexdigest()
    return f"t={timestamp},{version}={fingerprint}"


def _event(session_id, reference, type_event="checkout.session.completed"):
    # The reference is qualified by the entity ('Commande:id'): it is what the
    # server now sends, so that the webhook never confuses an id of one payable
    # entity with ANOTHER's, in an app declaring several.
    return json.dumps({
        "type": type_event,
        "data": {"object": {"id": session_id,
                            "client_reference_id": f"Commande:{reference}"}},
    }).encode()


def _state_in_database(folder, identifier):
    with _base_spec(folder) as conn:
        return conn.execute(
            "SELECT payment_status, payment_ref FROM commande WHERE id = ?",
            (identifier,)).fetchone()


# ======================================= the amount comes from the database --
def test_the_charged_amount_comes_from_the_database_never_the_client(application, faux_stripe):
    """The brick's central guarantee. A cart that sends its own price is a cart
    one can negotiate — the test therefore sends a request body announcing a
    completely different amount, and checks what the provider REALLY received, not
    what the server answered."""
    base, _folder = application
    headers = _headers(application, "acheteuse")
    identifier = _order(application, headers, "chaise", 42.50)

    before = len(faux_stripe.received)
    response = requests.post(f"{base}/commande/{identifier}/paiement",
                            headers=headers,
                            json={"total": 1, "montant_centimes": 1,
                                  "unit_amount": 1})
    assert response.status_code == 200, response.text

    request = faux_stripe.received[before]
    assert request["champs"]["line_items[0][price_data][unit_amount]"] == "4250", (
        f"the amount announced by the client was kept: {request['champs']}")
    assert response.json()["montant_centimes"] == 4250, response.text
    assert response.json()["url"] == "https://paiement.example/session"


def test_the_amount_follows_the_database_when_it_changes(application, faux_stripe):
    """Corollary of the previous one, and it does not go without saying: the
    amount is reread on EVERY request. An amount frozen at creation would let a
    stale price be charged after a correction in the database."""
    base, folder = application
    headers = _headers(application, "revisee")
    identifier = _order(application, headers, "table", 10.00)

    requests.post(f"{base}/commande/{identifier}/paiement", headers=headers)
    with _base_spec(folder) as conn:
        conn.execute("UPDATE commande SET total = 99.99 WHERE id = ?", (identifier,))

    before = len(faux_stripe.received)
    requests.post(f"{base}/commande/{identifier}/paiement", headers=headers)
    assert faux_stripe.received[before]["champs"][
        "line_items[0][price_data][unit_amount]"] == "9999"


def test_the_session_carries_the_reference_and_the_server_key(application, faux_stripe):
    """`client_reference_id` is the only thread linking the session to the
    payment: it is what the webhook rereads to know which row to mark paid.
    Without it, a successful payment lands on no order."""
    base, _folder = application
    headers = _headers(application, "referencee")
    identifier = _order(application, headers, "lampe", 7.00)

    before = len(faux_stripe.received)
    requests.post(f"{base}/commande/{identifier}/paiement", headers=headers)
    request = faux_stripe.received[before]

    assert request["chemin"] == "/v1/checkout/sessions"
    assert request["champs"]["client_reference_id"] == f"Commande:{identifier}"
    # The key goes in a header, never in the URL nor the body.
    assert request["autorisation"] == f"Bearer {KEY_SECRETE}"
    assert KEY_SECRETE not in request["chemin"]


# ========================================================= the refusals ======
def test_paying_another_accounts_record_is_refused(application):
    """Someone else's order is not only unreadable: it is not payable either.
    Without this check, a third party could open payment sessions on rows they
    will never see — and discover their amount through the response."""
    base, _folder = application
    owner = _headers(application, "proprietaire")
    identifier = _order(application, owner, "vélo", 300.00)

    intruder = _headers(application, "intruse")
    refusal = requests.post(f"{base}/commande/{identifier}/paiement",
                          headers=intruder)
    assert refusal.status_code == 403, refusal.text
    assert "belong to you" in refusal.json()["detail"]


def test_a_nonexistent_record_gives_404(application):
    base, _folder = application
    headers = _headers(application, "fantome")
    refusal = requests.post(f"{base}/commande/999999/paiement", headers=headers)
    assert refusal.status_code == 404, refusal.text


def test_a_zero_amount_is_not_charged(application, faux_stripe):
    """Zero is not a price. Letting it through would produce a 0 session at the
    provider, refused on its side — hence an incomprehensible error, far from its
    cause."""
    base, _folder = application
    headers = _headers(application, "gratuite")
    identifier = _order(application, headers, "échantillon", 0)

    before = len(faux_stripe.received)
    refusal = requests.post(f"{base}/commande/{identifier}/paiement",
                          headers=headers)
    assert refusal.status_code == 400, refusal.text
    assert len(faux_stripe.received) == before, (
        "a session was opened for a zero amount")


def test_a_request_without_token_is_refused(application):
    """The payment route is never public: the validator also refuses `payable` on
    a `public` creation, for lack of an identity to attach the payment to."""
    base, _folder = application
    headers = _headers(application, "anonyme")
    identifier = _order(application, headers, "livre", 15.00)
    refusal = requests.post(f"{base}/commande/{identifier}/paiement")
    assert refusal.status_code in (401, 403), refusal.text


def test_the_provider_refusal_comes_up_as_502_with_its_message(application, faux_stripe):
    """When the provider says no, monl must neither pretend everything is fine
    nor hide the reason: 502 and the received message. It is the only information
    whoever debugs has."""
    base, _folder = application
    headers = _headers(application, "recalee")
    identifier = _order(application, headers, "canapé", 800.00)

    faux_stripe.refuse = True
    try:
        refusal = requests.post(f"{base}/commande/{identifier}/paiement",
                              headers=headers)
    finally:
        faux_stripe.refuse = False
    assert refusal.status_code == 502, refusal.text
    assert "carte refusée" in refusal.json()["detail"]


def test_without_key_the_server_refuses_loudly_naming_the_variable(
        application_without_keys):
    """A freshly compiled monl project has no key: the route exists anyway, and
    says which one is missing. Silence — or a 500 — would force reading the
    generated code to understand there is nothing else to configure."""
    base, _folder = application_without_keys
    headers = _headers(application_without_keys, "sansclef")
    identifier = _order(application_without_keys, headers, "étagère", 55.00)

    refusal = requests.post(f"{base}/commande/{identifier}/paiement",
                          headers=headers)
    assert refusal.status_code == 503, refusal.text
    assert "STRIPE_SECRET_KEY" in refusal.json()["detail"]

    # The webhook too, with ITS variable: the two are configured separately.
    refusal_webhook = requests.post(f"{base}/paiement/webhook", data=b"{}")
    assert refusal_webhook.status_code == 503, refusal_webhook.text
    assert "STRIPE_WEBHOOK_SECRET" in refusal_webhook.json()["detail"]


def test_the_server_without_key_starts_and_serves_the_rest(application_without_keys):
    """The corollary that counts for the smoke test: the absence of a payment key
    prevents NOTHING else. A backend refusing to start would make `monl run`
    impossible offline."""
    base, _folder = application_without_keys
    headers = _headers(application_without_keys, "ordinaire")
    identifier = _order(application_without_keys, headers, "tabouret", 20.00)
    lu = requests.get(f"{base}/commande/{identifier}", headers=headers)
    assert lu.status_code == 200, lu.text


# ====================================================== the signature ========
def test_the_signed_webhook_marks_the_record_paid(application):
    """The full journey: order, session, signed notification. It is the only path
    through which `payment_status` changes — no business write route touches it."""
    base, folder = application
    headers = _headers(application, "reglee")
    identifier = _order(application, headers, "bureau", 120.00)

    session = requests.post(f"{base}/commande/{identifier}/paiement",
                            headers=headers).json()
    body = _event(session["session_id"], identifier)
    received = requests.post(f"{base}/paiement/webhook", data=body,
                         headers={"stripe-signature": _signer(body)})
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "success"

    state, reference = _state_in_database(folder, identifier)
    assert state == "payee", state
    assert reference == session["session_id"], reference

    # And the read says so: without it, the interface could not tell a settled
    # order from a pending one.
    lu = requests.get(f"{base}/commande/{identifier}", headers=headers).json()
    assert lu["data"]["payment_status"] == "payee", lu


def test_an_oversized_webhook_is_refused_with_or_without_content_length(
        application):
    """Both HTTP encodings stop before signature parsing."""
    base, _folder = application
    body = b"x" * (256 * 1024 + 1)

    announced = requests.post(f"{base}/paiement/webhook", data=body, timeout=10)
    chunks = (body[i:i + 8192] for i in range(0, len(body), 8192))
    cut = requests.post(
        f"{base}/paiement/webhook", data=chunks,
        headers={"stripe-signature": "invalide"}, timeout=10,
    )

    assert announced.status_code == 413, announced.text
    assert cut.status_code == 413, cut.text


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
    names = ["absente", "vide", "sans-signature", "sans-horodatage", "forgée"]

    def cas(header):
        base, folder = application
        headers = _headers(application, f"tentative{abs(hash(str(header))) % 10000}")
        identifier = _order(application, headers, "coffre", 60.00)

        body = _event("cs_forge", identifier)
        sending = {} if header is None else {"stripe-signature": header}
        refusal = requests.post(f"{base}/paiement/webhook", data=body, headers=sending)

        assert refusal.status_code == 400, refusal.text
        assert _state_in_database(folder, identifier)[0] == "en_attente", (
            "an invalid signature was enough to mark the order paid")

    check_each_case([(valeur,) for valeur in table], cas, ids=names)


def test_a_signature_valid_for_another_body_is_refused(application):
    """The case a naive comparison would let through: the signature is authentic,
    but it covers another message. That is how one order's reference would be
    substituted for another."""
    base, folder = application
    headers = _headers(application, "substituee")
    target = _order(application, headers, "armoire", 200.00)

    other_body = _event("cs_autre", 1)
    signature_valid = _signer(other_body)
    body_substituted = _event("cs_autre", target)

    refusal = requests.post(f"{base}/paiement/webhook", data=body_substituted,
                          headers={"stripe-signature": signature_valid})
    assert refusal.status_code == 400, refusal.text
    assert _state_in_database(folder, target)[0] == "en_attente"


def test_a_signature_made_with_another_key_is_refused(application):
    """The signature is well formed and does cover this body — but it was
    produced with a secret the server does not know. It is exactly what someone
    who read the generated code without having the key can forge."""
    base, folder = application
    headers = _headers(application, "mauvaiseclef")
    identifier = _order(application, headers, "buffet", 90.00)

    body = _event("cs_pirate", identifier)
    refusal = requests.post(
        f"{base}/paiement/webhook", data=body,
        headers={"stripe-signature": _signer(body, secret="whsec_pirate")})
    assert refusal.status_code == 400, refusal.text
    assert _state_in_database(folder, identifier)[0] == "en_attente"


def test_an_event_of_another_type_is_ignored_without_changing_anything(application):
    """Stripe sends dozens of event types to the same endpoint. Treating
    everything as a payment would mark paid an order whose session merely expired."""
    base, folder = application
    headers = _headers(application, "expiree")
    identifier = _order(application, headers, "miroir", 30.00)

    body = _event("cs_expiree", identifier,
                       type_event="checkout.session.expired")
    received = requests.post(f"{base}/paiement/webhook", data=body,
                         headers={"stripe-signature": _signer(body)})
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "ignored"
    assert _state_in_database(folder, identifier)[0] == "en_attente"


def test_settling_the_same_record_twice_is_refused(application, faux_stripe):
    """Once the order is paid, no more session opens: without this lock, a double
    click on a payment link charges twice."""
    base, _folder = application
    headers = _headers(application, "doublee")
    identifier = _order(application, headers, "fauteuil", 250.00)

    session = requests.post(f"{base}/commande/{identifier}/paiement",
                            headers=headers).json()
    body = _event(session["session_id"], identifier)
    requests.post(f"{base}/paiement/webhook", data=body,
                  headers={"stripe-signature": _signer(body)})

    before = len(faux_stripe.received)
    refusal = requests.post(f"{base}/commande/{identifier}/paiement",
                          headers=headers)
    assert refusal.status_code == 409, refusal.text
    assert len(faux_stripe.received) == before, (
        "a second session was opened on an already settled order")


# ============================== the tracking columns are not for the client --
def test_the_client_cannot_declare_itself_paid_on_creation(application):
    """`payment_status` belongs to the server, like a `generated` field. A client
    sending it anyway must not see its value land in the database — otherwise the
    whole brick is bypassed through a JSON field."""
    base, folder = application
    headers = _headers(application, "autoproclamee")

    with _base_spec(folder) as conn:
        article = conn.execute('INSERT INTO article (nom, prix) VALUES (?, ?)',
                              ("gratuite", 500.00)).lastrowid
    # `total` is sent too, and also ignored since point 79: the body tries the
    # three fields the server keeps for itself.
    response = requests.post(f"{base}/commande", headers=headers,
                            json={"libelle": "gratuite", "quantite": 1,
                                  "article_id": article, "total": 0.01,
                                  "payment_status": "payee",
                                  "payment_ref": "cs_invente"})
    identifier = response.json()["id"]
    assert _state_in_database(folder, identifier) == ("en_attente", None), (
        _state_in_database(folder, identifier))
    with _base_spec(folder) as conn:
        assert conn.execute("SELECT total FROM commande WHERE id = ?",
                           (identifier,)).fetchone()[0] == 500.00


def test_an_update_cannot_change_the_payment_state(application):
    """Same guarantee on the other write route. `Update` is in the workflow
    precisely to test it: a settled order that can be put back "pending" — or the
    reverse — empties the lock of its meaning."""
    base, folder = application
    headers = _headers(application, "modifiee")
    identifier = _order(application, headers, "commode", 75.00)

    with _base_spec(folder) as conn:
        article = conn.execute('SELECT article_id FROM commande WHERE id = ?',
                              (identifier,)).fetchone()[0]
    change = requests.put(f"{base}/commande/{identifier}", headers=headers,
                         json={"libelle": "commode restaurée", "quantite": 1,
                               "article_id": article, "total": 0.01,
                               "payment_status": "payee",
                               "payment_ref": "cs_invente"})
    assert change.status_code in (200, 201), change.text
    assert _state_in_database(folder, identifier) == ("en_attente", None)
    # The amount cannot be rewritten through this route either (point 79).
    with _base_spec(folder) as conn:
        assert conn.execute("SELECT total FROM commande WHERE id = ?",
                           (identifier,)).fetchone()[0] == 75.00


def test_the_tracking_columns_are_missing_from_input_schemas(application):
    """The public contract says the same thing as the server: these columns are
    readable but never offered as input. We query the component really referenced
    by the request rather than the route's text — their absence from a string
    would just as well prove we searched badly.

    Since point 79, `total` has joined this list: it is CALCULATED by the server,
    hence absent from input too. The witness becomes `quantite` — one is needed,
    otherwise an empty schema would pass the test."""
    base, _folder = application
    schema = requests.get(f"{base}/openapi.json").json()

    for method, path in (("post", "/commande"), ("put", "/commande/{id}")):
        reference = schema["paths"][path][method]["requestBody"]["content"][
            "application/json"]["schema"]["$ref"]
        properties = schema["components"]["schemas"][
            reference.rsplit("/", 1)[-1]]["properties"]
        assert "quantite" in properties, properties
        for reserve in ("total", "payment_status", "payment_ref"):
            assert reserve not in properties, (method, reserve, properties)


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

    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                "MONL_STRIPE_BASE_URL"):
        monkeypatch.delenv(key, raising=False)

    project = tmp_path / "boutique"
    project.mkdir()
    (project / "spec.ml").write_text(SPEC_BOUTIQUE, encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))

    coherent, errors_coherence, _w = check_coherence(str(project))
    assert coherent, errors_coherence
    ok, errors, _warnings = run_smoke_test(str(project), say=lambda *_a, **_k: None)
    assert ok, errors
