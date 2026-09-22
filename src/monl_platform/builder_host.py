"""Host-based forwarding middleware for built sites."""

from __future__ import annotations

from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .hosting import SiteHostingError, SiteNotCompiledError
from .hosting_admission import SITE_INACTIVITY_SECONDS

# Au-dessus des 32 Mio d'upload applicatif, sous les 50 Mio de Nginx.
SITE_MAX_BODY_BYTES = 40 * 1024 * 1024


async def _bounded_body(request):
    raw_length = request.headers.get("content-length")
    try:
        content_length = int(raw_length) if raw_length is not None else None
    except ValueError:
        content_length = None
    if content_length is not None and content_length > SITE_MAX_BODY_BYTES:
        return None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > SITE_MAX_BODY_BYTES:
            return None
        body.extend(chunk)
    return bytes(body)


def mount_builder_host_routes(application, runtime):
    @application.middleware("http")
    async def route_by_host(request, call_next):
        try:
            running = runtime.sites.target_for_host(request.headers.get("host"))
        except SiteNotCompiledError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        except SiteHostingError as exc:
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
                headers={"Retry-After": str(SITE_INACTIVITY_SECONDS)},
            )
        if running is None:
            return await call_next(request)
        body = await _bounded_body(request)
        if body is None:
            return JSONResponse(
                status_code=413,
                content={"detail": "Le corps relayé dépasse 40 Mio."},
            )
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
