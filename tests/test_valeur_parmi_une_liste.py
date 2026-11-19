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
from tests.support.processus import arreter_processus
from tests.support.server import free_port as _port_libre

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

SANS_REGLE = SPEC.replace(
    'rule Commande.statut oneOf "panier", "en préparation", "expédiée", "livrée"\n', "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation refuses
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    ast = _valide(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"] == [
        "panier", "en préparation", "expédiée", "livrée"]
    capsys.readouterr()


def test_the_declared_order_is_kept(capsys):
    """For a status, the order is the lifecycle's — it carries meaning, and it is
    the one a dropdown menu must present."""
    ast = _valide(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"][0] == "panier"
    capsys.readouterr()


def test_a_nonexistent_field_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("Commande.statut oneOf", "Commande.fantome oneOf"))
    assert "nonexistent field" in str(refus.value)
    capsys.readouterr()


def test_a_numeric_field_is_refused(capsys):
    """Three ways to express the same constraint would end up contradicting each
    other: for a number, 'min'/'max' and 'categorized' already exist."""
    spec = SPEC.replace("    note: String", "    montant: Integer")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace("Commande.statut oneOf", "Commande.montant oneOf"))
    assert "String or Text" in str(refus.value)
    capsys.readouterr()


def test_a_single_value_is_refused(capsys):
    """A field with a single possible value need not be entered — and a rule
    producing nothing is what point 85 refuses."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace(
            'oneOf "panier", "en préparation", "expédiée", "livrée"', 'oneOf "panier"'))
    assert "only one value" in str(refus.value)
    capsys.readouterr()


def test_an_empty_value_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"panier",', '"   ",'))
    assert "empty value" in str(refus.value)
    capsys.readouterr()


def test_a_duplicate_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"livrée"', '"panier"'))
    assert "repeats" in str(refus.value)
    capsys.readouterr()


def test_two_rules_on_the_same_field_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + 'rule Commande.statut oneOf "a", "b"\n')
    assert "which list" in str(refus.value)
    capsys.readouterr()


def test_combining_with_generated_is_refused(capsys):
    """The server writes the field itself: the list would never be read, and the
    screen would offer an inert menu."""
    spec = SPEC + "rule Commande.note generated\n"
    spec = spec.replace('rule Commande.statut oneOf "panier", "en préparation", '
                        '"expédiée", "livrée"',
                        'rule Commande.note oneOf "a", "b"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "generated" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation writes
# --------------------------------------------------------------------------

def test_the_rule_really_changes_the_output(tmp_path, capsys):
    """The test forbidding a decorative rule (point 85): compiling WITH and
    WITHOUT must give different outputs."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    avec = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert avec != sans
    assert "Literal['panier'" in avec
    assert "Literal[" not in sans


def test_the_contract_and_brief_carry_the_list(tmp_path, capsys):
    """The AI reads the brief, not the JSON — both must carry it, otherwise it
    draws a text field and the user collects a 422."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    champ = next(f for f in contrat["entities"]["Commande"]["fields"]
                 if f["name"] == "statut")
    assert champ["allowed_values"] == ["panier", "en préparation", "expédiée", "livrée"]
    brief = (tmp_path / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "DROPDOWN MENU" in brief
    assert "“en préparation”" in brief


def test_without_rule_no_list_in_the_contract(tmp_path, capsys):
    """The witness: an absent rule must leave no trace."""
    (tmp_path / "spec.ml").write_text(SANS_REGLE, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    assert not any(f.get("allowed_values")
                   for f in contrat["entities"]["Commande"]["fields"])
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
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "content rewritten: choices of Commande.statut" in sortie, sortie
    assert "field added" not in sortie, sortie


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _appel(url, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        with err:
            brut = err.read()
            try:
                return err.code, json.loads(brut or b"{}")
            except ValueError:
                return err.code, {"detail": brut.decode("utf-8", "replace")}


@pytest.fixture
def serveur(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
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
                with urllib.request.urlopen(base + "/docs", timeout=5) as reponse:
                    reponse.read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, jeton["access_token"]
    finally:
        arreter_processus(proc, delai=10)


@pytest.mark.parametrize("valide", ["panier", "en préparation", "expédiée", "livrée"])
def test_the_declared_values_are_accepted(serveur, valide):
    base, jeton = serveur
    code, reponse = _appel(base + "/commande", {"statut": valide, "note": "x"}, jeton)
    assert code == 200, reponse


@pytest.mark.parametrize("invalide", ["livrée par moi", "", "PANIER", "expediee"])
def test_any_other_value_is_refused(serveur, invalide):
    """THE defect measured on the real shop: the client declared itself
    "delivered" on its own, on an unpaid order."""
    base, jeton = serveur
    code, _ = _appel(base + "/commande", {"statut": invalide, "note": "x"}, jeton)
    assert code == 422


def test_the_refusal_lists_the_allowed_values(serveur):
    """A 422 that does not say what it expects forces reading the documentation.
    The list is in the message, it comes from `Literal`."""
    base, jeton = serveur
    _, reponse = _appel(base + "/commande", {"statut": "inventé", "note": "x"}, jeton)
    message = json.dumps(reponse, ensure_ascii=False)
    assert "panier" in message and "livrée" in message


def test_the_constraint_ALSO_holds_on_update(serveur):
    """The branch one forgets (points 91, 92): the Pydantic schema is unique per
    entity, so PUT is covered — but it must be CHECKED, not assumed."""
    base, jeton = serveur
    _, cree = _appel(base + "/commande", {"statut": "panier", "note": "x"}, jeton)

    code, _ = _appel(f"{base}/commande/{cree['id']}",
                     {"statut": "livrée par moi", "note": "x"}, jeton, methode="PUT")
    assert code == 422

    code, _ = _appel(f"{base}/commande/{cree['id']}",
                     {"statut": "expédiée", "note": "x"}, jeton, methode="PUT")
    assert code == 200
    _, relue = _appel(f"{base}/commande/{cree['id']}", jeton=jeton)
    assert relue["data"]["statut"] == "expédiée"


def test_a_refusal_leaves_nothing_in_the_database(serveur):
    """422 before any INSERT: the guard lives in input validation, not in the
    middle of a write."""
    base, jeton = serveur
    _appel(base + "/commande", {"statut": "inventé", "note": "x"}, jeton)
    _, liste = _appel(base + "/commande", jeton=jeton)
    assert liste["total"] == 0
