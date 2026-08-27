"""Public persistence façade for the platform store.

The builder store remains one class while database, project and build concerns
are composed as focused mixins.
"""

from __future__ import annotations

from .store_builds import StoreBuildsMixin
from .store_core import BUILD_STATES, StoreCoreMixin, normalize_slug
from .store_projects import StoreProjectsMixin


class PlatformStore(StoreCoreMixin, StoreProjectsMixin, StoreBuildsMixin):
    """SQLite store for builder metadata and build history."""


Store = PlatformStore

__all__ = ["BUILD_STATES", "PlatformStore", "Store", "normalize_slug"]
