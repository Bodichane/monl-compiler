"""The phantom attachment — point 99.

What the compiler did. An entity that is a child of a BUSINESS table (a
variant and its product) received, in the `produit_id` column, the id of the
ACCOUNT that created it — and `schema.sql` declared it
`REFERENCES _monl_users(id)`. The client had no way to designate the product:
the column carried the business link's name and contained something else.
Silent, at compile time as at runtime.

Why nobody had seen it. No example of the repository presents this case:
`Like` and `Report` escape it because they are counter targets (the client
designates "THIS post"), `Comment` because it declares `ownedBy Member`,
`OrderLine` because it is owned transitively. All five examples compile an
entity that is a child of an ACTOR. The probe that revealed it fit in three
relations.

What the point decides, and what did not go without saying:

* **"filled from identity" requires the parent to BE an account.** The
  condition was missing: any incoming relation would do. It is point 80's
  defect from the other end — there an entity was named as owner and the
  attachment was wrong, here none is named and it is just as wrong;
* **the choice no longer depends on declaration order.** Only actor parents
  are candidates; among them, `ownedBy` decides;
* **`payable` loses an ACCIDENTAL safeguard, hence gains a refusal.** The
  payment route compared the ownership column with the caller. It was only
  right because the column received `current_user_id` for lack of anything
  better — that is, because of the bug. With the attachment honest again, the
  comparison would become wrong: the refusal must be written.
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
from monl.cli import _contract_signature, compile_project
from monl.parser import parse_monl_string
from tests.support.process import stop_process
from tests.support.server import free_port as _port_free

# The BUSINESS relation (`Produit hasMany Variante`) is declared BEFORE the
# others, on purpose: the old implementation kept the first incoming relation
# that came along, and a bench declaring it last would hide half of the defect.
SPEC = """app BancRattachement

entity Produit
    nom: String

entity Variante
    taille: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Client
    nom: String

relation Produit hasMany Variante
relation Client hasMany Commande
relation Commande hasMany Ligne
relation Variante hasMany Ligne
relation Client hasMany Client

actor Client selfRegister
actor Patron selfRegister

rule Produit.Read public
rule Variante.Read public
rule Variante.stock min 0
rule Ligne.quantite required
rule Ligne.quantite min 1
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Variante.stock by quantite

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Delete Ligne
    Create Client
    Read Client
    Read Produit
    Read Variante

workflow Gerer for Patron
    Create Produit
    Read Produit
    Create Variante
    Read Variante
    Update Variante

seed Produit
    nom: "Halo RS"
    nom: "Deck Low"
    nom: "Court Mid"
"""


def _valid(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


def _compile(tmp_path, spec=SPEC):
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    contract = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return contract, (tmp_path / "app.py").read_text(encoding="utf-8"), \
        (tmp_path / "schema.sql").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(tmp_path, capsys):
    """The witness of everything that follows."""
    contract, _, _ = _compile(tmp_path)
    assert "Variante" in contract["entities"]
    capsys.readouterr()


def test_the_business_parent_references_the_business_table(tmp_path, capsys):
    """THE bug. `produit_id` was declared `REFERENCES _monl_users(id)`: the
    variant pointed to the account registry, never to its product."""
    _, _, schema = _compile(tmp_path)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"produit_id"' in li
              and "FOREIGN KEY" in li)
    assert 'REFERENCES "produit"(id)' in fk
    assert "_monl_users" not in fk


def test_the_business_parent_is_designated_by_the_client(tmp_path, capsys):
    """The other half of the same defect: the column received `current_user_id`,
    so NO product could be designated at creation."""
    _, generated, _ = _compile(tmp_path)
    capsys.readouterr()
    insertion = next(li for li in generated.splitlines()
                     if 'INSERT INTO "variante"' in li)
    assert '"produit_id"' in insertion
    values = generated.splitlines()[generated.splitlines().index(insertion) + 2]
    assert "data.produit_id" in values
    assert "current_user_id" not in values


def test_the_business_parent_enters_the_input_schema(tmp_path, capsys):
    """A column the client must provide and no schema accepts would give an
    unavoidable 422 — point 57's defect, replayed."""
    _, generated, _ = _compile(tmp_path)
    capsys.readouterr()
    debut = generated.index("class VarianteSchema")
    assert "produit_id: int" in generated[debut:debut + 400]


def test_the_actor_parent_did_not_move(tmp_path, capsys):
    """The non-regression that counts: the CORRECT case — an entity that is a
    child of an actor — must keep being filled from the token. A fix making every
    foreign key client-supplied would open a much wider hole than the one it
    closes."""
    _, generated, schema = _compile(tmp_path)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"client_id"' in li
              and "FOREIGN KEY" in li and "commande" not in li.lower())
    assert "_monl_users" in fk
    insertion = next(li for li in generated.splitlines()
                     if 'INSERT INTO "commande"' in li)
    assert '"client_id"' in insertion
    debut = generated.index("class CommandeSchema")
    assert "client_id" not in generated[debut:debut + 300], \
        "the owner column must NEVER enter the request body"


