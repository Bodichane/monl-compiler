"""Mutations reproductibles : compiler réellement ou refuser proprement (point 204).

Une spec abîmée doit soit compiler, soit lever une erreur monl NOMMÉE. Toute
autre exception est un défaut du compilateur. Graine fixe : un échec se rejoue.

Campagne hors suite : MONL_FUZZ_CASES=20000 MONL_FUZZ_SEED=7 pytest -q -s ce_fichier.
Première campagne (20 000 cas) : deux plantages, gardés plus bas en régression.
"""
import contextlib
import io
import os
import random
from pathlib import Path

import pytest

from monl.ast_validator import ASTValidationError
from monl.cli import compile_project
from monl.errors import CompilationGenerationError, CompilationInputError
from monl.parser import MonlSyntaxError

ROOT = Path(__file__).resolve().parents[1]
ERRORS = (MonlSyntaxError, ASTValidationError, CompilationInputError,
          CompilationGenerationError)
# `main.py` enveloppe TOUTE exception de génération : un refus voulu du
# générateur (le garde-fou `payable` du point 99, par exemple) y arrive comme
# un défaut de code. La cause les distingue — ces types-là trahissent un bogue.
CAUSES_DE_BOGUE = (KeyError, TypeError, AttributeError, IndexError, NameError,
                   AssertionError, RecursionError, ZeroDivisionError)


def mutations(count):
    rng = random.Random(int(os.getenv('MONL_FUZZ_SEED', '120')))
    paths = sorted(set(ROOT.glob('exemples/*.ml')) |
                   set(ROOT.glob('demo/spec.ml')) |
                   set(ROOT.glob('plugin/**/exemples/*.ml')) |
                   set(ROOT.glob('plugins/**/exemples/*.ml')))
    assert paths
    sources = [(p, p.read_text(encoding='utf-8')) for p in paths]
    # Les originaux exercent aussi la génération et servent à la contre-épreuve.
    yield from sources
    for case in range(count):
        path, source = rng.choice(sources)
        lines = source.splitlines(keepends=True)
        index = rng.randrange(len(lines))
        operation = case % 9
        if operation == 0:
            del lines[index]
        elif operation == 1:
            lines.insert(index, lines[index])
        elif operation == 2:
            other = rng.randrange(len(lines))
            lines[index], lines[other] = lines[other], lines[index]
        elif operation == 3:
            lines[index] = rng.choice(['\t', ' ', '   ', '     ']) + lines[index].lstrip()
        elif operation == 4:
            yield path, source[:rng.randrange(len(source) + 1)]
            continue
        elif operation == 5:
            lines[index] = rng.choice(['\x00', '\x01', '\x1b', 'é', '漢', '\u202e']) + lines[index]
        elif operation == 6:
            lines[index] = rng.choice(['entity', 'workflow', 'rule', 'app', 'seed', 'ownedBy']) + ' ' + lines[index]
        elif operation == 7:
            lines[index] = lines[index].replace('1', rng.choice(['9' * 5000, '1e9999', '-999999999999999999999']))
        else:
            lines[index] = lines[index].replace('"', '', 1) if '"' in lines[index] else lines[index].rstrip() + ' "non fermée\n'
        yield path, ''.join(lines)


def test_fuzzing_pipeline(tmp_path):
    spec = tmp_path / 'spec.ml'
    for index, (origin, source) in enumerate(mutations(int(os.getenv('MONL_FUZZ_CASES', '1500')))):
        spec.write_text(source, encoding='utf-8')
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                compile_project(str(spec), str(tmp_path / 'out'), base_dir=str(origin.parent))
        except ERRORS as exc:
            # Une enveloppe générique ne doit pas cacher une exception interne.
            if isinstance(exc, CompilationGenerationError):
                assert not isinstance(exc.__cause__, CAUSES_DE_BOGUE), (
                    index, origin.name, repr(exc.__cause__), source)
        except Exception as exc:
            pytest.fail(f'cas {index}, {origin.name}: {type(exc).__name__}: {exc}\n{source}')


def test_une_ligne_desindentee_de_travers_est_situee():
    """Plantage 1 : Lark levait `DedentError`, brut et sans ligne."""
    from monl.parser import parse_monl_string

    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string("app X\n\nentity A\n    nom: String\n  age: Integer\n")
    assert erreur.value.line == 5
    assert "indentation" in str(erreur.value)


def test_un_entier_de_milliers_de_chiffres_est_refuse_proprement():
    """Plantage 2 : Python refuse de convertir plus de 4 300 chiffres, et
    l'erreur remontait dans un `VisitError` de Lark."""
    from monl.parser import parse_monl_string

    spec = ("app X\n\nentity A\n    n: Integer\n\nseed A\n    n: "
            + "9" * 5000 + "\n")
    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string(spec)
    assert erreur.value.line == 7
    assert "trop long" in str(erreur.value)


def test_un_exposant_est_un_decimal_et_l_infini_est_refuse():
    """Plantage 3 : la grammaire accepte `1e3`, mais le parseur faisait
    `int('1e3')` ; et `1e999900` vaut l'infini, qu'aucune base ne stocke."""
    from monl.parser import parse_monl_string

    spec = "app X\n\nentity A\n    n: Float\n\nseed A\n    n: {}\n"
    assert parse_monl_string(spec.format("1e3"))["seeds"][0]["rows"] == [{"n": 1000.0}]
    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string(spec.format("1e999900"))
    assert erreur.value.line == 7
    assert "hors limites" in str(erreur.value)
