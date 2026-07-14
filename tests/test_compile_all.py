"""
Test de non-régression : chaque fichier de exemples/*.yaml doit compiler
sans exception. Conçu pour tourner en local (pytest) et en CI (voir
.github/workflows/ci.yml), et détecter une régression comme celle du bug
v6 #2 (un exemple casse silencieusement après un refactor) avant qu'elle
ne s'accumule sur plusieurs versions.

Usage local : pytest tests/test_compile_all.py -v
"""
import os
import sys
import glob

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from parser import parse_monlang_file
from ast_validator import MonLangAST
from generator import MonLangSecureGenerator

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")
EXAMPLE_FILES = sorted(glob.glob(os.path.join(EXEMPLES_DIR, "*.yaml")))


@pytest.mark.parametrize("yaml_path", EXAMPLE_FILES, ids=[os.path.basename(p) for p in EXAMPLE_FILES])
def test_example_compiles(yaml_path):
    """Compile le socle déterministe (parsing + audit + génération) pour
    chaque exemple. Ne teste PAS l'étape IA (facultative, non bloquante,
    et dépendante d'un serveur Ollama qui n'est pas disponible en CI)."""
    raw_json = parse_monlang_file(yaml_path)
    ast_manager = MonLangAST(raw_json)
    normalized_ast = ast_manager.validate_and_audit()
    generator = MonLangSecureGenerator(normalized_ast)
    generator.generate_all()

    # Vérifie que les 3 artefacts d'infrastructure attendus ont bien été
    # produits. SUPPRESSION (roadmap, sur demande explicite) : 'frontend.html'
    # (l'ancien back-office React '/ui') n'est plus généré du tout — voir
    # docs/design_decisions.md, point 22. Un 4e artefact optionnel,
    # 'landing.html', n'existe que pour les specs avec un bloc 'landing'
    # (voir test_landing_examples_produce_landing_html ci-dessous).
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    for artefact in ("app.py", "schema.sql", "sandbox_ai.py"):
        artefact_path = os.path.join(base_dir, artefact)
        assert os.path.exists(artefact_path), f"{artefact} n'a pas été généré pour {os.path.basename(yaml_path)}"


def test_at_least_one_example_exists():
    """Garde-fou : évite un faux 'tout est vert' si le dossier exemples/ est vide."""
    assert len(EXAMPLE_FILES) > 0, "Aucun fichier .yaml trouvé dans exemples/"


def test_no_example_ever_produces_frontend_html():
    """SUPPRESSION (roadmap, sur demande explicite) : verrouille l'absence de
    tout back-office '/ui' auto-généré — pour TOUS les exemples, y compris
    ceux avec un bloc 'landing'. Si 'frontend.html' réapparaît un jour (ex.
    une régression qui restaure _generate_frontend), ce test doit échouer."""
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    frontend_path = os.path.join(base_dir, "frontend.html")
    for yaml_path in EXAMPLE_FILES:
        raw_json = parse_monlang_file(yaml_path)
        normalized_ast = MonLangAST(raw_json).validate_and_audit()
        MonLangSecureGenerator(normalized_ast).generate_all()
        assert not os.path.exists(frontend_path), (
            f"'frontend.html' a été généré pour {os.path.basename(yaml_path)} — "
            f"MonLang ne doit plus jamais produire de back-office auto-généré."
        )


def test_landing_examples_produce_landing_html():
    """Les specs avec un bloc 'landing' (mode 'ai' ou 'template') doivent
    produire 'landing.html' ; celles sans bloc 'landing' ne doivent PAS en
    produire un (pas de front fantôme laissé par un test précédent)."""
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    landing_path = os.path.join(base_dir, "landing.html")
    for yaml_path in EXAMPLE_FILES:
        if os.path.exists(landing_path):
            os.remove(landing_path)
        raw_json = parse_monlang_file(yaml_path)
        normalized_ast = MonLangAST(raw_json).validate_and_audit()
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
        if generator.landing_config:
            assert os.path.exists(landing_path), (
                f"'landing.html' attendu mais absent pour {os.path.basename(yaml_path)}"
            )
        else:
            assert not os.path.exists(landing_path), (
                f"'landing.html' généré sans bloc 'landing' pour {os.path.basename(yaml_path)}"
            )
    if os.path.exists(landing_path):
        os.remove(landing_path)
