"""The four rules that did nothing: required, unique, min, max — point 85.

Why this file exists. `required`, `unique`, `min` and `max` are the compiler's
OLDEST rules, present before all the bricks. They were accepted by the
grammar, and **that was all**. Two findings, both obtained by execution:

* a phantom reference went through silently. `rule Colis.champFantome
  required` compiled; so did `rule Fantome.reference required`. Every brick
  added since (`hidden`, `generated`, `categorized`, `payable`,
  `derivedFrom`, `sumOf`) validated its reference — the original four, never;
* **the output was byte-identical** with or without them. The same project
  compiled twice, once with `rule X.f required` and `rule X.g unique`, once
  without: `diff` silent on `app.py` AND on `schema.sql`.

The first repository to suffer from it was the repository itself.
`exemples/02_boutique.ml` declares `rule Product.price min 0` and
`rule Product.stock min 0`; the server accepted `price: -99, stock: -5` and
wrote them to the database. In a shop where the price is multiplied into a
subtotal (`derivedFrom`), summed into a total (`sumOf`) and sent to the
provider (`payable`), this bound was the last thing between the catalog and a
charged negative amount.

What this file guards, and in this order: reference refusals (the "we do not
promise what we do not enforce" half), then behavior against a real server
(the "we enforce what we promise" half). Compile coverage alone would have
seen nothing: it saw nothing for the project's whole life.
"""
import json
import os
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
from tests.support.cas import check_each_case
from tests.support.server import free_port as _port_libre

SPEC = """app BancContraintes

entity Membre
    pseudo: String
    courriel: Email
    age: Integer

actor Visiteur selfRegister

rule Membre.pseudo unique
rule Membre.pseudo min 3
rule Membre.age min 18
rule Membre.age max 120
rule Membre.Read public

workflow Gerer for Visiteur
    Create Membre
    Read Membre
    Update Membre
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


def _without_constraints(spec):
    """The same spec, without its four constraint rules."""
    return "\n".join(li for li in spec.splitlines()
                     if not any(li.strip().endswith(f" {mot}")
                                or f" {mot} " in li for mot in
                                ("unique", "required", "min", "max"))) + "\n"


# --------------------------------------------------------------------------
# What must no longer compile: a constraint that applies to nothing
# --------------------------------------------------------------------------

def test_a_well_formed_spec_compiles(capsys):
    """The witness of all refusals: without it, a validator refusing EVERY
    constraint would pass them all."""
    ast = _valide(SPEC)
    contraintes = ast["security"]["field_constraints"]
    assert contraintes[("Membre", "pseudo")]["unique"] is True
    assert contraintes[("Membre", "pseudo")]["min"] == {"portee": "longueur", "valeur": 3}
    assert contraintes[("Membre", "age")]["min"] == {"portee": "valeur", "valeur": 18}
    capsys.readouterr()


def test_a_nonexistent_field_is_refused(capsys):
    """THE point 85 defect: these four lines compiled without a word. The author
    believes they hold a constraint, they have none, and nothing says so."""
    table = [
        "rule Membre.champFantome required",
        "rule Membre.champFantome unique",
        "rule Membre.champFantome min 2",
        "rule Membre.champFantome max 9",
    ]

    def cas(regle):
        with pytest.raises(ASTValidationError) as refus:
            _valide(SPEC + regle + "\n")
        message = str(refus.value)
        assert "champFantome" in message
        assert "does not declare" in message
        # The message must say WHY the refusal is there, not only refuse.
        assert "does not apply to anything" in message
        capsys.readouterr()

    check_each_case([(valeur,) for valeur in table], cas)


def test_a_nonexistent_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Fantome.pseudo required\n")
    assert "'Fantome'" in str(refus.value) and "which does not exist" in str(refus.value)
    capsys.readouterr()


def test_a_case_typo_gets_a_suggestion(capsys):
    """The most likely mistake is a typo: the refusal must suggest the
    neighboring field rather than leave people searching."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.Pseudo required\n")
    assert "Did you mean 'pseudo'" in str(refus.value)
    capsys.readouterr()


def test_a_bound_on_an_unboundable_type_is_refused(capsys):
    spec = SPEC.replace("    age: Integer", "    age: Integer\n    actif: Boolean")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec + "rule Membre.actif min 1\n")
    assert "Boolean" in str(refus.value)
    capsys.readouterr()


