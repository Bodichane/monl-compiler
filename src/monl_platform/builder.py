"""Orchestration d'une construction de plateforme, sans interface HTTP."""

import contextlib
import io
import json
import os

from monl.cli import compile_project
from monl.frontend_ai import generate_and_verify
from monl.usage import UsagePriceError, build_usage_report

from .paths import ProjectPathError, project_directory
from .quota import QuotaError


class BuildIsolationError(RuntimeError):
    """Le projet demandé n'appartient pas au compte ou son chemin est sûr."""


_IMAGE_FAILURE_MARKER = "MONL_PLATFORM_IMAGE_FAILURE"


class _ImageProviderAdapter:
    """Marque une panne image pour permettre le repli texte de la plateforme."""

    def __init__(self, provider):
        self._provider = provider

    @property
    def provider_name(self):
        return getattr(self._provider, "provider_name", "image-custom")

    @property
    def model(self):
        return getattr(self._provider, "model", None)

    @property
    def last_usage(self):
        return getattr(self._provider, "last_usage", None)

    @last_usage.setter
    def last_usage(self, value):
        if hasattr(self._provider, "last_usage"):
            self._provider.last_usage = value

    def __call__(self, prompt):
        try:
            image = self._provider(prompt)
        except Exception as exc:
            raise RuntimeError(
                f"{_IMAGE_FAILURE_MARKER}: fournisseur d'image en erreur : {exc}"
            ) from exc
        if not isinstance(image, (bytes, bytearray, memoryview)) or not image:
            raise RuntimeError(
                f"{_IMAGE_FAILURE_MARKER}: le fournisseur d'image n'a pas rendu "
                "des octets"
            )
        return image


def _disable_generated_images(project_dir):
    """Rend le manifeste neutre si la dépense image n'a pas abouti."""
    path = os.path.join(project_dir, "ASSET_MANIFEST.json")
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        marker = "<!-- généré par monl — design system -->\n"
        if not content.startswith(marker):
            return
        manifest = json.loads("\n".join(content.splitlines()[1:]))
        if manifest.get("generated_by") != "monl":
            return
        manifest["generated_assets"] = []
        manifest["status"] = "planned"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(marker)
            fh.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
            fh.write("\n")
    except (OSError, json.JSONDecodeError, TypeError):
        # Le second passage de génération conservera l'erreur de vérification
        # si le manifeste est réellement illisible.
        return


def _is_optional_image_failure(error):
    message = str(error)
    return (
        _IMAGE_FAILURE_MARKER in message
        or message.startswith("--generate-images exige")
        or message.startswith("la génération d'images est activée")
        or "avant la génération d'image" in message
        or message.startswith("chemin d'image générée refusé")
    )


def _emit(say, message):
    if say is not None and message:
        say(message)


