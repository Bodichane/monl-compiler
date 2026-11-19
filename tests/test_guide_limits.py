"""The table "What this platform does not do" is CHECKED against the code.

It was hand-written, and one of its four lines had gone stale silently: "No
upload — a spec declaring an `assets` block or an `Image` field is refused".
Measured against the running platform, a spec carrying an `Upload` field
compiles with 201, and the produced backend receives real files since brick
32. It is point 178's defect through another door: a statement nothing ties
to what the code does.

This file does not reread the table's text to check it is well written — it
MEASURES what the compiler accepts and refuses, then requires that the table
not say the opposite.
"""

import contextlib
import io
import re
from pathlib import Path

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.parser import parse_monl_string
from monl_platform.guide import guide_html
from monl_platform.guide_data import LIMITES
from tests.support.cases import check_each_case

RACINE = Path(__file__).resolve().parent.parent

BASE = """app Vitrine

entity Realisation
    titre: String
{champs}
actor Admin selfRegister
{relation}
rule Realisation.titre required
{regles}
workflow Gerer for Admin
    Create Realisation
    Read Realisation
    Update Realisation
{seed}
landing
    brief: "Une vitrine."
    link "Contact": "mailto:a@b.c"
"""


def _spec(fields="", rules="rule Realisation.Read public", relation="", seed=""):
    return BASE.format(champs=fields, regles=rules, relation=relation, seed=seed)


