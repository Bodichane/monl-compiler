"""Les marqueurs de section exigés du frontend livré.

Un marqueur NOMME une section, il ne prouve pas qu'elle contient quelque
chose : la matière se mesure ailleurs (point 143, section_substance.py)."""

from ..design_system import build_asset_manifest, infer_design_profile


def _marker_block_description(marker):
    """Décrit le bloc HTML qui porte un marqueur du manifeste."""
    if marker.startswith('data-monl-media="'):
        entity = marker.split('"', 2)[1]
        return f"the area that renders the images of the entity `{entity}`"
    if not marker.startswith('data-monl-section="'):
        return "the HTML element of the matching visual block"
    section = marker.split('"', 2)[1]
    descriptions = {
        "hero": "the hero block / main banner",
        "catalogue": "the catalogue block that renders the product list",
        "panier": "the cart or order summary block",
        "workspace": "the workspace block of the role concerned",
        "faq": "the structured FAQ block",
        "editorial": "the editorial story block",
        "trust": "the proof or reassurance block",
        "closing-cta": "the final call-to-action block",
    }
    return descriptions.get(section, f"the HTML block of the section `{section}`")

def _required_markers_block(contract):
    """Rend dans le brief la carte exécutable des marqueurs obligatoires."""
    manifest = build_asset_manifest(contract, infer_design_profile(contract))
    markers = (manifest.get("required_markers") or {}).get("index.html") or []
    if not markers:
        return ""
    lines = "\n".join(
        f"- Exact file: `frontend/index.html` — exact marker: `{marker}` — "
        f"exact block: {_marker_block_description(marker)}."
        for marker in markers
    )
    return f"""
## Required visual markers — exact file and block

The manifest requires the following markers. Write each one in the file and
on the block given below; the marker text must be copied exactly, quotes
included. Do not replace it with a CSS class or a comment.

{lines}
"""
