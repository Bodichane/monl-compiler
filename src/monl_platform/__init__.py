"""Socle Python de la plateforme monl.

La plateforme dépend de ``monl`` pour compiler et vérifier, mais ``monl`` ne
dépend jamais de ce paquet. Cette frontière permet d'ajouter une interface
HTTP plus tard sans créer une seconde chaîne de génération.
"""

from .builder import BuildIsolationError, build_project
from .quota import QuotaError, QuotaExceededError, QuotaUnavailableError, TokenQuota
from .store import PlatformStore

__all__ = [
    "BuildIsolationError",
    "PlatformStore",
    "QuotaError",
    "QuotaExceededError",
    "QuotaUnavailableError",
    "TokenQuota",
    "build_project",
]
