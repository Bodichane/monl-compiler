"""Point 208: the platform compiles specs, never user Python."""

import ast
from pathlib import Path

import pytest

from monl_platform.service import CompilationService

RACINE = Path(__file__).resolve().parents[1]


def test_custom_description_stays_exactly_a_shell(tmp_path):
    descriptions = ["x'); import os #", r'avant \"\"\" après', '${name}']
    blocs = '\n'.join(
        f'custom Bloc{i}\n    description: "{description}"\n'
        '    input: titre: String\n    output: resultat: String\n'
        for i, description in enumerate(descriptions)
    )
    spec = 'app GardeCustom\n\nentity Note\n    titre: String\n\n' + blocs
    service = CompilationService(tmp_path)
    resultat = service.compile(spec)
    source = (tmp_path / resultat['id'] / 'sandbox_ai.py').read_text(encoding='utf-8')
    attendu = "# 'custom' BLOCKS — business logic to complete by hand (deterministic)\n\n"
    for i, description in enumerate(descriptions):
        description = description.replace('\\', '\\\\')
        attendu += (
            f'def Bloc{i}(context: dict) -> dict:\n    """\n'
            f'    Purpose: {description}\n    """\n    # TODO:\n'
            f"    return {{'message': 'Deterministic empty shell for Bloc{i}'}}\n"
            + ('\n' if i < len(descriptions) - 1 else '')
        )
    assert source == attendu
    arbre = ast.parse(source)
    assert len(arbre.body) == len(descriptions)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(arbre))
    for i, fonction in enumerate(arbre.body):
        assert isinstance(fonction, ast.FunctionDef)
        assert fonction.name == f'Bloc{i}'
        assert len(fonction.body) == 2
        assert isinstance(fonction.body[0], ast.Expr)
        assert isinstance(fonction.body[0].value, ast.Constant)
        assert isinstance(fonction.body[0].value.value, str)
        assert isinstance(fonction.body[1], ast.Return)
        assert ast.literal_eval(fonction.body[1].value) == {
            'message': f'Deterministic empty shell for Bloc{i}'
        }


def _assert_writes_without_custom(fichiers):
    assert fichiers, 'no platform file inspected'
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text(encoding='utf-8'))
        # Conservative resolution of path variables: every assignment is
        # followed, even in another branch. This guard does not prove a general
        # flow analysis nor dynamically built paths.
        valeurs = {}
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    if isinstance(cible, ast.Name):
                        valeurs.setdefault(cible.id, []).append(noeud.value)

        def vise_custom(noeud, vus=frozenset(), valeurs=valeurs):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                return 'sandbox_ai' in noeud.value
            if isinstance(noeud, ast.Name) and noeud.id not in vus:
                return any(vise_custom(v, vus | {noeud.id})
                           for v in valeurs.get(noeud.id, []))
            return any(vise_custom(enfant, vus) for enfant in ast.iter_child_nodes(noeud))

        for appel in ast.walk(arbre):
            if not isinstance(appel, ast.Call):
                continue
            fonction = appel.func
            nom = fonction.attr if isinstance(fonction, ast.Attribute) else (
                fonction.id if isinstance(fonction, ast.Name) else '')
            if nom in {'write_text', 'write_bytes', 'write', 'writelines', 'open',
                       'copy', 'copyfile', 'copy2', 'copytree', 'move', 'rename', 'replace'}:
                cibles = list(appel.args) + [k.value for k in appel.keywords]
                if isinstance(fonction, ast.Attribute):
                    cibles.append(fonction.value)
                assert not any(vise_custom(c) for c in cibles), (
                    f'{fichier}:{appel.lineno}: write targeting sandbox_ai forbidden'
                )


def test_platform_does_not_write_sandbox_ai():
    _assert_writes_without_custom(sorted((RACINE / 'src/monl_platform').rglob('*.py')))


def test_guard_refuses_an_empty_scope():
    with pytest.raises(AssertionError, match='no file'):
        _assert_writes_without_custom([])
