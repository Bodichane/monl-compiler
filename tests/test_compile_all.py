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

    # Vérifie que les 4 artefacts attendus ont bien été produits
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    for artefact in ("app.py", "schema.sql", "sandbox_ai.py", "frontend.html"):
        artefact_path = os.path.join(base_dir, artefact)
        assert os.path.exists(artefact_path), f"{artefact} n'a pas été généré pour {os.path.basename(yaml_path)}"


def test_at_least_one_example_exists():
    """Garde-fou : évite un faux 'tout est vert' si le dossier exemples/ est vide."""
    assert len(EXAMPLE_FILES) > 0, "Aucun fichier .yaml trouvé dans exemples/"