def test_a_counter_target_stays_designated_by_the_client(tmp_path, capsys):
    """Brick 3 non-regression: "I report THIS member" is the client's choice, not
    a deduced ownership. This case already passed — it must keep doing so, and
    through the same path as before."""
    spec = SPEC.replace("relation Variante hasMany Ligne",
                        "relation Variante hasMany Ligne\nrelation Produit hasMany Avis")
    spec = spec.replace("entity Client\n    nom: String",
                        "entity Client\n    nom: String\n\nentity Avis\n    note: Integer")
    spec = spec.replace("rule Ligne.Create decrements Variante.stock by quantite",
                        "rule Ligne.Create decrements Variante.stock by quantite\n"
                        "rule Avis.Create increments Produit.avis by 1")
    spec = spec.replace("entity Produit\n    nom: String",
                        "entity Produit\n    nom: String\n    avis: Integer")
    spec = spec.replace("    Read Variante\n\nworkflow Gerer",
                        "    Read Variante\n    Create Avis\n    Read Avis\n\nworkflow Gerer")
    _, generated, schema = _compile(tmp_path, spec)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"produit_id"' in li
              and "FOREIGN KEY" in li)
    assert 'REFERENCES "produit"(id)' in fk
    assert "data.produit_id" in generated


def test_the_choice_does_not_depend_on_relation_order(tmp_path, capsys):
    """The old implementation kept `placements[0]`: two parents, and the owner
    was decided by the spec's writing order. A business parent declared first
    stole the actor's place."""
    base = SPEC.replace("entity Client\n    nom: String",
                        "entity Client\n    nom: String\n\nentity Avis\n    note: Integer")
    base = base.replace("    Read Variante\n\nworkflow Gerer",
                        "    Read Variante\n    Create Avis\n    Read Avis\n\nworkflow Gerer")
    metier_first = base.replace(
        "relation Client hasMany Client",
        "relation Produit hasMany Avis\nrelation Client hasMany Avis\n"
        "relation Client hasMany Client")
    actor_first = base.replace(
        "relation Client hasMany Client",
        "relation Client hasMany Avis\nrelation Produit hasMany Avis\n"
        "relation Client hasMany Client")
    _, _, schema_a = _compile(tmp_path, metier_first)
    _, _, schema_b = _compile(tmp_path, actor_first)
    capsys.readouterr()

    def review_links(schema):
        block = schema[schema.index('CREATE TABLE IF NOT EXISTS "avis"'):]
        # The trailing comma depends on the line's RANK in the block, not its
        # meaning: remove it, otherwise the test compares formatting.
        return {li.strip().rstrip(",") for li in block.splitlines()
                if "FOREIGN KEY" in li}

    assert review_links(schema_a) == review_links(schema_b)
    assert any('"client_id"' in li and "_monl_users" in li
               for li in review_links(schema_a))
    assert any('"produit_id"' in li and '"produit"(id)' in li
               for li in review_links(schema_a))


# --------------------------------------------------------------------------
# What the contract must say
# --------------------------------------------------------------------------

def test_the_contract_says_what_the_column_contains(tmp_path, capsys):
    """POINT 88: a join made on the wrong one of the two natures works HALFWAY.
    The contract announced `references_account` on a column carrying a product
    id."""
    contract, _, _ = _compile(tmp_path)
    capsys.readouterr()
    link = next(li for li in contract["entities"]["Variante"]["foreign_keys"]
                if li["column"] == "produit_id")
    assert link["references_account"] is False
    assert link["references"] == "Produit"
    assert "produit_id" in contract["entities"]["Variante"]["client_foreign_keys"]


def test_the_contract_asks_for_the_parent_in_the_body(tmp_path, capsys):
    """Without it, an interface AI faithful to the contract builds a form without
    product choice and collects a 422 on every creation."""
    contract, _, _ = _compile(tmp_path)
    capsys.readouterr()
    route = next(r for r in contract["routes"]
                 if r["path"] == "/variante" and r["method"] == "POST")
    assert "produit_id" in route["request_fields"]


def test_the_delta_sees_the_change_of_nature(tmp_path, capsys):
    """The question CLAUDE.md requires asking BEFORE writing: does
    `_contract_signature` see it? A foreign key does not live in `fields` — the
    answer was no, for the sixth time."""
    contract_metier, _, _ = _compile(tmp_path)
    actor = SPEC.replace("relation Produit hasMany Variante",
                          "relation Client hasMany Variante")
    contract_actor, _, _ = _compile(tmp_path, actor)
    capsys.readouterr()
    links_metier = _contract_signature(contract_metier)[7]
    links_actor = _contract_signature(contract_actor)[7]
    assert links_metier != links_actor
    assert any("produit_id" in li and "to be sent by the client" in li
               for li in links_metier)
    assert any("client_id" in li and "account identifier" in li
               and "filled by the server" in li for li in links_actor)


