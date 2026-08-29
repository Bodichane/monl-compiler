"""Authenticated API routes for the platform core."""

from __future__ import annotations

import contextlib

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from .app_http import (
    _client_ip,
    _is_compile_message,
    _json_body,
    _rate_limit,
    _require_project,
    _require_user,
    _require_user_ou_cle,
    _session_response,
)
from .identity import IdentityError, IdentityStore
from .journal import anomalie, court, evenement
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
            builder_runtime.remove_project(user["id"], project_id)
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
        builder_runtime.remove_project(user["id"], project_id)
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
        user = _require_user_ou_cle(request, identities)
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

