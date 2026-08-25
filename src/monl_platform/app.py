from __future__ import annotations

import os
import threading
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from monl import __version__ as MONL_VERSION

from . import examples
from .account import ACCOUNT_HTML, AUTH_HTML
from .console import CONSOLE_HTML
from .docs_page import DOCS_HTML
from .guide import guide_html
from .identity import IdentityError, IdentityStore
from .landing import LANDING_HTML
from .mcp_server import MCPDispatcher
from .security import SECURITY_HTML
from .service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    PlatformNotFoundError,
)
from .theme import FAVICON, LOGO_SVG, page

# Une page servie deux fois identique n'a pas besoin d'être reconstruite à
# chaque visite : le guide est du HTML pur, dérivé de constantes.
GUIDE_HTML = guide_html()


def create_app(*, workspace=None) -> FastAPI:
    service = CompilationService(workspace)
    identities = IdentityStore(service.workspace)
    for expired_id in identities.expired_projects():
        try:
            service.delete(expired_id)
        except PlatformNotFoundError:
            pass
    dispatcher = MCPDispatcher(service, identities)
    compile_slots = threading.BoundedSemaphore(
        max(1, int(os.environ.get("MONL_MAX_CONCURRENT_COMPILES", "2")))
    )
    application = FastAPI(
        title="Monl Compiler Platform",
        description="Validation et compilation distante de backends Monl.",
        version="0.2.0",
        docs_url="/api-docs",
    )
    application.state.compilation_service = service
    application.state.identity_store = identities

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def accueil():
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

    @application.get("/logo.svg", include_in_schema=False)
    def logo():
        return Response(
            LOGO_SVG, media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "monl-compiler"}

    @application.get("/ready")
    def ready():
        if not identities.ready() or not os.access(service.workspace, os.W_OK):
            raise HTTPException(status_code=503, detail="Le stockage n'est pas disponible.")
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
    def liste_exemples():
        return {"examples": examples.catalogue()}

    @application.get("/api/examples/{example_id}")
    def exemple(example_id: str):
        try:
            return {"id": example_id, "spec": examples.spec_of(example_id)}
        except KeyError:
            raise HTTPException(status_code=404, detail="Exemple introuvable.") from None

    @application.post("/api/auth/register", status_code=201)
    async def register(request: Request):
        _rate_limit(request, identities, "register", _client_ip(request), 5, 60)
        payload = await _json_body(request)
        try:
            user = identities.register(payload.get("email"), payload.get("password"))
        except IdentityError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _session_response(identities, user, status_code=201)

    @application.post("/api/auth/login")
    async def login(request: Request):
        _rate_limit(request, identities, "login", _client_ip(request), 5, 60)
        payload = await _json_body(request)
        user = identities.authenticate(payload.get("email"), payload.get("password"))
        if not user:
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
        return _session_response(identities, user)

    @application.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        identities.revoke_session(request.cookies.get("monl_session"))
        response = Response(status_code=204)
        response.delete_cookie("monl_session", path="/", httponly=True, samesite="strict")
        return response

    @application.get("/api/auth/me")
    def me(request: Request):
        return _require_user(request, identities)

    @application.get("/api/projects")
    def list_projects(request: Request):
        user = _require_user(request, identities)
        return {"projects": identities.projects(user["id"])}

    @application.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str, request: Request):
        user = _require_user(request, identities)
        _require_project(identities, user["id"], project_id)
        service.delete(project_id)
        identities.delete_project(user["id"], project_id)
        return Response(status_code=204)

    @application.get("/api/keys")
    def list_keys(request: Request):
        user = _require_user(request, identities)
        return {"keys": identities.api_keys(user["id"])}

    @application.post("/api/keys", status_code=201)
    async def create_key(request: Request):
        user = _require_user(request, identities)
        payload = await _json_body(request)
        try:
            return identities.create_api_key(user["id"], payload.get("name"))
        except IdentityError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.delete("/api/keys/{key_id}", status_code=204)
    def revoke_key(key_id: str, request: Request):
        user = _require_user(request, identities)
        if not identities.revoke_api_key(user["id"], key_id):
            raise HTTPException(status_code=404, detail="Clé introuvable.")
        return Response(status_code=204)

    @application.post("/api/validate")
    async def validate(request: Request):
        payload = await _json_body(request)
        try:
            return service.validate(payload.get("spec")).as_dict()
        except PlatformInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PlatformExecutionError as exc:
            raise HTTPException(
                status_code=503, detail=str(exc), headers={"Retry-After": "10"}
            ) from exc

    @application.post("/api/compile", status_code=201)
    async def compile_backend(request: Request):
        user = _require_user(request, identities)
        _rate_limit(request, identities, "compile", user["id"], 10, 3600)
        payload = await _json_body(request)
        if not compile_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="Les compilateurs sont occupés. Réessayez dans quelques instants.",
                headers={"Retry-After": "5"},
            )
        try:
            manifest = await run_in_threadpool(service.compile, payload.get("spec"))
            identities.add_project(user["id"], manifest["id"], manifest["summary"]["app"])
            return manifest
        except PlatformInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            compile_slots.release()

    @application.get("/api/projects/{project_id}")
    def inspect(project_id: str, request: Request):
        user = _require_user(request, identities)
        _require_project(identities, user["id"], project_id)
        try:
            return service.inspect(project_id)
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/projects/{project_id}/contract")
    def contract(project_id: str, request: Request):
        user = _require_user(request, identities)
        _require_project(identities, user["id"], project_id)
        try:
            return service.contract(project_id)
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/projects/{project_id}/download")
    def download(project_id: str, request: Request):
        user = _require_user(request, identities)
        _require_project(identities, user["id"], project_id)
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
        authorization = request.headers.get("authorization", "")
        raw_key = authorization[7:] if authorization.lower().startswith("bearer ") else None
        user = identities.api_key_user(raw_key)
        if not user:
            raise HTTPException(status_code=401, detail="Clé MCP absente, invalide ou révoquée.")
        _rate_limit(request, identities, "mcp", user["id"], 120, 60)
        message = await _json_body(request)
        needs_compiler = _is_compile_message(message)
        if needs_compiler and not compile_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="Les compilateurs sont occupés. Réessayez dans quelques instants.",
                headers={"Retry-After": "5"},
            )
        try:
            response = await run_in_threadpool(dispatcher.dispatch, message, user["id"])
        finally:
            if needs_compiler:
                compile_slots.release()
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