def _compile(spec, folder):
    """The PLATFORM path: `base_dir` is the project folder, so the existence of
    declared files is really checked (point 83)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return MonlAST(parse_monl_string(spec),
                       base_dir=str(folder)).validate_and_audit()


# --- what the compiler REALLY does -------------------------------------------

def test_an_upload_field_compiles(tmp_path):
    """The file sent at RUNTIME: that is what the table denied."""
    spec = _spec(
        fields="    piece: Upload\n",
        relation="\nrelation Admin hasMany Realisation\n",
        rules=('rule Realisation.piece upload max 5242880 types "image/png"\n'
                "rule Realisation.Read ownedBy Admin\n"
                "rule Realisation.Update ownedBy Admin"))
    assert _compile(spec, tmp_path)["meta"]["appName"] == "Vitrine"


def test_an_image_field_without_value_compiles(tmp_path):
    """An `Image` field declares a TYPE, not a path — there is nothing to check
    as long as no value designates a file."""
    assert _compile(_spec(fields="    photo: Image\n"), tmp_path)


def test_a_declared_but_missing_asset_is_refused(tmp_path):
    """The REAL limit: the file provided at COMPILE time."""
    spec = 'app Vitrine\n\nassets\n    dir: "assets"\n    logo: "absent.svg"\n' \
           + _spec()[len("app Vitrine\n"):]
    with pytest.raises(ASTValidationError, match=re.escape("absent.svg")):
        _compile(spec, tmp_path)


def test_an_image_value_pointing_to_a_missing_file_is_refused(tmp_path):
    spec = _spec(fields="    photo: Image\n",
                 seed='\nseed Realisation\n    titre: "Halo"\n'
                      '    photo: "absente.jpg"\n')
    with pytest.raises(ASTValidationError, match=re.escape("absente.jpg")):
        _compile(spec, tmp_path)


# --- the table must not say the opposite -------------------------------------

def test_no_limit_denies_upload_at_runtime(tmp_path):
    """The exact defect that had gone stale.

    The link is DERIVED: the `Upload` spec is compiled first; if it passes, no
    line of the table may say that no file can be sent. Copying the expected
    sentence would only measure my own copy."""
    spec = _spec(
        fields="    piece: Upload\n",
        relation="\nrelation Admin hasMany Realisation\n",
        rules=('rule Realisation.piece upload max 5242880 types "image/png"\n'
                "rule Realisation.Read ownedBy Admin\n"
                "rule Realisation.Update ownedBy Admin"))
    _compile(spec, tmp_path)                      # fails here if it no longer compiles

    for title, text in LIMITES:
        whole = f"{title} {text}".lower()
        assert "no upload" not in whole, (
            f"the table denies upload while an `Upload` spec "
            f"compiles: \"{title}\"")


def test_the_file_limit_names_both_moments():
    """A limit that does not say WHEN the file arrives suggests the platform
    accepts none — that is the reading that went stale."""
    line = next((f"{t} {x}" for t, x in LIMITES
                  if "compile" in t.lower()), None)
    assert line, f"no line on the compilation files: {LIMITES}"
    assert "Upload" in line
    assert "assets" in line


# --- what the reader is told to install --------------------------------------

def _distribution_name():
    """The name READ from `pyproject.toml`, never copied.

    The import is INSIDE the function and carries its fallback: `tomllib` only
    arrives in 3.11, the declared minimum is 3.10, and a top-level import would
    make COLLECTION of the whole file fail on that version — the architecture
    witness forbidding it bit while writing this bench."""
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (declared in the `dev` extra)
    with open(RACINE / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["name"]


def _names_installed_from_an_index(text):
    """The names `pip install` / `pipx install` commands will LOOK UP on an index,
    as opposed to a local path or a requirements file.

    A path carries a slash, starts with a dot or a tilde; a flag starts with a
    dash; the argument following `-r`, `-c` or `--requirement` is a FILE. The
    extra (`[ai]`) and a version constraint (`==0.9.0b9`) are removed: the NAME
    decides what is installed."""
    names = []
    for command in re.findall(r"pipx? install ([^<\n`]*)", text):
        next_is_a_file = False
        for brut in command.split():
            argument = brut.strip("\"'")
            if next_is_a_file:
                next_is_a_file = False
                continue
            if argument in {"-r", "-c", "--requirement", "--constraint"}:
                next_is_a_file = True
                continue
            if (not argument or argument.startswith(("-", ".", "/", "~"))
                    or "/" in argument):
                continue
            names.append(re.split(r"[\[=<>!~;]", argument)[0])
    return names


def test_the_extractor_tells_a_name_from_a_path():
    """Without this witness, an extractor returning nothing would make the rule
    below green while looking at nothing (point 161)."""
    assert _names_installed_from_an_index("pip install monl") == ["monl"]
    assert _names_installed_from_an_index(
        "pip install 'monl-compiler[ai]'") == ["monl-compiler"]
    assert _names_installed_from_an_index(
        "pipx install monl-compiler==0.9.0b9") == ["monl-compiler"]
    assert _names_installed_from_an_index(
        "pip install ./monl-compiler -r requirements.txt -e .") == []


def test_an_installation_from_an_index_names_the_real_distribution():
    """`monl-compiler` has been published on PyPI since 0.9.0-beta.9: the old
    witness, which forbade any installation from an index as long as nothing was
    published, announced it itself — "on publication day, it will be the one
    reminding us to revisit these lines".

    The danger that remains is the NAME. Plain `monl` is FREE on the index
    (point 167bis): documentation writing `pip install monl` would install the
    package of whoever grabbed it. Every installation from an index must
    therefore name the distribution READ from `pyproject.toml`.

    Measured on 24/09/2026: without `--pre`, `pip install monl-compiler` does
    install the beta — pip accepts a pre-release when the index has nothing else.
    The flag is therefore not required here; requiring it would teach a useless
    step."""
    table = ["README.md", "QUICKSTART.md"]

    def cas(path):
        name = _distribution_name()
        foreign = [n for n in _names_installed_from_an_index(
            (RACINE / path).read_text(encoding="utf-8")) if n != name]
        assert not foreign, (
            f"{path} installs from an index something other than {name}: "
        f"{foreign}")

    check_each_case([(valeur,) for valeur in table], cas)


def test_the_guide_only_installs_the_real_distribution():
    """Same rule on the SERVED page, not on the module constant: point 163 saw a
    page break between the two."""
    name = _distribution_name()
    foreign = [n for n in _names_installed_from_an_index(guide_html())
                 if n != name]
    assert not foreign, (
        f"the served guide installs something other than {name}: {foreign}")
