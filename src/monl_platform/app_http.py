"""Shared HTTP helpers for the platform application."""

from __future__ import annotations

import contextlib
import json
import os

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .identity import IdentityStore
from .log import anomaly
from .session import set_session_cookie
from .theme import page

SIZE_MAX_BODY_JSON = 300_000
LIMIT_COMPILATIONS_BY_HOUR = 10
WINDOW_COMPILATIONS_SECONDES = 3600


def _links_of_footer(brut):
    """Normalizes the links declared by the console, without guessing the
    others."""
    from monl.dialogue_engine import address_of_link

    links, seen = [], set()
    for entry in brut or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        address = address_of_link(str(entry.get("url") or ""))
        key = label.casefold()
        if not label or '"' in label or not address or key in seen:
            continue
        seen.add(key)
        links.append({"label": label, "url": address})
    return links

def _session_response(identities: IdentityStore, user: dict[str, str],
                      status_code: int = 200, extra: dict | None = None) -> JSONResponse:
    token = identities.create_session(user["id"])
    response = JSONResponse({"user": user, **(extra or {})}, status_code=status_code)
    set_session_cookie(response, token)
    return response


def _require_user(request: Request, identities: IdentityStore) -> dict[str, str]:
    user = identities.session_user(request.cookies.get("monl_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def _key_mcp(request: Request) -> str | None:
    """The key carried by the ``Authorization: Bearer …`` header, or nothing."""
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None


def _require_user_ou_key(request: Request, identities: IdentityStore) -> dict[str, str]:
    """The browser session OR an MCP key.

    POINT 162. Fetching one's archive was the ONLY thing an agent could not do
    without opening a browser — exactly the step the direction wants to
    remove. It is not a second door: it is the SAME authentication path as
    ``/mcp`` (``api_key_user``), with the same ownership check behind it
    (``_require_project``). The reversal to understand: an MCP key identifies
    an ACCOUNT, not a capability — refusing it what the same account's session
    gets was not protection, only a dependency on the browser.

    The session is tried FIRST: in a browser, a stray ``Authorization`` header
    must never win over whoever is logged in."""
    user = identities.session_user(request.cookies.get("monl_session"))
    if user:
        return user
    key = _key_mcp(request)
    if key:
        user = identities.api_key_user(key)
        if user:
            return user
    raise HTTPException(
        status_code=401,
        detail="Sign in, or provide an MCP key in the Authorization header.",
    )


def _require_project(identities: IdentityStore, user_id: str, project_id: str) -> None:
    if not identities.owns_project(user_id, project_id):
        # The same response for a missing project and another account's: the
        # opaque identifier does not become an existence oracle.
        raise HTTPException(status_code=404, detail="Project not found.")


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
        # `sujet` is NOT logged: it is an IP address or an account identifier.
        # The scope and the wait are enough to notice abuse.
        anomaly("debit_depasse", portee=scope, attente_s=retry)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry)},
        )


#: The MCP tools that run the COMPILER, and therefore must take a slot in the
#: `MONL_MAX_CONCURRENT_COMPILES` semaphore. POINT 162: diff and update compile
#: too (in a throwaway folder for the first, in the project for the second) —
#: forgetting them here would leave the concurrency bound intact when read and
#: bypassed when executed.
TOOLS_QUI_COMPILE = frozenset({
    "monl_compile_backend", "monl_diff_spec", "monl_update_backend",
})


def _is_compile_message(message: dict) -> bool:
    params = message.get("params")
    return (
        message.get("method") == "tools/call"
        and isinstance(params, dict)
        and params.get("name") in TOOLS_QUI_COMPILE
    )


def _wants_of_json(request: Request) -> bool:
    if request.url.path.startswith(("/api/", "/mcp")):
        return True
    return "text/html" not in request.headers.get("accept", "")


def _page_404(detail: str) -> str:
    return page(
        title="Page not found — MONL",
        description="This address does not exist on the monl platform.",
        body=f"""
<section class="shell section" style="text-align:center;padding-block:var(--space-8)">
<span class="eyebrow" style="justify-content:center">Error 404</span>
<h2 style="font-size:clamp(28px,4vw,40px);margin-bottom:var(--space-3)">This page does not exist.</h2>
<p class="muted" style="max-width:520px;margin:0 auto var(--space-6)">{detail}</p>
<div style="display:flex;gap:var(--space-3);justify-content:center;flex-wrap:wrap">
<a class="primary" href="/">Back to home</a>
<a class="secondary" href="/console">Open the console</a>
<a class="secondary" href="/guide">Read the guide</a>
</div>
</section>""",
    )


async def _json_body(request: Request) -> dict:
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > SIZE_MAX_BODY_JSON:
                raise HTTPException(status_code=413, detail="Request too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length.") from None
    try:
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > SIZE_MAX_BODY_JSON:
                raise HTTPException(status_code=413, detail="Request too large.")
            chunks.append(chunk)
        payload = json.loads(b"".join(chunks))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="A JSON object is expected.")
    return payload


@contextlib.asynccontextmanager
async def _admission_compilation(request, identities, compile_slots, prepare=None):
    """Shares the quota and the execution slot of every HTTP compilation."""
    _rate_limit(
        request,
        identities,
        "compile",
        _require_user(request, identities)["id"],
        LIMIT_COMPILATIONS_BY_HOUR,
        WINDOW_COMPILATIONS_SECONDES,
    )
    preparation = await prepare() if prepare is not None else None
    if not compile_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="The compilers are busy. Try again in a moment.",
            headers={"Retry-After": "5"},
        )
    try:
        yield preparation
    finally:
        compile_slots.release()


def mount_error_handler(application):
    @application.exception_handler(404)
    async def not_found(request: Request, exc: HTTPException):
        # A visitor receives a page, an API client receives JSON. Serving HTML
        # to curl would make the error unreadable where it must be read.
        detail = getattr(exc, "detail", "Introuvable.")
        if _wants_of_json(request):
            return JSONResponse({"detail": detail}, status_code=404)
        return HTMLResponse(_page_404(detail), status_code=404)
