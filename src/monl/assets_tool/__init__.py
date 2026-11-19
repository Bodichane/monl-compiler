"""`monl assets`: the ONLY place in the repository, outside the dialogue,
that writes to the human's spec (point 84).

Three rules hold everything there: TEXTUAL editing (the comments are the
project's documentation), revalidation by the real parser and the real
validator BEFORE writing, and full rollback on failure.

The public surface did not move when it became a package."""

from ..ast_validator import DEFAULT_ASSETS_DIR, resolve_asset
from .commands import add_asset, lister_assets
from .editing import _blocks_seed, _literal
from .foundations import AssetsToolError, slugify
from .resolution import paths_declares
from .specio import _charger, _revalidate

__all__ = [
    "DEFAULT_ASSETS_DIR",
    "AssetsToolError",
    "_blocks_seed",
    "_charger",
    "_literal",
    "_revalidate",
    "add_asset",
    "lister_assets",
    "paths_declares",
    "resolve_asset",
    "slugify",
]
