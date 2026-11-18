"""Configuration et pose de l'unique cookie de session de la plateforme."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

COOKIE_SECURE_ENV = "MONL_COOKIE_SECURE"
PUBLIC_URL_ENV = "MONL_PLATFORM_PUBLIC_URL"
_VALEURS_VRAIES = {"1", "true", "yes"}


def cookie_secure(environ=None) -> bool:
    """Says whether the session cookie must carry the ``Secure`` attribute."""
    # The name comes from the CONSTANT in both branches: hard-coded here, it
    # would survive a rename and the default read would look for a variable
    # that no longer exists — the cookie would silently become insecure again.
    source = os.environ if environ is None else environ
    return str(source.get(COOKIE_SECURE_ENV, "")).strip().lower() in _VALEURS_VRAIES


def verifier_configuration_cookie(environ=None) -> None:
    """Refuses the only configuration that contradicts the announced security.

    A missing or HTTP public URL stays allowed: they correspond to local
    development and internal networks. The contradiction is precisely HTTPS
    announced with a cookie that still accepts HTTP."""
    source = os.environ if environ is None else environ
    public_url = str(source.get(PUBLIC_URL_ENV, "")).strip()
    if (public_url and urlsplit(public_url).scheme.lower() == "https"
            and not cookie_secure(source)):
        raise RuntimeError(
            f"incompatible configuration: {PUBLIC_URL_ENV} announces HTTPS, but "
            f"{COOKIE_SECURE_ENV} is not enabled; set "
            f"{COOKIE_SECURE_ENV}=1 to require HTTPS for the session cookie."
        )


def set_session_cookie(response, token) -> None:
    """Sets the session cookie, the single source for every caller."""
    response.set_cookie(
        "monl_session", token, max_age=30 * 24 * 3600, path="/",
        httponly=True, samesite="strict", secure=cookie_secure(),
    )
