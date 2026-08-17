"""Orchestration d'une construction de plateforme, sans interface HTTP."""

import contextlib
import io

from monl.cli import compile_project
from monl.frontend_ai import generate_and_verify
from monl.usage import UsagePriceError, build_usage_report

from .paths import ProjectPathError, project_directory
from .quota import QuotaError


class BuildIsolationError(RuntimeError):
    """Le projet demandé n'appartient pas au compte ou son chemin est sûr."""


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
):
    """Construit un projet dans le pipeline monl complet.

    ``say`` vaut ``None`` par défaut : la compilation historique de monl écrit
    sur stdout, donc sa sortie est capturée puis redirigée uniquement lorsque
    l'appelant fournit un sink. Le fournisseur est la seule dépendance IA
    injectée; compilation et re-vérification restent celles de monl.
    """
    project = store.get_project_for_account(account_id, project_id)
    if project is None:
        raise BuildIsolationError(
            f"projet {project_id} introuvable pour le compte {account_id}"
        )
    resolved_account = store.resolve_account_id(account_id)
    build_id = store.create_build(project["id"])
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
        result = generate_and_verify(str(project_dir), provider, say=say_fn)
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
