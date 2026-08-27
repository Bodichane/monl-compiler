"""Public application factory.

The platform application only composes its lifecycle, page routes and API
routes; each concern remains independently discoverable and testable.
"""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI

from .app_api_routes import mount_api_routes
from .app_http import _liens_de_pied, mount_error_handler
from .app_lifecycle import _purger, create_lifespan
from .app_pages import mount_page_routes
from .builder_routes import create_runtime, mount_builder_routes
from .identity import IdentityStore
from .journal import anomalie, configurer, evenement
from .mcp_server import MCPDispatcher
from .service import CompilationService


def create_app(
    *,
    workspace=None,
    domain=None,
    quota_limit=1_000_000,
    provider=None,
    provider_factory=None,
    model_provider_factory=None,
    image_provider_factory=None,
    image_provider=None,
    prices_path=None,
    poll_interval=0.05,
    downloads_dir=None,
    start_worker=True,
) -> FastAPI:
    configurer()
    service = CompilationService(workspace)
    identities = IdentityStore(service.workspace)
    sans_codes = identities.comptes_sans_codes()
    comptes_herites = identities.comptes_herites()
    if sans_codes:
        anomalie("comptes_sans_codes_de_secours", nombre=sans_codes)
    if comptes_herites:
        anomalie(
            "comptes_heritages_non_convertibles",
            nombre=comptes_herites,
            raison="hachage et identifiants du registre historique incompatibles",
        )
    evenement("demarrage", workspace=str(service.workspace),
              purges=_purger(service, identities))

    builder_runtime = create_runtime(
        service,
        identities,
        domain=domain,
        quota_limit=quota_limit,
        provider=provider,
        provider_factory=provider_factory,
        model_provider_factory=model_provider_factory,
        image_provider_factory=image_provider_factory,
        image_provider=image_provider,
        prices_path=prices_path,
        poll_interval=poll_interval,
        downloads_dir=downloads_dir,
        start_worker=start_worker,
    )
    dispatcher = MCPDispatcher(service, identities)
    compile_slots = threading.BoundedSemaphore(
        max(1, int(os.environ.get("MONL_MAX_CONCURRENT_COMPILES", "2")))
    )
    application = FastAPI(
        lifespan=create_lifespan(service, identities, builder_runtime),
        title="Monl Compiler Platform",
        description="Validation et compilation distante de backends Monl.",
        version="0.2.0",
        docs_url="/api-docs",
    )
    application.state.compilation_service = service
    application.state.identity_store = identities
    application.state.builder_runtime = builder_runtime
    application.state.store = builder_runtime.store
    application.state.quota = builder_runtime.quota
    application.state.sites = builder_runtime.sites
    application.state.worker = builder_runtime.worker

    mount_builder_routes(application, builder_runtime)
    mount_page_routes(application, identities, service)
    mount_api_routes(application, service, identities, builder_runtime, dispatcher, compile_slots)
    mount_error_handler(application)
    return application


app = create_app(workspace=os.environ.get("MONL_PLATFORM_WORKSPACE"))

__all__ = ["_liens_de_pied", "app", "create_app"]
