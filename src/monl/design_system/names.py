"""The design system's file names, in one place.

These are paths RELATIVE to the project, not mere names: the visual
direction is READ, so it lives in `docs/`. The prefix is carried here
rather than at each call — some thirty places use them, and adding them
one by one would inevitably leave a silent omission."""

from ..artifacts import DOCS_DIR

DESIGN_SYSTEM_FILENAME = f"{DOCS_DIR}/DESIGN_SYSTEM.md"

DESIGN_SPEC_FILENAME = f"{DOCS_DIR}/DESIGN_SPEC.md"

ASSET_MANIFEST_FILENAME = f"{DOCS_DIR}/ASSET_MANIFEST.json"

GENERATED_MARKER = "<!-- généré par monl — design system -->"