# --------------------------------------------------------------------------
# The refusal the fix makes necessary
# --------------------------------------------------------------------------


# The line amount is CALCULATED (point 77): otherwise point 82's cross-check
# would refuse the spec before reaching the check we want to test — summing an
# amount the client writes is already forbidden.
SPEC_PAYMENT = """app BancEncaissement

entity Produit
    nom: String
    prix: Money

entity Facture
    total: Money

entity Ligne
    quantite: Integer
    montant: Money

relation Produit hasMany Facture
relation Facture hasMany Ligne
relation Client hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Ligne.Read ownedBy Client
rule Ligne.quantite required
rule Ligne.montant derivedFrom Produit.prix by quantite
rule Facture.total sumOf Ligne.montant
rule Facture.total payable

workflow Acheter for Client
    Create Facture
    Read Facture
    Create Ligne
    Read Ligne
"""

# The same charge, but the invoice is owned THROUGH the order: point 87's join
# returns an ACCOUNT id, so the refusal must not apply. Written in full rather
# than derived by substitution — an ownership chain reads badly in
# `.replace()`.
SPEC_PAYMENT_TRANSITIVE = """app BancEncaissementTransitif

entity Produit
    nom: String
    prix: Money

entity Commande
    statut: String

entity Facture
    total: Money

entity Ligne
    quantite: Integer
    montant: Money

relation Client hasMany Commande
relation Commande hasMany Facture
relation Facture hasMany Ligne
relation Client hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Commande.Read ownedBy Client
rule Facture.Read ownedBy Commande
rule Ligne.Read ownedBy Client
rule Ligne.quantite required
rule Ligne.montant derivedFrom Produit.prix by quantite
rule Facture.total sumOf Ligne.montant
rule Facture.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Facture
    Read Facture
    Create Ligne
    Read Ligne
"""


