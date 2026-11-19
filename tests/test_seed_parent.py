"""Brick 21: a demo dataset can attach a child — point 100.

Why the brick. Point 99 made honest the foreign key of an entity that is a
child of a business table. Such an entity still could not appear in demo
data: a `seed` only accepts DECLARED fields, and an attachment column is not
one. A shop with variants therefore opened on a catalog where nothing could
be ordered — compile coverage without the behavior, exactly what point 95
denounces.

    seed Variant for Product.name "Chaise Ligne"
        finish: "Chêne naturel", price: 249.90, stock: 12

What the brick decides, and what did not go without saying:

* **designate by a VALUE, never by a rank.** A line number cannot be read and
  shifts as soon as a line is inserted in the middle. It is already the choice
  of `monl assets add --for "Halo RS"` (point 84), and for the same reason: it
  is what the human has in front of them;
* **an ambiguous designation is REFUSED.** Two rows carrying the designated
  value would give a different showcase from one compilation to the next, and
  nobody would see it before looking at the screen;
* **the attachment is resolved at STARTUP, by a read.** A rank computed at
  compile time would have assumed the parent was just seeded. But the base
  only seeds a table if it is EMPTY: on a database where the products already
  exist, the rank would have designated the wrong row. The test proving it is
  `test_the_attachment_follows_the_real_id_not_the_rank`.
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
from tests.support.processus import arreter_processus, fermer_tubes
from tests.support.server import free_port as _port_libre

SPEC = """app BancSemis

entity Produit
    nom: String
    categorie: String

entity Variante
    finition: String
    prix: Money
    stock: Integer

actor Patron selfRegister

relation Produit hasMany Variante

rule Produit.Read public
rule Variante.Read public
rule Variante.stock min 0

workflow Gerer for Patron
    Create Produit
    Read Produit
    Create Variante
    Read Variante

seed Produit
    nom: "Chaise Ligne", categorie: "Assises"
    nom: "Lampe Arc", categorie: "Luminaires"
    nom: "Table Onde", categorie: "Tables"

# The targeted parent is the THIRD: if the attachment were computed from a rank
# in the child block, it would land on the first product and the test would
# pass for the wrong reasons.
seed Variante for Produit.nom "Table Onde"
    finition: "Frêne ondé", prix: 1200.00, stock: 2
    finition: "Noyer massif", prix: 1450.00, stock: 1

seed Variante for Produit.nom "Chaise Ligne"
    finition: "Chêne naturel", prix: 249.90, stock: 12
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation must refuse
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    """The witness of the seven refusals that follow."""
    ast = _valide(SPEC)
    blocs = [s for s in ast["seeds"] if s["entity"] == "Variante"]
    assert len(blocs) == 2
    assert blocs[0]["parent"] == {"entity": "Produit", "field": "nom",
                                 "value": "Table Onde"}
    capsys.readouterr()


def test_a_parent_that_is_not_an_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Fantome.nom "Table Onde"'))
    assert "is not a declared entity" in str(refus.value)
    capsys.readouterr()


