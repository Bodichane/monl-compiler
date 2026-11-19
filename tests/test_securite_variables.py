"""docs/SECURITE.md lists the variables the generated backend really reads.

A documented variable never read will be configured for nothing; a variable
read but missing from the document will never be configured — which is what
happened to `MONL_CORS_ORIGINS`, shipped while the page still announced "no
configurable CORS". Same discipline as for docs/EXPLOITATION.md (point 141):
compare in BOTH directions.

The truth is read in the COMPILED code, not the emitters: several names go
through a constant (`_DB_POOL_MIN_ENV`) or a split line, which a text
pattern on the sources would not see (point 172).
"""

import ast
import re
from pathlib import Path

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string
from tests.test_authentification_b4 import SPEC_B4
from tests.test_fedapay import SPEC_FEDAPAY
from tests.test_messages import SPEC as SPEC_MESSAGES
from tests.test_paiement import SPEC_BOUTIQUE
from tests.test_uploads import SPEC as SPEC_UPLOADS

DOC = Path(__file__).resolve().parent.parent / "docs" / "SECURITE.md"
# One spec per brick that reads its own variables: auth B4 (SMTP, reset,
# refresh tokens), Stripe, FedaPay, messages, file uploads.
SPECS = (SPEC_B4, SPEC_BOUTIQUE, SPEC_FEDAPAY, SPEC_MESSAGES, SPEC_UPLOADS)


def _constantes(arbre):
    return {
        cible.id: noeud.value.value
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Assign)
        and isinstance(noeud.value, ast.Constant)
        and isinstance(noeud.value.value, str)
        for cible in noeud.targets
        if isinstance(cible, ast.Name)
    }


def _argument_lu(noeud):
    if (isinstance(noeud, ast.Call) and noeud.args
            and ast.unparse(noeud.func) in ("os.environ.get", "os.getenv")):
        return noeud.args[0]
    if isinstance(noeud, ast.Subscript) and ast.unparse(noeud.value) == "os.environ":
        return noeud.slice
    return None


def variables_lues(source):
    """Environment names read by a Python module; fails on what it cannot read."""
    arbre = ast.parse(source)
    constantes = _constantes(arbre)
    lues = set()
    for noeud in ast.walk(arbre):
        argument = _argument_lu(noeud)
        if argument is None:
            continue
        if isinstance(argument, ast.Constant):
            lues.add(argument.value)
        elif isinstance(argument, ast.Name) and argument.id in constantes:
            lues.add(constantes[argument.id])
        else:
            raise AssertionError(f"lecture d'environnement illisible : {ast.unparse(noeud)}")
    return lues


def backend_variables(tmp_path):
    lues = set()
    for rang, spec in enumerate(SPECS):
        dossier = tmp_path / str(rang)
        ast_valide = MonlAST(parse_monl_string(spec)).validate_and_audit()
        MonlSecureGenerator(ast_valide, output_dir=str(dossier)).generate_all()
        for module in dossier.glob("*.py"):
            lues |= variables_lues(module.read_text(encoding="utf-8"))
    return lues


def variables_documentees(texte):
    debut = texte.index("## Deployment settings")
    fin = texte.index("\n## ", debut + 1)
    noms = re.findall(r"`((?:MONL|STRIPE)_[A-Z0-9_]+)(?:=[^`]*)?`", texte[debut:fin])
    return set(noms)


def test_security_md_and_backend_read_the_same_variables(tmp_path, capsys):
    lues = backend_variables(tmp_path)
    documentees = variables_documentees(DOC.read_text(encoding="utf-8"))
    # An extractor that finds nothing would make both directions pass while
    # looking at nothing (point 161).
    assert len(lues) >= 15, lues
    assert len(documentees) >= 15, documentees
    assert not lues - documentees, f"lues mais non documentées : {sorted(lues - documentees)}"
    assert not documentees - lues, f"documentées mais jamais lues : {sorted(documentees - lues)}"


def test_the_extractor_follows_a_constant_and_refuses_the_unreadable():
    source = "import os\n_NOM = 'MONL_X'\na = os.environ.get(_NOM)\nb = os.environ['MONL_Y']\n"
    assert variables_lues(source) == {"MONL_X", "MONL_Y"}
    try:
        variables_lues("import os\na = os.environ.get('MONL_' + suffixe)\n")
    except AssertionError as erreur:
        assert "illisible" in str(erreur)
    else:
        raise AssertionError("une lecture dynamique doit faire échouer l'extracteur")


def test_the_document_extractor_reads_the_form_with_a_value():
    texte = "## Deployment settings\n- `MONL_DOCS=off`: x\n- `MONL_A`, `STRIPE_B`\n## Next\n`MONL_HORS`\n"
    assert variables_documentees(texte) == {"MONL_DOCS", "MONL_A", "STRIPE_B"}
