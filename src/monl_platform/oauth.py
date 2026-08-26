"""Connexion par un compte Google ou GitHub.

Née d'un constat : la plateforme dépense de l'argent réel à chaque
construction, et n'importe qui pouvait ouvrir un compte avec une chaîne de
caractères quelconque. Le point 95 du journal ferme la vérification par
courriel — « monl vérifie la forme, jamais qu'une boîte reçoit » — et cette
frontière tient toujours : ce module n'envoie AUCUN message. Il délègue la
vérification à un fournisseur qui, lui, l'a déjà faite.

QUATRE DÉCISIONS, et aucune n'est cosmétique.

1. **Les comptes OAuth vivent dans leur PROPRE espace de noms**
   (``github:12345``, ``google:1078…``), jamais sous l'adresse de courriel.
   Rattacher un compte OAuth à un compte mot de passe portant la même adresse
   serait une prise de contrôle : les comptes mot de passe ne sont vérifiés
   par personne, donc n'importe qui peut s'inscrire sous ``alice@exemple.fr``
   AVANT Alice et récupérer sa session le jour où elle se connecte par Google.
   Le prix de ce choix est énoncé : un compte créé au mot de passe ne se
   retrouve pas en se connectant par Google, ce sont deux comptes.

2. **Seule une adresse VÉRIFIÉE par le fournisseur est acceptée.** GitHub
   marque ses adresses ``verified``, Google renseigne ``email_verified``. Sans
   ce contrôle, la brique ne vérifierait rien du tout — elle déplacerait
   simplement la chaîne de caractères quelconque d'un formulaire à un autre.

3. **Le ``state`` est SIGNÉ et DATÉ.** Signé, il empêche qu'un tiers déclenche
   une connexion depuis son propre site (CSRF) ; daté, il empêche qu'un aller
   capté une fois reste rejouable indéfiniment — même raisonnement, et même
   tolérance de dix minutes, que la signature du webhook de paiement.

4. **L'adresse de retour vient de la CONFIGURATION, jamais de l'en-tête
   ``Host``.** Le Host est fourni par le client : le lire pour composer le
   ``redirect_uri`` laisserait détourner l'aller-retour vers un domaine
   choisi par l'attaquant.

Les secrets viennent de l'environnement, comme la clé de paiement (point 74) :
un fournisseur non configuré n'est simplement pas proposé, et sa route répond
503 en NOMMANT la variable absente plutôt qu'en échouant sans rien dire.
"""

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

#: Tolérance d'un aller-retour, en secondes. Même durée que la signature du
#: webhook de paiement : assez pour une connexion humaine, trop court pour un
#: rejeu.
STATE_TTL = 600

