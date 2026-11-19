"""Brick 19: one value from a list — point 96.

Called "the next obvious brick" at points 91 and 92, and for good reason: on
an UNPAID order, the client set `status: "livrée"` and the server accepted
it. A status is not text, it is one state among a few.

What the brick decides:

* **`Literal` rather than a pattern.** The refusal falls at Pydantic
  validation — a 422 BEFORE any INSERT, same place as point 85's bounds — and
  the list comes out as is in the OpenAPI schema, hence in `/docs`, without
  having to copy it;
* **TEXT types only.** For a number, `min`/`max` (point 85) and
  `categorized` (brick 5) already say that; a third way to express the same
  constraint would end up contradicting another;
* **the contract carries the list.** Without it the AI draws a text field,
  and the user invents a value that collects a 422 — while the list fits in a
  dropdown menu.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.process import stop_process
from tests.support.server import free_port as _port_free

SPEC = """app BancChoix

entity Commande
    statut: String
    note: String

relation Client hasMany Commande

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.statut oneOf "panier", "en préparation", "expédiée", "livrée"

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
"""

WITHOUT_RULE = SPEC.replace(
    'rule Commande.statut oneOf "panier", "en préparation", "expédiée", "livrée"\n', "")


def _valid(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation refuses
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    ast = _valid(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"] == [
        "panier", "en préparation", "expédiée", "livrée"]
    capsys.readouterr()


def test_the_declared_order_is_kept(capsys):
    """For a status, the order is the lifecycle's — it carries meaning, and it is
    the one a dropdown menu must present."""
    ast = _valid(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"][0] == "panier"
    capsys.readouterr()


def test_a_nonexistent_field_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace("Commande.statut oneOf", "Commande.fantome oneOf"))
    assert "nonexistent field" in str(refusal.value)
    capsys.readouterr()


def test_a_numeric_field_is_refused(capsys):
    """Three ways to express the same constraint would end up contradicting each
    other: for a number, 'min'/'max' and 'categorized' already exist."""
    spec = SPEC.replace("    note: String", "    montant: Integer")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec.replace("Commande.statut oneOf", "Commande.montant oneOf"))
    assert "String or Text" in str(refusal.value)
    capsys.readouterr()


def test_a_single_value_is_refused(capsys):
    """A field with a single possible value need not be entered — and a rule
    producing nothing is what point 85 refuses."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace(
            'oneOf "panier", "en préparation", "expédiée", "livrée"', 'oneOf "panier"'))
    assert "only one value" in str(refusal.value)
    capsys.readouterr()


def test_an_empty_value_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"panier",', '"   ",'))
    assert "empty value" in str(refusal.value)
    capsys.readouterr()


def test_a_duplicate_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"livrée"', '"panier"'))
    assert "repeats" in str(refusal.value)
    capsys.readouterr()


def test_two_rules_on_the_same_field_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC + 'rule Commande.statut oneOf "a", "b"\n')
    assert "which list" in str(refusal.value)
    capsys.readouterr()


