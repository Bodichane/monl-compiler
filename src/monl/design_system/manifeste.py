"""The asset manifest: what the site DECLARES it carries."""

import json
from pathlib import Path

from .marqueurs import _declared_section_markers, _required_markers, _section_substance
from .noms import ASSET_MANIFEST_FILENAME, DESIGN_SYSTEM_FILENAME, GENERATED_MARKER
from .profil import _slug


def _generated_image_plan(contract: dict, profile: dict) -> list[dict]:
    """Returns the explicit plan of raster images.

    The absence of a plan is the default. This function therefore never reads
    the brief looking for a keyword: the ``generate_images`` boolean is the
    human decision that calls it."""
    assets_dir = ((contract.get("assets") or {}).get("dir") or "assets").strip("/")
    prefix = f"{assets_dir}/generated"
    planned = [{
        "kind": "generated-image",
        "path": f"{prefix}/hero.jpg",
        "role": "main banner of the first screen",
        "aspect_ratio": {"width": 16, "height": 9},
        "frontend_reference": f"{prefix}/hero.jpg",
        "required": True,
    }]
    if contract.get("sections") or profile["kind"] in {"service", "editorial", "commerce"}:
        planned.append({
            "kind": "generated-image",
            "path": f"{prefix}/editorial.jpg",
            "role": "secondary thumbnail for the story or the proof",
            "frontend_reference": f"{prefix}/editorial.jpg",
            "required": True,
        })
    return planned

def build_asset_manifest(contract: dict, profile: dict, generate_images=False) -> dict:
    """Builds an asset plan without claiming the files already exist."""
    planned = []
    for media in profile["media_entities"]:
        for field in media["fields"]:
            planned.append({
                "kind": "entity-media",
                "entity": media["entity"],
                "field": field,
                "path_pattern": f"assets/{_slug(media['entity'])}/{{slug}}.svg",
                "required": True,
            })
    if contract.get("sections"):
        planned.append({
            "kind": "editorial-hero",
            "path_pattern": "assets/editorial/hero.svg",
            "required": True,
        })
    generated_assets = (_generated_image_plan(contract, profile)
                        if generate_images else [])
    return {
        "schema_version": 1,
        "status": "planned",
        "generated_by": "monl",
        "design_system": DESIGN_SYSTEM_FILENAME,
        "products": {},
        "editorial": {},
        "planned_assets": planned,
        "generated_assets": generated_assets,
        "required_markers": {"index.html": _required_markers(contract, profile)},
        "unique_section_markers": {
            "index.html": _declared_section_markers(contract),
        },
        # A marker names a section, it does not prove there is something in it.
        # The substance rule therefore travels WITH the marker: a project
        # compiled by an earlier version has none and stays accepted as is, as
        # was the case for `required_markers` in its time.
        "section_substance": {
            "index.html": _section_substance(contract, profile),
        },
        "notes": [
            "The planned_assets paths are expectations for the first build.",
            "After the frontend is generated, Monl switches this manifest to active and checks the delivered files.",
            "A manifest written by the author replaces this plan and is never overwritten.",
        ],
    }

def activate_asset_manifest(project_dir: str) -> bool:
    """Switches the generated manifest to verifiable mode after the frontend is
    written."""
    path = Path(project_dir) / ASSET_MANIFEST_FILENAME
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        if GENERATED_MARKER not in content:
            return False
        manifest = json.loads("\n".join(content.splitlines()[1:]))
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("generated_by") != "monl" or manifest.get("status") != "planned":
        return False
    manifest["status"] = "active"
    path.write_text(
        GENERATED_MARKER + "\n" + json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return True
