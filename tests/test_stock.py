"""Brick 14: counting down what the client requested — point 86.

Why this brick. `decrements` could subtract a CONSTANT (`by 3`), which suits a
reputation or a like. A shop needs to subtract *what the client ordered*, and
`exemples/02_boutique.ml` had been charging for real since point 74 without
ever touching its stock: one could order fifty pairs out of twelve, and pay.

What the brick decides, and what did not go without saying:

* **the floor is not wired in.** A count going below zero is a stock that LIES
  — the shop would show "-3 available" after charging for the eight it did not
  have. But a reputation does have the right to be negative. What tells the
  two apart is not the field name: it is the DECLARATION
  `rule Product.stock min 0`, arrived at point 85. The check therefore arms
  itself, from what the spec says — and stays absent where nothing asks for
  it;
* **a single SQL statement.** Reading the stock then writing it would let two
  simultaneous orders read the same figure and each count down on its own
  side. The condition travels INSIDE the `UPDATE`, and `rowcount` says whether
  it held;
* **the targeted column is the one pointing to the decremented entity.** As
  long as a triggering entity had only one incoming relation, "the owner
  relation" and "the counter target" coincided. `OrderLine` has two — the bug
  is described below, it was found by reading the generated SQL.
"""
import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

SPEC = """app BancStock

entity Produit
    nom: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Client
    nom: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Produit.nom required
rule Produit.stock min 0
rule Ligne.quantite required
rule Ligne.quantite min 1
rule Produit.Read public
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Produit.stock by quantite

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    # POINT 91: `Update Ligne` is here to test counting on PUT. Without this
    # action, the brick had no way to be caught out — and it was: the quantity
    # changed, the stock did not.
    Update Ligne
    # POINT 92: `Delete Ligne` tests RESTITUTION. Without this action, the
    # brick still had no way to be caught out — and it was: emptying one's cart
    # made the stock disappear for good.
    Delete Ligne
    Create Client
    Read Client
    Read Produit

workflow Gerer for Patron
    Create Produit
    Read Produit
    Update Produit

seed Produit
    nom: "Halo RS", stock: 3
    nom: "Deck Low", stock: 0
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation must refuse
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    """The witness of the refusals that follow."""
    ast = _valide(SPEC)
    regle = next(r for r in ast["security"]["reputation_rules"]
                 if r["target_field"] == "stock")
    assert regle["amount_field"] == "quantite"
    assert regle["amount"] is None
    capsys.readouterr()


def test_a_quantity_that_is_not_a_field_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("by quantite", "by fantome"))
    assert "field does not exist" in str(refus.value)
    capsys.readouterr()


def test_a_non_integer_quantity_is_refused(capsys):
    spec = SPEC.replace("    quantite: Integer", "    quantite: Integer\n    note: String")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace("by quantite", "by note"))
    assert "Integer" in str(refus.value)
    capsys.readouterr()


def test_an_optional_quantity_is_refused(capsys):
    """Same requirement as `derivedFrom`'s multiplier (point 77), and for the
    same reason: a field the client can omit would count down on nothing."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Ligne.quantite required\n", ""))
    assert "required" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def test_counting_targets_the_right_foreign_key(tmp_path, capsys):
    """THE bug found by reading the generated SQL, not by rereading the code.

    The quantity was subtracted `WHERE id = data.commande_id`: the stock of the
    product carrying the ORDER's id. Invisible as long as a triggering entity had
    only ONE incoming relation (Report -> Member, Like -> Post); `Ligne` has two.
    The compiler had already known this defect ("a foreign key mechanism that
    decremented the wrong record"): it came back through the second relation's
    door."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if '"stock" - ?' in li)
    assert "data.produit_id" in ligne
    assert "data.commande_id" not in ligne


def test_without_declared_floor_counting_stays_free(tmp_path, capsys):
    """A reputation has the right to go below zero. The check comes from `min`,
    not from a "stock" exception wired into the compiler: removing the declaration
    must remove the safeguard."""
    (tmp_path / "spec.ml").write_text(SPEC.replace("rule Produit.stock min 0\n", ""),
                                      encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "rowcount == 0" not in genere
    assert "insufficient" not in genere


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
        try:
            brut = err.read()
            return err.code, json.loads(brut or b"{}")
        except ValueError:
            return err.code, {"brut": brut[:300].decode("utf-8", "replace")}
        finally:
            err.close()


@pytest.fixture
def boutique(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if processus.poll() is not None:
                pytest.fail(processus.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        jeton = jeton["access_token"]
        _appel(base + "/client", {"nom": "Zoe"}, jeton)
        # Three orders so that the kept id DIVERGES from the products': with
        # "order 1" and "product 1", a foreign key confusion would go unnoticed
        # — it is the lesson of point 81's probe.
        for _ in range(3):
            _, commande = _appel(base + "/commande", {"statut": "panier"}, jeton)
        _, catalogue = _appel(base + "/produit?limit=20")
        produits = {p["nom"]: p for p in catalogue["data"]}
        yield base, jeton, commande["id"], produits, tmp_path
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait(timeout=5)
        if processus.stdout is not None:
            processus.stdout.close()


def _stock(base, produit_id):
    _, reponse = _appel(f"{base}/produit/{produit_id}")
    return reponse["data"]["stock"]


def test_an_order_counts_down_the_stock(boutique):
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    assert _stock(base, halo) == 3

    code, _ = _appel(base + "/ligne", {"quantite": 2, "commande_id": commande,
                                       "produit_id": halo}, jeton)
    assert code == 200
    assert _stock(base, halo) == 1, "le décompte doit valoir la QUANTITÉ, pas 1"


def test_ordering_more_than_the_stock_is_refused(boutique):
    """The hole the brick closes: before it, the shop charged for fifty pairs out
    of twelve."""
    base, jeton, commande, produits, dossier = boutique
    halo = produits["Halo RS"]["id"]

    code, reponse = _appel(base + "/ligne", {"quantite": 4, "commande_id": commande,
                                             "produit_id": halo}, jeton)
    assert code == 409
    assert "insufficient" in reponse["detail"]
    assert _stock(base, halo) == 3, "un refus ne doit rien avoir décompté"
    # And the line must not exist: the refusal comes INSIDE the transaction.
    base_donnees = sqlite3.connect(dossier / "app.db")
    try:
        assert base_donnees.execute("SELECT COUNT(*) FROM ligne").fetchone()[0] == 0
    finally:
        base_donnees.close()


def test_a_sold_out_product_refuses_any_line(boutique):
    base, jeton, commande, produits, _ = boutique
    deck = produits["Deck Low"]["id"]
    assert _stock(base, deck) == 0
    code, _ = _appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                                       "produit_id": deck}, jeton)
    assert code == 409


def test_stock_never_goes_below_zero_even_over_several_orders(boutique):
    """Three orders of 1 on a stock of 3: all three pass. The fourth does not.
    The cumulative total counts, not each request taken alone."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    codes = [_appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                                      "produit_id": halo}, jeton)[0]
             for _ in range(4)]
    assert codes == [200, 200, 200, 409]
    assert _stock(base, halo) == 0


