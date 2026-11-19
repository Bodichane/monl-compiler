"""The design system: what monl DESCRIBES about the site without deciding
anything.

Point 72: the compiler picks neither palette, nor typography, nor radius.
It deduces a PROFILE from the spec, requires section markers, and returns
a document the interface AI must follow.

The public surface did not move when it became a package."""

from .manifest import activate_asset_manifest, build_asset_manifest
from .markers import _declared_section_markers, _section_substance
from .names import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    GENERATED_MARKER,
)
from .profile import infer_design_profile
from .rendering import ensure_design_artifacts, plan_generated_images

# POINT 139: there is NO palette here anymore, and there must not be one. Five
# palettes indexed on the kind of business lived in this place. Point 72
# forbids it — "the compiler decides NOTHING visual: neither palette, nor
# typography, nor radius" — and three facts settled it rather than an argument:
# the five `:root` colors of projets/AtelierNaya are byte-identical to the
# "service" palette, written forty minutes earlier; the safeguard only looked
# at the contract, while the palette traveled through DESIGN_SYSTEM.md; and
# that palette failed the contrast it promised itself in the same document
# (white on #D07A4B: 3.20:1 for an announced threshold of 4.5:1, measured on
# the "Book" button).
#
# The line drawn is finer than "method versus taste": a scale, a rhythm, a
# duration or a break become TASTE as soon as the compiler picks their VALUES.
# This file can therefore require that a scale exists and is followed; it
# cannot say which one.

__all__ = [
    "ASSET_MANIFEST_FILENAME",
    "DESIGN_SPEC_FILENAME",
    "DESIGN_SYSTEM_FILENAME",
    "GENERATED_MARKER",
    "_declared_section_markers",
    "_section_substance",
    "activate_asset_manifest",
    "build_asset_manifest",
    "ensure_design_artifacts",
    "infer_design_profile",
    "plan_generated_images",
]
