"""Host-based forwarding middleware for built sites."""

from __future__ import annotations

from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .hosting import SiteHostingError, SiteNotBuiltError


def mount_builder_host_routes(application, runtime):
    @application.middleware("http")
    async def route_by_host(request, call_next):
        try:
            running = runtime.sites.target_for_host(request.headers.get("host"))
        except SiteNotBuiltError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        except SiteHostingError as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})
        if running is None:
            return await call_next(request)
        body = await request.body()
        raw_path = request.scope.get("raw_path", b"/").decode("latin-1")
        query = request.scope.get("query_string", b"").decode("latin-1")
        target = raw_path + ("?" + query if query else "")
        try:
            return await run_in_threadpool(
                runtime.sites.forward,
                running,
                request.method,
                target,
                dict(request.headers),
                body,
            )
        except SiteHostingError as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})


