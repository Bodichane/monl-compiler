"""Fournisseurs d'images matricielles pour la construction frontend.

Le fournisseur d'images est volontairement séparé de ``frontend_ai`` : le
modèle texte ne peut rendre que des chaînes dans des fichiers autorisés, alors
qu'une image doit traverser la frontière sous forme d'octets et être écrite
dans le dossier d'assets du projet.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone

from .errors import FrontendError

IMAGE_USAGE_FILENAME = ".monl_ai_usage.jsonl"
YANDEXART_GENERATE_URL = (
    "https://ai.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
)
YANDEXART_OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/{operation_id}"
DEFAULT_YANDEXART_MODEL = "yandex-art/latest"
DEFAULT_IMAGE_POLL_INTERVAL = 2.0
DEFAULT_IMAGE_POLL_TIMEOUT = 600.0


class ImageProviderError(FrontendError):
    """Erreur de service image ; la plateforme la traite comme indisponibilité."""

    status_code = 503


def _requests_module():
    try:
        import requests
    except ImportError as exc:
        raise ImageProviderError(
            "Le fournisseur d'images nécessite l'extra optionnel : "
            "pip install 'monl-compiler[ai]'."
        ) from exc
    return requests


def _poll_setting(name, default):
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ImageProviderError(f"{name} doit être un nombre positif.") from exc
    if value <= 0:
        raise ImageProviderError(f"{name} doit être un nombre positif.")
    return value


def _image_from_operation(payload):
    response = payload.get("response") or {}
    encoded = response.get("image")
    if not encoded:
        return None
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageProviderError("YandexART a renvoyé une image base64 invalide.") from exc
    if not image:
        raise ImageProviderError("YandexART a renvoyé une image vide.")
    return image


def yandexart_provider(model=None, *, key_env="YANDEX_API_KEY",
                       folder_env="YANDEX_FOLDER_ID"):
    """Construit un fournisseur d'octets JPEG basé sur YandexART.

    La clé et le dossier viennent uniquement de l'environnement. Le modèle
    peut être surchargé pour les environnements qui exposent une version
    différente, mais le préréglage reste déterministe.
    """
    api_key = (os.environ.get(key_env) or "").strip()
    if not api_key:
        raise ImageProviderError(
            f"503 — YandexART indisponible : {key_env} absent de l'environnement."
        )
    folder_id = (os.environ.get(folder_env) or "").strip()
    if not folder_id:
        raise ImageProviderError(
            f"503 — YandexART indisponible : {folder_env} absent de l'environnement."
        )
    model_uri = model or f"art://{folder_id}/{DEFAULT_YANDEXART_MODEL}"

    def call(prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ImageProviderError("Le prompt YandexART ne peut pas être vide.")
        requests = _requests_module()
        started = time.monotonic()
        call.last_usage = None
        body = {
            "modelUri": model_uri,
            "generationOptions": {"mimeType": "image/jpeg"},
            "messages": [{"weight": 1, "text": prompt}],
        }
        try:
            response = requests.post(
                YANDEXART_GENERATE_URL,
                headers={"Authorization": f"Api-Key {api_key}",
                         "Content-Type": "application/json"},
                json=body,
                timeout=300,
            )
        except requests.RequestException as exc:
            raise ImageProviderError(f"YandexART inaccessible : {exc}") from exc
        if response.status_code not in (200, 202):
            raise ImageProviderError(
                f"YandexART : {response.status_code} — {response.text[:300]}"
            )
        try:
            operation = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ImageProviderError("YandexART a renvoyé un JSON invalide.") from exc

        image = _image_from_operation(operation)
        operation_id = operation.get("id")
        if image is None and not operation_id:
            raise ImageProviderError("YandexART a renvoyé une opération sans identifiant.")

        if image is None:
            deadline = time.monotonic() + _poll_setting(
                "MONL_IMAGE_POLL_TIMEOUT", DEFAULT_IMAGE_POLL_TIMEOUT)
            while time.monotonic() < deadline:
                time.sleep(_poll_setting(
                    "MONL_IMAGE_POLL_INTERVAL", DEFAULT_IMAGE_POLL_INTERVAL))
                try:
                    status = requests.get(
                        YANDEXART_OPERATION_URL.format(operation_id=operation_id),
                        headers={"Authorization": f"Api-Key {api_key}"},
                        timeout=60,
                    )
                except requests.RequestException as exc:
                    raise ImageProviderError(
                        f"YandexART : lecture de l'opération impossible — {exc}"
                    ) from exc
                if status.status_code != 200:
                    raise ImageProviderError(
                        f"YandexART : lecture de l'opération {status.status_code} — "
                        f"{status.text[:300]}"
                    )
                try:
                    operation = status.json()
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ImageProviderError(
                        "YandexART a renvoyé un état d'opération invalide."
                    ) from exc
                if operation.get("error"):
                    detail = operation["error"].get("message", "erreur inconnue")
                    raise ImageProviderError(f"YandexART : {detail}")
                image = _image_from_operation(operation)
                if image is not None:
                    break
                if operation.get("done"):
                    raise ImageProviderError(
                        "YandexART a terminé sans renvoyer de données image."
                    )
            if image is None:
                raise ImageProviderError("YandexART : délai d'attente dépassé.")

        call.last_usage = {
            "duration_seconds": round(time.monotonic() - started, 3),
            "requests": 1,
        }
        return image

    call.provider_name = "yandexart"
    call.model = model_uri
    call.last_usage = None
    return call


IMAGE_PROVIDERS = {"yandexart": yandexart_provider}


def record_image_usage(project_dir, provider, operation, attempt, *, run_id,
                       stage=None, path=None, status="success"):
    """Ajoute une requête image sans fabriquer de compteurs de jetons."""
    usage = getattr(provider, "last_usage", None) or {}
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "provider": getattr(provider, "provider_name", "image-custom"),
        "model": getattr(provider, "model", None),
        "operation": operation,
        "attempt": attempt,
        "billing_unit": "request",
        "requests": usage.get("requests", 1),
        "duration_seconds": usage.get("duration_seconds"),
        "status": status,
    }
    if stage is not None:
        event["stage"] = stage
    if path is not None:
        event["asset_path"] = path
    journal = os.path.join(project_dir, IMAGE_USAGE_FILENAME)
    with open(journal, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