def test_counting_targets_the_requested_product_and_no_other(boutique):
    """The foreign key bug's counter-proof: with deliberately DIVERGENT ids,
    counting down the wrong row would show."""
    base, jeton, commande, produits, _ = boutique
    halo, deck = produits["Halo RS"]["id"], produits["Deck Low"]["id"]
    assert halo != commande, "identifiants confondus : le test ne prouve rien"

    _appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                             "produit_id": halo}, jeton)
    assert _stock(base, halo) == 2
    assert _stock(base, deck) == 0, "aucun autre produit ne doit avoir bougé"


# ---------------------------------------------------------------------------
# POINT 91: counting on PUT. `decrements` only fired on CREATION — creating a
# line at 1 then setting it to 4 billed four pairs and counted only one. It is
# point 78's defect moved from money to goods, and it had lived in the brick
# since point 86.

def _line_of(base, jeton, commande, produit, quantite):
    code, reponse = _appel(base + "/ligne", {"quantite": quantite,
                                             "commande_id": commande,
                                             "produit_id": produit}, jeton)
    assert code == 200, reponse
    return reponse["id"]


def test_increasing_the_quantity_counts_the_difference(boutique):
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _line_of(base, jeton, commande, halo, 1)
    assert _stock(base, halo) == 2

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 3, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 200, reponse
    # 3 at the start, 3 ordered: the DELTA of 2 is added to the 1 already
    # counted.
    assert _stock(base, halo) == 0, "le PUT doit décompter la différence"


