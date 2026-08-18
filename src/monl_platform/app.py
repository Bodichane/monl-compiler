"""Service HTTP de la plateforme monl."""

import os
import sqlite3
import time
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from monl.app_templates import TEMPLATES

from .app_templates import materialize_template
from .console import console_response
from .hosting import SiteHostingError, SiteManager, SiteNotBuiltError
from .paths import ProjectPathError, project_directory
from .quota import TokenQuota
from .store import PlatformStore
from .worker import BuildWorker


class Credentials(BaseModel):
    identifier: str | None = None
    username: str | None = None
    password: str


def _catalogue():
    return [
        {
            "name": template["name"],
            "hint": template["hint"],
            "actors": list(template.get("actors", [])),
            "entities": sorted(template.get("entities", {})),
        }
        for template in TEMPLATES
    ]


def _without_secret(account):
    return {
        "id": account["id"],
        "identifier": account["identifier"],
        "created_at": account["created_at"],
    }


def _build_view(build):
    return {
        "id": build["id"],
        "state": build["state"],
        "error": build["error_message"],
        "error_message": build["error_message"],
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
    }


def _project_view(store, project, sites=None):
    builds = [_build_view(build) for build in store.list_builds(project["id"])]
    latest = builds[-1] if builds else None
    return {
        "id": project["id"],
        "slug": project["slug"],
        "created_at": project["created_at"],
        "state": latest["state"] if latest else "pas_de_construction",
        "host": sites.host_for(project) if sites is not None else None,
        "running": sites.is_running(project["id"]) if sites is not None else False,
        "builds": builds,
    }


def _http_error(message, code):
    raise HTTPException(status_code=code, detail=message)


