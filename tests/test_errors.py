"""Contrat de séparation entre API de bibliothèque et frontière CLI."""

import pytest

from monl import cli
from monl.errors import CompilationInputError, MonlError
from monl.main import compile_monl
from monl.parser import MonlSyntaxError


def test_compile_monl_leve_une_erreur_typée_sans_quitter_le_processus(tmp_path):
    with pytest.raises(CompilationInputError) as refus:
        compile_monl(str(tmp_path / "absente.ml"))

    assert isinstance(refus.value, MonlError)
    assert "absente.ml" in str(refus.value)


def test_les_erreurs_de_parseur_appartiennent_a_la_famille_monl():
    assert issubclass(MonlSyntaxError, MonlError)


def test_la_cli_convertit_une_erreur_de_compilation_en_code_de_sortie(
    tmp_path, capsys
):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["compile", str(tmp_path / "absente.ml")])

    assert sortie.value.code == 1
    assert "absente.ml" in capsys.readouterr().out