def _capture_compile(spec_path, project_dir, say):
    """Appelle l'API de compilation sans laisser sa sortie fuir."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        contract = compile_project(str(spec_path), str(project_dir))
    for line in output.getvalue().splitlines():
        _emit(say, line)
    return contract


def _usage_report(project_dir, prices_path=None):
    try:
        return build_usage_report(str(project_dir), prices_path=prices_path)
    except UsagePriceError:
        # Le quota est en jetons et la vérité des compteurs reste lisible même
        # si l'exploitant n'a pas encore fourni une table de prix exploitable.
        return build_usage_report(str(project_dir), prices_path=None)


def _run_ids(report):
    return {item["run_id"] for item in report["executions"] if item.get("run_id")}


def _execution_for_build(report, previous_run_ids):
    executions = [
        item
        for item in report["executions"]
        if item.get("run_id") and item["run_id"] not in previous_run_ids
    ]
    if not executions:
        return None
    return executions[-1]


def _usage_fields(report, previous_run_ids):
    execution = _execution_for_build(report, previous_run_ids)
    if execution is None:
        return {
            "run_id": None,
            "tokens_consumed": None,
            "input_tokens": None,
            "output_tokens": None,
            "cost": None,
            "currency": report["price_table"].get("currency"),
            "price_status": "no_usage",
        }
    return {
        "run_id": execution.get("run_id"),
        "tokens_consumed": execution.get("total_tokens"),
        "input_tokens": execution.get("input_tokens"),
        "output_tokens": execution.get("output_tokens"),
        "cost": execution.get("cost"),
        "currency": report["price_table"].get("currency"),
        "price_status": execution.get("price_status"),
    }


def _failure_message(error):
    if isinstance(error, (list, tuple)):
        return "\n".join(str(item) for item in error)
    return str(error)


def build_project(
    project_id,
    spec,
    provider,
    *,
    account_id,
    store,
    workspace_root,
    quota,
    prices_path=None,
    say=None,
    build_id=None,
    model_routes=None,
    provider_factory=None,
    generate_images=False,
    image_provider=None,
):
    """Construit un projet dans le pipeline monl complet.

    ``say`` vaut ``None`` par défaut : la compilation historique de monl écrit
    sur stdout, donc sa sortie est capturée puis redirigée uniquement lorsque
    l'appelant fournit un sink. Les fournisseurs texte et image restent
    injectés séparément; compilation et re-vérification restent celles de monl.
    """
    project = store.get_project_for_account(account_id, project_id)
    if project is None:
        raise BuildIsolationError(
            f"projet {project_id} introuvable pour le compte {account_id}"
        )
    resolved_account = store.resolve_account_id(account_id)
    if build_id is None:
        build_id = store.create_build(project["id"])
    else:
        existing_build = store.get_build_for_project(project["id"], build_id)
        if existing_build is None:
            raise BuildIsolationError(
                f"construction {build_id} introuvable pour le projet {project_id}"
            )
        if existing_build["state"] not in {"en_attente", "en_cours"}:
            raise RuntimeError(f"construction déjà terminée : {build_id}")
    try:
        quota.ensure_available(resolved_account)
    except QuotaError as exc:
        message = _failure_message(exc)
        store.finish_build(build_id, "echouee", error_message=message)
        if hasattr(exc, "build_id"):
            exc.build_id = build_id
        raise

    try:
        project_dir = project_directory(
            workspace_root, resolved_account, project["id"], create=True
        )
    except ProjectPathError as exc:
        message = _failure_message(exc)
        store.finish_build(build_id, "echouee", error_message=message)
        raise BuildIsolationError(message) from exc

    store.start_build(build_id)
    say_fn = say if say is not None else (lambda *_args: None)
    spec_path = project_dir / "spec.ml"
    previous_report = _usage_report(project_dir, prices_path=None)
    previous_run_ids = _run_ids(previous_report)
    try:
        if not isinstance(spec, str) or not spec.strip():
            raise ValueError("la spec doit être un texte non vide")
        spec_path.write_text(spec, encoding="utf-8")
        _capture_compile(spec_path, project_dir, say_fn)
        routed_image_provider = (
            _ImageProviderAdapter(image_provider)
            if generate_images and image_provider is not None
            else image_provider
        )
        try:
            result = generate_and_verify(
                str(project_dir),
                provider,
                say=say_fn,
                model_routes=model_routes,
                provider_factory=provider_factory,
                generate_images=generate_images,
                image_provider=routed_image_provider,
            )
        except Exception as exc:
            if not generate_images or not _is_optional_image_failure(exc):
                raise
            # Une photographie ne doit pas rendre inutilisable un frontend
            # sain. On retire le plan incomplet puis on rejoue la génération
            # texte dans un nouveau run_id, ce qui garde la télémétrie honnête.
            _disable_generated_images(str(project_dir))
            say_fn(
                " ⚠️  Images indisponibles : construction poursuivie sans "
                "images générées."
            )
            result = generate_and_verify(
                str(project_dir),
                provider,
                say=say_fn,
                model_routes=model_routes,
                provider_factory=provider_factory,
                generate_images=False,
                image_provider=None,
            )
        if not isinstance(result, tuple) or len(result) != 2:
            raise RuntimeError("generate_and_verify a retourné un résultat inattendu")
        ok, errors = result
        report = _usage_report(project_dir, prices_path=prices_path)
        usage = _usage_fields(report, previous_run_ids)
        if ok:
            store.finish_build(build_id, "reussie", **usage)
        else:
            store.finish_build(
                build_id,
                "echouee",
                error_message=_failure_message(errors),
                **usage,
            )
    except Exception as exc:
        try:
            report = _usage_report(project_dir, prices_path=prices_path)
            usage = _usage_fields(report, previous_run_ids)
        except Exception:
            usage = {}
        store.finish_build(
            build_id,
            "echouee",
            error_message=_failure_message(exc),
            **usage,
        )
    return store.get_build(build_id)


build_site = build_project
