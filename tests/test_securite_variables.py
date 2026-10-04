"""docs/SECURITE.md liste les variables que le backend généré lit vraiment.

Une variable documentée mais jamais lue sera configurée pour rien ; une
variable lue mais absente du document ne sera jamais configurée — c'est ce
qui était arrivé à `MONL_CORS_ORIGINS`, livré alors que la page annonçait
encore « pas de CORS configurable ». Même discipline que pour
docs/EXPLOITATION.md (point 141) : comparer dans les DEUX sens.

La vérité est lue dans le code COMPILÉ, pas dans les émetteurs : plusieurs
noms passent par une constante (`_DB_POOL_MIN_ENV`) ou une ligne coupée,
qu'un motif textuel sur les sources ne verrait pas (point 172).
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
# Une spec par brique qui lit ses propres variables : auth B4 (SMTP,
# réinitialisation, jetons de rafraîchissement), Stripe, FedaPay, messages,
# dépôts de fichiers.
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
    """Noms d'environnement lus par un module Python ; échoue sur l'illisible."""
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


def variables_du_backend(tmp_path):
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


def test_securite_md_et_backend_lisent_les_memes_variables(tmp_path, capsys):
    lues = variables_du_backend(tmp_path)
    documentees = variables_documentees(DOC.read_text(encoding="utf-8"))
    # Un extracteur qui ne trouve rien ferait passer les deux sens sans rien
    # regarder (point 161).
    assert len(lues) >= 15, lues
    assert len(documentees) >= 15, documentees
    assert not lues - documentees, f"lues mais non documentées : {sorted(lues - documentees)}"
    assert not documentees - lues, f"documentées mais jamais lues : {sorted(documentees - lues)}"


def test_l_extracteur_suit_une_constante_et_refuse_l_illisible():
    source = "import os\n_NOM = 'MONL_X'\na = os.environ.get(_NOM)\nb = os.environ['MONL_Y']\n"
    assert variables_lues(source) == {"MONL_X", "MONL_Y"}
    try:
        variables_lues("import os\na = os.environ.get('MONL_' + suffixe)\n")
    except AssertionError as erreur:
        assert "illisible" in str(erreur)
    else:
        raise AssertionError("une lecture dynamique doit faire échouer l'extracteur")


def test_l_extracteur_du_document_lit_la_forme_avec_valeur():
    texte = "## Deployment settings\n- `MONL_DOCS=off`: x\n- `MONL_A`, `STRIPE_B`\n## Next\n`MONL_HORS`\n"
    assert variables_documentees(texte) == {"MONL_DOCS", "MONL_A", "STRIPE_B"}