def test_a_max_beyond_the_column_is_refused(capsys):
    """The constraint would promise data the database cannot hold: String is a
    VARCHAR(255) column."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.pseudo max 400\n")
    assert "255" in str(refus.value)
    capsys.readouterr()


def test_contradictory_bounds_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.courriel min 40\nrule Membre.courriel max 10\n")
    assert "no value satisfies both" in str(refus.value)
    capsys.readouterr()


def test_a_bound_on_a_server_calculated_field_is_refused(capsys):
    """A bound lives in the Pydantic schema, hence in the request body. On a
    field the server fills, that field is NOT there: the bound would apply to
    nothing — that is, the very fault point 85 fixes."""
    spec = """app BancSomme

entity Ligne
    quantite: Integer

entity Panier
    total: Integer

entity Client
    nom: String

relation Client hasMany Panier
relation Panier hasMany Ligne
# Carries the ownership column of the customer record itself: without it,
# 'Client.Read ownedBy Client' is refused BEFORE the bound we want to test.
relation Client hasMany Client

# Actor NAMED LIKE the owning entity: 'ownedBy Client' must lead back to an
# account. Naming the actor otherwise hits point 81's chain refusal, and the
# test would no longer test what it announces.
actor Client selfRegister

rule Ligne.quantite required
rule Panier.Read ownedBy Client
rule Panier.Update ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Panier
rule Panier.total sumOf Ligne.quantite
rule Panier.total min 0

workflow Acheter for Client
    Create Panier
    Read Panier
    Update Panier
    Create Ligne
    Read Ligne
    Create Client
    Read Client
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "the SERVER calculates this field" in str(refus.value)
    capsys.readouterr()


def test_the_same_constraint_twice_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.pseudo unique\n")
    assert "declared twice on the same field" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation must produce — and did not
# --------------------------------------------------------------------------

def test_the_constraints_change_the_output(tmp_path, capsys):
    """The finding that opened point 85, turned into a guard: compiling with and
    without the four rules gave a SILENT `diff` on app.py and schema.sql. This
    test fails the day one of them becomes decorative again."""
    avec, sans = tmp_path / "avec", tmp_path / "sans"
    for dossier, spec in ((avec, SPEC), (sans, _without_constraints(SPEC))):
        dossier.mkdir()
        (dossier / "spec.ml").write_text(spec, encoding="utf-8")
        compile_project(str(dossier / "spec.ml"), str(dossier))
    capsys.readouterr()

    app_avec = (avec / "app.py").read_text(encoding="utf-8")
    app_sans = (sans / "app.py").read_text(encoding="utf-8")
    assert app_avec != app_sans
    assert "min_length=3" in app_avec and "min_length=3" not in app_sans
    assert "ge=18" in app_avec and "le=120" in app_avec
    assert "idx_unique_membre_pseudo" in app_avec
    assert "idx_unique_membre_pseudo" not in app_sans


def test_the_contract_announces_the_constraints(tmp_path, capsys):
    """An interface ignoring the bounds lets a form be filled only to be refused
    at the end, while it could have said so right away. Same reason as for
    `server_generated` at point 79: the contract describes what the backend
    really does, including what it REFUSES."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    contrat = json.loads((tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    champs = {f["name"]: f for f in contrat["entities"]["Membre"]["fields"]}
    assert champs["pseudo"]["min_length"] == 3
    assert champs["pseudo"]["unique"] is True
    assert "409" in champs["pseudo"]["unique_note"]
    assert champs["age"]["min_value"] == 18
    assert champs["age"]["max_value"] == 120


def test_custom_blocks_no_longer_call_a_deprecated_method(tmp_path, capsys):
    """`payload.dict()` is deprecated in Pydantic v2 and REMOVED in v3: every
    backend carrying a 'custom' block would have stopped working at the first
    installation on Pydantic 3. No example, no test exercised this path —
    schemas.py's coverage hole is what found it."""
    spec = """app BancCustom

entity Colis
    reference: String

actor Client selfRegister

rule Colis.Read public

custom Estimer
    description: "Estime un délai"
    input: poids: Float, destination: String
    output: jours: Integer

workflow Suivre for Client
    Read Colis
    Execute Estimer
"""
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "payload.model_dump()" in genere
    assert ".dict()" not in genere


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
            return err.code, {"brut": brut[:200].decode("utf-8", "replace")}
        finally:
            err.close()


@pytest.fixture
def server(tmp_path):
    """A real ephemeral server on the bench spec."""
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
                sortie = processus.stdout.read().decode("utf-8", "replace")
                pytest.fail(f"the server stopped:\n{sortie[-2000:]}")
            try:
                # /docs returns HTML: probing with _appel (which decodes JSON)
                # would make a READY server pass for a silent one.
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("the server never answered")
        _appel(base + "/register", {"username": "v", "password": "motdepasse1",
                                    "actor": "Visiteur"})
        _, corps = _appel(base + "/login", {"username": "v",
                                            "password": "motdepasse1"})
        yield base, corps["access_token"], tmp_path
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait(timeout=5)
        if processus.stdout is not None:
            processus.stdout.close()


