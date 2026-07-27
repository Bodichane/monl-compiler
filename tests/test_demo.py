# Verrou de la démonstration (docs/DEMO.md) : la spec livrée dans demo/ et
# le frontend livré dans demo/frontend/ doivent TOUJOURS former un ensemble
# qui compile et passe le smoke test comportemental. Si une évolution du
# compilateur, du contrat ou du smoke test casse la démo, ce test le dit —
# la démo ne peut pas pourrir en silence.
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli import check_coherence, compile_project
from smoke_test import run_smoke_test

DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "demo")


def test_la_demo_livree_compile_et_passe_le_smoke_test(tmp_path):
    proj = tmp_path / "demo"
    proj.mkdir()
    shutil.copy2(os.path.join(DEMO_DIR, "spec.ml"), proj / "spec.ml")
    shutil.copytree(os.path.join(DEMO_DIR, "frontend"), proj / "frontend")

    compile_project(str(proj / "spec.ml"), str(proj))

    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors
    ok, errors, warnings = run_smoke_test(str(proj), say=lambda *a: None)
    assert ok, errors
    # Le frontend a réellement parlé à l'API (pas un faux positif muet).
    assert not any("aucun appel API" in w for w in warnings), warnings


def test_le_frontend_de_la_demo_respecte_le_contrat_a_la_lettre():
    """Autonomie exigée par le contrat : aucun script externe, extensions
    dans la liste blanche (.html/.css/.js/.svg/.json), y compris dans les
    sous-dossiers — la démo embarque ses diagrammes."""
    frontend = os.path.join(DEMO_DIR, "frontend")
    autorisees = (".html", ".css", ".js", ".svg", ".json")
    fichiers = 0
    for racine, _dirs, noms in os.walk(frontend):
        for name in noms:
            chemin = os.path.join(racine, name)
            assert name.lower().endswith(autorisees), f"extension hors liste blanche : {chemin}"
            with open(chemin, encoding="utf-8") as fh:
                content = fh.read()
            assert "https://cdn" not in content and "<script src=\"http" not in content
            fichiers += 1
    assert fichiers >= 3