#: Ce qu'il faut pour proposer un fournisseur. La valeur de gauche est la
#: variable d'environnement, celle de droite ce qu'elle contient.
PROVIDERS = {
    "github": {
        "label": "GitHub",
        "client_id_env": "MONL_OAUTH_GITHUB_CLIENT_ID",
        "secret_env": "MONL_OAUTH_GITHUB_SECRET",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "api": "https://api.github.com",
        "scope": "read:user user:email",
        # Pour éprouver la brique sans appeler le vrai GitHub, comme
        # MONL_STRIPE_BASE_URL le fait pour le paiement (point 74).
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

#: L'adresse publique de la plateforme, celle que le fournisseur rappellera.
PUBLIC_URL_ENV = "MONL_PLATFORM_PUBLIC_URL"


class OAuthError(Exception):
    """Échec attribuable au fournisseur ou à la configuration."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class OAuthNotConfigured(OAuthError):
    """Le fournisseur n'a pas ses secrets : on NOMME la variable manquante."""

    def __init__(self, variable):
        super().__init__(
            f"connexion indisponible : la variable d'environnement {variable} "
            "n'est pas renseignée sur ce serveur",
            status_code=503,
        )
        self.variable = variable


# ─────────────────────────────────────────────────────── configuration ──
def _env(name, environ=None):
    valeur = (environ if environ is not None else os.environ).get(name)
    return valeur.strip() if isinstance(valeur, str) and valeur.strip() else None


def configured_providers(environ=None):
    """Les fournisseurs réellement utilisables, dans un ordre stable.

    Un bouton qui mène à un 503 est pire que pas de bouton : on ne propose
    que ce qui est configuré.
    """
    prets = []
    for nom, spec in PROVIDERS.items():
        if _env(spec["client_id_env"], environ) and _env(spec["secret_env"], environ):
            prets.append({"name": nom, "label": spec["label"]})
    return prets


def _spec(provider):
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise OAuthError(f"fournisseur inconnu : {provider}", status_code=404)
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
    """Adresse d'un point d'entrée du fournisseur, surchargeable pour les tests."""
    spec = _spec(provider)
    remplacement = _env(spec["base_env"], environ)
    if not remplacement:
        return spec[cle]
    chemin = urllib.parse.urlsplit(spec[cle]).path
    return remplacement.rstrip("/") + chemin


def redirect_uri(provider, environ=None):
    """L'adresse de retour, prise dans la CONFIGURATION.

    Jamais reconstruite depuis l'en-tête ``Host`` : il est fourni par le
    client, et le lire ici laisserait détourner l'aller-retour.
    """
    public = _env(PUBLIC_URL_ENV, environ)
    if not public:
        raise OAuthNotConfigured(PUBLIC_URL_ENV)
    return f"{public.rstrip('/')}/auth/{provider}/retour"


# ────────────────────────────────────────────────────────────── state ──
def _signer(secret, charge):
    return hmac.new(secret.encode("utf-8"), charge.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def make_state(provider, secret, *, maintenant=None):
    """Un jeton d'aller, signé et daté."""
    horodatage = int(maintenant if maintenant is not None else time.time())
    charge = f"{provider}.{horodatage}.{secrets.token_urlsafe(16)}"
    return f"{charge}.{_signer(secret, charge)}"


def check_state(state, provider, secret, *, maintenant=None):
    """Refuse un état forgé, rejoué ou venu d'un autre fournisseur."""
    morceaux = str(state or "").split(".")
    if len(morceaux) != 4:
        raise OAuthError("état de connexion illisible", status_code=400)
    nom, horodatage, _alea, signature = morceaux
    charge = ".".join(morceaux[:3])
    if not hmac.compare_digest(signature, _signer(secret, charge)):
        raise OAuthError("état de connexion non signé par ce serveur",
                         status_code=400)
    if nom != provider:
        raise OAuthError("état de connexion émis pour un autre fournisseur",
                         status_code=400)
    try:
        age = int(maintenant if maintenant is not None else time.time()) - int(horodatage)
    except ValueError:
        raise OAuthError("état de connexion illisible", status_code=400) from None
    if age < -STATE_TTL or age > STATE_TTL:
        raise OAuthError("connexion expirée : recommencer depuis la console",
                         status_code=400)
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


# ──────────────────────────────────────────────── échange et identité ──
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
        raise OAuthError(
            f"le fournisseur a refusé l'échange ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError(f"fournisseur injoignable : {exc}") from exc


def _get_json(url, jeton, timeout=15):
    requete = urllib.request.Request(url, method="GET")
    requete.add_header("Accept", "application/json")
    requete.add_header("Authorization", f"Bearer {jeton}")
    requete.add_header("User-Agent", "monl-platform")
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OAuthError(f"le fournisseur a refusé la lecture ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError(f"fournisseur injoignable : {exc}") from exc


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
        raise OAuthError("le fournisseur n'a pas délivré de jeton d'accès")
    return jeton


def fetch_identity(provider, jeton, environ=None):
    """Rend ``(identifiant, libellé)`` — ou refuse une adresse non vérifiée.

    Sans le contrôle de vérification, la brique ne vérifierait rien : elle
    déplacerait la chaîne quelconque d'un formulaire vers un autre.
    """
    api = _base_url(provider, "api", environ)
    if provider == "github":
        compte = _get_json(f"{api}/user", jeton)
        sujet = compte.get("id")
        if not sujet:
            raise OAuthError("le fournisseur n'a pas identifié le compte")
        adresses = _get_json(f"{api}/user/emails", jeton)
        verifiee = next(
            (a.get("email") for a in adresses
             if isinstance(a, dict) and a.get("verified") and a.get("primary")),
            None,
        )
        if not verifiee:
            raise OAuthError(
                "ce compte GitHub n'a aucune adresse principale vérifiée : "
                "vérifiez-la chez GitHub, puis recommencez",
                status_code=403,
            )
        return f"github:{sujet}", verifiee
    compte = _get_json(f"{api}/v1/userinfo", jeton)
    sujet = compte.get("sub")
    if not sujet:
        raise OAuthError("le fournisseur n'a pas identifié le compte")
    if not compte.get("email_verified"):
        raise OAuthError(
            "ce compte Google n'a pas d'adresse vérifiée",
            status_code=403,
        )
    return f"google:{sujet}", compte.get("email") or f"google:{sujet}"
