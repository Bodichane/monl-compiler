"""
Test de non-régression : chaque fichier de exemples/*.ml (ou *.yaml, ancienne extension) doit compiler
sans exception. Conçu pour tourner en local (pytest) et en CI (voir
.github/workflows/ci.yml), et détecter une régression comme celle du bug
v6 #2 (un exemple casse silencieusement après un refactor) avant qu'elle
ne s'accumule sur plusieurs versions.

Usage local : pytest tests/test_compile_all.py -v

POINT 64 : ces tests compilaient DANS LA RACINE DU DÉPÔT — chaque exécution
de la suite y redéposait app.py, schema.sql, sandbox_ai.py, manage.py et
.jwt_secret, et le rituel de nettoyage de CLAUDE.md existait pour ça. Le
générateur accepte un output_dir depuis longtemps ; il est désormais utilisé.
Compiler ailleurs que dans le dépôt rend aussi les assertions plus fortes :
un artefact trouvé ne peut plus être le reliquat d'une compilation
précédente.

POINT 85 : `base_dir` est désormais passé au validateur. Sans lui, la
vérification d'EXISTENCE des assets (brique 13, point 83) se tait — et se
taisait ici, puisque aucun exemple ne déclarait d'assets. `01_portfolio.ml` en
déclare maintenant : ces tests vérifient donc aussi que les fichiers du dossier
`exemples/assets/` sont RÉELLEMENT là. Retirer `base_dir` rendrait ces
compilations muettes sur la moitié de ce qu'elles éprouvent.
"""
import glob
import os
import tempfile

import pytest

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")
EXAMPLE_FILES = sorted(glob.glob(os.path.join(EXEMPLES_DIR, "*.ml")) + glob.glob(os.path.join(EXEMPLES_DIR, "*.monl")) + glob.glob(os.path.join(EXEMPLES_DIR, "*.yaml")))


@pytest.mark.parametrize("yaml_path", EXAMPLE_FILES, ids=[os.path.basename(p) for p in EXAMPLE_FILES])
def test_example_compiles(yaml_path):
    """Compile le socle déterministe (parsing + audit + génération) pour
    chaque exemple, et vérifie qu'il aboutit sans erreur."""
    raw_json = parse_monl_file(yaml_path)
    ast_manager = MonlAST(raw_json, base_dir=EXEMPLES_DIR)
    normalized_ast = ast_manager.validate_and_audit()
    with tempfile.TemporaryDirectory() as sortie:
        MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()

        # Vérifie que les 3 artefacts d'infrastructure attendus ont bien été
        # produits. SUPPRESSION (roadmap, sur demande explicite) :
        # 'frontend.html' (l'ancien back-office React '/ui') n'est plus généré
        # du tout — voir docs/design_decisions.md, point 22. Plus AUCUN front
        # n'est généré depuis le pivot (point 41) — voir le dernier test.
        for artefact in ("app.py", "schema.sql", "sandbox_ai.py"):
            artefact_path = os.path.join(sortie, artefact)
            assert os.path.exists(artefact_path), f"{artefact} n'a pas été généré pour {os.path.basename(yaml_path)}"


def test_at_least_one_example_exists():
    """Garde-fou : évite un faux 'tout est vert' si le dossier exemples/ est vide."""
    assert len(EXAMPLE_FILES) > 0, "Aucun fichier .ml (ou .yaml) trouvé dans exemples/"


def test_no_example_ever_produces_frontend_html():
    """SUPPRESSION (roadmap, sur demande explicite) : verrouille l'absence de
    tout back-office '/ui' auto-généré — pour TOUS les exemples, y compris
    ceux avec un bloc 'landing'. Si 'frontend.html' réapparaît un jour (ex.
    une régression qui restaure _generate_frontend), ce test doit échouer."""
    for yaml_path in EXAMPLE_FILES:
        raw_json = parse_monl_file(yaml_path)
        normalized_ast = MonlAST(raw_json, base_dir=EXEMPLES_DIR).validate_and_audit()
        with tempfile.TemporaryDirectory() as sortie:
            MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()
            frontend_path = os.path.join(sortie, "frontend.html")
        assert not os.path.exists(frontend_path), (
            f"'frontend.html' a été généré pour {os.path.basename(yaml_path)} — "
            f"monl ne doit plus jamais produire de back-office auto-généré."
        )


def test_no_example_ever_produces_any_generated_frontend():
    """PIVOT (point 41) : monl ne génère plus AUCUN frontend — ni
    'frontend.html' (retiré au point 22), ni 'landing.html', ni
    'dashboard.html'. Si l'un d'eux réapparaît, ce test doit échouer :
    l'interface vient exclusivement de l'IA frontend, via le contrat."""
    for yaml_path in EXAMPLE_FILES:
        raw_json = parse_monl_file(yaml_path)
        normalized_ast = MonlAST(raw_json, base_dir=EXEMPLES_DIR).validate_and_audit()
        with tempfile.TemporaryDirectory() as sortie:
            MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()
            fantomes = {g: os.path.exists(os.path.join(sortie, g))
                        for g in ("landing.html", "dashboard.html", "frontend.html")}
        for ghost, present in fantomes.items():
            assert not present, (
                f"'{ghost}' a été généré pour {os.path.basename(yaml_path)} — "
                f"monl ne doit plus produire aucun frontend (point 41)."
            )
