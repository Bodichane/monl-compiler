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
from monl.ast_validator.champs import ChampsMixin
from monl.cli.signature import _contract_signature
from monl.dialogue_engine.emission_parts import TYPES_TEXTE, emit_base_rules
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


def _spec(index, reponse="n", seed=False):
    with contextlib.redirect_stdout(io.StringIO()):
        return _run_template(index, reponse, want_seed=seed)


def _first_fields(index, reponse, seed):
    """The FIRST field of each entity, with its type — that is the one the
    dialogue makes required (`emit_base_rules`)."""
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
    """Compiles what the dialogue produces for the shop, and runs it."""
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


# --- what the dialogue WRITES ------------------------------------------------

def test_every_required_text_field_is_also_bounded():
    """On the ten templates, in both directions: a first TEXT field made required
    carries `min 1`. That is the rule, swept where it applies."""
    manquants = []
    for index, modele in enumerate(TEMPLATES, 1):
        for reponse, seed in (("n", False), ("o", True)):
            _spec_, regles, premiers = _first_fields(index, reponse, seed)
            for (entite, champ), type_ in premiers.items():
                obligatoire = f"rule {entite}.{champ} required" in regles
                borne = f"rule {entite}.{champ} min 1" in regles
                if obligatoire and type_ in TYPES_TEXTE and not borne:
                    manquants.append(f"{modele['name']} ({reponse}) : "
                                     f"{entite}.{champ} ({type_})")
    assert not manquants, (
        "a required text field without a floor accepts the empty string:\n  "
        + "\n  ".join(manquants))


def test_a_first_numeric_field_gets_no_floor():
    """The rule's limit, exercised on its PRODUCER.

    A sweep of the ten templates could not measure it: `min 1` is also emitted
    there, on purpose, on the quantities of a stock movement — by a distinct
    decision (a zero-unit movement means nothing). Reading the spec text would
    confuse the two producers; `emit_base_rules` carries the rule, so it is the
    one queried."""
    for type_ in ("Integer", "Float", "Money"):
        lignes = []
        emit_base_rules(lignes, {"Commande": [("total", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Commande": ["Admin"]},
                        calculated=set())
        assert "rule Commande.total required" in lignes, type_
        assert "rule Commande.total min 1" not in lignes, (
            f"a floor on {type_} would forbid the value zero: {lignes}")


def test_a_first_text_field_gets_its_floor():
    """The counter-proof of the witness above: without it, a function that never
    emitted a floor again would make both green."""
    for type_ in TYPES_TEXTE:
        lignes = []
        emit_base_rules(lignes, {"Fiche": [("titre", type_)]},
                        extra_rules=[], public_read=set(), public_create=set(),
                        owned={}, managers={"Fiche": ["Admin"]},
                        calculated=set())
        assert "rule Fiche.titre min 1" in lignes, (type_, lignes)


def test_the_shop_bounds_its_name_not_its_total():
    """Both cases side by side in a REAL spec, the one running this file's
    server."""
    regles = {ligne.strip() for ligne in _spec(BOUTIQUE).splitlines()}
    assert "rule Customer.displayName min 1" in regles
    assert "rule Order.total required" in regles
    assert "rule Order.total min 1" not in regles


def test_the_text_type_list_comes_from_the_compiler():
    """It is not copied: a second list would end up diverging, and the dialogue
    would emit a rule the compiler refuses — the worst outcome for someone being
    guided (point 173)."""
    assert TYPES_TEXTE is ChampsMixin.BORNES_TEXTE


# --- what the SERVER does ----------------------------------------------------

def test_the_server_refuses_an_empty_text_field(boutique, entete):
    """The defect measured on the maintainer's archive, at its source."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": ""}, timeout=10)
    assert reponse.status_code == 422, reponse.text


def test_the_server_also_refuses_a_whitespace_only_field(
        boutique, entete):
    """Empty after strip is refused before insertion."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": "   "}, timeout=10)
    assert reponse.status_code == 422, reponse.text


def test_the_server_still_accepts_a_named_record(boutique, entete):
    """The counter-proof telling a right floor from a floor that refuses
    everything."""
    reponse = requests.post(f"{boutique}/customer", headers=entete,
                            json={"displayName": " a "}, timeout=10)
    assert reponse.status_code == 200, reponse.text
    # Reread IN THE DATABASE: a status code says the route answered, never that
    # the value arrived.
    fiche = requests.get(f"{boutique}/customer/{reponse.json()['id']}",
                         headers=entete, timeout=10)
    assert fiche.status_code == 200, fiche.text
    assert fiche.json()["data"]["displayName"] == " a "


def test_a_zero_total_stays_accepted(boutique, entete):
    """The limit, tested against the server and not only in the spec: an empty
    cart is worth zero, and refusing it would break the shop."""
    reponse = requests.post(f"{boutique}/order", headers=entete,
                            json={"total": 0, "status": "nouvelle"}, timeout=10)
    assert reponse.status_code == 200, reponse.text


def test_update_refuses_empty_without_changing_the_value(boutique, entete):
    creation = requests.post(f"{boutique}/customer", headers=entete,
                             json={"displayName": " a "}, timeout=10)
    assert creation.status_code == 200, creation.text
    url = f"{boutique}/customer/{creation.json()['id']}"
    refus = requests.put(url, headers=entete, json={"displayName": "   "}, timeout=10)
    assert refus.status_code == 422, refus.text
    assert requests.get(url, headers=entete, timeout=10).json()["data"]["displayName"] == " a "
    accepte = requests.put(url, headers=entete, json={"displayName": " a "}, timeout=10)
    assert accepte.status_code == 200, accepte.text
    assert requests.get(url, headers=entete, timeout=10).json()["data"]["displayName"] == " a "


def test_non_required_text_stays_accepted(boutique, entete):
    creation = requests.post(f"{boutique}/order", headers=entete,
                             json={"total": 0, "status": "   "}, timeout=10)
    assert creation.status_code == 200, creation.text
    url = f"{boutique}/order/{creation.json()['id']}"
    assert requests.get(url, headers=entete, timeout=10).json()["data"]["status"] == "   "
    update = requests.put(url, headers=entete, json={"total": 0, "status": "   "}, timeout=10)
    assert update.status_code == 200, update.text
    assert requests.get(url, headers=entete, timeout=10).json()["data"]["status"] == "   "


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
