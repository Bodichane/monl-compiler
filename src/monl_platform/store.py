"""Persistence façade of the platform store.

POINT 162: the builds mixin disappeared with the build queue. Only the
database and the projects remain — a catalog of slugs, not a history of
billed jobs."""

from __future__ import annotations

from .store_core import StoreCoreMixin, normalize_slug
from .store_projects import StoreProjectsMixin


class PlatformStore(StoreCoreMixin, StoreProjectsMixin):
    """SQLite store of project metadata."""


Store = PlatformStore

__all__ = ["PlatformStore", "Store", "normalize_slug"]
