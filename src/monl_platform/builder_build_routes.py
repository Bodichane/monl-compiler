"""Compilation d'un projet de compte et cycle de vie de son API.

POINT 162. Ce module portait la file de constructions IA — mise en attente,
suivi d'étapes, historique et coût. Le constructeur retiré, il ne reste que
deux gestes, et ils sont déterministes : COMPILER la spec du projet dans son
dossier privé, puis DÉMARRER le backend obtenu pour l'essayer.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.concurrency import run_in_threadpool

from .builder_runtime import _ensure_builder_project, _http_error, _require_user
from .compilation import ProjectIsolationError, compiler_le_projet
from .hosting import SiteHostingError, SiteNotCompiledError
from .service import PlatformExecutionError, PlatformInputError


def mount_builder_build_routes(application, runtime):
    identities = runtime.identities

    @application.post("/api/projects/{project_id}/compiler", status_code=201)
    async def compile_into_project(project_id: str, request: Request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        try:
            resultat = await run_in_threadpool(
                compiler_le_projet,
                project["project_id"],
                account_id=user["id"],
                store=runtime.store,
                workspace_root=runtime.workspace_root,
                service=runtime.service,
            )
        except ProjectIsolationError as exc:
            _http_error(str(exc), 404)
        except PlatformInputError as exc:
            _http_error(str(exc), 422)
        except PlatformExecutionError as exc:
            _http_error(str(exc), 503)
        return {
            "project_id": resultat["project_id"],
            "files": resultat["files"],
            "routes": len(resultat["contract"].get("routes", [])),
        }

    def start_site(project_id, request):
        user = _require_user(request, identities)
        project = _ensure_builder_project(runtime, user, project_id)
        try:
            running = runtime.sites.start_project(project)
        except SiteNotCompiledError as exc:
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
