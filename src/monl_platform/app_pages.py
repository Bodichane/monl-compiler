"""HTML pages and read-only catalogue endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from monl import __version__ as MONL_VERSION

from . import examples
from .account import ACCOUNT_HTML, AUTH_HTML
from .console import CONSOLE_HTML
from .docs_page import DOCS_HTML
from .guide import guide_html
from .identity import IdentityStore
from .landing import LANDING_HTML
from .legal import CONDITIONS_HTML, MENTIONS_HTML, PRIVACY_HTML
from .mcp_page import MCP_HTML
from .security import SECURITY_HTML
from .theme import FAVICON, ICON_ICO, LOGO_SVG, VERSION_ICO, VERSION_SVG, cache_icon

WORDMARK = Path(__file__).with_name("static") / "monl-wordmark.png"
SOCIAL = Path(__file__).with_name("static") / "monl-social.png"
GUIDE_HTML = guide_html()


def mount_page_routes(application: FastAPI, identities: IdentityStore, service):
    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return LANDING_HTML

    @application.get("/console", response_class=HTMLResponse, include_in_schema=False)
    def console(request: Request):
        if not identities.session_user(request.cookies.get("monl_session")):
            target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
        return CONSOLE_HTML

    @application.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def auth_page(request: Request):
        if identities.session_user(request.cookies.get("monl_session")):
            return RedirectResponse("/console", status_code=303)
        return AUTH_HTML

    @application.get("/account", response_class=HTMLResponse, include_in_schema=False)
    def account(request: Request):
        if not identities.session_user(request.cookies.get("monl_session")):
            return RedirectResponse("/login?next=/account", status_code=303)
        return ACCOUNT_HTML

    @application.get("/mcp", response_class=HTMLResponse, include_in_schema=False)
    def mcp_access(request: Request):
        if not identities.session_user(request.cookies.get("monl_session")):
            return RedirectResponse("/login?next=/mcp", status_code=303)
        return MCP_HTML

    @application.get("/guide", response_class=HTMLResponse, include_in_schema=False)
    def guide():
        return GUIDE_HTML

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def documentation():
        return DOCS_HTML

    @application.get("/mentions-legales", response_class=HTMLResponse,
                     include_in_schema=False)
    def mentions_legal():
        return MENTIONS_HTML

    @application.get("/conditions", response_class=HTMLResponse, include_in_schema=False)
    def conditions():
        return CONDITIONS_HTML

    @application.get("/confidentialite", response_class=HTMLResponse, include_in_schema=False)
    def privacy():
        return PRIVACY_HTML

    @application.get("/security", response_class=HTMLResponse, include_in_schema=False)
    def security():
        return SECURITY_HTML

    @application.get("/favicon.svg", include_in_schema=False)
    def favicon(v: str = ""):
        # Without it, every visit leaves a 404 in the server logs — and a log
        # that contains normal noise stops being read.
        return Response(
            FAVICON, media_type="image/svg+xml",
            headers=cache_icon(v, VERSION_SVG),
        )

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon_ico(v: str = ""):
        # Browsers request /favicon.ico BY DEFAULT, even when the page declares
        # an SVG. This path answered 404, and a 404 replaces nothing: the
        # browser kept the OLD icon from its cache. The file is made from the
        # brand's paths by outils/fabriquer_images.py, so it cannot say
        # anything other than /favicon.svg. The received fingerprint decides
        # the caching: see cache_icone (theme.py).
        return FileResponse(
            ICON_ICO, media_type="image/x-icon",
            headers=cache_icon(v, VERSION_ICO),
        )

    @application.get("/logo.svg", include_in_schema=False)
    def logo():
        return Response(
            LOGO_SVG, media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/brand/monl-wordmark.png", include_in_schema=False)
    def wordmark():
        return FileResponse(
            WORDMARK, media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/brand/monl-social.png", include_in_schema=False)
    def social():
        """The image of the share cards. Raster is mandatory: no social bot renders
        an SVG."""
        return FileResponse(
            SOCIAL, media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "monl-compiler"}

    @application.get("/ready")
    def ready():
        if not identities.ready() or not os.access(service.workspace, os.W_OK):
            raise HTTPException(status_code=503, detail="Storage is not available.")
        return {"status": "ready", "storage": "available"}

    @application.get("/api/version")
    def version():
        return {
            "compiler": MONL_VERSION,
            "platform": application.version,
            "contract": service.contract_version(),
        }

    @application.get("/api/templates")
    def templates():
        return {"templates": service.list_templates()}

    @application.get("/api/examples")
    def list_examples():
        return {"examples": examples.catalogue()}

    @application.get("/api/examples/{example_id}")
    def example(example_id: str):
        try:
            return {"id": example_id, "spec": examples.spec_of(example_id)}
        except KeyError:
            raise HTTPException(status_code=404, detail="Example not found.") from None