def test_reducing_the_quantity_gives_stock_back(boutique):
    """The delta works both ways, without separate code: `stock - (-2)` goes back
    above the floor, so the same statement is enough."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _line_of(base, jeton, commande, halo, 3)
    assert _stock(base, halo) == 0

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 1, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 200, reponse
    assert _stock(base, halo) == 2


def test_a_quantity_exceeding_the_stock_is_refused_on_put(boutique):
    """The hole as measured on a real shop: four pairs billed, only one counted."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _line_of(base, jeton, commande, halo, 1)

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 9, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 409, reponse
    assert "insufficient" in reponse["detail"]
    assert _stock(base, halo) == 2, "un refus ne doit rien avoir décompté"
    _, relue = _appel(f"{base}/ligne/{ligne}", jeton=jeton)
    assert relue["data"]["quantite"] == 1, (
        "la ligne ne doit pas être écrite quand le stock refuse")


# --------------------------------------------------------------------------
# POINT 92: restitution — the third branch, the one people forget
# --------------------------------------------------------------------------

def test_deleting_a_line_gives_the_stock_back(boutique):
    """THE defect, measured on `projets/SneakerLab` against a real server:
    ordering three pairs then emptying one's cart left the stock at 9 out of 12.

    Counting fired on creation (point 86) then on update (point 91), never on
    deletion. The parent total, meanwhile, did go back to zero since point 82 —
    hence a database contradicting itself, and a catalog running out without a
    pair being sold."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    ligne = _line_of(base, jeton, commande, halo, 2)
    assert _stock(base, halo) == depart - 2

    code, reponse = _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert code == 200, reponse
    assert _stock(base, halo) == depart, "la ligne supprimée n'a pas rendu son stock"


def test_restitution_gives_back_the_CURRENT_quantity_not_the_creation_one(boutique):
    """Created at 1 then set to 3, the line consumed 3: it must give back 3. The
    quantity is reread FROM THE DATABASE at deletion time — reading it elsewhere
    would give back the original value and leave two pairs evaporated."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    ligne = _line_of(base, jeton, commande, halo, 1)
    _appel(f"{base}/ligne/{ligne}", {"quantite": 3, "commande_id": commande,
                                     "produit_id": halo}, jeton, methode="PUT")
    assert _stock(base, halo) == depart - 3

    _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert _stock(base, halo) == depart


def test_restitution_targets_the_lines_product_and_no_other(boutique):
    """Same trap as at point 86, on the other branch: `Ligne` has TWO incoming
    relations, and giving the stock back to the product carrying the ORDER's id
    would be invisible as long as the two ids coincide. The bench makes the ids
    diverge on purpose."""
    base, jeton, commande, produits, _ = boutique
    halo, deck = produits["Halo RS"]["id"], produits["Deck Low"]["id"]
    depart_halo, depart_deck = _stock(base, halo), _stock(base, deck)
    ligne = _line_of(base, jeton, commande, halo, 2)

    _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert _stock(base, halo) == depart_halo
    assert _stock(base, deck) == depart_deck, "le stock d'un autre produit a bougé"


