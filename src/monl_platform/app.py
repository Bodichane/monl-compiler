from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .console import CONSOLE_HTML
from .mcp_server import MCPDispatcher
from .service import CompilationService, PlatformInputError, PlatformNotFoundError


def create_app(*, workspace=None) -> FastAPI:
    service = CompilationService(workspace)
    dispatcher = MCPDispatcher(service)
    application = FastAPI(
        title="Monl Compiler Platform",
        description="Validation et compilation distante de backends Monl.",
        version="0.1.0",
    )
    application.state.compilation_service = service

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def console():
        return CONSOLE_HTML

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "monl-compiler"}

    @application.get("/api/templates")
    def templates():
        return {"templates": service.list_templates()}

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

    return application


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
