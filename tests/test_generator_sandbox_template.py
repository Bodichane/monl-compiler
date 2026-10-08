"""Identité des octets, exécution et garde structurelle du premier gabarit."""

import ast
import inspect

from monl.generator import sandbox
from tests.test_bloc_custom_absent import AVEC_CUSTOM, _compiler


def test_sandbox_emission_sans_f_string_ni_addition():
    tree = ast.parse(inspect.getsource(sandbox))
    assert not any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))
    assert not any(isinstance(node, (ast.BinOp, ast.AugAssign))
                   and isinstance(node.op, ast.Add) for node in ast.walk(tree))


def test_sandbox_custom_octets_et_execution(tmp_path):
    source = AVEC_CUSTOM.replace('Publie une note', 'Publie ${name} {note} $5 \\n')
    folder = _compiler(source, tmp_path / 'custom')
    generated = (folder / 'sandbox_ai.py').read_bytes()
    expected = b"# BLOCS 'custom' \xe2\x80\x94 logique m\xc3\xa9tier \xc3\xa0 compl\xc3\xa9ter \xc3\xa0 la main (d\xc3\xa9terministe)\n\ndef Publier(context: dict) -> dict:\n    \"\"\"\n    Objectif : Publie ${name} {note} $5 \\n\n    \"\"\"\n    # TODO:\n    return {'message': 'Coquille vide d\xc3\xa9terministe pour Publier'}\n"
    assert generated == expected
    namespace = {}
    exec(compile(generated, 'sandbox_ai.py', 'exec'), namespace)
    assert namespace['Publier']({}) == {
        'message': 'Coquille vide déterministe pour Publier',
    }
