"""Login with a Google or GitHub account.

Born from an observation: the platform spends real money on each build,
and anyone could open an account with any string of characters. Point 95
of the journal rules out email verification — "monl checks the form,
never that an inbox receives" — and that boundary still holds: this module
sends NO message. It delegates verification to a provider that has
already done it.

FOUR DECISIONS, and none is cosmetic.

1. **OAuth accounts live in their OWN namespace** (``github:12345``,
   ``google:1078…``), never under the email address. Attaching an OAuth
   account to a password account carrying the same address would be a
   takeover: password accounts are verified by nobody, so anyone can
   register under ``alice@exemple.fr`` BEFORE Alice and recover her session
   the day she logs in with Google. The price of this choice is stated: an
   account created with a password is not found again by logging in with
   Google, they are two accounts.

2. **Only an address VERIFIED by the provider is accepted.** GitHub marks
   its addresses ``verified``, Google fills in ``email_verified``. Without
   this check, the brick would verify nothing at all — it would simply move
   the arbitrary string of characters from one form to another.

3. **The ``state`` is SIGNED and DATED.** Signed, it prevents a third party
   from triggering a login from their own site (CSRF); dated, it prevents a
   request captured once from staying replayable forever — the same
   reasoning, and the same ten-minute tolerance, as the payment webhook's
   signature.

4. **The return address comes from the CONFIGURATION, never from the
   ``Host`` header.** The Host is supplied by the client: reading it to
   compose the ``redirect_uri`` would let the round trip be diverted to a
   domain chosen by the attacker.

The secrets come from the environment, like the payment key (point 74):
an unconfigured provider is simply not offered, and its route answers 503
NAMING the missing variable rather than failing without a word."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

#: Tolerance of a round trip, in seconds. The same duration as the payment
#: webhook's signature: enough for a human login, too short for a replay.
STATE_TTL = 600
OAUTH_FLOW_COOKIE = "monl_oauth_flow"
OAUTH_FLOW_PATH = "/auth/"

#: What it takes to offer a provider. The left value is the environment
#: variable, the right one what it contains.
PROVIDERS = {
    "github": {
        "label": "GitHub",
        "client_id_env": "MONL_OAUTH_GITHUB_CLIENT_ID",
        "secret_env": "MONL_OAUTH_GITHUB_SECRET",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "api": "https://api.github.com",
        "scope": "read:user user:email",
        # To exercise the brick without calling the real GitHub, as
        # MONL_STRIPE_BASE_URL does for payment (point 74).
        "base_env": "MONL_OAUTH_GITHUB_BASE_URL",
    },
    "google": {
        "label": "Google",
        "client_id_env": "MONL_OAUTH_GOOGLE_CLIENT_ID",
        "secret_env": "MONL_OAUTH_GOOGLE_SECRET",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "api": "https://openidconnect.googleapis.com",
        "scope": "openid email profile",
        "base_env": "MONL_OAUTH_GOOGLE_BASE_URL",
    },
}

#: The platform's public address, the one the provider will call back.
PUBLIC_URL_ENV = "MONL_PLATFORM_PUBLIC_URL"


class OAuthError(Exception):
    """Failure attributable to the provider or the configuration."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class OAuthNotConfigured(OAuthError):
    """The provider lacks its secrets: the missing variable is NAMED."""

    def __init__(self, variable):
        super().__init__(
            f"sign-in unavailable: the environment variable {variable} "
            "is not set on this server",
            status_code=503,
        )
        self.variable = variable


# ─────────────────────────────────────────────────────── configuration ──
def _env(name, environ=None):
    valeur = (environ if environ is not None else os.environ).get(name)
    return valeur.strip() if isinstance(valeur, str) and valeur.strip() else None


def configured_providers(environ=None):
    """The really usable providers, in a stable order.

    A button that leads to a 503 is worse than no button: only what is
    configured is offered."""
    prets = []
    for nom, spec in PROVIDERS.items():
        if _env(spec["client_id_env"], environ) and _env(spec["secret_env"], environ):
            prets.append({"name": nom, "label": spec["label"]})
    return prets


def _spec(provider):
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise OAuthError(f"unknown provider: {provider}", status_code=404)
    return spec


def _credentials(provider, environ=None):
    spec = _spec(provider)
    client_id = _env(spec["client_id_env"], environ)
    if not client_id:
        raise OAuthNotConfigured(spec["client_id_env"])
    secret = _env(spec["secret_env"], environ)
    if not secret:
        raise OAuthNotConfigured(spec["secret_env"])
    return client_id, secret


def _base_url(provider, cle, environ=None):
    """Address of a provider endpoint, overridable for tests."""
    spec = _spec(provider)
    remplacement = _env(spec["base_env"], environ)
    if not remplacement:
        return spec[cle]
    chemin = urllib.parse.urlsplit(spec[cle]).path
    return remplacement.rstrip("/") + chemin


def redirect_uri(provider, environ=None):
    """The return address, taken from the CONFIGURATION.

    Never rebuilt from the ``Host`` header: it is supplied by the client, and
    reading it here would let the round trip be diverted."""
    public = _env(PUBLIC_URL_ENV, environ)
    if not public:
        raise OAuthNotConfigured(PUBLIC_URL_ENV)
    return f"{public.rstrip('/')}/auth/{provider}/retour"


