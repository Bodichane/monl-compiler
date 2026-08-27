"""Le manifeste des assets : ce que le site DÉCLARE porter."""

import json
from pathlib import Path

from .marqueurs import _declared_section_markers, _required_markers, _section_substance
from .noms import ASSET_MANIFEST_FILENAME, DESIGN_SYSTEM_FILENAME, GENERATED_MARKER
from .profil import _slug


def _generated_image_plan(contract: dict, profile: dict) -> list[dict]:
    """Retourne le plan explicite d'images matricielles.

    L'absence de plan est le défaut. Cette fonction ne lit donc jamais le
    brief pour chercher un mot-clé : le booléen ``generate_images`` est la
    décision humaine qui l'appelle.
    """
    assets_dir = ((contract.get("assets") or {}).get("dir") or "assets").strip("/")
    prefix = f"{assets_dir}/generated"
    planned = [{
        "kind": "generated-image",
        "path": f"{prefix}/hero.jpg",
        "role": "bandeau principal du premier écran",
        "aspect_ratio": {"width": 16, "height": 9},
        "frontend_reference": f"{prefix}/hero.jpg",
        "required": True,
    }]
    if contract.get("sections") or profile["kind"] in {"service", "editorial", "commerce"}:
        planned.append({
            "kind": "generated-image",
            "path": f"{prefix}/editorial.jpg",
            "role": "vignette secondaire pour le récit ou la preuve",
            "frontend_reference": f"{prefix}/editorial.jpg",
            "required": True,
        })
    return planned

def build_asset_manifest(contract: dict, profile: dict, generate_images=False) -> dict:
    """Construit un plan d'assets sans prétendre que les fichiers existent déjà."""
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
        # Un marqueur nomme une section, il ne prouve pas qu'il y a quelque
        # chose dedans. La règle de substance voyage donc AVEC le marqueur :
        # un projet compilé par une version antérieure n'en a pas et reste
        # accepté tel quel, comme pour `required_markers` en son temps.
        "section_substance": {
            "index.html": _section_substance(contract, profile),
        },
        "notes": [
            "Les chemins de planned_assets sont des attentes de première construction.",
            "Après génération du frontend, Monl passe ce manifeste à active et vérifie les fichiers livrés.",
            "Un manifeste rédigé par l'auteur remplace ce plan et n'est jamais écrasé.",
        ],
    }

def activate_asset_manifest(project_dir: str) -> bool:
    """Passe le manifeste généré en mode vérifiable après écriture du frontend."""
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
