"""Authenticated API routes for the platform core."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from . import deletion
from .account_deletion import check_deletion
from .app_http import (
    _admission_compilation,
    _client_ip,
    _is_compile_message,
    _json_body,
    _rate_limit,
    _require_project,
    _require_user,
    _require_user_ou_key,
    _session_response,
)
from .dialogue import DialogueInputError, bounded_answer, bounded_answers, submit
from .identity import IdentityError, IdentityStore
from .log import anomaly, event, short
from .mcp_server import MCPDispatcher
from .service import PlatformExecutionError, PlatformInputError, PlatformNotFoundError


def mount_api_routes(
    application, service, identities: IdentityStore, builder_runtime,
    dispatcher: MCPDispatcher, compile_slots,
):
    @application.post("/api/auth/register", status_code=201)
    async def register(request: Request):
        _rate_limit(request, identities, "register", _client_ip(request), 5, 60)
        payload = await _json_body(request)
        try:
            user = identities.register(payload.get("email"), payload.get("password"))
        except IdentityError as exc:
            anomaly("inscription_refusee", cause=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        codes = identities.create_recovery_codes(user["id"])
        event("compte_cree", compte=short(user["id"]))
        # The codes come out ONLY here and on regeneration. Like an API key,
        # they cannot be read back: only their fingerprint is kept.
        return _session_response(identities, user, status_code=201,
                                 extra={"recovery_codes": codes})

    @application.post("/api/auth/login")
    async def login(request: Request):
        _rate_limit(request, identities, "login", _client_ip(request), 5, 60)
        payload = await _json_body(request)
        user = identities.authenticate(payload.get("email"), payload.get("password"))
        if not user:
            # The address tried is not logged: it would be personal data in a
            # file the whole hosting can read.
            anomaly("connexion_refusee", ip=_client_ip(request))
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        event("connexion", compte=short(user["id"]))
        return _session_response(identities, user)

    @application.get("/api/auth/recovery-codes")
    def lister_codes(request: Request):
        user = _require_user(request, identities)
        return {"remaining": identities.count_recovery_codes(user["id"])}

    @application.post("/api/auth/recovery-codes", status_code=201)
    async def regenerate_codes(request: Request):
        user = _require_user(request, identities)
        _rate_limit(request, identities, "regenerer_codes", user["id"], 5, 60)
        payload = await _json_body(request)
        if not identities.authenticate(user["email"], payload.get("password")):
            raise HTTPException(status_code=403,
                                detail="Incorrect password: the codes were not regenerated. OAuth accounts cannot regenerate codes.")
        codes = identities.create_recovery_codes(
            user["id"], session=request.cookies.get("monl_session"))
        event("codes_regeneres", compte=short(user["id"]))
        return {"recovery_codes": codes}

    @application.post("/api/auth/recover", status_code=204)
    async def recover(request: Request):
        """Taking back control of an account whose password is lost.

        BOUNDED BY IP ADDRESS, like login. A code is 16 random characters, but
        eight live codes per account make eight chances per attempt: without a
        ceiling, the only thing protecting it would be the attacker's patience.

        The refusal is the SAME for a wrong code, an unknown address and a
        password that is too short — 401 and nothing else. Telling them apart
        would teach an attacker which of the three they already have."""
        _rate_limit(request, identities, "recover", _client_ip(request), 5, 3600)
        payload = await _json_body(request)
        user = identities.consume_recovery_code(
            payload.get("email"), payload.get("code"), payload.get("password"))
        if not user:
            anomaly("recuperation_refusee", ip=_client_ip(request))
            raise HTTPException(status_code=401,
                                detail="Invalid or already used recovery code.")
        event("compte_recupere", compte=short(user["id"]),
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
        user = _require_user(request, identities)
        payload = await _json_body(request)
        check_deletion(identities, user, request.cookies.get("monl_session"), payload)
        projects = deletion.delete_account(builder_runtime, user["id"])
        event("compte_supprime", compte=short(user["id"]), projets=len(projects))
        response = Response(status_code=204)
        response.delete_cookie("monl_session", path="/", httponly=True, samesite="strict")
        return response

    @application.get("/api/auth/me")
    def me(request: Request):
        user = _require_user(request, identities)
        proof = identities.session_proof(request.cookies.get("monl_session"))
        return {**user, "auth_provider": proof["auth_provider"] if proof else None}

    @application.get("/api/projects")
    def list_projects(request: Request):
        user = _require_user(request, identities)
        return {"projects": identities.projects(user["id"])}

    @application.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str, request: Request):
        user = _require_user(request, identities)
        _require_project(identities, user["id"], project_id)
        deletion.delete_project(builder_runtime, user["id"], project_id)
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
            key = await run_in_threadpool(
                identities.create_api_key, user["id"], payload.get("name"),
                session=request.cookies.get("monl_session"))
            event("cle_creee", compte=short(user["id"]), cle=short(key["id"]))
            return key
        except IdentityError as exc:
            _require_user(request, identities)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.delete("/api/keys/{key_id}", status_code=204)
    def revoke_key(key_id: str, request: Request):
        user = _require_user(request, identities)
        if not identities.revoke_api_key(user["id"], key_id):
            raise HTTPException(status_code=404, detail="Key not found.")
        event("cle_revoquee", compte=short(user["id"]), cle=short(key_id))
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

    @application.post("/api/dialogue")
    async def dialogue(request: Request):
        """Replays the guided dialogue up to the next question.

        The complete list comes from the browser on every call; it is never
        persisted by the platform. The dialogue stays the only place that knows
        how to validate the answers and build the DSL.

        The response carries ``answers``: the AUTHORITATIVE list, the one the
        browser must adopt as is. A refused answer does not enter it — otherwise
        it would burn one of the engine's three attempts and three typos would
        kill the dialogue (see ``soumettre``)."""
        user = _require_user(request, identities)
        _rate_limit(request, identities, "dialogue", user["id"], 120, 60)
        payload = await _json_body(request)
        try:
            answers = bounded_answers(payload.get("answers"))
            candidate = bounded_answer(payload.get("answer"))
            return await run_in_threadpool(submit, answers, candidate)
        except DialogueInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/compile", status_code=201)
    async def compile_backend(request: Request):
        user = _require_user(request, identities)
        async with _admission_compilation(
            request, identities, compile_slots, lambda: _json_body(request)
        ) as payload:
            try:
                manifest = await run_in_threadpool(
                    service.compile, payload.get("spec"), account_id=user["id"]
                )
                identities.add_project(user["id"], manifest["id"], manifest["summary"]["app"])
                event("compilation", compte=short(user["id"]), projet=short(manifest["id"]),
                          routes=len(manifest["summary"].get("routes", [])))
                return manifest
            except PlatformInputError as exc:
                anomaly("compilation_refusee", compte=short(user["id"]), cause=str(exc)[:120])
                raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        user = _require_user_ou_key(request, identities)
        _rate_limit(request, identities, "download", user["id"], 30, 60)
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
            raise HTTPException(status_code=401, detail="MCP key missing, invalid or revoked.")
        _rate_limit(request, identities, "mcp", user["id"], 120, 60)
        message = await _json_body(request)
        needs_compiler = _is_compile_message(message)
        if needs_compiler and not compile_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=503,
                detail="The compilers are busy. Try again in a moment.",
                headers={"Retry-After": "5"},
            )
        try:
            response = await run_in_threadpool(dispatcher.dispatch, message, user["id"])
        finally:
            if needs_compiler:
                compile_slots.release()
        return JSONResponse(response or {}, status_code=200)
