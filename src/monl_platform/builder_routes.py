"""Public builder-route façade.

The builder is composed from its host middleware, authentication/catalogue
routes, and build/site lifecycle routes.
"""

from __future__ import annotations

from .builder_auth_routes import OAUTH_STATE_SECRET_ENV, mount_builder_auth_routes
from .builder_build_routes import mount_builder_build_routes
from .builder_host import mount_builder_host_routes
from .builder_runtime import (
    BuilderRuntime,
    create_runtime,
)


def mount_builder_routes(application, runtime):
    """Mount all builder concerns while preserving the historical entrypoint."""
    mount_builder_host_routes(application, runtime)
    mount_builder_auth_routes(application, runtime)
    mount_builder_build_routes(application, runtime)
    return runtime


__all__ = [
    "OAUTH_STATE_SECRET_ENV",
    "BuilderRuntime",
    "create_runtime",
    "mount_builder_routes",
]
