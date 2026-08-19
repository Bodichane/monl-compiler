"""Point d'entrée du service HTTP de la plateforme monl.

Le service est un processus long : sa configuration vient donc uniquement de
l'environnement, jamais de secrets passés en ligne de commande. La
construction du fournisseur IA réutilise la table de préréglages de
``monl.frontend_ai`` afin que la plateforme et ``monl frontend`` parlent
exactement les mêmes dialectes.
"""

import argparse
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass


class PlatformConfigurationError(ValueError):
    """Une variable d'environnement de la plateforme est inexploitable."""


@dataclass(frozen=True, slots=True)
class PlatformSettings:
    database: str
    workspace_root: str
    domain: str
    jwt_secret: str
    quota_limit: int
    host: str
    port: int
    worker_interval: float
    prices_path: str | None
    downloads_dir: str | None
    ai_provider: str
    ai_model: str
    image_provider: str
    image_model: str | None


def _environment(environ):
    return os.environ if environ is None else environ


def _text(environ, name, default=None, *, required=False):
    value = environ.get(name)
    if value is None:
        if required:
            raise PlatformConfigurationError(
                f"{name} absent de l'environnement — cette valeur est obligatoire."
            )
        return default
    value = str(value).strip()
    if not value:
        raise PlatformConfigurationError(f"{name} ne peut pas être vide.")
    return value


