"""Orchestration d'une construction de plateforme, sans interface HTTP."""

import contextlib
import io

from monl.cli import compile_project
from monl.frontend_ai import generate_and_verify
from monl.image_ai import ImageProviderError
from monl.usage import UsagePriceError, build_usage_report

from .paths import ProjectPathError, project_directory
from .quota import QuotaError
from .revisions import create_snapshot


class BuildIsolationError(RuntimeError):
    """Le projet demandé n'appartient pas au compte ou son chemin est sûr."""


class _ImageProviderAdapter:
    """Conserve le signal typé d'une panne image pour le repli plateforme."""

    def __init__(self, provider):
        self._provider = provider
        self.failure = None

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
        except ImageProviderError as exc:
            self.failure = exc
            raise
        except Exception as exc:
            failure = ImageProviderError(
                f"fournisseur d'image en erreur : {exc}"
            )
            self.failure = failure
            raise failure from exc
        if not isinstance(image, (bytes, bytearray, memoryview)) or not image:
            failure = ImageProviderError(
                "le fournisseur d'image n'a pas rendu des octets"
            )
            self.failure = failure
            raise failure
        return image


def _is_optional_image_failure(error):
    """Reconnaît une panne image par son contrat d'erreur, jamais son texte."""
    return isinstance(error, ImageProviderError)


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
    project = store.get_project_for_user(account_id, project_id)
    if project is None:
        raise BuildIsolationError(
            f"projet {project_id} introuvable pour le compte {account_id}"
        )
    # L'identité de main est déjà l'identifiant texte canonique du compte.
    # Le constructeur ne résout plus de registre parallèle.
    resolved_account = account_id
    if build_id is None:
        build_id = store.create_build(project["project_id"])
    else:
        existing_build = store.get_build_for_project(project["project_id"], build_id)
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
            workspace_root, resolved_account, project["project_id"], create=True
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
    warning_message = None
    try:
        if not isinstance(spec, str) or not spec.strip():
            raise ValueError("la spec doit être un texte non vide")
        spec_path.write_text(spec, encoding="utf-8")
        _capture_compile(spec_path, project_dir, say_fn)
        routed_image_provider = (
            _ImageProviderAdapter(image_provider)
            if generate_images
            else image_provider
        )
        image_failure = None
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
            image_failure = exc
        else:
            image_failure = getattr(routed_image_provider, "failure", None)
        if _is_optional_image_failure(image_failure):
            # ``generate_and_verify`` a déjà pu planifier les images avant de
            # rendre l'échec au compilateur. Repasser la spec par l'API du
            # compilateur régénère ses artefacts avec sa décision sans images;
            # la plateforme ne touche jamais au manifeste elle-même.
            _capture_compile(spec_path, project_dir, say_fn)
            warning_message = (
                "⚠️  Images demandées indisponibles : le site est livré sans "
                "images générées."
            )
            _emit(say_fn, warning_message)
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
            snapshot = create_snapshot(project_dir, build_id)
            store.finish_build(
                build_id,
                "reussie",
                warning_message=warning_message,
                snapshot_path=snapshot["path"],
                snapshot_sha256=snapshot["sha256"],
                snapshot_bytes=snapshot["bytes"],
                **usage,
            )
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
