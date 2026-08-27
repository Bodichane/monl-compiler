"""Shared validation constants for the identity store."""

from __future__ import annotations

import os
import re

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SESSION_TTL = 30 * 24 * 3600
PROJECT_TTL = int(os.environ.get("MONL_PROJECT_RETENTION_DAYS", "30")) * 24 * 3600


class IdentityError(ValueError):
    pass
