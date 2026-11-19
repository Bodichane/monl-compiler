"""The section markers required of the delivered frontend.

A marker NAMES a section, it does not prove that it contains anything:
substance is measured elsewhere (point 143, section_substance.py)."""

from ..design_system import build_asset_manifest, infer_design_profile


def _marker_block_description(marker):
    """Describes the HTML block that carries a manifest marker."""
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
    """Renders in the brief the executable map of the mandatory markers."""
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
