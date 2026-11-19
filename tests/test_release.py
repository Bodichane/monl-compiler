"""Brick 20: reaching a value UNDOES an effect — point 98.

The last live bug left by the comparison with a classic shop (point 96):
cancelling an order switched it to "cancelled" and kept its lines, so the
stock stayed consumed. Deleting the lines gave it back (point 92) but erased
the history — a merchant wants both.

`oneOf` (point 96) was the prerequisite: one had to be able to designate a
state.

What the brick decides:

* **give back ONLY ONCE.** The state is read before the write and release
  only happens on the TRANSITION. Two successive PUTs to "cancelled" would
  otherwise give the stock back twice, and the shop would invent pairs;
* **the released state is TERMINAL.** Reactivating after giving back would
  leave a live order having consumed nothing — free stock, same family as
  point 77's exploits. Taking it again on return would assume it is still
  available, which nothing guarantees;
* **no floor on restitution**, as at point 92: we give back a state that
  existed and was valid.
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

SPEC = """app BancLiberation

entity Produit
    nom: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Produit.stock min 0
rule Ligne.quantite required
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Produit.stock by quantite
rule Commande.statut oneOf "panier", "en préparation", "annulée"
rule Commande.statut "annulée" releases Ligne

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Read Produit

seed Produit
    nom: "Halo RS", stock: 10
"""

WITHOUT_RULE = SPEC.replace('rule Commande.statut "annulée" releases Ligne\n', "")


def _valid(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation refuses
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    ast = _valid(SPEC)
    assert ast["security"]["release_rules"] == [
        {"entity": "Commande", "field": "statut", "value": "annulée",
         "releases": "Ligne"}]
    capsys.readouterr()


def test_without_oneOf_the_rule_is_refused(capsys):
    """THE refusal that carries the brick: without a list of values, a typo would
    give a rule that NEVER fires — and nothing would say so. It is exactly what
    point 85 refuses."""
    spec = SPEC.replace(
        'rule Commande.statut oneOf "panier", "en préparation", "annulée"\n', "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "oneOf" in str(refusal.value)
    capsys.readouterr()


def test_a_value_outside_the_list_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace('"annulée" releases', '"remboursée" releases'))
    assert "it would never occur" in str(refusal.value)
    capsys.readouterr()


def test_releasing_an_entity_without_counting_is_refused(capsys):
    """"Giving back" assumes something was taken."""
    spec = SPEC.replace("rule Ligne.Create decrements Produit.stock by quantite\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "decrements" in str(refusal.value)
    capsys.readouterr()


def test_releasing_without_relation_is_refused(capsys):
    """Without a relation, nothing says WHICH lines depend on this order."""
    spec = SPEC.replace("relation Commande hasMany Ligne\n",
                        "relation Client hasMany Ligne\n")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "relation" in str(refusal.value)
    capsys.readouterr()


def test_an_unknown_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC.replace("releases Ligne", "releases Fantome"))
    assert "Fantome" in str(refusal.value)
    capsys.readouterr()


def test_two_rules_on_the_same_field_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC + 'rule Commande.statut "panier" releases Ligne\n')
    assert "the second would return it a second time" in str(refusal.value)
    capsys.readouterr()


def test_the_rule_really_changes_the_output(tmp_path, capsys):
    """The test forbidding a decorative rule (point 85)."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(WITHOUT_RULE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    with_ = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert with_ != sans
    assert "_bascule" in with_ and "_bascule" not in sans


def test_the_contract_announces_the_release_and_the_one_way_trip(tmp_path, capsys):
    """Without this note, an interface offers "back to preparation" on a
    cancelled order and discovers a 409 on click."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contract = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    route = next(r for r in contract["routes"]
                 if r["method"] == "PUT" and r["path"] == "/commande/{id}")
    assert route["releases_on"] == {"field": "statut", "value": "annulée",
                                    "releases": "Ligne", "terminal": True}
    assert "RELEASE" in route["note"]
    assert "ONE-WAY" in route["note"]


def test_the_delta_reports_an_added_release(tmp_path, capsys):
    """POINT 98: the seventh time. Setting `releases` creates no route and
    changes no field — but a "reactivate" button becomes a 409."""
    from monl.cli import cmd_update

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "spec.ml").write_text(WITHOUT_RULE, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    capsys.readouterr()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")

    cmd_update(str(proj))
    output = capsys.readouterr().out

    assert "no interface changes" not in output, output
    assert "release on PUT /commande/{id}" in output, output
    assert "route added" not in output, output


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
def boutique(tmp_path):
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


def _stock(base):
    _, r = _call(f"{base}/produit/1")
    return r["data"]["stock"]


def _order_of(base, token, quantity):
    _, cmd = _call(base + "/commande", {"statut": "panier"}, token)
    _call(base + "/ligne", {"quantite": quantity, "commande_id": cmd["id"],
                             "produit_id": 1}, token)
    return cmd["id"]


def test_cancelling_gives_the_stock_back(boutique):
    """THE defect, measured by comparing the shop with a real one: cancelling
    kept the lines, so the stock stayed consumed."""
    base, token = boutique
    start = _stock(base)
    cmd = _order_of(base, token, 3)
    assert _stock(base) == start - 3

    code, response = _call(f"{base}/commande/{cmd}", {"statut": "annulée"},
                           token, method="PUT")

    assert code == 200, response
    assert _stock(base) == start


def test_cancelling_KEEPS_the_lines(boutique):
    """The brick's whole reason for being: deleting the lines already gave the
    stock back (point 92), but erased the history. A merchant wants both."""
    base, token = boutique
    cmd = _order_of(base, token, 2)
    _call(f"{base}/commande/{cmd}", {"statut": "annulée"}, token, method="PUT")

    _, lines = _call(f"{base}/ligne", token=token)
    assert lines["total"] == 1


def test_cancelling_again_does_not_give_back_a_second_time(boutique):
    """THE point of the brick, and what only a real server shows: without the
    transition guard, two PUTs would give the stock back twice and the shop would
    invent pairs."""
    base, token = boutique
    start = _stock(base)
    cmd = _order_of(base, token, 3)
    for _ in range(3):
        code, _ = _call(f"{base}/commande/{cmd}", {"statut": "annulée"},
                         token, method="PUT")
        assert code == 200

    assert _stock(base) == start, "the stock was given back several times"


def test_reactivating_after_cancellation_is_refused(boutique):
    """Without this refusal: cancelling gives the stock back, reactivating leaves
    the order live having consumed nothing — free stock, same family as point
    77's exploits."""
    base, token = boutique
    start = _stock(base)
    cmd = _order_of(base, token, 3)
    _call(f"{base}/commande/{cmd}", {"statut": "annulée"}, token, method="PUT")

    code, response = _call(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                           token, method="PUT")

    assert code == 409, response
    assert _stock(base) == start, "a refusal must have consumed nothing"
    _, reread = _call(f"{base}/commande/{cmd}", token=token)
    assert reread["data"]["statut"] == "annulée", "the state changed despite the refusal"


