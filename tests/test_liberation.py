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
from tests.support.processus import arreter_processus
from tests.support.server import free_port as _port_libre

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

SANS_REGLE = SPEC.replace('rule Commande.statut "annulée" releases Ligne\n', "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation refuses
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    ast = _valide(SPEC)
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
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "oneOf" in str(refus.value)
    capsys.readouterr()


def test_a_value_outside_the_list_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"annulée" releases', '"remboursée" releases'))
    assert "it would never occur" in str(refus.value)
    capsys.readouterr()


def test_releasing_an_entity_without_counting_is_refused(capsys):
    """"Giving back" assumes something was taken."""
    spec = SPEC.replace("rule Ligne.Create decrements Produit.stock by quantite\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "decrements" in str(refus.value)
    capsys.readouterr()


def test_releasing_without_relation_is_refused(capsys):
    """Without a relation, nothing says WHICH lines depend on this order."""
    spec = SPEC.replace("relation Commande hasMany Ligne\n",
                        "relation Client hasMany Ligne\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "relation" in str(refus.value)
    capsys.readouterr()


def test_an_unknown_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("releases Ligne", "releases Fantome"))
    assert "Fantome" in str(refus.value)
    capsys.readouterr()


def test_two_rules_on_the_same_field_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + 'rule Commande.statut "panier" releases Ligne\n')
    assert "the second would return it a second time" in str(refus.value)
    capsys.readouterr()


def test_the_rule_really_changes_the_output(tmp_path, capsys):
    """The test forbidding a decorative rule (point 85)."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    avec = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert avec != sans
    assert "_bascule" in avec and "_bascule" not in sans


def test_the_contract_announces_the_release_and_the_one_way_trip(tmp_path, capsys):
    """Without this note, an interface offers "back to preparation" on a
    cancelled order and discovers a 409 on click."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    route = next(r for r in contrat["routes"]
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
    (proj / "spec.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    capsys.readouterr()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")

    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "release on PUT /commande/{id}" in sortie, sortie
    assert "route added" not in sortie, sortie


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
def boutique(tmp_path):
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


def _stock(base):
    _, r = _appel(f"{base}/produit/1")
    return r["data"]["stock"]


def _commande_de(base, jeton, quantite):
    _, cmd = _appel(base + "/commande", {"statut": "panier"}, jeton)
    _appel(base + "/ligne", {"quantite": quantite, "commande_id": cmd["id"],
                             "produit_id": 1}, jeton)
    return cmd["id"]


def test_cancelling_gives_the_stock_back(boutique):
    """THE defect, measured by comparing the shop with a real one: cancelling
    kept the lines, so the stock stayed consumed."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    assert _stock(base) == depart - 3

    code, reponse = _appel(f"{base}/commande/{cmd}", {"statut": "annulée"},
                           jeton, methode="PUT")

    assert code == 200, reponse
    assert _stock(base) == depart


def test_cancelling_KEEPS_the_lines(boutique):
    """The brick's whole reason for being: deleting the lines already gave the
    stock back (point 92), but erased the history. A merchant wants both."""
    base, jeton = boutique
    cmd = _commande_de(base, jeton, 2)
    _appel(f"{base}/commande/{cmd}", {"statut": "annulée"}, jeton, methode="PUT")

    _, lignes = _appel(f"{base}/ligne", jeton=jeton)
    assert lignes["total"] == 1


def test_cancelling_again_does_NOT_give_back_a_second_time(boutique):
    """THE point of the brick, and what only a real server shows: without the
    transition guard, two PUTs would give the stock back twice and the shop would
    invent pairs."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    for _ in range(3):
        code, _ = _appel(f"{base}/commande/{cmd}", {"statut": "annulée"},
                         jeton, methode="PUT")
        assert code == 200

    assert _stock(base) == depart, "le stock a été rendu plusieurs fois"


def test_reactivating_after_cancellation_is_refused(boutique):
    """Without this refusal: cancelling gives the stock back, reactivating leaves
    the order live having consumed nothing — free stock, same family as point
    77's exploits."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    _appel(f"{base}/commande/{cmd}", {"statut": "annulée"}, jeton, methode="PUT")

    code, reponse = _appel(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                           jeton, methode="PUT")

    assert code == 409, reponse
    assert _stock(base) == depart, "un refus ne doit rien avoir consommé"
    _, relue = _appel(f"{base}/commande/{cmd}", jeton=jeton)
    assert relue["data"]["statut"] == "annulée", "l'état a changé malgré le refus"


def test_another_status_releases_nothing(boutique):
    """The witness: it is the declared VALUE that releases, not any update.
    Without it, a brick giving back on every PUT would pass the previous tests."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 2)

    code, _ = _appel(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                     jeton, methode="PUT")

    assert code == 200
    assert _stock(base) == depart - 2, "un statut ordinaire a rendu du stock"


def test_cancelling_gives_back_only_ITS_lines(boutique):
    """Two open orders: cancelling one must not give back what the other
    consumed. The foreign key trap, once more."""
    base, jeton = boutique
    depart = _stock(base)
    premiere = _commande_de(base, jeton, 3)
    _commande_de(base, jeton, 2)
    assert _stock(base) == depart - 5

    _appel(f"{base}/commande/{premiere}", {"statut": "annulée"}, jeton, methode="PUT")

    assert _stock(base) == depart - 2, "la libération a débordé sur l'autre commande"


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
SPEC_APRES_PAIEMENT = SPEC.replace(
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
    (tmp_path / "spec.ml").write_text(SPEC_APRES_PAIEMENT, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")

    generique = source.split("def modifier_commande_apres_paiement")[0]
    assert "data.statut" not in generique, (
        "l'Update générique lit un champ que son schéma Pydantic ne porte "
        "pas : tout PUT répondra 500")
    assert "class CommandeSchema" in source
    schema = source.split("class CommandeSchema")[1].split("class ")[0]
    assert "statut" not in schema, "prémisse fausse : le champ est resté au schéma"


def test_the_release_follows_the_field_into_the_after_payment_route(tmp_path, capsys):
    """The transition is emitted where the field is written — otherwise it
    disappears.

    Without this witness, removing the transition from the generic Update would
    be enough to make the suite green, dropping stock restitution on the way.
    """
    (tmp_path / "spec.ml").write_text(SPEC_APRES_PAIEMENT, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    source = (tmp_path / "app.py").read_text(encoding="utf-8")

    route = source.split("def modifier_commande_apres_paiement")[1]
    assert "_bascule" in route, "la libération ne suit pas le champ qui l'arme"
    assert 'UPDATE "produit" SET "stock"' in route, (
        "la bascule est émise mais ne rend rien")
    # This route's fields are OPTIONAL: without this guard, a call not touching
    # the status would refuse the order it does not modify.
    assert "data.statut is not None" in route, (
        "le refus de réactivation se déclencherait sur un appel qui ne "
        "modifie pas le statut")
