"""Public identity-store façade.

The store remains one public class while each concern lives in a focused
mixin, following the package composition used by the generator package.
"""

from __future__ import annotations

from .identity_admin import IdentityAdminMixin
from .identity_auth import IdentityAuthMixin
from .identity_credentials import IdentityCredentialsMixin
from .identity_database import IdentityDatabaseMixin
from .identity_keys import IdentityKeysMixin
from .identity_limits import IdentityLimitsMixin
from .identity_primitives import EMAIL, PROJECT_TTL, SESSION_TTL, IdentityError
from .identity_projects import IdentityProjectsMixin
from .identity_recovery import IdentityRecoveryMixin


class IdentityStore(
    IdentityDatabaseMixin,
    IdentityCredentialsMixin,
    IdentityAuthMixin,
    IdentityProjectsMixin,
    IdentityRecoveryMixin,
    IdentityAdminMixin,
    IdentityKeysMixin,
    IdentityLimitsMixin,
):
    """Persistent identities, sessions, projects, keys and recovery codes."""


__all__ = ["EMAIL", "PROJECT_TTL", "SESSION_TTL", "IdentityError", "IdentityStore"]
