"""`monl assets` : le SEUL endroit du dépôt, hors dialogue, qui écrive
dans la spec de l'humain (point 84).

Trois règles y tiennent tout : édition TEXTUELLE (les commentaires
sont la documentation du projet), revalidation par le vrai parseur et
le vrai validateur AVANT écriture, et retour en arrière complet en cas
d'échec.

La surface publique n'a pas bougé en devenant un paquet."""

from ..ast_validator import DEFAULT_ASSETS_DIR, resoudre_asset
from .commandes import ajouter_asset, lister_assets
from .edition import _blocs_seed, _litteral
from .fondations import AssetsToolError, sluggify
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
