"""Byte identity, execution and structural guard of the first template."""

import ast
import importlib.util
import inspect

import pytest

from monl.generator import (
    admin_cli,
    calculations,
    payment,
    prerequisites,
    routes_access,
    routes_uploads,
    runtime_auth_functions,
    runtime_base,
    runtime_extras,
    runtime_login,
    runtime_migrations,
    runtime_mounting,
    runtime_pool,
    runtime_preparation,
    runtime_tokens,
    sandbox,
    schemas,
)
from tests.support.cases import check_each_case
from tests.test_missing_custom_block import WITH_CUSTOM, _compiler

MIGRATED_MODULES = (
    sandbox, runtime_extras, runtime_preparation, runtime_migrations,
    admin_cli, runtime_auth_functions, runtime_mounting, runtime_base,
    routes_uploads, runtime_pool, payment, prerequisites, calculations, schemas,
    routes_access, runtime_tokens, runtime_login,
)

DATABASE_MONTAGE_MODULES = (runtime_mounting,)


def test_mount_modules_list_not_empty():
    assert DATABASE_MONTAGE_MODULES


def test_mounting_without_legacy_splitting():
    table = DATABASE_MONTAGE_MODULES

    def cas(module):
        tree = ast.parse(inspect.getsource(module))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "index"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "api_lines"
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "__MONL_DB_END__" in node.value
            for node in ast.walk(tree)
        )

    check_each_case([(valeur,) for valeur in table], cas)


def test_migrated_modules_list_not_empty():
    assert MIGRATED_MODULES


def test_sandbox_emission_without_f_string_or_concatenation():
    table = MIGRATED_MODULES

    def cas(module):
        tree = ast.parse(inspect.getsource(module))
        assert not any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))
        assert not any(isinstance(node, (ast.BinOp, ast.AugAssign))
                       and isinstance(node.op, ast.Add) for node in ast.walk(tree))

    check_each_case([(valeur,) for valeur in table], cas)


def test_custom_sandbox_bytes_and_execution(tmp_path):
    source = WITH_CUSTOM.replace('Publie une note', 'Publie ${name} {note} $5 \\n')
    folder = _compiler(source, tmp_path / 'custom')
    generated = (folder / 'sandbox_ai.py').read_bytes()
    expected = b"# 'custom' BLOCKS \xe2\x80\x94 business logic to complete by hand (deterministic)\n\ndef Publier(context: dict) -> dict:\n    \"\"\"\n    Purpose: Publie ${name} {note} $5 \\\\n\n    \"\"\"\n    # TODO:\n    return {'message': 'Deterministic empty shell for Publier'}\n"
    assert generated == expected
    namespace = {}
    exec(compile(generated, 'sandbox_ai.py', 'exec'), namespace)
    assert namespace['Publier']({}) == {
        'message': 'Deterministic empty shell for Publier',
    }


def test_schema_server_fields_do_not_mask_substrings(tmp_path):
    source = WITH_CUSTOM.replace(
        "    titre: String", "    titre: String\n    a: String\n    created_at: DateTime"
    ) + "\nrule Note.created_at timestamp\n"
    folder = _compiler(source, tmp_path / "schema")
    tree = ast.parse((folder / "app.py").read_text(encoding="utf-8"))
    schema = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "NoteSchema")
    fields = {node.target.id for node in schema.body
              if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    assert "a" in fields
    assert "created_at" not in fields


@pytest.mark.parametrize("description", [
    r"Etude \N fin",
    r"Etude \u12",
    r"Etude \x",
    r'Etude \"\"\" x',
    "Etude " + "\\" * 2,
])
def test_sandbox_description_backslash_literal(tmp_path, description):
    source = WITH_CUSTOM.replace("Publie une note", description)
    folder = _compiler(source, tmp_path / "custom")
    path = folder / "sandbox_ai.py"
    ast.parse(path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("sandbox_description", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Publier({}) == {
        "message": "Deterministic empty shell for Publier",
    }
    # Python 3.13+ dedents __doc__: compare the line, not the indentation.
    assert module.Publier.__doc__.strip() == f"Purpose: {description}"
