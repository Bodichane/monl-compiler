"""A required field born from the DIALOGUE also refuses the EMPTY string.

`required` says a field is PRESENT in the request body, never that it is
FILLED — it is point 85 read literally, and nobody had read it that way from
the guided dialogue. Measured on an archive downloaded by the maintainer: a
catalog record titled `""` entered the database with 200, and the site showed
a card without a name.

This bench starts from the USER PATH — the answers to the dialogue, the spec
it produces, the server that spec produces — and checks BOTH directions: the
empty string is refused, and what is legitimate still passes. An instrument
that refuses everything is as useless as one that accepts everything, and it
looks more serious (point 168).
"""

import contextlib
import copy
import io
import os
from tempfile import TemporaryDirectory

import pytest
import requests

from monl.app_templates import TEMPLATES
from monl.ast_validator import MonlAST
from monl.ast_validator.fields import FieldsMixin
from monl.cli.signature import _contract_signature
from monl.dialogue_engine.emission_parts import TYPES_TEXT, emit_base_rules
from monl.frontend_contract import build_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.support.server import uvicorn_server
from tests.test_app_templates import _run_template

#: The "Online shop" template carries BOTH cases in a single spec:
#: `Customer.displayName` is text (bounded), `Order.total` is a number (never
#: bounded). A single server is therefore enough to test the rule and its
#: limit.
BOUTIQUE = next(i for i, t in enumerate(TEMPLATES, 1)
                if t["name"] == "Online shop")


def _spec(index, response="n", seed=False):
    with contextlib.redirect_stdout(io.StringIO()):
        return _run_template(index, response, want_seed=seed)


def _first_fields(index, response, seed):
    """The FIRST field of each entity, with its type — that is the one the
    dialogue makes required (`emit_base_rules`)."""
    with contextlib.redirect_stdout(io.StringIO()):
        spec = _run_template(index, response, want_seed=seed)
        ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
    rules = {line.strip() for line in spec.splitlines()}
    first_ones = {}
    for name, fields in ast["schema"]["entities"].items():
        if fields:
            first = next(iter(fields))
            first_ones[(name, first)] = fields[first]
    return spec, rules, first_ones


@pytest.fixture(scope="module")
def boutique():
    """Compiles what the dialogue produces for the shop, and runs it."""
    spec = _spec(BOUTIQUE)
    with TemporaryDirectory(prefix="monl-texte-non-vide-") as folder:
        with contextlib.redirect_stdout(io.StringIO()):
            ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
            MonlSecureGenerator(ast, output_dir=folder).generate_all()
        env = os.environ.copy()
        env.pop("MONL_DATABASE_URL", None)
        env["MONL_JWT_SECRET"] = "texte-non-vide-secret-de-32-octets-au-moins"
        with uvicorn_server(folder, env=env) as base:
            yield base


@pytest.fixture(scope="module")
def header(boutique):
    inscription = requests.post(
        f"{boutique}/register",
        json={"username": "acheteuse", "password": "motdepasse8",
              "actor": "Customer"}, timeout=10)
    assert inscription.status_code == 200, inscription.text
    login = requests.post(
        f"{boutique}/login",
        json={"username": "acheteuse", "password": "motdepasse8"}, timeout=10)
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- what the dialogue WRITES ------------------------------------------------

def test_every_required_text_field_is_also_bounded():
    """On the ten templates, in both directions: a first TEXT field made required
    carries `min 1`. That is the rule, swept where it applies."""
    missing = []
    for index, template in enumerate(TEMPLATES, 1):
        for response, seed in (("n", False), ("o", True)):
            _spec_, rules, first_ones = _first_fields(index, response, seed)
            for (entity, field), type_ in first_ones.items():
                required = f"rule {entity}.{field} required" in rules
                bound = f"rule {entity}.{field} min 1" in rules
                if required and type_ in TYPES_TEXT and not bound:
                    missing.append(f"{template['name']} ({response}) : "
                                     f"{entity}.{field} ({type_})")
    assert not missing, (
        "a required text field without a floor accepts the empty string:\n  "
        + "\n  ".join(missing))