def test_combining_with_generated_is_refused(capsys):
    """The server writes the field itself: the list would never be read, and the
    screen would offer an inert menu."""
    spec = SPEC + "rule Commande.note generated\n"
    spec = spec.replace('rule Commande.statut oneOf "panier", "en préparation", '
                        '"expédiée", "livrée"',
                        'rule Commande.note oneOf "a", "b"')
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "generated" in str(refusal.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation writes
# --------------------------------------------------------------------------

def test_the_rule_really_changes_the_output(tmp_path, capsys):
    """The test forbidding a decorative rule (point 85): compiling WITH and
    WITHOUT must give different outputs."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(WITHOUT_RULE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    with_ = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert with_ != sans
    assert "Literal['panier'" in with_
    assert "Literal[" not in sans


def test_the_contract_and_brief_carry_the_list(tmp_path, capsys):
    """The AI reads the brief, not the JSON — both must carry it, otherwise it
    draws a text field and the user collects a 422."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contract = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    field = next(f for f in contract["entities"]["Commande"]["fields"]
                 if f["name"] == "statut")
    assert field["allowed_values"] == ["panier", "en préparation", "expédiée", "livrée"]
    brief = (tmp_path / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "DROPDOWN MENU" in brief
    assert "“en préparation”" in brief


def test_without_rule_no_list_in_the_contract(tmp_path, capsys):
    """The witness: an absent rule must leave no trace."""
    (tmp_path / "spec.ml").write_text(WITHOUT_RULE, encoding="utf-8")
    contract = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    assert not any(f.get("allowed_values")
                   for f in contract["entities"]["Commande"]["fields"])
    assert "MENU DÉROULANT" not in (
        tmp_path / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")


def test_the_delta_reports_a_changing_list(tmp_path, capsys):
    """POINT 96: the sixth time. Setting `oneOf` renames nothing, and the list
    can change without the field moving — a text field becomes a menu, and the
    menu gains an entry. Comparing names alone would be point 89's mistake."""
    from monl.cli import cmd_update

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    capsys.readouterr()
    (proj / "spec.ml").write_text(SPEC.replace('"livrée"', '"livrée", "annulée"'),
                                  encoding="utf-8")

    cmd_update(str(proj))
    output = capsys.readouterr().out

    assert "no interface changes" not in output, output
    assert "content rewritten: choices of Commande.statut" in output, output
    assert "field added" not in output, output


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _call(url, body=None, token=None, method=None):
    donnees = json.dumps(body).encode() if body is not None else None
    query = urllib.request.Request(url, data=donnees, method=method)
    query.add_header("Content-Type", "application/json")
    if token:
        query.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(query, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as err:
        with err:
            brut = err.read()
            try:
                return err.code, json.loads(brut or b"{}")
            except ValueError:
                return err.code, {"detail": brut.decode("utf-8", "replace")}


@pytest.fixture
def server(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_free()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5) as response:
                    response.read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("the server never answered")
        _call(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, token = _call(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, token["access_token"]
    finally:
        stop_process(proc, delay=10)


@pytest.mark.parametrize("valid", ["panier", "en préparation", "expédiée", "livrée"])
def test_the_declared_values_are_accepted(server, valid):
    base, token = server
    code, response = _call(base + "/commande", {"statut": valid, "note": "x"}, token)
    assert code == 200, response


@pytest.mark.parametrize("invalid", ["livrée par moi", "", "PANIER", "expediee"])
def test_any_other_value_is_refused(server, invalid):
    """THE defect measured on the real shop: the client declared itself
    "delivered" on its own, on an unpaid order."""
    base, token = server
    code, _ = _call(base + "/commande", {"statut": invalid, "note": "x"}, token)
    assert code == 422


def test_the_refusal_lists_the_allowed_values(server):
    """A 422 that does not say what it expects forces reading the documentation.
    The list is in the message, it comes from `Literal`."""
    base, token = server
    _, response = _call(base + "/commande", {"statut": "inventé", "note": "x"}, token)
    message = json.dumps(response, ensure_ascii=False)
    assert "panier" in message and "livrée" in message


def test_the_constraint_ALSO_holds_on_update(server):
    """The branch one forgets (points 91, 92): the Pydantic schema is unique per
    entity, so PUT is covered — but it must be CHECKED, not assumed."""
    base, token = server
    _, created = _call(base + "/commande", {"statut": "panier", "note": "x"}, token)

    code, _ = _call(f"{base}/commande/{created['id']}",
                     {"statut": "livrée par moi", "note": "x"}, token, method="PUT")
    assert code == 422

    code, _ = _call(f"{base}/commande/{created['id']}",
                     {"statut": "expédiée", "note": "x"}, token, method="PUT")
    assert code == 200
    _, reread = _call(f"{base}/commande/{created['id']}", token=token)
    assert reread["data"]["statut"] == "expédiée"


def test_a_refusal_leaves_nothing_in_the_database(server):
    """422 before any INSERT: the guard lives in input validation, not in the
    middle of a write."""
    base, token = server
    _call(base + "/commande", {"statut": "inventé", "note": "x"}, token)
    _, list_ = _call(base + "/commande", token=token)
    assert list_["total"] == 0
