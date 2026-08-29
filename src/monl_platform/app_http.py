"""Shared HTTP helpers for the platform application."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .identity import IdentityStore
from .journal import anomalie
from .theme import page


def _liens_de_pied(brut):
    """Normalise les liens déclarés par la console, sans deviner les autres."""
    from monl.dialogue_engine import adresse_de_lien

    liens, vus = [], set()
    for entree in brut or []:
        if not isinstance(entree, dict):
            continue
        label = str(entree.get("label") or "").strip()
        adresse = adresse_de_lien(str(entree.get("url") or ""))
        cle = label.casefold()
        if not label or '"' in label or not adresse or cle in vus:
            continue
        vus.add(cle)
        liens.append({"label": label, "url": adresse})
    return liens

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


def _cle_mcp(request: Request) -> str | None:
    """La clé portée par l'en-tête ``Authorization: Bearer …``, ou rien."""
    autorisation = request.headers.get("authorization", "")
    if not autorisation.lower().startswith("bearer "):
        return None
    return autorisation[7:].strip() or None


def _require_user_ou_cle(request: Request, identities: IdentityStore) -> dict[str, str]:
    """La session du navigateur OU une clé MCP.

    POINT 161. Récupérer son archive était la SEULE chose qu'un agent ne
    pouvait pas faire sans ouvrir un navigateur — exactement le passage que le
    cap veut supprimer. Ce n'est pas une seconde porte : c'est le MÊME chemin
    d'authentification que ``/mcp`` (``api_key_user``), avec le même contrôle
    de propriété derrière (``_require_project``). Le renversement à comprendre :
    une clé MCP identifie un COMPTE, pas une capacité — lui refuser ce que la
    session du même compte obtient n'était pas une protection, seulement une
    dépendance au navigateur.

    La session est essayée en PREMIER : dans un navigateur, un en-tête
    ``Authorization`` traînant ne doit jamais l'emporter sur qui est connecté.
    """
    user = identities.session_user(request.cookies.get("monl_session"))
    if user:
        return user
    cle = _cle_mcp(request)
    if cle:
        user = identities.api_key_user(cle)
        if user:
            return user
    raise HTTPException(
        status_code=401,
        detail="Connectez-vous, ou fournissez une clé MCP en en-tête Authorization.",
    )


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


#: Les outils MCP qui font tourner le COMPILATEUR, donc qui doivent prendre
#: une place au sémaphore de `MONL_MAX_CONCURRENT_COMPILES`. POINT 161 : le
#: diff et la mise à jour compilent eux aussi (dans un dossier jetable pour le
#: premier, dans le projet pour le second) — les oublier ici laisserait la
#: borne de concurrence intacte à la lecture et contournée à l'exécution.
OUTILS_QUI_COMPILENT = frozenset({
    "monl_compile_backend", "monl_diff_spec", "monl_update_backend",
})


def _is_compile_message(message: dict) -> bool:
    params = message.get("params")
    return (
        message.get("method") == "tools/call"
        and isinstance(params, dict)
        and params.get("name") in OUTILS_QUI_COMPILENT
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


def mount_error_handler(application):
    @application.exception_handler(404)
    async def introuvable(request: Request, exc: HTTPException):
        # Un visiteur reçoit une page, un client d'API reçoit du JSON. Servir
        # du HTML à curl rendrait l'erreur illisible là où elle doit être lue.
        detail = getattr(exc, "detail", "Introuvable.")
        if _veut_du_json(request):
            return JSONResponse({"detail": detail}, status_code=404)
        return HTMLResponse(_page_404(detail), status_code=404)

