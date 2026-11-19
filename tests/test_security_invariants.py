"""Project-wide security invariant: on the REALLY generated code, no client
or runtime value lives in the text of a SQL query.

Point 107 (brick 24) shipped an access control that pasted `data.<fk>` into
the SQL text — 500 on every creation. Point 108 made the defect hard to write
(typed emission); this test makes it unshippable, and not only on the example
that revealed it: it compiles EVERY spec of the repository and checks the
invariant on each.

The method is AST, not substring: we look ONLY at string literals that are
SQL. An `x = data.y` in Python is not a string literal, hence never a false
positive — only a `'... = data.y ...'` INSIDE a query is faulty. That is
exactly the shape of point 107's defect.

What the generator must always do instead: `... WHERE col = ?` with the value
in the tuple passed to `cursor.execute`. A bound value leaves no trace in the
text.
"""

import ast
import glob
import os
import tempfile

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file, parse_monl_string
from tests.support.cases import check_each_case

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")

# Python expressions (client or runtime value) that must ALWAYS be bound as a
# parameter, hence never appear in a query's text.
FORBIDDEN_IN_SQL = ("data.", "named_row", "current_user_id")

# A literal is "SQL" as soon as it carries one of these markers — enough to
# catch any read, write or access-control query.
MILESTONES_SQL = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", " FROM ", " WHERE ")


def _literals_sql(source):
    """Every string literal of the module that is SQL, through the AST."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if any(milestone in text for milestone in MILESTONES_SQL):
                yield text


def _app_source(spec_ou_path, from_file, base_dir):
    raw = (parse_monl_file(spec_ou_path) if from_file
           else parse_monl_string(spec_ou_path))
    ast_manager = MonlAST(raw, base_dir=base_dir)
    normalized = ast_manager.validate_and_audit()
    with tempfile.TemporaryDirectory() as output:
        MonlSecureGenerator(normalized, output_dir=output).generate_all()
        with open(os.path.join(output, "app.py"), encoding="utf-8") as file:
            return file.read()


# A spec cut to exercise the WHOLE transitive access-control surface (depth 2:
# list, detail, create, Update, Delete), where point 107 lived. The examples
# cover depth 1 (02_boutique); this one guarantees depth 2 is tested by the
# invariant too.
SPEC_DEPTH = """app Inv

entity Commande
    libelle: String

entity Bloc
    note: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Bloc.Read ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc

workflow W for Client
    Create Commande
    Read Commande
    Create Bloc
    Read Bloc
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

EXAMPLES = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.ml")))


def test_no_example_pastes_a_value_into_sql():
    table = EXAMPLES
    names = [os.path.basename(p) for p in EXAMPLES]

    def cas(path):
        source = _app_source(path, from_file=True, base_dir=EXAMPLES_DIR)
        for query in _literals_sql(source):
            for forbidden in FORBIDDEN_IN_SQL:
                assert forbidden not in query, (
                    f"{os.path.basename(path)}: value '{forbidden}' pasted into "
                f"the SQL text (point 107) — {query!r}")

    check_each_case([(valeur,) for valeur in table], cas, ids=names)


def test_depth_2_pastes_no_value_into_sql():
    source = _app_source(SPEC_DEPTH, from_file=False, base_dir=None)
    for query in _literals_sql(source):
        for forbidden in FORBIDDEN_IN_SQL:
            assert forbidden not in query, (
                f"depth 2: value '{forbidden}' pasted into the SQL text "
                f"(point 107) — {query!r}")


def test_the_invariant_really_sees_access_control():
    """Safeguard of the safeguard: an invariant that scans no access-control
    query would always pass, and would no longer say anything. The depth spec
    MUST produce access-control queries (ownership join), and they MUST bind
    their values (`= ?`)."""
    queries = list(_literals_sql(
        _app_source(SPEC_DEPTH, from_file=False, base_dir=None)))
    control = [r for r in queries if "IN (SELECT id FROM" in r or
                ('WHERE id = ' in r and "SELECT" in r)]
    assert control, "no access-control query generated — invariant blind"
    assert any("= ?" in r for r in control), \
        "access control binds no value — point 107 regression"


def test_b4_pastes_no_value_into_sql():
    from tests.test_authentication_b4 import SPEC_B4

    source = _app_source(SPEC_B4, from_file=False, base_dir=None)
    for query in _literals_sql(source):
        for forbidden in (*FORBIDDEN_IN_SQL, "req.", "payload.", "row["):
            assert forbidden not in query, (
                f"B4: value '{forbidden}' pasted into the SQL text — {query!r}")
