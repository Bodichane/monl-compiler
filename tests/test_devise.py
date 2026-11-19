"""The charging currency and its EXPONENT — brick 2a.

The code froze two things: the currency (`'eur'`) and the conversion factor
(`amount × 100`). The second is the real danger. A provider expects an
INTEGER in the currency's minor unit; for the euro that is the cent, hence
×100. **The CFA franc has no subunit**: a 5,000 FCFA order would have gone to
the provider for 500,000 FCFA — a hundred times the price.

This defect shows neither on reading (the calculation is right for the
euro), nor in the existing tests (they charge in euros), nor at runtime on
monl's side (the server answers 200). It shows on the customer's bank
statement. It is point 77's family — the amount someone else decides —
through a door nobody had opened: UNITS.

**The test carrying the brick is a PAIR**: the same 5,000 order, compiled in
XOF then in EUR, and what the fake provider really received. Taken alone, the
XOF case would pass with a `×100` forgotten somewhere if the other half of
the chain compensated; taken alone, the EUR case would prove no regression.
Together, they pin the factor.
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

# The fake provider is the payment bench's: it decodes the
# `x-www-form-urlencoded` body and KEEPS the received fields. Rewriting it here
# would give two fake providers to maintain, and that is exactly what a
# duplicate decoder ends up hiding.
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
# What the validator refuses — and why it refuses rather than guesses
# --------------------------------------------------------------------------

def test_an_unknown_currency_is_refused_never_guessed():
    """Guessing "two decimals" would bring back the bug being closed."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    currency: ZZZ\n")
    message = str(refus.value)
    assert "ZZZ" in message
    assert "multiply every amount by one hundred" in message


def test_a_three_decimal_currency_is_refused_with_a_reason():
    """The Tunisian dinar is a perfectly valid code: the message must not send
    people looking for a typo."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability payment\n    currency: TND\n")
    assert "three decimal places" in str(refus.value)


def test_currency_on_capability_auth_names_the_right_capability():
    """The grammar shares a single set of properties between capabilities: a
    line in the wrong place is the expected error, not a typo."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_BOUTIQUE + "\ncapability auth\n    currency: XOF\n")
    assert "capability payment" in str(refus.value)


def test_two_currencies_do_not_compile():
    spec = (SPEC_BOUTIQUE + "\ncapability payment\n    currency: XOF\n"
            + "\ncapability payment\n    currency: EUR\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "currency is declared twice" in str(refus.value)


def test_a_currency_with_nothing_to_charge_is_refused():
    """Point 85: a rule without effect is refused, never silently ignored —
    otherwise the author believes they configured their application."""
    sans_paiement = SPEC_BOUTIQUE.replace("rule Commande.total payable\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans_paiement + "\ncapability payment\n    currency: XOF\n")
    assert "payable" in str(refus.value)


def test_a_silent_spec_keeps_the_euro_and_the_factor_of_100():
    """The non-regression witness: nothing declared, nothing changed."""
    ast = _valide(SPEC_BOUTIQUE)
    assert ast["security"]["payment_currency"] is None


def test_the_declared_currency_carries_its_exponent():
    devise = _valide(SPEC_XOF)["security"]["payment_currency"]
    assert devise == {"code": "XOF", "exponent": 0}


# --------------------------------------------------------------------------
# What the provider REALLY receives — the pair that carries the brick
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


def _pay_an_order_of(spec, faux_prestataire, montant, identifiant):
    """Registers an account, creates an order of `montant`, pays it — and returns
    the fields the provider really received."""
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
        assert faux_prestataire.recu, "the provider received nothing"
        return faux_prestataire.recu[-1]["champs"], reglement.json()


def test_in_cfa_franc_the_amount_goes_as_is(faux_prestataire):
    """5,000 FCFA must go out as 5,000, never 500,000."""
    champs, reponse = _pay_an_order_of(
        SPEC_XOF, faux_prestataire, 5000, "awa@example.com")

    assert champs["line_items[0][price_data][currency]"] == "xof"
    assert champs["line_items[0][price_data][unit_amount]"] == "5000", (
        "the CFA franc has no subunit: multiplying by a hundred would bill "
        "a hundred times the price")
    assert reponse["devise"] == "XOF"
    assert reponse["montant"] == 5000


def test_in_euro_the_amount_stays_in_cents(faux_prestataire):
    """The other half of the pair: without it, a factor of 1 applied everywhere
    would pass the test above while breaking the euro."""
    champs, reponse = _pay_an_order_of(
        SPEC_BOUTIQUE, faux_prestataire, 5000, "leo@example.com")

    assert champs["line_items[0][price_data][currency]"] == "eur"
    assert champs["line_items[0][price_data][unit_amount]"] == "500000"
    assert reponse["devise"] == "EUR"


def test_the_readable_amount_goes_with_the_minor_unit(faux_prestataire):
    """`montant_centimes` KEEPS its name on the wire (point 95: renaming would
    break every existing project's "Pay" button), but `devise` and `montant` now
    sit beside it — an interface no longer has to divide by a hundred at random."""
    _champs, reponse = _pay_an_order_of(
        SPEC_XOF, faux_prestataire, 2500, "koffi@example.com")
    assert reponse["montant_centimes"] == 2500
    assert reponse["montant"] == 2500
    assert reponse["devise"] == "XOF"
