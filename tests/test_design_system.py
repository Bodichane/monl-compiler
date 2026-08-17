"""Le design system est produit avant le frontend et reste vérifiable."""

import json

from monl.cli import check_coherence, compile_project
from monl.design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    activate_asset_manifest,
)
from monl.frontend_ai import _design_completeness_errors, build_generation_prompt

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


def test_manifest_ne_planifie_plus_d_images_depuis_le_brief(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC.replace(
        "Une boutique artisanale chaleureuse et éditoriale.",
        "Une boutique artisanale chaleureuse : les images portent le site."),
        encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    manifest = _manifest(tmp_path / ASSET_MANIFEST_FILENAME)
    # Renversement explicite du point F : le brief libre ne décide plus d'une
    # dépense image. L'option --generate-images est couverte séparément.
    assert manifest["generated_assets"] == []
    assert 'data-monl-section="a-propos"' in manifest["required_markers"]["index.html"]
    assert manifest["unique_section_markers"]["index.html"] == [
        'data-monl-section="a-propos"'
    ]
    design = (tmp_path / DESIGN_SYSTEM_FILENAME).read_text(encoding="utf-8")
    assert "- `hero.svg` —" not in design
    assert 'data-monl-section="<slug>"' in design
    prompt = build_generation_prompt(str(tmp_path), False)
    assert "- `editorial.svg` —" not in prompt
    assert 'data-monl-section="<slug>"' in prompt


def test_sections_au_meme_slug_sont_distinctes_et_acceptees(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC.replace(
        '    section "À propos": "Des objets fabriqués en petites séries."\n',
        '    section "À propos": "Des objets fabriqués en petites séries."\n'
        '    section "A propos": "Une seconde histoire, distincte."\n'),
        encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    manifest = _manifest(tmp_path / ASSET_MANIFEST_FILENAME)
    unique_markers = manifest["unique_section_markers"]["index.html"]
    required_markers = manifest["required_markers"]["index.html"]

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    rendered = [f"<section {marker}></section>" for marker in unique_markers]
    rendered.extend(
        f"<section {marker}></section>"
        for marker in required_markers
        if marker not in set(unique_markers)
    )
    (frontend / "index.html").write_text("\n".join(rendered), encoding="utf-8")
    assert activate_asset_manifest(str(tmp_path))
    assert _design_completeness_errors(str(tmp_path)) == []

    assert unique_markers == [
        'data-monl-section="a-propos"',
        'data-monl-section="a-propos-2"',
    ]
    assert len(unique_markers) == len(set(unique_markers))
    assert set(unique_markers) <= set(required_markers)


def _active_manifest_errors(tmp_path, section_count=1, media_count=1):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    compile_project(str(spec), str(tmp_path))
    manifest = _manifest(tmp_path / ASSET_MANIFEST_FILENAME)
    section_markers = set(manifest["unique_section_markers"]["index.html"])
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    rendered = []
    for marker in manifest["required_markers"]["index.html"]:
        if marker in section_markers:
            count = section_count
        elif marker.startswith('data-monl-media="'):
            count = media_count
        else:
            count = 1
        rendered.extend(f"<section {marker}></section>" for _ in range(count))
    (frontend / "index.html").write_text("\n".join(rendered), encoding="utf-8")
    assert activate_asset_manifest(str(tmp_path))
    return _design_completeness_errors(str(tmp_path)), manifest


def test_frontend_refuse_l_absence_d_une_section_declaree(tmp_path):
    errors, manifest = _active_manifest_errors(tmp_path, section_count=0)
    marker = manifest["unique_section_markers"]["index.html"][0]

    assert any(marker in error and "absente" in error for error in errors)


def test_frontend_refuse_la_duplication_d_une_section_declaree(tmp_path):
    errors, manifest = _active_manifest_errors(tmp_path, section_count=2)
    marker = manifest["unique_section_markers"]["index.html"][0]

    assert any(marker in error and "2 fois" in error for error in errors)


def test_frontend_accepte_un_marqueur_media_sur_plusieurs_cartes(tmp_path):
    errors, manifest = _active_manifest_errors(tmp_path, media_count=3)
    media_marker = next(
        marker for marker in manifest["required_markers"]["index.html"]
        if marker.startswith('data-monl-media="')
    )

    assert not any(media_marker in error for error in errors)
    assert not errors


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
