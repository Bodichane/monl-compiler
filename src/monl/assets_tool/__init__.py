"""`monl assets`: the ONLY place in the repository, outside the dialogue,
that writes to the human's spec (point 84).

Three rules hold everything there: TEXTUAL editing (the comments are the
project's documentation), revalidation by the real parser and the real
validator BEFORE writing, and full rollback on failure.

The public surface did not move when it became a package."""

from ..ast_validator import DEFAULT_ASSETS_DIR, resoudre_asset
from .commands import ajouter_asset, lister_assets
from .editing import _blocs_seed, _litteral
from .foundations import AssetsToolError, sluggify
from .resolution import chemins_declares
from .specio import _charger, _revalider

__all__ = [
    "DEFAULT_ASSETS_DIR",
    "AssetsToolError",
    "_blocs_seed",
    "_charger",
    "_litteral",
    "_revalider",
    "ajouter_asset",
    "chemins_declares",
    "lister_assets",
    "resoudre_asset",
    "sluggify",
]
