"""Le design system est produit avant le frontend et reste vérifiable."""

import json

from monl.cli import check_coherence, compile_project
from monl.design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    activate_asset_manifest,
)
from monl.frontend_ai import build_generation_prompt

SPEC = """app Atelier

entity Product
    title: String
    price: Money
    image: Image

actor Visitor selfRegister

rule Product.Read public

workflow Browse for Visitor
    Read Product

landing
    brief: "Une boutique artisanale chaleureuse et éditoriale."
    section "À propos": "Des objets fabriqués en petites séries."
"""


def _manifest(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(lines[1:]))


def test_compile_prepare_design_system_et_manifest(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))

    for name in (DESIGN_SYSTEM_FILENAME, DESIGN_SPEC_FILENAME,
                 ASSET_MANIFEST_FILENAME):
        assert (tmp_path / name).is_file(), name
    design_system = (tmp_path / DESIGN_SYSTEM_FILENAME).read_text(encoding="utf-8")
    assert "Pattern :" in design_system
    assert "Anti-patterns" in design_system
    assert "Contraste" in design_system

    manifest = _manifest(tmp_path / ASSET_MANIFEST_FILENAME)
    assert manifest["status"] == "planned"
    assert 'data-monl-section="hero"' in manifest["required_markers"]["index.html"]

    prompt = build_generation_prompt(str(tmp_path), False)
    assert "DESIGN_SYSTEM.md" in prompt
    assert "ASSET_MANIFEST.json" in prompt


def test_manifest_generated_devient_bloquant_apres_frontend(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    front = tmp_path / "frontend"
    front.mkdir()
    (front / "index.html").write_text("<html><body></body></html>", encoding="utf-8")

    assert activate_asset_manifest(str(tmp_path))
    ok, errors, _warnings = check_coherence(str(tmp_path))
    assert not ok
    assert any("data-monl-section=\"hero\"" in error for error in errors)