def test_a_first_numeric_field_gets_no_floor():
    """The rule's limit, exercised on its PRODUCER.

    A sweep of the ten templates could not measure it: `min 1` is also emitted
    there, on purpose, on the quantities of a stock movement — by a distinct
    decision (a zero-unit movement means nothing). Reading the spec text would
    confuse the two producers; `emit_base_rules` carries the rule, so it is the
    one queried."""
    for type_ in ("Integer", "Float", "Money"):
        lines = []
        emit_base_rules(lines, {"Commande": [("total", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Commande": ["Admin"]},
                        calculated=set())
        assert "rule Commande.total required" in lines, type_
        assert "rule Commande.total min 1" not in lines, (
            f"a floor on {type_} would forbid the value zero: {lines}")


def test_a_first_text_field_gets_its_floor():
    """The counter-proof of the witness above: without it, a function that never
    emitted a floor again would make both green."""
    for type_ in TYPES_TEXT:
        lines = []
        emit_base_rules(lines, {"Fiche": [("titre", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Fiche": ["Admin"]},
                        calculated=set())
        assert "rule Fiche.titre min 1" in lines, (type_, lines)


def test_the_shop_bounds_its_name_not_its_total():
    """Both cases side by side in a REAL spec, the one running this file's
    server."""
    rules = {line.strip() for line in _spec(BOUTIQUE).splitlines()}
    assert "rule Customer.displayName min 1" in rules
    assert "rule Order.total required" in rules
    assert "rule Order.total min 1" not in rules


def test_the_text_type_list_comes_from_the_compiler():
    """It is not copied: a second list would end up diverging, and the dialogue
    would emit a rule the compiler refuses — the worst outcome for someone being
    guided (point 173)."""
    assert TYPES_TEXT is FieldsMixin.BOUNDS_TEXT


# --- what the SERVER does ----------------------------------------------------

def test_the_server_refuses_an_empty_text_field(boutique, header):
    """The defect measured on the maintainer's archive, at its source."""
    response = requests.post(f"{boutique}/customer", headers=header,
                            json={"displayName": ""}, timeout=10)
    assert response.status_code == 422, response.text


def test_the_server_also_refuses_a_whitespace_only_field(
        boutique, header):
    """Empty after strip is refused before insertion."""
    response = requests.post(f"{boutique}/customer", headers=header,
                            json={"displayName": "   "}, timeout=10)
    assert response.status_code == 422, response.text


def test_the_server_still_accepts_a_named_record(boutique, header):
    """The counter-proof telling a right floor from a floor that refuses
    everything."""
    response = requests.post(f"{boutique}/customer", headers=header,
                            json={"displayName": " a "}, timeout=10)
    assert response.status_code == 200, response.text
    # Reread IN THE DATABASE: a status code says the route answered, never that
    # the value arrived.
    fiche = requests.get(f"{boutique}/customer/{response.json()['id']}",
                         headers=header, timeout=10)
    assert fiche.status_code == 200, fiche.text
    assert fiche.json()["data"]["displayName"] == " a "


def test_a_zero_total_stays_accepted(boutique, header):
    """The limit, tested against the server and not only in the spec: an empty
    cart is worth zero, and refusing it would break the shop."""
    response = requests.post(f"{boutique}/order", headers=header,
                            json={"total": 0, "status": "nouvelle"}, timeout=10)
    assert response.status_code == 200, response.text


def test_update_refuses_empty_without_changing_the_value(boutique, header):
    creation = requests.post(f"{boutique}/customer", headers=header,
                             json={"displayName": " a "}, timeout=10)
    assert creation.status_code == 200, creation.text
    url = f"{boutique}/customer/{creation.json()['id']}"
    refusal = requests.put(url, headers=header, json={"displayName": "   "}, timeout=10)
    assert refusal.status_code == 422, refusal.text
    assert requests.get(url, headers=header, timeout=10).json()["data"]["displayName"] == " a "
    accepted = requests.put(url, headers=header, json={"displayName": " a "}, timeout=10)
    assert accepted.status_code == 200, accepted.text
    assert requests.get(url, headers=header, timeout=10).json()["data"]["displayName"] == " a "


def test_non_required_text_stays_accepted(boutique, header):
    creation = requests.post(f"{boutique}/order", headers=header,
                             json={"total": 0, "status": "   "}, timeout=10)
    assert creation.status_code == 200, creation.text
    url = f"{boutique}/order/{creation.json()['id']}"
    assert requests.get(url, headers=header, timeout=10).json()["data"]["status"] == "   "
    update = requests.put(url, headers=header, json={"total": 0, "status": "   "}, timeout=10)
    assert update.status_code == 200, update.text
    assert requests.get(url, headers=header, timeout=10).json()["data"]["status"] == "   "


def test_contract_announces_non_blank_and_the_signature_sees_it(tmp_path):
    # Without min 1: the promise belongs to required, not to the dialogue
    # alone.
    spec = _spec(BOUTIQUE).replace("rule Customer.displayName min 1", "")
    with contextlib.redirect_stdout(io.StringIO()):
        ast = MonlAST(parse_monl_string(spec)).validate_and_audit()
        generator = MonlSecureGenerator(ast, output_dir=str(tmp_path))
        contract = build_contract(ast, generator)
    fields = {f"{entity}.{field['name']}": field
              for entity, model in contract["entities"].items()
              for field in model["fields"]}
    assert fields["Customer.displayName"]["non_blank"] is True
    assert "non_blank" not in fields["Order.status"]
    assert "non_blank" not in fields["Order.total"]
    previous = copy.deepcopy(contract)
    for model in previous["entities"].values():
        for field in model["fields"]:
            field.pop("non_blank", None)
    assert _contract_signature(previous) != _contract_signature(contract)
    assert "@field_validator('displayName')" in "\n".join(generator._generate_schema_lines())
