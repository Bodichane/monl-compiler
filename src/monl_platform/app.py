from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
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
from .journal import anomalie, configurer, court, evenement, panne
from .landing import LANDING_HTML
from .legal import CONDITIONS_HTML, CONFIDENTIALITE_HTML, MENTIONS_HTML
from .mcp_page import MCP_HTML
from .mcp_server import MCPDispatcher
from .security import SECURITY_HTML
from .service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    PlatformNotFoundError,
)
from .theme import FAVICON, LOGO_SVG, page

WORDMARK = Path(__file__).with_name("static") / "monl-wordmark.png"

# Une page servie deux fois identique n'a pas besoin d'être reconstruite à
# chaque visite : le guide est du HTML pur, dérivé de constantes.
GUIDE_HTML = guide_html()


def _purger(service: CompilationService, identities: IdentityStore) -> int:
    """Efface les projets échus, en base ET sur le disque.

    Source unique : le démarrage et la boucle périodique appellent la même
    fonction. Deux copies auraient fini par diverger, et c'est le nettoyage
    qui aurait perdu.
    """
    efface = 0
    for expired_id in identities.expired_projects():
        try:
            service.delete(expired_id)
        except PlatformNotFoundError:
            pass
        efface += 1
    return efface


def create_app(*, workspace=None) -> FastAPI:
    configurer()
    service = CompilationService(workspace)
    identities = IdentityStore(service.workspace)
    sans_codes = identities.comptes_sans_codes()
    if sans_codes:
        # Les comptes antérieurs n'ont pas de codes : la migration additive
        # rattrape une table, jamais son contenu. Leur en fabriquer au
        # démarrage serait pire — il faudrait les leur montrer, et personne
        # ne les lirait. On les NOMME, la page du compte fait le reste.
        anomalie("comptes_sans_codes_de_secours", nombre=sans_codes)
    evenement("demarrage", workspace=str(service.workspace),
              purges=_purger(service, identities))

    @contextlib.asynccontextmanager
    async def _cycle_de_vie(_app):
        """La purge tourne TANT QUE le serveur tourne.

        Elle ne s'exécutait qu'au montage de l'application : sur un conteneur
        qui vit trois mois, `MONL_PROJECT_RETENTION_DAYS` n'était honoré
        qu'au redémarrage, donc jamais. Le fil vit dans le cycle de vie et non
        dans `create_app`, pour que construire l'application dans un test n'en
        démarre aucun.
        """
        arret = threading.Event()
        intervalle = max(1, int(os.environ.get("MONL_PURGE_INTERVAL_SECONDS", "3600")))

        def boucle():
            while not arret.wait(intervalle):
                try:
                    efface = _purger(service, identities)
                    if efface:
                        evenement("purge", projets=efface)
                except Exception as exc:
                    # Un ménage raté ne doit jamais tuer le serveur :
                    # on le NOMME et la boucle continue.
                    panne("purge_impossible", cause=type(exc).__name__)

        fil = threading.Thread(target=boucle, name="monl-purge", daemon=True)
        fil.start()
        try:
            yield
        finally:
            arret.set()
            fil.join(timeout=5)

    dispatcher = MCPDispatcher(service, identities)
    compile_slots = threading.BoundedSemaphore(
        max(1, int(os.environ.get("MONL_MAX_CONCURRENT_COMPILES", "2")))
    )
    application = FastAPI(
        lifespan=_cycle_de_vie,
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
    def mentions_legales():
        return MENTIONS_HTML

    @application.get("/conditions", response_class=HTMLResponse, include_in_schema=False)
    def conditions():
        return CONDITIONS_HTML

    @application.get("/confidentialite", response_class=HTMLResponse, include_in_schema=False)
    def confidentialite():
        return CONFIDENTIALITE_HTML

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

    @application.get("/brand/monl-wordmark.png", include_in_schema=False)
    def wordmark():
        return FileResponse(
            WORDMARK, media_type="image/png",
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
            anomalie("inscription_refusee", cause=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        codes = identities.create_recovery_codes(user["id"])
        evenement("compte_cree", compte=court(user["id"]))
        # Les codes ne sortent QU'ICI et à la régénération. Comme une clé
        # d'API, ils ne sont pas relisibles : seule leur empreinte est gardée.
        return _session_response(identities, user, status_code=201,
                                 extra={"recovery_codes": codes})

    @application.post("/api/auth/login")
    async def login(request: Request):
        _rate_limit(request, identities, "login", _client_ip(request), 5, 60)
        payload = await _json_body(request)
        user = identities.authenticate(payload.get("email"), payload.get("password"))
        if not user:
            # L'adresse essayée n'est pas journalisée : elle serait une donnée
            # personnelle dans un fichier que tout l'hébergement peut lire.
            anomalie("connexion_refusee", ip=_client_ip(request))
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
        evenement("connexion", compte=court(user["id"]))
        return _session_response(identities, user)

    @application.get("/api/auth/recovery-codes")
    def lister_codes(request: Request):
        user = _require_user(request, identities)
        return {"remaining": identities.count_recovery_codes(user["id"])}

    @application.post("/api/auth/recovery-codes", status_code=201)
    def regenerer_codes(request: Request):
        user = _require_user(request, identities)
        codes = identities.create_recovery_codes(user["id"])
        evenement("codes_regeneres", compte=court(user["id"]))
        return {"recovery_codes": codes}

    @application.post("/api/auth/recover", status_code=204)
    async def recuperer(request: Request):
        """Reprendre la main sur un compte dont le mot de passe est perdu.

        BORNÉE PAR L'ADRESSE IP, comme la connexion. Un code fait 16
        caractères tirés au sort, mais huit codes vivants par compte font huit
        chances par essai : sans plafond, la seule chose qui protégerait
        serait la patience de l'attaquant.

        Le refus est le MÊME pour un code faux, une adresse inconnue et un
        mot de passe trop court — 401 et rien d'autre. Distinguer apprendrait
        à un attaquant laquelle des trois il tient déjà.
        """
        _rate_limit(request, identities, "recover", _client_ip(request), 5, 3600)
        payload = await _json_body(request)
        user = identities.consume_recovery_code(
            payload.get("email"), payload.get("code"), payload.get("password"))
        if not user:
            anomalie("recuperation_refusee", ip=_client_ip(request))
            raise HTTPException(status_code=401,
                                detail="Code de secours invalide ou déjà utilisé.")
        evenement("compte_recupere", compte=court(user["id"]),
                  restants=identities.count_recovery_codes(user["id"]))
        return Response(status_code=204)

    @application.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        identities.revoke_session(request.cookies.get("monl_session"))
        response = Response(status_code=204)
        response.delete_cookie("monl_session", path="/", httponly=True, samesite="strict")
        return response

    @application.delete("/api/auth/account", status_code=204)
    async def delete_account(request: Request):
        """Efface le compte, ses clés, ses projets et leurs dossiers.

        **Le mot de passe est exigé à nouveau**, session valide ou non : une
        suppression irréversible ne doit pas tenir au seul fait qu'un onglet
        soit resté ouvert, ni pouvoir être déclenchée par une requête que
        l'utilisateur n'a pas voulue.

        Les dossiers sont retirés APRÈS l'effacement en base : si le disque
        résiste, le compte est déjà parti et le ménage se rattrape à la purge
        périodique — l'inverse laisserait un compte sans ses projets.
        """
        user = _require_user(request, identities)
        payload = await _json_body(request)
        if not identities.authenticate(user["email"], payload.get("password")):
            anomalie("suppression_compte_refusee", compte=court(user["id"]))
            raise HTTPException(status_code=403,
                                detail="Mot de passe incorrect : le compte n'a pas été supprimé.")
        projets = identities.delete_user(user["id"])
        for project_id in projets:
            with contextlib.suppress(PlatformNotFoundError):
                service.delete(project_id)
        evenement("compte_supprime", compte=court(user["id"]), projets=len(projets))
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
            cle = identities.create_api_key(user["id"], payload.get("name"))
            evenement("cle_creee", compte=court(user["id"]), cle=court(cle["id"]))
            return cle
        except IdentityError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.delete("/api/keys/{key_id}", status_code=204)
    def revoke_key(key_id: str, request: Request):
        user = _require_user(request, identities)
        if not identities.revoke_api_key(user["id"], key_id):
            raise HTTPException(status_code=404, detail="Clé introuvable.")
        evenement("cle_revoquee", compte=court(user["id"]), cle=court(key_id))
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
            evenement("compilation", compte=court(user["id"]), projet=court(manifest["id"]),
                      routes=len(manifest["summary"].get("routes", [])))
            return manifest
        except PlatformInputError as exc:
            anomalie("compilation_refusee", compte=court(user["id"]), cause=str(exc)[:120])
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
                      status_code: int = 200, extra: dict | None = None) -> JSONResponse:
    token = identities.create_session(user["id"])
    response = JSONResponse({"user": user, **(extra or {})}, status_code=status_code)
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
        # `sujet` n'est PAS journalisé : c'est une adresse IP ou un identifiant
        # de compte. La portée et l'attente suffisent à constater un abus.
        anomalie("debit_depasse", portee=scope, attente_s=retry)
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
