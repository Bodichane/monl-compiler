"""Compile a project IN its private folder, without an ounce of AI.

POINT 162. It is what remains of ``builder.py`` once the frontend builder
is removed. The old ``build_project`` chained five things — quota, writing
the spec, compilation, ``generate_and_verify`` (the AI), snapshot — and
billed the last four to the platform. The direction having changed, only
the third remains: the platform compiles, the user builds their interface
at home with THEIR provider.

What this removes, and what we do not put back: the quota (there is
nothing left to bill), the build queue (a compilation lasts one second, it
does not need to be queued or tracked step by step), and the snapshot (it
dated from a time when the served folder could differ from the compiled
folder — it is now the same, see ``hosting.py``).

The compilation's isolation is the foundation's: ``compiler_isole`` runs
the compiler in a limited subprocess. The platform compiles SUPPLIED
specs, it never executes them in its own interpreter."""

from __future__ import annotations

import json

from .paths import ProjectPathError, project_directory
from .service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    compiler_dans,
)


class ProjectIsolationError(RuntimeError):
    """The requested project does not belong to the account, or its path is not
    safe."""


def compiler_le_projet(project_id, *, account_id, store, workspace_root, service=None):
    """Compiles the ``spec.ml`` of a project's private folder and returns its
    contract.

    ``service`` is used only to validate the spec before launching the
    worker: a validator refusal is an input fault (readable message), not an
    execution failure — the distinction carries the route's HTTP code."""
    project = store.get_project_for_user(account_id, project_id)
    if project is None:
        raise ProjectIsolationError(
            f"project {project_id} not found for account {account_id}"
        )
    try:
        project_dir = project_directory(
            workspace_root, account_id, project["project_id"], create=True
        )
    except ProjectPathError as exc:
        raise ProjectIsolationError(str(exc)) from exc

    spec_path = project_dir / "spec.ml"
    if not spec_path.is_file():
        raise PlatformInputError("The project specification was not found.")
    spec = spec_path.read_text(encoding="utf-8")

    validation = (service or CompilationService(workspace_root)).validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])

    sortie = compiler_dans(spec_path, project_dir)
    contrat_path = project_dir / "frontend_contract.json"
    if not contrat_path.is_file():
        raise PlatformExecutionError(
            "The compilation produced no frontend contract."
        )
    contrat = json.loads(contrat_path.read_text(encoding="utf-8"))
    return {
        "project_id": project["project_id"],
        "directory": str(project_dir),
        "contract": contrat,
        "compiler_output": sortie,
        "files": sorted(
            str(path.relative_to(project_dir))
            for path in project_dir.rglob("*")
            if path.is_file() and path.name != ".jwt_secret"
        ),
    }
