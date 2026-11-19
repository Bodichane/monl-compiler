"""Point 208: the platform compiles specs, never user Python."""

import ast
from pathlib import Path

import pytest

from monl_platform.service import CompilationService

RACINE = Path(__file__).resolve().parents[1]


def test_custom_description_stays_exactly_a_shell(tmp_path):
    descriptions = ["x'); import os #", r'avant \"\"\" après', '${name}']
    blocks = '\n'.join(
        f'custom Bloc{i}\n    description: "{description}"\n'
        '    input: titre: String\n    output: resultat: String\n'
        for i, description in enumerate(descriptions)
    )
    spec = 'app GardeCustom\n\nentity Note\n    titre: String\n\n' + blocks
    service = CompilationService(tmp_path)
    result = service.compile(spec)
    source = (tmp_path / result['id'] / 'sandbox_ai.py').read_text(encoding='utf-8')
    expected = "# 'custom' BLOCKS — business logic to complete by hand (deterministic)\n\n"
    for i, description in enumerate(descriptions):
        description = description.replace('\\', '\\\\')
        expected += (
            f'def Bloc{i}(context: dict) -> dict:\n    """\n'
            f'    Purpose: {description}\n    """\n    # TODO:\n'
            f"    return {{'message': 'Deterministic empty shell for Bloc{i}'}}\n"
            + ('\n' if i < len(descriptions) - 1 else '')
        )
    assert source == expected
    tree = ast.parse(source)
    assert len(tree.body) == len(descriptions)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
    for i, function in enumerate(tree.body):
        assert isinstance(function, ast.FunctionDef)
        assert function.name == f'Bloc{i}'
        assert len(function.body) == 2
        assert isinstance(function.body[0], ast.Expr)
        assert isinstance(function.body[0].value, ast.Constant)
        assert isinstance(function.body[0].value.value, str)
        assert isinstance(function.body[1], ast.Return)
        assert ast.literal_eval(function.body[1].value) == {
            'message': f'Deterministic empty shell for Bloc{i}'
        }


def _assert_writes_without_custom(files):
    assert files, 'no platform file inspected'
    for file in files:
        tree = ast.parse(file.read_text(encoding='utf-8'))
        # Conservative resolution of path variables: every assignment is
        # followed, even in another branch. This guard does not prove a general
        # flow analysis nor dynamically built paths.
        values = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values.setdefault(target.id, []).append(node.value)

        def vise_custom(node, seen=frozenset(), values=values):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return 'sandbox_ai' in node.value
            if isinstance(node, ast.Name) and node.id not in seen:
                return any(vise_custom(v, seen | {node.id})
                           for v in values.get(node.id, []))
            return any(vise_custom(child, seen) for child in ast.iter_child_nodes(node))

        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            function = call.func
            name = function.attr if isinstance(function, ast.Attribute) else (
                function.id if isinstance(function, ast.Name) else '')
            if name in {'write_text', 'write_bytes', 'write', 'writelines', 'open',
                       'copy', 'copyfile', 'copy2', 'copytree', 'move', 'rename', 'replace'}:
                targets = list(call.args) + [k.value for k in call.keywords]
                if isinstance(function, ast.Attribute):
                    targets.append(function.value)
                assert not any(vise_custom(c) for c in targets), (
                    f'{file}:{call.lineno}: write targeting sandbox_ai forbidden'
                )


def test_platform_does_not_write_sandbox_ai():
    _assert_writes_without_custom(sorted((RACINE / 'src/monl_platform').rglob('*.py')))


def test_guard_refuses_an_empty_scope():
    with pytest.raises(AssertionError, match='no platform file'):
        _assert_writes_without_custom([])