def _integer(environ, name, default, *, minimum=0):
    raw = _text(environ, name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise PlatformConfigurationError(f"{name} doit être un entier.") from exc
    if value < minimum:
        raise PlatformConfigurationError(f"{name} doit être supérieur ou égal à {minimum}.")
    return value


def _number(environ, name, default, *, minimum=0.0):
    raw = _text(environ, name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise PlatformConfigurationError(f"{name} doit être un nombre.") from exc
    if value < minimum:
        raise PlatformConfigurationError(f"{name} doit être supérieur ou égal à {minimum}.")
    return value


def _verifier_la_connexion_par_fournisseur(environ):
    """Un bouton « Continuer avec GitHub » doit mener quelque part.

    L'adresse de retour vient de la configuration et jamais de l'en-tête
    ``Host`` (point 142) : sans ``MONL_PLATFORM_PUBLIC_URL``, un fournisseur
    par ailleurs complet propose un bouton qui répond 503 au clic. Le défaut
    ne se verrait donc qu'à l'usage, sur le compte de quelqu'un d'autre — on
    refuse de démarrer plutôt que de le laisser vivre.
    """
    from .oauth import PUBLIC_URL_ENV, configured_providers

    prets = configured_providers(environ)
    if prets and not (environ.get(PUBLIC_URL_ENV) or "").strip():
        noms = ", ".join(p["name"] for p in prets)
        raise PlatformConfigurationError(
            f"{PUBLIC_URL_ENV} absent alors que la connexion par {noms} est "
            "configurée — l'adresse de retour ne peut pas être devinée depuis "
            "l'en-tête Host, et le bouton mènerait à un 503."
        )


def load_settings(environ: Mapping[str, str] | None = None):
    """Lit toute la configuration de ``python -m monl_platform``.

    Le secret JWT est volontairement obligatoire : générer un secret à chaque
    démarrage invaliderait les sessions existantes et masquerait une erreur de
    déploiement.
    """
    environ = _environment(environ)
    downloads_dir = _text(environ, "MONL_PLATFORM_DOWNLOADS")
    prices_path = _text(environ, "MONL_PLATFORM_PRICES")
    if prices_path is None:
        prices_path = _text(environ, "MONL_USAGE_PRICES")
    _verifier_la_connexion_par_fournisseur(environ)
    provider = _text(environ, "MONL_PLATFORM_AI_PROVIDER", "yandex")
    model = _text(environ, "MONL_PLATFORM_AI_MODEL", required=True)
    image_provider = _text(environ, "MONL_PLATFORM_IMAGE_PROVIDER", "yandexart")
    image_model = _text(environ, "MONL_PLATFORM_IMAGE_MODEL")
    return PlatformSettings(
        database=_text(environ, "MONL_PLATFORM_DATABASE", "platform.db"),
        workspace_root=_text(environ, "MONL_PLATFORM_WORKSPACE", "platform-projects"),
        domain=_text(environ, "MONL_PLATFORM_DOMAIN", "localhost"),
        jwt_secret=_text(environ, "MONL_PLATFORM_JWT_SECRET", required=True),
        quota_limit=_integer(environ, "MONL_PLATFORM_QUOTA", 1_000_000),
        host=_text(environ, "MONL_PLATFORM_HOST", "127.0.0.1"),
        port=_integer(environ, "MONL_PLATFORM_PORT", 8000, minimum=0),
        worker_interval=_number(environ, "MONL_PLATFORM_WORKER_INTERVAL", 0.05),
        prices_path=prices_path,
        downloads_dir=downloads_dir,
        ai_provider=provider,
        ai_model=model,
        image_provider=image_provider,
        image_model=image_model,
    )


def create_configured_app(environ: Mapping[str, str] | None = None):
    """Construit l'application et son fournisseur avant de lancer Uvicorn."""
    from monl.frontend_ai import PROVIDERS, FrontendAIError
    from monl.image_ai import IMAGE_PROVIDERS

    settings = load_settings(environ)
    try:
        provider_builder = PROVIDERS[settings.ai_provider]
    except KeyError as exc:
        raise PlatformConfigurationError(
            f"MONL_PLATFORM_AI_PROVIDER inconnu : {settings.ai_provider} — "
            f"valeurs connues : {', '.join(sorted(PROVIDERS))}"
        ) from exc
    def model_provider_factory(model):
        try:
            return provider_builder(model=model)
        except FrontendAIError as exc:
            raise PlatformConfigurationError(str(exc)) from exc

    try:
        provider = model_provider_factory(settings.ai_model)
    except FrontendAIError as exc:
        raise PlatformConfigurationError(str(exc)) from exc

    try:
        image_provider_builder = IMAGE_PROVIDERS[settings.image_provider]
    except KeyError as exc:
        raise PlatformConfigurationError(
            f"MONL_PLATFORM_IMAGE_PROVIDER inconnu : {settings.image_provider} — "
            f"valeurs connues : {', '.join(sorted(IMAGE_PROVIDERS))}"
        ) from exc

    def image_provider_factory(_project, _build):
        return image_provider_builder(model=settings.image_model)

    from .app import create_app

    return create_app(
        database=settings.database,
        workspace_root=settings.workspace_root,
        domain=settings.domain,
        jwt_secret=settings.jwt_secret,
        quota_limit=settings.quota_limit,
        provider=provider,
        model_provider_factory=model_provider_factory,
        image_provider_factory=image_provider_factory,
        prices_path=settings.prices_path,
        downloads_dir=settings.downloads_dir,
        poll_interval=settings.worker_interval,
    ), settings


def _parser():
    from monl.frontend_ai import OPENAI_COMPATIBLE, PROVIDERS
    from monl.image_ai import IMAGE_PROVIDERS

    provider_keys = sorted({key_env for _url, key_env in OPENAI_COMPATIBLE.values()})
    provider_keys.extend(("ANTHROPIC_API_KEY", "MONL_AI_API_KEY"))
    provider_keys = ", ".join(sorted(set(provider_keys)))
    environment_help = (
        "Configuration exclusivement par l'environnement (aucun secret en argument) :\n"
        "  MONL_PLATFORM_DATABASE          base SQLite (défaut : platform.db)\n"
        "  MONL_PLATFORM_WORKSPACE         racine des espaces de travail\n"
        "  MONL_PLATFORM_DOMAIN            domaine des sites (défaut : localhost)\n"
        "  MONL_PLATFORM_JWT_SECRET        secret JWT obligatoire, jamais généré\n"
        "  MONL_PLATFORM_QUOTA             quota de jetons (défaut : 1000000)\n"
        "  MONL_PLATFORM_HOST              hôte d'écoute (défaut : 127.0.0.1)\n"
        "  MONL_PLATFORM_PORT              port d'écoute (défaut : 8000)\n"
        "  MONL_PLATFORM_WORKER_INTERVAL   intervalle du worker en secondes\n"
        "  MONL_PLATFORM_PRICES            chemin de la table de prix JSON\n"
        "  MONL_PLATFORM_DOWNLOADS         dossier des artefacts telechargeables\n"
        "  MONL_PLATFORM_PUBLIC_URL        adresse publique, obligatoire dès qu'un\n"
        "                                  fournisseur de connexion est configuré\n"
        "  MONL_OAUTH_GITHUB_CLIENT_ID     connexion GitHub : identifiant public\n"
        "  MONL_OAUTH_GITHUB_SECRET        connexion GitHub : secret\n"
        "  MONL_OAUTH_GOOGLE_CLIENT_ID     connexion Google : identifiant public\n"
        "  MONL_OAUTH_GOOGLE_SECRET        connexion Google : secret\n"
        "  MONL_USAGE_PRICES               repli existant pour la table de prix\n"
        "  MONL_PLATFORM_AI_PROVIDER       préréglage frontend_ai (défaut : yandex)\n"
        "  MONL_PLATFORM_AI_MODEL          modèle obligatoire, sans valeur par défaut\n"
        "  MONL_PLATFORM_IMAGE_PROVIDER    préréglage image_ai (défaut : yandexart) ; "
        "activation explicite par projet\n"
        "  MONL_PLATFORM_IMAGE_MODEL       modèle image facultatif du préréglage\n"
        f"  Clés lues par les préréglages : {provider_keys}\n"
        "  MONL_AI_BASE_URL                base du fournisseur openai-compatible\n"
        "  YANDEX_FOLDER_ID                dossier Yandex pour le préréglage yandex\n"
        f"  Préréglages texte disponibles : {', '.join(sorted(PROVIDERS))}\n"
        f"  Préréglages image disponibles : {', '.join(sorted(IMAGE_PROVIDERS))}"
    )
    return argparse.ArgumentParser(
        prog="python3 -m monl_platform",
        description="Démarre le service HTTP de la plateforme monl.",
        epilog=environment_help,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv=None):
    """Valide la configuration, construit l'IA, puis remet l'ASGI à Uvicorn."""
    _parser().parse_args(argv)
    try:
        application, settings = create_configured_app()
    except (PlatformConfigurationError, ValueError) as exc:
        print(f"monl platform : configuration invalide — {exc}", file=sys.stderr)
        return 2
    import uvicorn

    uvicorn.run(application, host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
