"""Façade de persistance du magasin de plateforme.

POINT 161 : le mixin des constructions a disparu avec la file de builds. Ne
restent que la base et les projets — un catalogue de slugs, pas un historique
de travaux facturés.
"""

from __future__ import annotations

from .store_core import StoreCoreMixin, normalize_slug
from .store_projects import StoreProjectsMixin


class PlatformStore(StoreCoreMixin, StoreProjectsMixin):
    """Magasin SQLite des métadonnées de projets."""


Store = PlatformStore

__all__ = ["PlatformStore", "Store", "normalize_slug"]