def _session_response(identities: IdentityStore, user: dict[str, str],
                      status_code: int = 200) -> JSONResponse:
    token = identities.create_session(user["id"])
    response = JSONResponse({"user": user}, status_code=status_code)
    response.set_cookie(
        "monl_session", token, max_age=30 * 24 * 3600, path="/",
        httponly=True, samesite="strict",
        secure=os.environ.get("MONL_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
    )
    return response


def _require_user(request: Request, identities: IdentityStore) -> dict[str, str]:
    user = identities.session_user(request.cookies.get("monl_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Connectez-vous pour continuer.")
    return user


def _require_project(identities: IdentityStore, user_id: str, project_id: str) -> None:
    if not identities.owns_project(user_id, project_id):
        # Même réponse pour un projet absent et celui d'un autre compte :
        # l'identifiant opaque ne devient pas un oracle d'existence.
        raise HTTPException(status_code=404, detail="Projet introuvable.")


def _client_ip(request: Request) -> str:
    if os.environ.get("MONL_TRUST_PROXY", "").lower() in {"1", "true", "yes"}:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, identities: IdentityStore, scope: str,
                subject: str, limit: int, window: int) -> None:
    retry = identities.consume_limit(scope, subject, limit=limit, window=window)
    if retry is not None:
        raise HTTPException(
            status_code=429,
            detail="Trop de requêtes. Réessayez plus tard.",
            headers={"Retry-After": str(retry)},
        )


def _is_compile_message(message: dict) -> bool:
    params = message.get("params")
    return (
        message.get("method") == "tools/call"
        and isinstance(params, dict)
        and params.get("name") == "monl_compile_backend"
    )


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
