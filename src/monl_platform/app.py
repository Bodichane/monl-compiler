"""Service HTTP de la plateforme monl."""

import os
import sqlite3
import time
import urllib.parse
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from monl.app_templates import TEMPLATES
from monl.dialogue_engine import DialogueError

from .app_templates import materialize_template
from .console import console_response
from .downloads import default_directory, list_artifacts, resolve_artifact
from .hosting import SiteHostingError, SiteManager, SiteNotBuiltError
from .landing import landing_response
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


def _champ(account, nom):
    """Lit une colonne qui peut manquer d'une ligne ancienne.

    Les colonnes du point 142 sont ajoutées de façon ADDITIVE : une base
    créée avant elles les gagne au démarrage, mais un appelant peut fort
    bien passer un dictionnaire construit ailleurs.
    """
    try:
        return account[nom]
    except (KeyError, IndexError):
        return None


def _without_secret(account):
    # La liste est BLANCHE et le reste : c'est elle qui empêche
    # `password_hash` de sortir, pas une exclusion qu'on penserait à mettre à
    # jour. Le nom d'affichage est l'adresse VÉRIFIÉE que le fournisseur a
    # confirmée — sans lui, la console n'a que « github:4242 » à montrer.
    return {
        "id": account["id"],
        "identifier": account["identifier"],
        "created_at": account["created_at"],
        "display_name": _champ(account, "display_name"),
        "oauth_provider": _champ(account, "oauth_provider"),
    }


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


