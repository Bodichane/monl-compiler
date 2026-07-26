"""La direction de design est vérifiable quand la spec la déclare (bêta 3).

La clause 'design' du contrat était la seule qu'aucun contrôle ne confrontait
au livrable. Ces tests fixent la règle retenue : épinglée par la spec, elle
est contraignante ; déduite du vocabulaire, elle reste une proposition.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ast_validator import MonlAST  # noqa: E402
from frontend_contract import build_contract  # noqa: E402
from generator import MonlSecureGenerator  # noqa: E402
from parser import parse_monl_file  # noqa: E402
from smoke_test import _verifier_palette  # noqa: E402

BASE = """app Reparation

entity Piece
    label: String

actor Client selfRegister

workflow Catalogue for Client
    Create Piece
    Read Piece
"""

EPINGLE = BASE + """
ui Piece
    theme: atelier
"""


def _contrat(spec_source, workdir):
    chemin = os.path.join(workdir, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec_source)
    ast = MonlAST(parse_monl_file(chemin)).validate_and_audit()
    generateur = MonlSecureGenerator(ast, output_dir=workdir)
    return build_contract(ast, generateur)


def _frontend(workdir, css):
    dossier = os.path.join(workdir, "frontend")
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(css)
    return dossier


def test_theme_epingle_est_exact_et_contraignant():
    """Un thème épinglé échappe à la variation de teinte et lie le frontend."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(EPINGLE, workdir)
        design = contrat["design"]
        assert design["name"] == "atelier"
        assert design["pinned"] is True
        # Valeurs exactes du thème : une palette vérifiable ne peut pas être
        # décalée par la graine de variation propre au projet.
        assert design["accent"] == "#D9F227"
        assert design["bg"] == "#F1F3EE"

        conforme = _frontend(workdir, ":root{--a:#F1F3EE;--b:#FBFCFA;--c:#101C24;"
                                      "--d:#D9F227;--e:#A8412A;}")
        assert _verifier_palette(conforme, contrat) == []

        ecart = _frontend(workdir, ":root{--a:#F1F3EE;--b:#FBFCFA;--c:#101C24;"
                                   "--d:#FF00FF;--e:#A8412A;}")
        problemes = _verifier_palette(ecart, contrat)
        assert len(problemes) == 1
        message, bloquant = problemes[0]
        assert bloquant is True
        assert "#D9F227" in message


def test_theme_devine_reste_une_proposition():
    """Sans épinglage, l'écart est signalé mais ne fait pas échouer le build."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(BASE, workdir)
        assert contrat["design"]["pinned"] is False

        problemes = _verifier_palette(_frontend(workdir, "body{color:#123456}"), contrat)
        assert len(problemes) == 1
        message, bloquant = problemes[0]
        assert bloquant is False
        assert "theme:" in message  # le message indique comment rendre la règle contraignante


def test_demo_livree_respecte_son_theme_epingle():
    """Le frontend de la démo applique réellement la palette que sa spec épingle."""
    racine = os.path.join(os.path.dirname(__file__), "..")
    ast = MonlAST(parse_monl_file(os.path.join(racine, "demo", "spec.ml"))).validate_and_audit()
    with tempfile.TemporaryDirectory() as workdir:
        contrat = build_contract(ast, MonlSecureGenerator(ast, output_dir=workdir))
    assert contrat["design"]["pinned"] is True
    assert _verifier_palette(os.path.join(racine, "demo", "frontend"), contrat) == []