def test_a_parent_without_relation_is_refused(capsys):
    """Without a relation, no column carries the attachment: writing it would
    have nowhere to go."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("relation Produit hasMany Variante\n", ""))
    assert "no relation links them" in str(refus.value)
    capsys.readouterr()


def test_an_actor_parent_is_refused(capsys):
    """POINT 99: an ACTOR parent's column carries an ACCOUNT id. A demo dataset
    is inserted at startup, when no account exists yet — it has nobody to
    designate.

    The targeted parent here is an entity that is ALSO an actor (`Client`, like
    `projets/SneakerLab`'s `Customer`): it is the only case where the refusal is
    reachable, an actor without a namesake entity first hitting "is not a
    declared entity"."""
    spec = SPEC.replace(
        "entity Variante",
        "entity Client\n    nom: String\n\nentity Variante")
    spec = spec.replace("actor Patron selfRegister",
                        "actor Patron selfRegister\nactor Client selfRegister")
    spec = spec.replace("relation Produit hasMany Variante",
                        "relation Produit hasMany Variante\n"
                        "relation Client hasMany Variante")
    spec = spec.replace('seed Variante for Produit.nom "Table Onde"',
                        'seed Variante for Client.nom "Zoe"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "ACCOUNT identifier" in str(refus.value)
    capsys.readouterr()


def test_a_nonexistent_designation_field_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Produit.fantome "Table Onde"'))
    assert "is not a declared field" in str(refus.value)
    capsys.readouterr()


def test_designating_by_a_number_is_refused(capsys):
    """Matching two floats is already dubious; above all, a price NAMES nothing.
    The designation must be readable."""
    spec = SPEC.replace("entity Produit\n    nom: String",
                        "entity Produit\n    poids: Float\n    nom: String")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace('for Produit.nom "Table Onde"',
                             'for Produit.poids "3"'))
    assert "field that NAMES it" in str(refus.value)
    capsys.readouterr()


def test_a_parent_seeded_after_the_child_is_refused(capsys):
    """Data is inserted in block order. A parent declared after its child would
    not be in the database when attaching — and the row would be discarded at
    startup, without the spec having said anything false."""
    lignes = SPEC.split("seed Produit")
    inverse = ("app BancSemis" + lignes[0].split("app BancSemis")[1]
               + "seed Variante for Produit.nom \"Table Onde\"\n"
                 "    finition: \"Frêne ondé\", prix: 1200.00, stock: 2\n\n"
                 "seed Produit\n"
                 "    nom: \"Table Onde\", categorie: \"Tables\"\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(inverse)
    assert "BEFORE" in str(refus.value)
    capsys.readouterr()


def test_a_value_nobody_carries_is_refused(capsys):
    """THE slip the brick must catch: without this refusal, the showcase would be
    missing a whole section and nothing would say so."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Produit.nom "Table Ondée"'))
    assert "which no row in 'seed Produit' contains" in str(refus.value)
    capsys.readouterr()


def test_an_ambiguous_designation_is_refused(capsys):
    """Two rows carrying the designated value: nothing says which one. Guessing
    would give a different showcase from one compilation to the next."""
    spec = SPEC.replace('    nom: "Lampe Arc", categorie: "Luminaires"',
                        '    nom: "Table Onde", categorie: "Luminaires"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "2 rows" in str(refus.value)
    assert "values are distinct" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def test_the_base_carries_the_designation_not_a_rank(tmp_path, capsys):
    """The design decision, checked in the produced code: what travels to the
    server is the VALUE, not a computed identifier."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.startswith("_SEED_DATA"))
    assert "'column': 'produit_id'" in ligne
    assert "'field': 'nom'" in ligne
    assert "'value': 'Table Onde'" in ligne


def test_a_spec_without_attachment_seeds_as_before(tmp_path, capsys):
    """Non-regression: the shape of demo data changed (each entry is a pair), but
    a spec not using the brick must seed exactly what it seeded."""
    spec = SPEC.split("# Le parent visé")[0]
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.startswith("_SEED_DATA"))
    assert "'parent': None" in ligne
    assert "'nom': 'Chaise Ligne'" in ligne


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _appel(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        with err:
            return err.code, {}


def _demarrer(dossier, port):
    """Starts the server and returns (process, startup log)."""
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        if processus.poll() is not None:
            sortie = processus.stdout.read().decode("utf-8", "replace")[-2000:]
            fermer_tubes(processus)
            pytest.fail(sortie)
        try:
            with urllib.request.urlopen(base + "/docs", timeout=5) as reponse:
                reponse.read()
            return processus, base
        except OSError:
            time.sleep(0.25)
    arreter_processus(processus)
    pytest.fail("the server never answered")


def _arreter(processus):
    processus.terminate()
    try:
        # communicate() reads to the end AND closes the pipes.
        return processus.communicate(timeout=10)[0].decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        arreter_processus(processus)
        return ""


def _variantes(chemin_db):
    connexion = sqlite3.connect(str(chemin_db))
    try:
        return connexion.execute(
            'SELECT v.finition, p.nom FROM "variante" v '
            'LEFT JOIN "produit" p ON p.id = v."produit_id" '
            'ORDER BY v.id').fetchall()
    finally:
        connexion.close()


@pytest.fixture
def compile_banc(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return tmp_path


def test_seeded_variants_are_attached_to_the_right_product(compile_banc):
    """The behavior everything else serves. Read in the DATABASE through a join:
    the read route would return the same thing whatever value was written."""
    processus, base = _demarrer(compile_banc, _port_libre())
    try:
        code, catalogue = _appel(base + "/variante?limit=10")
        assert code == 200
        assert len(catalogue["data"]) == 3
    finally:
        _arreter(processus)
    assert _variantes(compile_banc / "app.db") == [
        ("Frêne ondé", "Table Onde"),
        ("Noyer massif", "Table Onde"),
        ("Chêne naturel", "Chaise Ligne"),
    ]


def test_seeding_stays_idempotent(compile_banc):
    """The base only seeds into an EMPTY table. A restart must not stack the
    variants — the brick must not undo that guarantee."""
    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)
    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)
    assert len(_variantes(compile_banc / "app.db")) == 3


def test_the_attachment_follows_the_real_id_not_the_rank(compile_banc):
    """THE test that settles between the two possible designs.

    We populate the products table BEFORE the first start, with ids matching no
    block rank: the base will therefore seed nothing there (non-empty table), and
    "Table Onde" carries id 41. An attachment computed at compile time would have
    written 3 — the row's rank in `seed Produit` — and the variants would have
    landed on a nonexistent product."""
    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    connexion.executescript((compile_banc / "schema.sql").read_text(encoding="utf-8"))
    connexion.execute('INSERT INTO "produit" (id, nom, categorie) VALUES (?,?,?)',
                      (17, "Chaise Ligne", "Assises"))
    connexion.execute('INSERT INTO "produit" (id, nom, categorie) VALUES (?,?,?)',
                      (41, "Table Onde", "Tables"))
    connexion.commit()
    connexion.close()

    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)

    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    try:
        liens = connexion.execute(
            'SELECT finition, "produit_id" FROM "variante" ORDER BY id').fetchall()
    finally:
        connexion.close()
    assert liens == [("Frêne ondé", 41), ("Noyer massif", 41),
                     ("Chêne naturel", 17)]


def test_a_parent_not_found_at_startup_is_named(compile_banc):
    """The only path where resolution fails: a database whose parent table is
    already populated OTHERWISE. The row is discarded — but never silently,
    otherwise one would look for the failure in the frontend."""
    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    connexion.executescript((compile_banc / "schema.sql").read_text(encoding="utf-8"))
    connexion.execute('INSERT INTO "produit" (nom, categorie) VALUES (?,?)',
                      ("Tabouret Pli", "Assises"))
    connexion.commit()
    connexion.close()

    processus, _ = _demarrer(compile_banc, _port_libre())
    journal = _arreter(processus)

    assert "Table Onde" in journal
    assert "Demo data skipped" in journal
    # "Chaise Ligne" does not exist either: the three rows are discarded, and
    # the server runs anyway.
    assert _variantes(compile_banc / "app.db") == []
