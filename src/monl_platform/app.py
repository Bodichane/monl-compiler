from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from monl import __version__ as MONL_VERSION

from . import examples
from .console import CONSOLE_HTML
from .docs_page import DOCS_HTML
from .guide import guide_html
from .landing import LANDING_HTML
from .mcp_server import MCPDispatcher
from .security import SECURITY_HTML
from .service import CompilationService, PlatformInputError, PlatformNotFoundError
from .theme import FAVICON, page

# Une page servie deux fois identique n'a pas besoin d'être reconstruite à
# chaque visite : le guide est du HTML pur, dérivé de constantes.
GUIDE_HTML = guide_html()


def create_app(*, workspace=None) -> FastAPI:
    service = CompilationService(workspace)
    dispatcher = MCPDispatcher(service)
    application = FastAPI(
        title="Monl Compiler Platform",
        description="Validation et compilation distante de backends Monl.",
        version="0.2.0",
        docs_url="/api-docs",
    )
    application.state.compilation_service = service

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def accueil():
        return LANDING_HTML

    @application.get("/console", response_class=HTMLResponse, include_in_schema=False)
    def console():
        return CONSOLE_HTML

    @application.get("/guide", response_class=HTMLResponse, include_in_schema=False)
    def guide():
        return GUIDE_HTML

    @application.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def documentation():
        return DOCS_HTML

    @application.get("/security", response_class=HTMLResponse, include_in_schema=False)
    def security():
        return SECURITY_HTML

    @application.get("/favicon.svg", include_in_schema=False)
    def favicon():
        # Sans elle, chaque visite laisse un 404 dans les journaux du serveur —
        # et un journal qui contient du bruit normal cesse d'être lu.
        return Response(
            FAVICON, media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "monl-compiler"}

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
    def liste_exemples():
        return {"examples": examples.catalogue()}

    @application.get("/api/examples/{example_id}")
    def exemple(example_id: str):
        try:
            return {"id": example_id, "spec": examples.spec_of(example_id)}
        except KeyError:
            raise HTTPException(status_code=404, detail="Exemple introuvable.") from None

    @application.post("/api/validate")
    async def validate(request: Request):
        payload = await _json_body(request)
        try:
            return service.validate(payload.get("spec")).as_dict()
        except PlatformInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/compile", status_code=201)
    async def compile_backend(request: Request):
        payload = await _json_body(request)
        try:
            return service.compile(payload.get("spec"))
        except PlatformInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/api/projects/{project_id}")
    def inspect(project_id: str):
        try:
            return service.inspect(project_id)
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/projects/{project_id}/contract")
    def contract(project_id: str):
        try:
            return service.contract(project_id)
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/projects/{project_id}/download")
    def download(project_id: str):
        try:
            archive = service.archive(project_id)
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(
            archive, media_type="application/zip",
            filename=f"monl-backend-{project_id[:8]}.zip",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @application.post("/mcp")
    async def mcp(request: Request):
        message = await _json_body(request)
        response = dispatcher.dispatch(message)
        return JSONResponse(response or {}, status_code=200)

    @application.exception_handler(404)
    async def introuvable(request: Request, exc: HTTPException):
        # Un visiteur reçoit une page, un client d'API reçoit du JSON. Servir
        # du HTML à `curl` rendrait l'erreur illisible là où elle doit être lue.
        detail = getattr(exc, "detail", "Introuvable.")
        if _veut_du_json(request):
            return JSONResponse({"detail": detail}, status_code=404)
        return HTMLResponse(_page_404(detail), status_code=404)

    return application


def _veut_du_json(request: Request) -> bool:
    if request.url.path.startswith(("/api/", "/mcp")):
        return True
    return "text/html" not in request.headers.get("accept", "")


def _page_404(detail: str) -> str:
    return page(
        title="Page introuvable — monl compiler",
        description="Cette adresse n'existe pas sur la plateforme monl.",
        body=f"""
<section class="shell section" style="text-align:center;padding-block:var(--space-8)">
<span class="eyebrow" style="justify-content:center">Erreur 404</span>
<h2 style="font-size:clamp(28px,4vw,40px);margin-bottom:var(--space-3)">Cette page n'existe pas.</h2>
<p class="muted" style="max-width:520px;margin:0 auto var(--space-6)">{detail}</p>
<div style="display:flex;gap:var(--space-3);justify-content:center;flex-wrap:wrap">
<a class="primary" href="/">Retour à l’accueil</a>
<a class="secondary" href="/console">Ouvrir la console</a>
<a class="secondary" href="/guide">Lire le guide</a>
</div>
</section>""",
    )


async def _json_body(request: Request) -> dict:
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > 300_000:
                raise HTTPException(status_code=413, detail="Requête trop volumineuse.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length invalide.") from None
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Corps JSON invalide.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Un objet JSON est attendu.")
    return payload


app = create_app(workspace=os.environ.get("MONL_PLATFORM_WORKSPACE"))
