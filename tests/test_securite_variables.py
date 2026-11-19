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


def _constants(tree):
    return {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _argument_lu(node):
    if (isinstance(node, ast.Call) and node.args
            and ast.unparse(node.func) in ("os.environ.get", "os.getenv")):
        return node.args[0]
    if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
        return node.slice
    return None


def variables_lues(source):
    """Environment names read by a Python module; fails on what it cannot read."""
    tree = ast.parse(source)
    constants = _constants(tree)
    lues = set()
    for node in ast.walk(tree):
        argument = _argument_lu(node)
        if argument is None:
            continue
        if isinstance(argument, ast.Constant):
            lues.add(argument.value)
        elif isinstance(argument, ast.Name) and argument.id in constants:
            lues.add(constants[argument.id])
        else:
            raise AssertionError(f"lecture d'environnement illisible : {ast.unparse(node)}")
    return lues


def backend_variables(tmp_path):
    lues = set()
    for rang, spec in enumerate(SPECS):
        folder = tmp_path / str(rang)
        ast_valid = MonlAST(parse_monl_string(spec)).validate_and_audit()
        MonlSecureGenerator(ast_valid, output_dir=str(folder)).generate_all()
        for module in folder.glob("*.py"):
            lues |= variables_lues(module.read_text(encoding="utf-8"))
    return lues


def variables_documented(text):
    debut = text.index("## Deployment settings")
    fin = text.index("\n## ", debut + 1)
    names = re.findall(r"`((?:MONL|STRIPE)_[A-Z0-9_]+)(?:=[^`]*)?`", text[debut:fin])
    return set(names)


def test_security_md_and_backend_read_the_same_variables(tmp_path, capsys):
    lues = backend_variables(tmp_path)
    documented = variables_documented(DOC.read_text(encoding="utf-8"))
    # An extractor that finds nothing would make both directions pass while
    # looking at nothing (point 161).
    assert len(lues) >= 15, lues
    assert len(documented) >= 15, documented
    assert not lues - documented, f"read but not documented: {sorted(lues - documented)}"
    assert not documented - lues, f"documented but never read: {sorted(documented - lues)}"


def test_the_extractor_follows_a_constant_and_refuses_the_unreadable():
    source = "import os\n_NOM = 'MONL_X'\na = os.environ.get(_NOM)\nb = os.environ['MONL_Y']\n"
    assert variables_lues(source) == {"MONL_X", "MONL_Y"}
    try:
        variables_lues("import os\na = os.environ.get('MONL_' + suffixe)\n")
    except AssertionError as error:
        assert "illisible" in str(error)
    else:
        raise AssertionError("a dynamic read must make the extractor fail")


def test_the_document_extractor_reads_the_form_with_a_value():
    text = "## Deployment settings\n- `MONL_DOCS=off`: x\n- `MONL_A`, `STRIPE_B`\n## Next\n`MONL_HORS`\n"
    assert variables_documented(text) == {"MONL_DOCS", "MONL_A", "STRIPE_B"}