def _project_view(store, project, sites=None):
    builds = [_build_view(build) for build in store.list_builds(project["id"])]
    latest = builds[-1] if builds else None
    return {
        "id": project["id"],
        "slug": project["slug"],
        "created_at": project["created_at"],
        "model_routes": project.get("model_routes", {}),
        "generate_images": bool(project.get("generate_images", False)),
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
    model_provider_factory=None,
    image_provider_factory=None,
    image_provider=None,
    prices_path=None,
    downloads_dir=None,
    poll_interval=0.05,
    start_worker=True,
):
    """Construit l'application, avec toutes ses dépendances injectables."""
    database = database or os.environ.get("MONL_PLATFORM_DATABASE", "platform.db")
    workspace_root = workspace_root or os.environ.get(
        "MONL_PLATFORM_WORKSPACE", "platform-projects"
    )
    domain = domain or os.environ.get("MONL_PLATFORM_DOMAIN", "localhost")
    downloads_dir = downloads_dir or default_directory()
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
        # Ne consommer un processus que pour un site explicitement servi. Si
        # le projet était déjà ouvert, le relancer lui fait adopter le snapshot
        # qui vient d'être publié ; sinon, le premier accès au sous-domaine ou
        # POST /start le lancera à la demande.
        if not sites.is_running(project["id"]):
            return
        sites.stop_project(project["id"])
        sites.start_project(project)

    worker = BuildWorker(
        store,
        workspace_root,
        quota,
        provider_factory=provider_factory,
        provider=provider,
        model_provider_factory=model_provider_factory,
        image_provider_factory=image_provider_factory,
        image_provider=image_provider,
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
    def landing():
        return landing_response()

    @application.get("/console")
    def console():
        return console_response()

    @application.get("/telechargements")
    @application.get("/downloads", include_in_schema=False)
    def downloads():
        """Ce que le serveur peut RÉELLEMENT livrer, mesuré sur le disque."""
        return {"artifacts": list_artifacts(downloads_dir)}

    @application.get("/telechargements/{name}")
    @application.get("/downloads/{name}", include_in_schema=False)
    def download(name: str):
        path = resolve_artifact(downloads_dir, name)
        if path is None:
            _http_error("artefact introuvable", status.HTTP_404_NOT_FOUND)
        return FileResponse(
            path, media_type="application/octet-stream", filename=path.name)

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

    # ─────────────────────────────────────────── connexion par fournisseur ──
    # La plateforme dépense de l'argent réel à chaque construction : un compte
    # ouvert avec une chaîne quelconque est une porte d'abus. Elle n'envoie
    # pour autant AUCUN message — la frontière du point 95 tient — elle
    # délègue à un fournisseur qui, lui, a déjà vérifié l'adresse.
    @application.get("/auth/fournisseurs")
    @application.get("/auth/providers", include_in_schema=False)
    def auth_providers():
        """Ceux qui sont RÉELLEMENT configurés.

        Un bouton qui mène à un 503 est pire que pas de bouton.
        """
        return {"providers": configured_providers()}

    @application.get("/auth/{provider}")
    def auth_start(provider: str):
        try:
            state = make_state(provider, jwt_secret)
            cible = authorize_url(provider, state)
        except OAuthError as exc:
            _http_error(str(exc), exc.status_code)
        return RedirectResponse(cible, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @application.get("/auth/{provider}/retour")
    @application.get("/auth/{provider}/callback", include_in_schema=False)
    def auth_return(provider: str, code: str = "", state: str = "",
                    error: str = ""):
        if error:
            # L'usager a refusé l'autorisation : ce n'est pas une panne.
            return RedirectResponse("/console#erreur=refus",
                                    status_code=status.HTTP_303_SEE_OTHER)
        try:
            check_state(state, provider, jwt_secret)
            if not code:
                raise OAuthError("le fournisseur n'a renvoyé aucun code",
                                 status_code=400)
            jeton_fournisseur = exchange_code(provider, code)
            identifiant, libelle = fetch_identity(provider, jeton_fournisseur)
        except OAuthError as exc:
            _http_error(str(exc), exc.status_code)
        account_id, _neuf = store.upsert_oauth_account(identifiant, provider, libelle)
        # Le jeton part dans le FRAGMENT et non dans la requête : un fragment
        # n'est jamais envoyé au serveur, donc jamais journalisé par un relais.
        return RedirectResponse(
            "/console#jeton=" + urllib.parse.quote(issue_token(account_id)),
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
            except (ValueError, StopIteration, DialogueError) as exc:
                _http_error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        if not isinstance(spec, str) or not spec.strip():
            _http_error("la spec doit être un texte non vide", status.HTTP_422_UNPROCESSABLE_ENTITY)
        generate_images = data.get("generate_images", False)
        if not isinstance(generate_images, bool):
            _http_error(
                "generate_images doit être un booléen explicite",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        model_routes = data.get("model_routes", {})
        if store.list_projects_by_slug(slug):
            _http_error("ce slug est déjà utilisé", status.HTTP_409_CONFLICT)
        project_id = None
        try:
            project_id = store.create_project(
                account["id"],
                slug,
                model_routes=model_routes,
                generate_images=generate_images,
            )
            directory = project_directory(
                workspace_root, account["id"], project_id, create=True
            )
            directory.joinpath("spec.ml").write_text(spec, encoding="utf-8")
        except (sqlite3.IntegrityError, OSError, ProjectPathError, ValueError) as exc:
            # La ligne SQLite n'est utile qu'avec sa spec. Une erreur disque ou
            # de confinement juste après l'insertion ne doit ni bloquer le
            # slug, ni laisser un projet impossible à construire.
            if project_id is not None:
                store.discard_project(account["id"], project_id)
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

    @application.get("/projects/{project_id}/builds/{build_id}/etapes")
    def build_stages(project_id: int, build_id: int, account= current_account):
        """Étapes RÉELLEMENT journalisées, y compris pendant la construction.

        Le suivi de la console s'appuie là-dessus plutôt que sur une
        progression inventée : chaque ligne correspond à un appel qui a
        vraiment rendu, avec sa durée et ses jetons.
        """
        project = owned_project(account, project_id)
        build = store.get_build_for_project(project["id"], build_id)
        if build is None:
            _http_error("construction introuvable", status.HTTP_404_NOT_FOUND)
        try:
            directory = project_directory(
                workspace_root, project["account_id"], project["id"]
            )
        except ProjectPathError:
            return {"stages": [], "remaining": list(PLANNED_STAGES)}
        stages = read_stages(directory, build["started_at"], build["finished_at"])
        return {
            "stages": stages,
            "remaining": planned_remaining(stages) if build["state"] in {
                "en_attente", "en_cours"} else [],
        }

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