def test_charging_without_an_actor_owner_is_refused(capsys):
    """The ACCIDENTAL safeguard the fix removes. This spec compiled: the payment
    route compared `produit_id` with the calling account's id, and the comparison
    was right only because the column received `current_user_id` — that is,
    because of the bug. Without this refusal, the owner could no longer pay, and a
    stranger could as soon as the two ids coincide."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_PAYMENT)
    assert "ACTOR" in str(refusal.value)
    assert "Facture" in str(refusal.value)
    capsys.readouterr()


def test_the_refusal_witness(capsys):
    """The same spec with an actor parent must compile — otherwise the refusal
    above would forbid the brick instead of forbidding the fault."""
    ast = _valid(SPEC_PAYMENT.replace(
        "relation Produit hasMany Facture",
        "relation Produit hasMany Facture\nrelation Client hasMany Facture"))
    assert ast["security"]["payable_fields"]
    capsys.readouterr()


def test_the_refusal_lets_transitive_ownership_through(capsys):
    """POINT 87: under a chain, the join returns an ACCOUNT id. The new refusal
    must not reopen the lock that point had lifted."""
    ast = _valid(SPEC_PAYMENT_TRANSITIVE)
    assert ast["security"]["payable_fields"]
    capsys.readouterr()


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
                return err.code, {"brut": brut[:300].decode("utf-8", "replace")}


@pytest.fixture
def boutique(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_free()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if process.poll() is not None:
                pytest.fail(process.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5) as response:
                    response.read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("the server never answered")
        # The seller registers LAST, after three other accounts: their id (4)
        # then coincides with NONE of the three products'. Without this
        # divergence, "account id" and "product id" are equivalent and the
        # faulty attachment would pass the test — it is the lesson of point
        # 81's probe, and it holds here word for word.
        for appearing in ("zoe", "ines", "malik"):
            _call(base + "/register", {"username": appearing,
                                        "password": "motdepasse1",
                                        "actor": "Client"})
        _call(base + "/register", {"username": "victor", "password": "motdepasse1",
                                    "actor": "Patron"})
        _, token_client = _call(base + "/login", {"username": "zoe",
                                                   "password": "motdepasse1"})
        _, token_patron = _call(base + "/login", {"username": "victor",
                                                   "password": "motdepasse1"})
        yield (base, token_client["access_token"], token_patron["access_token"],
               tmp_path)
    finally:
        stop_process(process, delay=10)


def _in_database(tmp_path, query, params=()):
    login = sqlite3.connect(str(tmp_path / "app.db"))
    try:
        return login.execute(query, params).fetchall()
    finally:
        login.close()


def test_the_variant_attaches_to_its_product(boutique):
    """The behavior everything else serves. Read in the DATABASE, not in the
    response: the read route would do a `SELECT *` and return the same thing
    whatever value was written."""
    base, _, patron, tmp_path = boutique
    _, catalogue = _call(base + "/produit?limit=20")
    deck = next(p for p in catalogue["data"] if p["nom"] == "Deck Low")

    accounts = _in_database(tmp_path, "SELECT id FROM _monl_users WHERE username = 'victor'")
    id_account = accounts[0][0]
    assert id_account != deck["id"], \
        "the two ids must DIVERGE, otherwise the test proves nothing"

    code, variant = _call(base + "/variante",
                            {"taille": "42", "stock": 5, "produit_id": deck["id"]},
                            patron)
    assert code == 200
    attachment = _in_database(tmp_path, 'SELECT "produit_id" FROM "variante" WHERE id = ?',
                            (variant["id"],))[0][0]
    assert attachment == deck["id"]
    assert attachment != id_account, \
        "the column carried the creating ACCOUNT's id, never the product's"


def test_the_designated_product_is_the_requested_one(boutique):
    """Two products, two variants: the attachment must FOLLOW the request, not a
    constant that would happen to be right one time out of two."""
    base, _, patron, tmp_path = boutique
    _, catalogue = _call(base + "/produit?limit=20")
    products = {p["nom"]: p["id"] for p in catalogue["data"]}
    poses = {}
    for name, size in (("Halo RS", "41"), ("Court Mid", "44")):
        _, variant = _call(base + "/variante",
                             {"taille": size, "stock": 2,
                              "produit_id": products[name]}, patron)
        poses[name] = variant["id"]
    for name, variant_id in poses.items():
        assert _in_database(tmp_path, 'SELECT "produit_id" FROM "variante" WHERE id = ?',
                        (variant_id,))[0][0] == products[name]


def test_stock_is_counted_per_variant(boutique):
    """The whole chain, end to end: it is the "stock per size" model a merchant
    keeps, and it did not hold together as long as the variant did not know which
    product it belonged to."""
    base, client, patron, _ = boutique
    _, catalogue = _call(base + "/produit?limit=20")
    halo = next(p["id"] for p in catalogue["data"] if p["nom"] == "Halo RS")
    _, forty_two = _call(base + "/variante",
                              {"taille": "42", "stock": 4, "produit_id": halo}, patron)
    _, forty_three = _call(base + "/variante",
                               {"taille": "43", "stock": 4, "produit_id": halo}, patron)

    _call(base + "/client", {"nom": "Zoe"}, client)
    _, order = _call(base + "/commande", {"statut": "panier"}, client)
    code, _ = _call(base + "/ligne",
                     {"quantite": 3, "commande_id": order["id"],
                      "variante_id": forty_two["id"]}, client)
    assert code == 200

    _, apres_42 = _call(f"{base}/variante/{forty_two['id']}")
    _, apres_43 = _call(f"{base}/variante/{forty_three['id']}")
    assert apres_42["data"]["stock"] == 1
    assert apres_43["data"]["stock"] == 4, \
        "two sizes of the same product have INDEPENDENT stocks"


def test_the_floor_holds_per_variant(boutique):
    """The previous test's witness: without an effective floor, "stock per size"
    would show pairs that do not exist."""
    base, client, patron, _ = boutique
    _, catalogue = _call(base + "/produit?limit=20")
    halo = next(p["id"] for p in catalogue["data"] if p["nom"] == "Halo RS")
    _, variant = _call(base + "/variante",
                         {"taille": "45", "stock": 2, "produit_id": halo}, patron)
    _call(base + "/client", {"nom": "Zoe"}, client)
    _, order = _call(base + "/commande", {"statut": "panier"}, client)
    code, response = _call(base + "/ligne",
                           {"quantite": 3, "commande_id": order["id"],
                            "variante_id": variant["id"]}, client)
    assert code == 409
    assert "insufficient" in json.dumps(response)
    _, apres = _call(f"{base}/variante/{variant['id']}")
    assert apres["data"]["stock"] == 2, "a refusal must have consumed nothing"


def test_a_nonexistent_product_creates_no_orphan_variant(boutique):
    """The counterpart of "the client provides the key": it must be CHECKED on
    write. Here the foreign key constraint takes care of it — point 81's design
    rule, applied to the other family of columns."""
    base, _, patron, tmp_path = boutique
    before = _in_database(tmp_path, 'SELECT COUNT(*) FROM "variante"')[0][0]
    code, _ = _call(base + "/variante",
                     {"taille": "42", "stock": 1, "produit_id": 99999}, patron)
    assert code == 409
    assert _in_database(tmp_path, 'SELECT COUNT(*) FROM "variante"')[0][0] == before