# ────────────────────────────────────────────────────────────── state ──
def _signer(secret, charge):
    return hmac.new(secret.encode("utf-8"), charge.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def make_browser_secret():
    """Creates the ephemeral secret that only leaves the initiating browser."""
    return secrets.token_urlsafe(32)


def _browser_digest(secret, browser_secret):
    return hmac.new(
        secret.encode("utf-8"),
        f"oauth-browser.{browser_secret}".encode(),
        hashlib.sha256,
    ).hexdigest()


def make_state(provider, secret, browser_secret, *, maintenant=None):
    """An outbound token, signed, dated and bound to the initiating browser."""
    horodatage = int(maintenant if maintenant is not None else time.time())
    empreinte = _browser_digest(secret, browser_secret)
    charge = f"{provider}.{horodatage}.{secrets.token_urlsafe(16)}.{empreinte}"
    return f"{charge}.{_signer(secret, charge)}"


def check_state(state, provider, secret, browser_secret, *, maintenant=None):
    """Refuses a forged, replayed state or one from another provider."""
    morceaux = str(state or "").split(".")
    if len(morceaux) != 5:
        raise OAuthError("unreadable sign-in state", status_code=400)
    nom, horodatage, _alea, empreinte, signature = morceaux
    charge = ".".join(morceaux[:4])
    if not hmac.compare_digest(signature, _signer(secret, charge)):
        raise OAuthError("sign-in state not signed by this server",
                         status_code=400)
    if nom != provider:
        raise OAuthError("sign-in state issued for another provider",
                         status_code=400)
    try:
        age = int(maintenant if maintenant is not None else time.time()) - int(horodatage)
    except ValueError:
        raise OAuthError("unreadable sign-in state", status_code=400) from None
    if age < -STATE_TTL or age > STATE_TTL:
        raise OAuthError("sign-in expired: start again from the console",
                         status_code=400)
    attendue = _browser_digest(secret, browser_secret or "")
    if not browser_secret or not hmac.compare_digest(empreinte, attendue):
        raise OAuthError(
            "sign-in state missing from this browser or already used",
            status_code=400,
        )
    return True


def authorize_url(provider, state, environ=None):
    client_id, _secret = _credentials(provider, environ)
    spec = _spec(provider)
    parametres = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider, environ),
        "scope": spec["scope"],
        "state": state,
        "response_type": "code",
    }
    return (_base_url(provider, "authorize", environ) + "?"
            + urllib.parse.urlencode(parametres))


# ──────────────────────────────────────────────── exchange and identity ──
def _post_json(url, donnees, entetes=None, timeout=15):
    corps = urllib.parse.urlencode(donnees).encode("utf-8")
    requete = urllib.request.Request(url, data=corps, method="POST")
    requete.add_header("Accept", "application/json")
    requete.add_header("Content-Type", "application/x-www-form-urlencoded")
    for cle, valeur in (entetes or {}).items():
        requete.add_header(cle, valeur)
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        with exc:
            raise OAuthError(
                f"the provider refused the exchange ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError(f"provider unreachable: {exc}") from exc


def _get_json(url, jeton, timeout=15):
    requete = urllib.request.Request(url, method="GET")
    requete.add_header("Accept", "application/json")
    requete.add_header("Authorization", f"Bearer {jeton}")
    requete.add_header("User-Agent", "monl-platform")
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        with exc:
            raise OAuthError(f"the provider refused the read ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError(f"provider unreachable: {exc}") from exc


def exchange_code(provider, code, environ=None):
    client_id, secret = _credentials(provider, environ)
    reponse = _post_json(_base_url(provider, "token", environ), {
        "client_id": client_id,
        "client_secret": secret,
        "code": code,
        "redirect_uri": redirect_uri(provider, environ),
        "grant_type": "authorization_code",
    })
    jeton = reponse.get("access_token")
    if not jeton:
        raise OAuthError("the provider issued no access token")
    return jeton


def fetch_identity(provider, jeton, environ=None):
    """Returns ``(identifier, label)`` — or refuses an unverified address.

    Without the verification check, the brick would verify nothing: it would
    move the arbitrary string from one form to another."""
    api = _base_url(provider, "api", environ)
    if provider == "github":
        compte = _get_json(f"{api}/user", jeton)
        sujet = compte.get("id")
        if not sujet:
            raise OAuthError("the provider did not identify the account")
        adresses = _get_json(f"{api}/user/emails", jeton)
        verifiee = next(
            (a.get("email") for a in adresses
             if isinstance(a, dict) and a.get("verified") and a.get("primary")),
            None,
        )
        if not verifiee:
            raise OAuthError(
                "this GitHub account has no verified primary address: "
                "verify it on GitHub, then start again",
                status_code=403,
            )
        return f"github:{sujet}", verifiee
    compte = _get_json(f"{api}/v1/userinfo", jeton)
    sujet = compte.get("sub")
    if not sujet:
        raise OAuthError("the provider did not identify the account")
    if not compte.get("email_verified"):
        raise OAuthError(
            "this Google account has no verified address",
            status_code=403,
        )
    return f"google:{sujet}", compte.get("email") or f"google:{sujet}"