def test_unique_refuses_a_duplicate_on_creation(server):
    """Before point 85: both POSTs answered 200 and the database carried two
    rows. Checked, not assumed."""
    base, jeton, dossier = server
    membre = {"pseudo": "zoe", "courriel": "z@x.fr", "age": 30}
    code1, _ = _appel(base + "/membre", membre, jeton)
    code2, corps2 = _appel(base + "/membre", membre, jeton)
    assert code1 == 200
    assert code2 == 409
    # The message must name the CAUSE: the same 409 already served for foreign
    # keys, and "invalid reference" would send people looking elsewhere.
    assert "unique" in corps2["detail"] and "pseudo" in corps2["detail"]

    base_donnees = sqlite3.connect(dossier / "app.db")
    try:
        lignes = base_donnees.execute(
            "SELECT COUNT(*) FROM membre WHERE pseudo = 'zoe'").fetchone()[0]
    finally:
        base_donnees.close()
    assert lignes == 1, "uniqueness must hold IN THE DATABASE, not only in the response"


def test_unique_refuses_a_duplicate_on_update(server):
    """The Update route wrote no foreign key, so it had no guard: the first try
    of this brick gave a 500 and left the connection open. SQLite raises at
    `execute`, not at `commit`."""
    base, jeton, _ = server
    _appel(base + "/membre", {"pseudo": "zoe", "courriel": "z@x.fr", "age": 30}, jeton)
    _appel(base + "/membre", {"pseudo": "autre", "courriel": "b@x.fr", "age": 40}, jeton)

    code, corps = _appel(base + "/membre/1",
                         {"pseudo": "autre", "courriel": "z@x.fr", "age": 30},
                         jeton, methode="PUT")
    assert code == 409, f"500 = the guard is missing or wraps the wrong call ({corps})"
    # Witness: a legitimate update still passes.
    code_ok, _ = _appel(base + "/membre/1",
                        {"pseudo": "zoe2", "courriel": "z@x.fr", "age": 31},
                        jeton, methode="PUT")
    assert code_ok == 200


@pytest.mark.parametrize("corps, champ", [
    ({"pseudo": "ab", "courriel": "a@x.fr", "age": 30}, "pseudo"),   # min 3
    ({"pseudo": "abc", "courriel": "a@x.fr", "age": 17}, "age"),     # min 18
    ({"pseudo": "abd", "courriel": "a@x.fr", "age": 130}, "age"),    # max 120
])
def test_bounds_give_a_422_before_any_insert(server, corps, champ):
    base, jeton, dossier = server
    code, reponse = _appel(base + "/membre", corps, jeton)
    assert code == 422
    assert any(champ in str(e.get("loc", "")) for e in reponse["detail"])
    base_donnees = sqlite3.connect(dossier / "app.db")
    try:
        assert base_donnees.execute("SELECT COUNT(*) FROM membre").fetchone()[0] == 0
    finally:
        base_donnees.close()


def test_a_value_within_bounds_passes(server):
    """The witness of the three refusals above."""
    base, jeton, _ = server
    code, _ = _appel(base + "/membre",
                     {"pseudo": "zoe", "courriel": "z@x.fr", "age": 18}, jeton)
    assert code == 200


def test_a_database_with_duplicates_says_so_instead_of_hiding_it(tmp_path, capsys):
    """A unique index CANNOT be created on data already duplicated. It is a
    non-automatable change (docs/MIGRATIONS.md): the server must NAME it at
    startup, and keep running — not swallow the error in the "ℹ️ DB already
    initialized" that would hide the rest of the script."""
    (tmp_path / "spec.ml").write_text(_without_constraints(SPEC), encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    # A database populated BEFORE 'unique' existed in the spec.
    base_donnees = sqlite3.connect(tmp_path / "app.db")
    try:
        with base_donnees:
            base_donnees.executescript(
                (tmp_path / "schema.sql").read_text(encoding="utf-8"))
            base_donnees.executemany(
                'INSERT INTO membre ("pseudo", "courriel", "age") VALUES (?, ?, ?)',
                [("zoe", "a@x.fr", 30), ("zoe", "b@x.fr", 40)])
    finally:
        base_donnees.close()

    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    sortie = subprocess.run(
        [sys.executable, "-c", "import app; app.init_db()"],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(tmp_path)}, timeout=60)
    trace = sortie.stdout + sortie.stderr
    assert "pseudo" in trace and "duplicate" in trace, trace[-1500:]
    assert sortie.returncode == 0, "the server must keep starting"