def test_emptying_then_reordering_loses_no_unit(boutique):
    """The full cycle's counter-proof: three round trips must not nibble away at
    the catalog. It is the form in which the defect showed in production — a
    stock that only goes one way."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    for _ in range(3):
        ligne = _line_of(base, jeton, commande, halo, 3)
        _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")
    assert _stock(base, halo) == depart


def test_restitution_carries_no_floor(tmp_path, capsys):
    """A deliberate decision: giving back is never refused. Restitution restores
    a state that existed and was valid — a returned `decrements` only goes up. A
    safeguard here would forbid cancelling an order, that is exactly what the
    brick repairs."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    bloc = genere.split("def delete_ligne(")[1].split("\n@app.")[0]
    rendu = next(li for li in bloc.splitlines() if '"stock" + ?' in li)
    assert ">= ?" not in rendu, "la restitution ne doit porter aucune condition"
    # And it gives back to the line's product: the column is named in the
    # preceding read, restitution reuses its value.
    assert 'SELECT "quantite", "produit_id"' in bloc


def test_restitution_reads_the_line_before_deleting_it(tmp_path, capsys):
    """After the DELETE, the line no longer exists and its foreign key with it:
    nothing says any more what to give back nor to whom. Same lesson as at point
    82 for aggregation — the order of the two statements IS the brick."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    bloc = ((tmp_path / "app.py").read_text(encoding="utf-8")
            .split("def delete_ligne(")[1].split("\n@app.")[0])
    lecture = bloc.index('SELECT "quantite", "produit_id"')
    suppression = bloc.index('DELETE FROM "ligne"')
    assert lecture < suppression, "la quantité est lue après la suppression"


# --------------------------------------------------------------------------
# POINT 92: the variable that leaked from one branch to another
# --------------------------------------------------------------------------

SPEC_SANS_CREATE = """app SansCreate

entity Fiche
    titre: String

relation Client hasMany Fiche

actor Client selfRegister

rule Fiche.Read ownedBy Client
rule Fiche.Update ownedBy Client

workflow Consulter for Client
    Read Fiche
    Update Fiche
"""


def test_an_update_without_any_create_compiles(tmp_path, capsys):
    """REGRESSION (point 91 → 92): counting on PUT read `reputation_rules_here`,
    a variable assigned in the `Create` branch. A spec with no `Create` therefore
    CRASHED the compiler — "cannot access local variable". No example or test
    exercised this path: every spec in the repository creates something."""
    (tmp_path / "spec.ml").write_text(SPEC_SANS_CREATE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    assert "def update_fiche(" in (tmp_path / "app.py").read_text(encoding="utf-8")


SPEC_FUITE = """app Fuite

entity Produit
    nom: String
    stock: Integer

entity Ligne
    quantite: Integer

entity Avis
    quantite: Integer
    texte: String

relation Client hasMany Ligne
relation Produit hasMany Ligne
relation Client hasMany Avis
relation Produit hasMany Avis

actor Client selfRegister

rule Produit.Read public
rule Produit.stock min 0
rule Ligne.quantite required
rule Avis.quantite required
rule Ligne.Create decrements Produit.stock by quantite

workflow Acheter for Client
    Read Produit
    Create Ligne
    Read Ligne
    Read Avis
    Update Avis
"""


def test_counting_rules_do_not_leak_from_one_entity_to_another(tmp_path, capsys):
    """The other face of the same regression, and the sneakiest: the `Update`
    branch inherited the rules of the LAST created entity. `Avis` carries no
    `decrements` — yet updating a review counted down a product's stock (checked
    in the generated SQL before the fix).

    The coincidence that hid the defect: when `Create X` immediately precedes
    `Update X`, the variable contains the right rules. Another entity slipping in
    between is enough for that to no longer hold."""
    (tmp_path / "spec.ml").write_text(SPEC_FUITE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    bloc = ((tmp_path / "app.py").read_text(encoding="utf-8")
            .split("def update_avis(")[1].split("\n@app.")[0])
    assert '"stock"' not in bloc, "l'Update d'Avis touche au stock d'un Produit"
    assert "_delta" not in bloc
