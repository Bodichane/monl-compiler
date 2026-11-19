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
from tests.support.cas import check_each_case

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")

# Python expressions (client or runtime value) that must ALWAYS be bound as a
# parameter, hence never appear in a query's text.
INTERDITS_EN_SQL = ("data.", "named_row", "current_user_id")

# A literal is "SQL" as soon as it carries one of these markers — enough to
# catch any read, write or access-control query.
JALONS_SQL = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", " FROM ", " WHERE ")


def _litteraux_sql(source):
    """Every string literal of the module that is SQL, through the AST."""
    arbre = ast.parse(source)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            texte = noeud.value
            if any(jalon in texte for jalon in JALONS_SQL):
                yield texte


def _app_source(spec_ou_chemin, depuis_fichier, base_dir):
    raw = (parse_monl_file(spec_ou_chemin) if depuis_fichier
           else parse_monl_string(spec_ou_chemin))
    ast_manager = MonlAST(raw, base_dir=base_dir)
    normalized = ast_manager.validate_and_audit()
    with tempfile.TemporaryDirectory() as sortie:
        MonlSecureGenerator(normalized, output_dir=sortie).generate_all()
        with open(os.path.join(sortie, "app.py"), encoding="utf-8") as fichier:
            return fichier.read()


# A spec cut to exercise the WHOLE transitive access-control surface (depth 2:
# list, detail, create, Update, Delete), where point 107 lived. The examples
# cover depth 1 (02_boutique); this one guarantees depth 2 is tested by the
# invariant too.
SPEC_PROFONDEUR = """app Inv

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

EXEMPLES = sorted(glob.glob(os.path.join(EXEMPLES_DIR, "*.ml")))


def test_no_example_pastes_a_value_into_sql():
    table = EXEMPLES
    noms = [os.path.basename(p) for p in EXEMPLES]

    def cas(chemin):
        source = _app_source(chemin, depuis_fichier=True, base_dir=EXEMPLES_DIR)
        for requete in _litteraux_sql(source):
            for interdit in INTERDITS_EN_SQL:
                assert interdit not in requete, (
                    f"{os.path.basename(chemin)}: value '{interdit}' pasted into "
                f"the SQL text (point 107) — {requete!r}")

    check_each_case([(valeur,) for valeur in table], cas, ids=noms)


def test_depth_2_pastes_no_value_into_sql():
    source = _app_source(SPEC_PROFONDEUR, depuis_fichier=False, base_dir=None)
    for requete in _litteraux_sql(source):
        for interdit in INTERDITS_EN_SQL:
            assert interdit not in requete, (
                f"depth 2: value '{interdit}' pasted into the SQL text "
                f"(point 107) — {requete!r}")


def test_the_invariant_really_sees_access_control():
    """Safeguard of the safeguard: an invariant that scans no access-control
    query would always pass, and would no longer say anything. The depth spec
    MUST produce access-control queries (ownership join), and they MUST bind
    their values (`= ?`)."""
    requetes = list(_litteraux_sql(
        _app_source(SPEC_PROFONDEUR, depuis_fichier=False, base_dir=None)))
    controle = [r for r in requetes if "IN (SELECT id FROM" in r or
                ('WHERE id = ' in r and "SELECT" in r)]
    assert controle, "no access-control query generated — invariant blind"
    assert any("= ?" in r for r in controle), \
        "access control binds no value — point 107 regression"


def test_b4_pastes_no_value_into_sql():
    from tests.test_authentification_b4 import SPEC_B4

    source = _app_source(SPEC_B4, depuis_fichier=False, base_dir=None)
    for requete in _litteraux_sql(source):
        for interdit in (*INTERDITS_EN_SQL, "req.", "payload.", "row["):
            assert interdit not in requete, (
                f"B4: value '{interdit}' pasted into the SQL text — {requete!r}")