def test_another_status_releases_nothing(boutique):
    """The witness: it is the declared VALUE that releases, not any update.
    Without it, a brick giving back on every PUT would pass the previous tests."""
    base, token = boutique
    start = _stock(base)
    cmd = _order_of(base, token, 2)

    code, _ = _call(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                     token, method="PUT")

    assert code == 200
    assert _stock(base) == start - 2, "an ordinary status gave stock back"


def test_cancelling_gives_back_only_ITS_lines(boutique):
    """Two open orders: cancelling one must not give back what the other
    consumed. The foreign key trap, once more."""
    base, token = boutique
    start = _stock(base)
    premiere = _order_of(base, token, 3)
    _order_of(base, token, 2)
    assert _stock(base) == start - 5

    _call(f"{base}/commande/{premiere}", {"statut": "annulée"}, token, method="PUT")

    assert _stock(base) == start - 2, "the release spilled over onto the other order"


# --------------------------------------------------------------------------
# When `writableAfterPayment` takes the field: the release follows it
# --------------------------------------------------------------------------
#
# Combined on the SAME field, the two bricks contradicted each other:
# `writableAfterPayment` removes the field from the generic Update's Pydantic
# schema, whose transition still read `data.<champ>`. Every PUT answered 500 —
# on `exemples/02_boutique.ml`, for the only role allowed to call it. Found by
# compiling a bench spec, not by rereading.
#
# The transition now lives in the route that REALLY writes the field. Moving it
# without carrying it there would have replaced a noisy 500 with a silent loss:
# cancelling a paid order would no longer have given its stock back.

# `writableAfterPayment` requires a chargeable amount, hence CALCULATED by the
# server (point 82): the line subtotal comes from the catalog price, and the
# order amount is their sum. Summing a field the client writes would be
# refused, and rightly so.
SPEC_AFTER_PAYMENT = SPEC.replace(
    "actor Client selfRegister",
    "actor Client selfRegister\nactor Gerant",
).replace(
    "entity Produit\n    nom: String\n    stock: Integer",
    "entity Produit\n    nom: String\n    stock: Integer\n    prix: Money",
).replace(
    "entity Commande\n    statut: String",
    "entity Commande\n    statut: String\n    montant: Money",
).replace(
    "entity Ligne\n    quantite: Integer",
    "entity Ligne\n    quantite: Integer\n    sousTotal: Money",
).replace(
    'rule Commande.statut "annulée" releases Ligne',
    'rule Commande.statut "annulée" releases Ligne\n'
    "rule Ligne.sousTotal derivedFrom Produit.prix by quantite\n"
    "rule Commande.montant sumOf Ligne.sousTotal\n"
    "rule Commande.montant payable\n"
    "rule Commande.statut writableAfterPayment Gerant",
).replace(
    'nom: "Halo RS", stock: 10',
    'nom: "Halo RS", stock: 10, prix: 89.0',
)


def test_the_field_taken_by_payment_no_longer_breaks_the_update(tmp_path, capsys):
    """The generic Update no longer reads a field absent from its schema.

    The witness is about the generated SOURCE: that is where the 500 lived, and a
    read of `data.statut` outside the after-payment route would bring it back.
    """
    (tmp_path / "spec.ml").write_text(SPEC_AFTER_PAYMENT, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")

    generic = source.split("def modifier_commande_apres_paiement")[0]
    assert "data.statut" not in generic, (
        "the generic Update reads a field its Pydantic schema does not "
        "carry: every PUT will answer 500")
    assert "class CommandeSchema" in source
    schema = source.split("class CommandeSchema")[1].split("class ")[0]
    assert "statut" not in schema, "false premise: the field stayed in the schema"


def test_the_release_follows_the_field_into_the_after_payment_route(tmp_path, capsys):
    """The transition is emitted where the field is written — otherwise it
    disappears.

    Without this witness, removing the transition from the generic Update would
    be enough to make the suite green, dropping stock restitution on the way.
    """
    (tmp_path / "spec.ml").write_text(SPEC_AFTER_PAYMENT, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")

    route = source.split("def modifier_commande_apres_paiement")[1]
    assert "_bascule" in route, "the release does not follow the field that arms it"
    assert 'UPDATE "produit" SET "stock"' in route, (
        "the transition is emitted but gives nothing back")
    # This route's fields are OPTIONAL: without this guard, a call not touching
    # the status would refuse the order it does not modify.
    assert "data.statut is not None" in route, (
        "the reactivation refusal would fire on a call that does not "
        "modify the status")
