"""Un projet sans bloc `custom` ne reçoit plus `sandbox_ai.py`.

LE DÉFAUT, MESURÉ SUR UNE ARCHIVE RÉELLEMENT TÉLÉCHARGÉE. Le fichier faisait
**une ligne** — un commentaire — `app.py` l'importait en tête et n'en appelait
jamais rien, et le supprimer faisait échouer le démarrage sur
`ModuleNotFoundError`. Soit un fichier qui ne fait rien et qu'on ne peut pas
enlever, dans une archive que l'usager ouvre et doit comprendre.

C'est le point 85 retourné : là-bas une règle déclarée ne produisait rien, ici
un fichier vide portait le démarrage par accident. L'import était écrit en dur
dans `runtime_socle.py`, sans jamais regarder si la spec avait un bloc.

Les deux sens sont éprouvés — sans quoi le correctif pourrait simplement ne
plus jamais émettre le module, et la brique `custom` mourrait en silence.
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


def test_sans_bloc_custom_le_module_nest_ni_ecrit_ni_importe(tmp_path):
    """Ni le fichier, ni l'import : rien qui ne serve à rien."""
    dossier = _compiler(SANS_CUSTOM, tmp_path / "sans")
    app = (dossier / "app.py").read_text(encoding="utf-8")

    assert not (dossier / "sandbox_ai.py").exists(), (
        "un module vide reste livré alors que la spec n'a aucun bloc 'custom'")
    assert "import sandbox_ai" not in app, (
        "app.py importe un module qui n'existe pas — le serveur ne démarrerait pas")


def test_sans_bloc_custom_le_backend_demarre_vraiment(tmp_path):
    """La preuve qui compte : le module absent, Python charge l'application.

    Une vérification de chaîne ne distingue pas un import retiré d'un import
    déplacé. On importe donc réellement `app.py`, dans un interpréteur séparé
    pour ne pas polluer celui de la suite.
    """
    dossier = _compiler(SANS_CUSTOM, tmp_path / "demarre")
    resultat = subprocess.run(
        [sys.executable, "-c", "import app; assert app.app is not None; print('ok')"],
        cwd=str(dossier), capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(dossier)},
    )
    assert resultat.returncode == 0, (
        f"l'application ne se charge pas :\n{resultat.stderr[-1500:]}")
    assert "ok" in resultat.stdout


def test_avec_un_bloc_custom_le_module_revient(tmp_path):
    """LA CONTRE-ÉPREUVE. Sans elle, ne plus jamais émettre le module rendrait
    ce fichier de tests vert tout en tuant la brique `custom`."""
    dossier = _compiler(AVEC_CUSTOM, tmp_path / "avec")
    app = (dossier / "app.py").read_text(encoding="utf-8")
    sandbox = (dossier / "sandbox_ai.py").read_text(encoding="utf-8")

    assert "import sandbox_ai" in app, "la brique 'custom' a perdu son module"
    assert "def publier" in sandbox.lower(), (
        f"la coquille de la fonction custom n'est pas écrite :\n{sandbox}")


def test_les_deux_compilations_ne_rendent_pas_le_meme_app(tmp_path):
    """Le témoin du point 85 : avec et sans doivent DIFFÉRER.

    Si les deux sorties étaient identiques, la condition qu'on vient d'écrire
    ne produirait rien — exactement ce qu'on reproche au défaut d'origine.
    """
    sans = _compiler(SANS_CUSTOM, tmp_path / "a") / "app.py"
    avec = _compiler(AVEC_CUSTOM, tmp_path / "b") / "app.py"
    assert sans.read_text(encoding="utf-8") != avec.read_text(encoding="utf-8")
