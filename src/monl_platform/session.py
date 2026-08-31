"""Configuration et pose de l'unique cookie de session de la plateforme."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

COOKIE_SECURE_ENV = "MONL_COOKIE_SECURE"
PUBLIC_URL_ENV = "MONL_PLATFORM_PUBLIC_URL"
_VALEURS_VRAIES = {"1", "true", "yes"}


def cookie_secure(environ=None) -> bool:
    """Indique si le cookie de session doit porter l'attribut ``Secure``."""
    # Le nom vient de la CONSTANTE dans les deux branches : écrit en dur ici,
    # il survivrait à un renommage et la lecture par défaut irait chercher une
    # variable qui n'existe plus — le cookie redeviendrait non sûr en silence.
    source = os.environ if environ is None else environ
    return str(source.get(COOKIE_SECURE_ENV, "")).strip().lower() in _VALEURS_VRAIES


def verifier_configuration_cookie(environ=None) -> None:
    """Refuse la seule configuration qui contredit la sécurité annoncée.

    Une URL publique absente ou en HTTP reste permise : elles correspondent au
    développement local et aux réseaux internes. La contradiction est
    précisément HTTPS annoncé avec un cookie qui accepte encore HTTP.
    """
    source = os.environ if environ is None else environ
    public_url = str(source.get(PUBLIC_URL_ENV, "")).strip()
    if (public_url and urlsplit(public_url).scheme.lower() == "https"
            and not cookie_secure(source)):
        raise RuntimeError(
            f"configuration incompatible : {PUBLIC_URL_ENV} annonce HTTPS, mais "
            f"{COOKIE_SECURE_ENV} n'est pas activée ; définir "
            f"{COOKIE_SECURE_ENV}=1 pour exiger HTTPS du cookie de session."
        )


def set_session_cookie(response, token) -> None:
    """Pose le cookie de session, source unique pour tous les appelants."""
    response.set_cookie(
        "monl_session", token, max_age=30 * 24 * 3600, path="/",
        httponly=True, samesite="strict", secure=cookie_secure(),
    )
