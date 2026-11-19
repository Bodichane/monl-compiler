"""Separation contract between the library API and the CLI boundary."""

import pytest

from monl import cli
from monl.errors import CompilationInputError, MonlError
from monl.main import compile_monl
from monl.parser import MonlSyntaxError


def test_compile_monl_raises_a_typed_error_without_exiting(tmp_path):
    with pytest.raises(CompilationInputError) as refusal:
        compile_monl(str(tmp_path / "absente.ml"))

    assert isinstance(refusal.value, MonlError)
    assert "absente.ml" in str(refusal.value)


def test_parser_errors_belong_to_the_monl_family():
    assert issubclass(MonlSyntaxError, MonlError)


def test_cli_turns_a_compilation_error_into_an_exit_code(
    tmp_path, capsys
):
    with pytest.raises(SystemExit) as output:
        cli.main(["compile", str(tmp_path / "absente.ml")])

    assert output.value.code == 1
    assert "absente.ml" in capsys.readouterr().out
