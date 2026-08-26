"""Routes HTTP du constructeur, montées sur les projets du socle.

Ce module ne possède ni registre de comptes ni mécanisme d'authentification.
Les projets viennent de ``IdentityStore`` et les sessions sont celles que
``app.py`` pose déjà sur le navigateur.  ``PlatformStore`` ne conserve que
les métadonnées propres à la construction et les constructions elles-mêmes.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from monl.app_templates import TEMPLATES

from .downloads import default_directory, list_artifacts, resolve_artifact
from .hosting import SiteHostingError, SiteManager, SiteNotBuiltError
from .oauth import (
    OAuthError,
    authorize_url,
    check_state,
    configured_providers,
    exchange_code,
    fetch_identity,
    make_state,
)
from .paths import ProjectPathError, project_directory
from .progress import PLANNED_STAGES, planned_remaining, read_stages
from .quota import TokenQuota
from .store import PlatformStore
from .worker import BuildWorker

OAUTH_STATE_SECRET_ENV = "MONL_PLATFORM_OAUTH_STATE_SECRET"


def _http_error(message, code):
    raise HTTPException(status_code=code, detail=message)


def _require_user(request: Request, identities):
    user = identities.session_user(request.cookies.get("monl_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Connectez-vous pour continuer.")
    return user


def _build_view(build):
    return {
        "id": build["id"],
        "state": build["state"],
        "error": build["error_message"],
        "error_message": build["error_message"],
        "warning_message": build["warning_message"],
        "run_id": build["run_id"],
        "tokens_consumed": build["tokens_consumed"],
        "total_tokens": build["total_tokens"],
        "input_tokens": build["input_tokens"],
        "output_tokens": build["output_tokens"],
        "cost": build["cost"],
        "currency": build["currency"],
        "price_status": build["price_status"],
        "created_at": build["created_at"],
        "started_at": build["started_at"],
        "finished_at": build["finished_at"],
        "snapshot_path": build["snapshot_path"],
        "snapshot_sha256": build["snapshot_sha256"],
        "snapshot_bytes": build["snapshot_bytes"],
    }


def _slug(name, project_id):
    """Déduit une adresse stable pour un projet créé par le socle."""
    value = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return value[:80] or f"projet-{project_id[:12]}"


def _identity_project(identities, user_id, project_id):
    for project in identities.projects(user_id):
        if project["project_id"] == project_id:
            return project
    return None


def _ensure_builder_project(runtime, user, project_id):
    """Rattache paresseusement un projet compilé au constructeur.

    ``/api/compile`` est la création de projet du socle.  Le constructeur ne
    crée donc jamais une seconde ligne métier : à la première route de build,
    il ajoute seulement ses métadonnées dans ``builder_projects`` et recopie
    la spec déjà publiée vers le dossier privé du compte.
    """
    identity_project = _identity_project(runtime.identities, user["id"], project_id)
    if identity_project is None:
        _http_error("Projet introuvable.", status.HTTP_404_NOT_FOUND)

    project = runtime.store.get_project_for_user(user["id"], project_id)
    if project is None:
        try:
            runtime.store.create_project(
                user["id"], project_id, _slug(identity_project["name"], project_id)
            )
        except (OSError, ValueError):
            _http_error("Le projet ne peut pas être préparé pour une construction.", 422)
        project = runtime.store.get_project_for_user(user["id"], project_id)

    try:
        private_dir = project_directory(
            runtime.workspace_root, user["id"], project_id, create=True
        )
    except ProjectPathError as exc:
        _http_error(str(exc), 422)

    spec_path = private_dir / "spec.ml"
    if not spec_path.is_file():
        source = Path(runtime.service.workspace) / project_id / "spec.ml"
        if not source.is_file():
            _http_error("La spécification du projet est introuvable.", 404)
        spec_path.write_bytes(source.read_bytes())
    return project


def _provider_catalogue():
    return [
        {
            "name": template["name"],
            "hint": template["hint"],
            "actors": list(template.get("actors", [])),
            "entities": sorted(template.get("entities", {})),
        }
        for template in TEMPLATES
    ]


def _set_session_cookie(response, token):
    response.set_cookie(
        "monl_session", token, max_age=30 * 24 * 3600, path="/",
        httponly=True, samesite="strict",
        secure=os.environ.get("MONL_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
    )


@dataclass
class BuilderRuntime:
    service: object
    identities: object
    store: PlatformStore
    quota: TokenQuota
    sites: SiteManager
    worker: BuildWorker
    workspace_root: Path
    downloads_dir: str | None
    start_worker: bool = True

    def start(self):
        if self.start_worker:
            self.worker.start()

    def stop(self):
        self.worker.stop(timeout=30)
        self.sites.stop_all()

    def remove_project(self, user_id, project_id):
        """Retire le dossier privé d'un projet précis, s'il existe."""
        try:
            directory = project_directory(
                self.workspace_root, user_id, project_id, create=False
            )
        except (ProjectPathError, FileNotFoundError):
            return
        if directory.is_dir():
            shutil.rmtree(directory)


def create_runtime(
    service,
    identities,
    *,
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
):
    """Construit les dépendances du constructeur sans monter de route."""
    store = PlatformStore(service.workspace)
    quota = TokenQuota(store, service.workspace, quota_limit)
    sites = SiteManager(
        store, service.workspace, domain or os.environ.get("MONL_PLATFORM_DOMAIN", "localhost")
    )
    worker = BuildWorker(
        store,
        service.workspace,
        quota,
        provider_factory=provider_factory,
        provider=provider,
        model_provider_factory=model_provider_factory,
        image_provider_factory=image_provider_factory,
        image_provider=image_provider,
        prices_path=prices_path,
        on_success=lambda project, _build: _restart_if_running(sites, project),
        poll_interval=poll_interval,
    )
    return BuilderRuntime(
        service=service,
        identities=identities,
        store=store,
        quota=quota,
        sites=sites,
        worker=worker,
        workspace_root=Path(service.workspace),
        downloads_dir=downloads_dir if downloads_dir is not None else default_directory(),
        start_worker=start_worker,
    )


def _restart_if_running(sites, project):
    if not sites.is_running(project["project_id"]):
        return
    sites.stop_project(project["project_id"])
    sites.start_project(project)


def mount_builder_routes(application, runtime):
    """Monte toutes les routes du constructeur et renvoie ``runtime``.

    Le retour OAuth pose le même cookie de session opaque que la connexion du
    socle ; il ne retourne jamais un jeton dans l'URL.
    """
    identities = runtime.identities

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

    @application.get("/auth/fournisseurs")
    def auth_providers():
        return {"providers": configured_providers()}

    @application.get("/auth/providers", include_in_schema=False)
    def auth_providers_alias():
        return auth_providers()

    @application.get("/auth/{provider}")
    def auth_start(provider: str):
        secret = os.environ.get("MONL_PLATFORM_OAUTH_STATE_SECRET", "").strip()
        if not secret:
            raise HTTPException(
                status_code=503,
                detail=f"connexion indisponible : la variable d'environnement "
                       f"{OAUTH_STATE_SECRET_ENV} n'est pas renseignée sur ce serveur",
            )
        try:
            state = make_state(provider, secret)
            target = authorize_url(provider, state)
        except OAuthError as exc:
            _http_error(str(exc), exc.status_code)
        return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @application.get("/auth/{provider}/retour")
    @application.get("/auth/{provider}/callback", include_in_schema=False)
    def auth_return(provider: str, code: str = "", state: str = "", error: str = ""):
        if error:
            return RedirectResponse("/console#erreur=refus", status_code=303)
        secret = os.environ.get("MONL_PLATFORM_OAUTH_STATE_SECRET", "").strip()
        if not secret:
            raise HTTPException(
                status_code=503,
                detail=f"connexion indisponible : la variable d'environnement "
                       f"{OAUTH_STATE_SECRET_ENV} n'est pas renseignée sur ce serveur",
            )
        try:
            check_state(state, provider, secret)
            if not code:
                raise OAuthError("le fournisseur n'a renvoyé aucun code", status_code=400)
            provider_token = exchange_code(provider, code)
            identifier, display_name = fetch_identity(provider, provider_token)
            user_id, _created = identities.upsert_oauth_account(
                identifier, provider, display_name
            )
        except (OAuthError, ValueError) as exc:
            code_status = getattr(exc, "status_code", 422)
            _http_error(str(exc), code_status)
        token = identities.create_session(user_id)
        response = RedirectResponse("/console", status_code=303)
        _set_session_cookie(response, token)
        return response

    @application.get("/api/models")
    def models():
        return {"models": _provider_catalogue()}

    @application.get("/api/usage")
    def usage(request: Request):
        user = _require_user(request, identities)
        try:
            current = runtime.quota.inspect(user["id"])
        except Exception as exc:
            _http_error(str(exc), 503)
        return {"usage": {
            "consumed_tokens": current.consumed_tokens,
            "limit_tokens": current.limit_tokens,
            "remaining_tokens": current.remaining_tokens,
            "project_totals": current.project_totals,
        }}

    @application.get("/api/telechargements")
    def downloads():
        return {"artifacts": list_artifacts(runtime.downloads_dir)}

    @application.get("/api/telechargements/{name}")
    def download(name: str):
        path = resolve_artifact(runtime.downloads_dir, name)
        if path is None:
            _http_error("artefact introuvable", 404)
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    @application.post("/api/projects/{project_id}/builds", status_code=202)
    def enqueue_build(project_id: str, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        try:
            build_id = runtime.store.create_build(project["project_id"])
        except (KeyError, ValueError):
            _http_error("Projet introuvable.", 404)
        return {"build": _build_view(runtime.store.get_build(build_id))}

    @application.post("/api/projects/{project_id}/build", status_code=202)
    def enqueue_build_alias(project_id: str, request: Request):
        return enqueue_build(project_id, request)

    @application.get("/api/projects/{project_id}/builds")
    def list_builds(project_id: str, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        return {"builds": [
            _build_view(item) for item in runtime.store.list_builds(project["project_id"])
        ]}

    @application.get("/api/projects/{project_id}/builds/{build_id}")
    def get_build(project_id: str, build_id: int, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        build = runtime.store.get_build_for_project(project["project_id"], build_id)
        if build is None:
            _http_error("Construction introuvable.", 404)
        return {"build": _build_view(build)}

    @application.get("/api/projects/{project_id}/builds/{build_id}/etapes")
    def build_stages(project_id: str, build_id: int, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        build = runtime.store.get_build_for_project(project["project_id"], build_id)
        if build is None:
            _http_error("Construction introuvable.", 404)
        try:
            directory = project_directory(
                runtime.workspace_root, project["user_id"], project["project_id"], create=False
            )
        except ProjectPathError:
            return {"stages": [], "remaining": list(PLANNED_STAGES)}
        stages = read_stages(directory, build["started_at"], build["finished_at"])
        return {
            "stages": stages,
            "remaining": planned_remaining(stages)
            if build["state"] in {"en_attente", "en_cours"} else [],
        }

    def start_site(project_id, request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        try:
            running = runtime.sites.start_project(project)
        except SiteNotBuiltError as exc:
            _http_error(str(exc), 409)
        except SiteHostingError as exc:
            _http_error(str(exc), 503)
        return {"host": running.host, "port": running.port, "pid": running.process.pid}

    @application.post("/api/projects/{project_id}/start")
    def start(project_id: str, request: Request):
        return start_site(project_id, request)

    @application.post("/api/projects/{project_id}/serve")
    def serve(project_id: str, request: Request):
        return start_site(project_id, request)

    @application.post("/api/projects/{project_id}/stop")
    def stop(project_id: str, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        return {"stopped": runtime.sites.stop_project(project["project_id"])}

    return runtime
