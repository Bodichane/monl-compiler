"""Les noms de fichiers du système de design, en un seul endroit.

Ce sont des chemins RELATIFS au projet, pas de simples noms : la direction
visuelle se LIT, donc elle vit dans `docs/`. Le préfixe est porté ici plutôt
qu'à chaque appel — une trentaine de sites les emploient, et les ajouter un
par un laisserait forcément un oubli silencieux.
"""

from ..artifacts import DOCS_DIR

DESIGN_SYSTEM_FILENAME = f"{DOCS_DIR}/DESIGN_SYSTEM.md"

DESIGN_SPEC_FILENAME = f"{DOCS_DIR}/DESIGN_SPEC.md"

ASSET_MANIFEST_FILENAME = f"{DOCS_DIR}/ASSET_MANIFEST.json"

GENERATED_MARKER = "<!-- généré par monl — design system -->"
