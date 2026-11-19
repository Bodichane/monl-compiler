"""Reproducible mutations: really compile or refuse cleanly (point 204).

A damaged spec must either compile or raise a NAMED monl error. Any other
exception is a compiler defect. Fixed seed: a failure replays.

Off-suite campaign: MONL_FUZZ_CASES=20000 MONL_FUZZ_SEED=7 pytest -q -s this_file.
First campaign (20,000 cases): two crashes, kept below as regressions.
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
# `main.py` wraps EVERY generation exception: a deliberate refusal of the
# generator (the point 99 `payable` safeguard, for instance) arrives there like
# a code defect. The cause tells them apart — these types betray a bug.
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
    # The originals also exercise generation and serve the counter-proof.
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
            # A generic wrapper must not hide an internal exception.
            if isinstance(exc, CompilationGenerationError):
                assert not isinstance(exc.__cause__, CAUSES_DE_BOGUE), (
                    index, origin.name, repr(exc.__cause__), source)
        except Exception as exc:
            pytest.fail(f'cas {index}, {origin.name}: {type(exc).__name__}: {exc}\n{source}')


def test_a_wrongly_dedented_line_is_located():
    """Crash 1: Lark raised `DedentError`, raw and without a line."""
    from monl.parser import parse_monl_string

    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string("app X\n\nentity A\n    nom: String\n  age: Integer\n")
    assert erreur.value.line == 5
    assert "indentation" in str(erreur.value)


def test_an_integer_of_thousands_of_digits_is_refused_cleanly():
    """Crash 2: Python refuses to convert more than 4,300 digits, and the error
    came up inside a Lark `VisitError`."""
    from monl.parser import parse_monl_string

    spec = ("app X\n\nentity A\n    n: Integer\n\nseed A\n    n: "
            + "9" * 5000 + "\n")
    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string(spec)
    assert erreur.value.line == 7
    assert "too long" in str(erreur.value)


def test_an_exponent_is_a_decimal_and_infinity_is_refused():
    """Crash 3: the grammar accepts `1e3`, but the parser did `int('1e3')`; and
    `1e999900` is infinity, which no database stores."""
    from monl.parser import parse_monl_string

    spec = "app X\n\nentity A\n    n: Float\n\nseed A\n    n: {}\n"
    assert parse_monl_string(spec.format("1e3"))["seeds"][0]["rows"] == [{"n": 1000.0}]
    with pytest.raises(MonlSyntaxError) as erreur:
        parse_monl_string(spec.format("1e999900"))
    assert erreur.value.line == 7
    assert "out of range" in str(erreur.value)
