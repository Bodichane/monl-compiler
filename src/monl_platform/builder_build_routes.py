"""Build queue, progress and site lifecycle routes."""

from __future__ import annotations

from fastapi import Request

from .builder_runtime import (
    _build_view,
    _ensure_builder_project,
    _http_error,
    _require_user,
)
from .hosting import SiteHostingError, SiteNotBuiltError
from .paths import ProjectPathError, project_directory
from .progress import PLANNED_STAGES, planned_remaining, read_stages


def mount_builder_build_routes(application, runtime):
    identities = runtime.identities
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


