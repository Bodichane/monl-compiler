"""Public application factory.

The platform application only composes its lifecycle, page routes and API
routes; each concern remains independently discoverable and testable.
"""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI

from .app_api_routes import mount_api_routes
from .app_http import _links_of_footer, mount_error_handler
from .app_lifecycle import _purge, create_lifespan
from .app_pages import mount_page_routes
from .builder_routes import create_runtime, mount_builder_routes
from .identity import IdentityStore
from .log import anomaly, configure, event
from .mcp_server import MCPDispatcher
from .service import CompilationService
from .session import check_configuration_cookie


def create_app(*, workspace=None, domain=None, downloads_dir=None) -> FastAPI:
    """POINT 162: no AI provider to inject anymore.

    The eight removed parameters (provider, provider_factory, quota_limit,
    prices_path, poll_interval, start_worker, and the two for images) all
    served the frontend builder. The platform no longer builds interfaces and
    no longer calls any model: what it does, it does offline."""
    check_configuration_cookie()
    configure()
    service = CompilationService(workspace)
    identities = IdentityStore(service.workspace)
    sans_codes = identities.accounts_without_codes()
    accounts_inherited = identities.accounts_inherited()
    if sans_codes:
        anomaly("comptes_sans_codes_de_secours", nombre=sans_codes)
    if accounts_inherited:
        anomaly(
            "comptes_heritages_non_convertibles",
            nombre=accounts_inherited,
            raison="legacy registry hashes and identifiers are incompatible",
        )
    builder_runtime = create_runtime(
        service, identities, domain=domain, downloads_dir=downloads_dir
    )
    event("demarrage", workspace=str(service.workspace),
              purges=_purge(service, identities, builder_runtime))
    dispatcher = MCPDispatcher(service, identities)
    compile_slots = threading.BoundedSemaphore(
        max(1, int(os.environ.get("MONL_MAX_CONCURRENT_COMPILES", "2")))
    )
    application = FastAPI(
        lifespan=create_lifespan(service, identities, builder_runtime),
        title="MONL Platform",
        description="Remote validation and compilation of Monl backends.",
        version="0.2.0",
        docs_url="/api-docs",
    )
    application.state.compilation_service = service
    application.state.identity_store = identities
    application.state.builder_runtime = builder_runtime
    application.state.store = builder_runtime.store
    application.state.sites = builder_runtime.sites

    mount_builder_routes(application, builder_runtime, compile_slots)
    mount_page_routes(application, identities, service)
    mount_api_routes(application, service, identities, builder_runtime, dispatcher, compile_slots)
    mount_error_handler(application)
    return application


app = create_app(workspace=os.environ.get("MONL_PLATFORM_WORKSPACE"))

__all__ = ["_links_of_footer", "app", "create_app"]
