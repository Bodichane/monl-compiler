"""A project without a `custom` block no longer gets `sandbox_ai.py`.

THE DEFECT, MEASURED ON A REALLY DOWNLOADED ARCHIVE. The file was **one
line** — a comment — `app.py` imported it at the top and never called
anything from it, and deleting it made startup fail with
`ModuleNotFoundError`. A file that does nothing and cannot be removed, in an
archive the user opens and must understand.

It is point 85 turned around: there a declared rule produced nothing, here
an empty file carried startup by accident. The import was hard-coded in
`runtime_socle.py`, without ever checking whether the spec had a block.

Both directions are tested — otherwise the fix could simply never emit the
module again, and the `custom` brick would die silently.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

SANS_CUSTOM = """app SansCustom

entity Note
    titre: String

actor Auteur selfRegister

relation Auteur hasMany Note

rule Note.Read ownedBy Auteur

workflow Ecrire for Auteur
    Create Note
    Read Note
"""

AVEC_CUSTOM = SANS_CUSTOM + textwrap.dedent("""
    custom Publier
        description: "Publie une note"
        input: titre: String
        output: resultat: String
    """)


def _compiler(source, dossier):
    ast = MonlAST(parse_monl_string(source)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(dossier)).generate_all()
    return dossier


def test_without_custom_block_the_module_is_neither_written_nor_imported(tmp_path):
    """Neither the file nor the import: nothing that serves no purpose."""
    dossier = _compiler(SANS_CUSTOM, tmp_path / "sans")
    app = (dossier / "app.py").read_text(encoding="utf-8")

    assert not (dossier / "sandbox_ai.py").exists(), (
        "an empty module is still shipped while the spec has no 'custom' block")
    assert "import sandbox_ai" not in app, (
        "app.py imports a module that does not exist — the server would not start")


def test_without_custom_block_the_backend_really_starts(tmp_path):
    """The proof that counts: with the module absent, Python loads the application.

    A string check cannot tell a removed import from a moved one. So `app.py`
    is really imported, in a separate interpreter so as not to pollute the
    suite's.
    """
    dossier = _compiler(SANS_CUSTOM, tmp_path / "demarre")
    resultat = subprocess.run(
        [sys.executable, "-c", "import app; assert app.app is not None; print('ok')"],
        cwd=str(dossier), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(dossier)},
    )
    assert resultat.returncode == 0, (
        f"the application does not load:\n{resultat.stderr[-1500:]}")
    assert "ok" in resultat.stdout


def test_with_a_custom_block_the_module_comes_back(tmp_path):
    """THE COUNTER-PROOF. Without it, never emitting the module again would make
    this test file green while killing the `custom` brick."""
    dossier = _compiler(AVEC_CUSTOM, tmp_path / "avec")
    app = (dossier / "app.py").read_text(encoding="utf-8")
    sandbox = (dossier / "sandbox_ai.py").read_text(encoding="utf-8")

    assert "import sandbox_ai" in app, "the 'custom' brick lost its module"
    assert "def publier" in sandbox.lower(), (
        f"the custom function's shell is not written:\n{sandbox}")


def test_the_two_compilations_do_not_give_the_same_app(tmp_path):
    """The point 85 witness: with and without must DIFFER.

    If both outputs were identical, the condition just written would produce
    nothing — exactly what the original defect is blamed for.
    """
    sans = _compiler(SANS_CUSTOM, tmp_path / "a") / "app.py"
    avec = _compiler(AVEC_CUSTOM, tmp_path / "b") / "app.py"
    assert sans.read_text(encoding="utf-8") != avec.read_text(encoding="utf-8")