def create_app(
    *,
    database=None,
    workspace_root=None,
    domain=None,
    jwt_secret=None,
    quota_limit=1_000_000,
    provider_factory=None,
    provider=None,
    prices_path=None,
    poll_interval=0.05,
    start_worker=True,
):
    """Construit l'application, avec toutes ses dépendances injectables."""
    database = database or os.environ.get("MONL_PLATFORM_DATABASE", "platform.db")
    workspace_root = workspace_root or os.environ.get(
        "MONL_PLATFORM_WORKSPACE", "platform-projects"
    )
    domain = domain or os.environ.get("MONL_PLATFORM_DOMAIN", "localhost")
    jwt_secret = jwt_secret or os.environ.get("MONL_PLATFORM_JWT_SECRET")
    if not jwt_secret:
        raise ValueError(
            "MONL_PLATFORM_JWT_SECRET absent de l'environnement — "
            "le secret est obligatoire et n'est jamais généré automatiquement"
        )
    if not isinstance(jwt_secret, str) or len(jwt_secret) < 16:
        raise ValueError("jwt_secret doit contenir au moins 16 caractères")

    store = PlatformStore(database)
    quota = TokenQuota(store, workspace_root, quota_limit)
    sites = SiteManager(store, workspace_root, domain)

    def on_build_success(project, _build):
        sites.start_project(project)

    worker = BuildWorker(
        store,
        workspace_root,
        quota,
        provider_factory=provider_factory,
        provider=provider,
        prices_path=prices_path,
        on_success=on_build_success,
        poll_interval=poll_interval,
    )
    application = FastAPI(title="monl platform", lifespan=None)
    application.state.store = store
    application.state.quota = quota
    application.state.sites = sites
    application.state.worker = worker

    def account_from_request(request: Request):
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            _http_error("authentification requise", status.HTTP_401_UNAUTHORIZED)
        try:
            payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            account_id = int(payload["sub"])
            account = store.get_account(account_id)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            _http_error("jeton invalide", status.HTTP_401_UNAUTHORIZED)
        return account

    current_account = Depends(account_from_request)

    def issue_token(account_id):
        now = int(time.time())
        return jwt.encode(
            {"sub": str(account_id), "iat": now, "exp": now + 24 * 3600},
            jwt_secret,
            algorithm="HS256",
        )

    @application.middleware("http")
    async def route_by_host(request, call_next):
        try:
            running = sites.target_for_host(request.headers.get("host"))
        except SiteNotBuiltError as exc:
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
        except SiteHostingError as exc:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})
        if running is None:
            return await call_next(request)
        body = await request.body()
        raw_path = request.scope.get("raw_path", b"/").decode("latin-1")
        query = request.scope.get("query_string", b"").decode("latin-1")
        target = raw_path + ("?" + query if query else "")
        try:
            return await run_in_threadpool(
                sites.forward,
                running,
                request.method,
                target,
                dict(request.headers),
                body,
            )
        except SiteHostingError as exc:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})

    @asynccontextmanager
    async def lifespan(_application):
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            stopped = worker.stop(timeout=30)
            sites.stop_all()
            if stopped:
                store.close()

    application.router.lifespan_context = lifespan

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/")
    def console():
        return console_response()

    @application.post("/register", status_code=status.HTTP_201_CREATED)
    @application.post("/auth/register", status_code=status.HTTP_201_CREATED, include_in_schema=False)
    def register(credentials: Credentials):
        identifier = (credentials.identifier or credentials.username or "").strip()
        if not identifier:
            _http_error("identifier requis", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if len(credentials.password) < 8:
            _http_error("le mot de passe doit contenir au moins 8 caractères", status.HTTP_422_UNPROCESSABLE_ENTITY)
        try:
            account_id = store.create_account(identifier, credentials.password)
            account = store.get_account(account_id)
        except sqlite3.IntegrityError:
            _http_error("ce compte existe déjà", status.HTTP_409_CONFLICT)
        return {"account": _without_secret(account), "token": issue_token(account_id)}

    @application.post("/login")
    @application.post("/auth/login", include_in_schema=False)
    def login(credentials: Credentials):
        identifier = credentials.identifier or credentials.username or ""
        account_id = store.authenticate_account(identifier, credentials.password)
        if account_id is None:
            _http_error("identifiants invalides", status.HTTP_401_UNAUTHORIZED)
        account = store.get_account(account_id)
        return {"account": _without_secret(account), "token": issue_token(account_id)}

    @application.get("/account")
    def account(account=current_account):
        return {"account": _without_secret(account)}

    @application.get("/usage")
    def usage(account=current_account):
        try:
            current = quota.inspect(account["id"])
        except Exception as exc:
            _http_error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        return {
            "usage": {
                "consumed_tokens": current.consumed_tokens,
                "limit_tokens": current.limit_tokens,
                "remaining_tokens": current.remaining_tokens,
                "project_totals": current.project_totals,
            }
        }

    @application.get("/catalogue")
    @application.get("/models", include_in_schema=False)
    def catalogue():
        return {"models": _catalogue()}

    async def project_payload(request):
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            data = {key: value for key, value in form.items() if key not in {"spec", "file"}}
            upload = form.get("spec") or form.get("file")
            if upload is not None and hasattr(upload, "read"):
                if getattr(upload, "filename", "").lower().endswith(".ml") is False:
                    _http_error("la spec fournie doit être un fichier .ml", status.HTTP_422_UNPROCESSABLE_ENTITY)
                data["spec"] = (await upload.read()).decode("utf-8")
            elif upload is not None:
                data["spec"] = str(upload)
            return data
        try:
            data = await request.json()
        except ValueError:
            _http_error("corps JSON invalide", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if not isinstance(data, dict):
            _http_error("le corps doit être un objet", status.HTTP_422_UNPROCESSABLE_ENTITY)
        return data

    @application.post("/projects", status_code=status.HTTP_201_CREATED)
    async def create_project(request: Request, account= current_account):
        data = await project_payload(request)
        slug = str(data.get("slug", "")).strip()
        if not slug:
            _http_error("slug requis", status.HTTP_422_UNPROCESSABLE_ENTITY)
        spec = data.get("spec") or data.get("spec_ml")
        model = data.get("model") or data.get("template")
        if bool(spec) == bool(model):
            _http_error("fournir exactement un modèle ou une spec", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if model:
            try:
                spec = materialize_template(
                    model,
                    app_name=data.get("app_name", "MonProjet"),
                    description=data.get("description"),
                )
            except (ValueError, StopIteration) as exc:
                _http_error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        if not isinstance(spec, str) or not spec.strip():
            _http_error("la spec doit être un texte non vide", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if store.list_projects_by_slug(slug):
            _http_error("ce slug est déjà utilisé", status.HTTP_409_CONFLICT)
        try:
            project_id = store.create_project(account["id"], slug)
            directory = project_directory(
                workspace_root, account["id"], project_id, create=True
            )
            directory.joinpath("spec.ml").write_text(spec, encoding="utf-8")
        except (sqlite3.IntegrityError, ProjectPathError, ValueError) as exc:
            _http_error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        project = store.get_project_for_account(account["id"], project_id)
        return {"project": _project_view(store, project, sites)}

    def owned_project(account, project_id):
        try:
            project = store.get_project_for_account(account["id"], project_id)
        except KeyError:
            project = None
        if project is None:
            _http_error("projet introuvable", status.HTTP_404_NOT_FOUND)
        return project

    @application.get("/projects")
    def list_projects(account= current_account):
        return {
            "projects": [
                _project_view(store, item, sites)
                for item in store.list_projects(account["id"])
            ]
        }

    @application.get("/projects/{project_id}")
    def get_project(project_id: int, account= current_account):
        return {"project": _project_view(store, owned_project(account, project_id), sites)}

    @application.post("/projects/{project_id}/builds", status_code=status.HTTP_202_ACCEPTED)
    @application.post("/projects/{project_id}/build", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
    def enqueue_build(project_id: int, account= current_account):
        project = owned_project(account, project_id)
        try:
            build_id = store.create_build(project["id"])
        except (KeyError, ValueError):
            _http_error("projet introuvable", status.HTTP_404_NOT_FOUND)
        return {"build": _build_view(store.get_build(build_id))}

    @application.get("/projects/{project_id}/builds")
    def list_builds(project_id: int, account= current_account):
        project = owned_project(account, project_id)
        return {"builds": [_build_view(item) for item in store.list_builds(project["id"])]}

    @application.get("/projects/{project_id}/builds/{build_id}")
    def get_build(project_id: int, build_id: int, account= current_account):
        project = owned_project(account, project_id)
        build = store.get_build_for_project(project["id"], build_id)
        if build is None:
            _http_error("construction introuvable", status.HTTP_404_NOT_FOUND)
        return {"build": _build_view(build)}

    def start_site(project_id, account):
        project = owned_project(account, project_id)
        try:
            running = sites.start_project(project)
        except SiteNotBuiltError as exc:
            _http_error(str(exc), status.HTTP_409_CONFLICT)
        except SiteHostingError as exc:
            _http_error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        return {"host": running.host, "port": running.port, "pid": running.process.pid}

    @application.post("/projects/{project_id}/start")
    @application.post("/projects/{project_id}/serve", include_in_schema=False)
    def start(project_id: int, account= current_account):
        return start_site(project_id, account)

    @application.post("/projects/{project_id}/stop")
    def stop(project_id: int, account= current_account):
        project = owned_project(account, project_id)
        return {"stopped": sites.stop_project(project["id"])}

    return application


# La plateforme est lancée par ``python -m monl_platform``. Ne pas construire
# une application ici : cela ouvrirait une base et créerait une configuration
# implicite lors de l'import du module.
app = None
