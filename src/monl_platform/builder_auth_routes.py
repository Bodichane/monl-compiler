"""Authentication, model catalogue and download routes for the builder."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from .builder_runtime import (
    _http_error,
    _provider_catalogue,
    _require_user,
    _set_session_cookie,
)
from .downloads import list_artifacts, resolve_artifact
from .oauth import (
    OAuthError,
    authorize_url,
    check_state,
    configured_providers,
    exchange_code,
    fetch_identity,
    make_state,
)

OAUTH_STATE_SECRET_ENV = "MONL_PLATFORM_OAUTH_STATE_SECRET"


def mount_builder_auth_routes(application, runtime):
    identities = runtime.identities
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
