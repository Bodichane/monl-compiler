# Lock on the demo (docs/DEMO.md): the spec shipped in demo/ and the frontend
# shipped in demo/frontend/ must ALWAYS form a whole that compiles and passes
# the behavioral smoke test. If a change to the compiler, the contract or the
# smoke test breaks the demo, this test says so — the demo cannot rot silently.
import os
import shutil

from monl.cli import check_coherence, compile_project
from monl.smoke_test import run_smoke_test

DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "demo")


def test_the_shipped_demo_compiles_and_passes_the_smoke_test(tmp_path):
    proj = tmp_path / "demo"
    proj.mkdir()
    shutil.copy2(os.path.join(DEMO_DIR, "spec.ml"), proj / "spec.ml")
    shutil.copytree(os.path.join(DEMO_DIR, "frontend"), proj / "frontend")
    # The photos are INPUTS of the demo just like the frontend (brick 13):
    # without them, the smoke test would serve a shop where every product shows
    # a broken image — and would not say so.
    shutil.copytree(os.path.join(DEMO_DIR, "assets"), proj / "assets")

    compile_project(str(proj / "spec.ml"), str(proj))

    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors
    ok, errors, warnings = run_smoke_test(str(proj), say=lambda *a: None)
    assert ok, errors
    # The frontend really talked to the API (not a silent false positive).
    assert not any("aucun appel API" in w for w in warnings), warnings


def test_the_demo_frontend_follows_the_contract_to_the_letter():
    """Self-containment required by the contract: no external script, extensions
    in the allowlist (.html/.css/.js/.svg/.json), subfolders included.

    The count only requires a minimum of 1: the current demo fits in a single
    `index.html` (inline CSS and JS), which is a legitimate shape and not an
    incomplete frontend. The allowlist and the absence of CDN carry the
    invariant — requiring three files measured a habit, not a property. The
    photos live outside `frontend/`: that is the whole point of brick 13, and
    why `.webp` need not be in the allowlist."""
    frontend = os.path.join(DEMO_DIR, "frontend")
    allowed = (".html", ".css", ".js", ".svg", ".json")
    files = 0
    for racine, _dirs, names in os.walk(frontend):
        for name in names:
            path = os.path.join(racine, name)
            assert name.lower().endswith(allowed), f"extension hors liste blanche : {path}"
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            assert "https://cdn" not in content and "<script src=\"http" not in content
            files += 1
    assert files >= 1
