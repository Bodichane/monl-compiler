from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from monl.app_templates import TEMPLATES
from monl.ast_validator import MonlAST
from monl.cli import compile_project
from monl.errors import MonlError
from monl.frontend_contract import CONTRACT_VERSION
from monl.parser import parse_monl_file

from .hosting import SITE_LOG_FILENAME
from .paths import project_directory

MAX_SPEC_BYTES = 256_000
PROJECT_ID = re.compile(r"^[0-9a-f]{32}$")


class PlatformInputError(ValueError):
    """Input refused before any compilation."""


class PlatformNotFoundError(LookupError):
    """Compiled project missing from the workspace."""


class PlatformExecutionError(RuntimeError):
    """The compilation worker could not finish cleanly."""


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    summary: dict[str, Any] | None
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "summary": self.summary, "errors": self.errors}


def _bounded_spec(spec: str) -> str:
    if not isinstance(spec, str):
        raise PlatformInputError("The specification must be UTF-8 text.")
    if not spec.strip():
        raise PlatformInputError("The specification is empty.")
    if len(spec.encode("utf-8")) > MAX_SPEC_BYTES:
        raise PlatformInputError("The specification exceeds the 256 KB limit.")
    if "\x00" in spec:
        raise PlatformInputError("The specification contains a forbidden NUL byte.")
    return spec


def _ir_summary(ir: dict[str, Any]) -> dict[str, Any]:
    entities = ir.get("schema", {}).get("entities", {})
    if isinstance(entities, list):
        entity_names = [item.get("name", "") for item in entities]
    else:
        entity_names = list(entities)
    actors = ir.get("security", {}).get("actors", {})
    if isinstance(actors, dict):
        actor_names = list(actors)
    else:
        actor_names = [item.get("name", item) if isinstance(item, dict) else item
                       for item in actors]
    return {
        "app": ir.get("meta", {}).get("appName") or "Application Monl",
        "entities": entity_names,
        "actors": actor_names,
        "entity_count": len(entity_names),
        "actor_count": len(actor_names),
    }


def contract_summary(contract: dict[str, Any]) -> dict[str, Any]:
    entities = contract.get("entities", {})
    routes = contract.get("routes", [])
    public_routes = [route for route in routes if not route.get("auth_required", True)]
    return {
        "app": contract.get("app", "Application Monl"),
        "contract_version": contract.get("monl_contract_version"),
        "actors": contract.get("actors", []),
        "self_register_actors": contract.get("self_register_actors", []),
        "entities": [
            {
                "name": name,
                "archetype": data.get("archetype"),
                "fields": data.get("fields", []),
            }
            for name, data in entities.items()
        ],
        "routes": routes,
        "counts": {
            "actors": len(contract.get("actors", [])),
            "entities": len(entities),
            "routes": len(routes),
            "public_routes": len(public_routes),
            "business_rules": sum(
                len(value) if isinstance(value, (list, dict)) else bool(value)
                for value in contract.get("business_rules", {}).values()
            ),
        },
    }


class CompilationService:
    """Safe façade without global state for the web and the MCP server."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None):
        default = os.environ.get("MONL_PLATFORM_WORKSPACE")
        self.workspace = Path(workspace or default or "platform-projects").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def contract_version(self) -> int:
        """The BASE version of the frontend contract.

        The contract really emitted can be one notch higher depending on what the
        spec declares: it is a compilation's manifest that carries the exact
        number, never this one. It serves to know against which generation of the
        contract the platform compiles, not to date a project."""
        return CONTRACT_VERSION

    def list_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "id": str(index + 1),
                "name": template["name"],
                "description": template["hint"],
                "actors": template.get("actors", []),
                "entities": list(template.get("entities", {})),
            }
            for index, template in enumerate(TEMPLATES)
        ]

    def validate(self, spec: str) -> ValidationResult:
        spec = _bounded_spec(spec)
        with tempfile.TemporaryDirectory(prefix="monl-validation-") as directory:
            path = Path(directory) / "spec.ml"
            path.write_text(spec, encoding="utf-8")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    parsed = parse_monl_file(str(path))
                    ir = MonlAST(parsed, base_dir=directory).validate_and_audit()
            except (MonlError, ValueError) as exc:
                return ValidationResult(False, None, [str(exc)])
        return ValidationResult(True, _ir_summary(ir), [])

    def compile(self, spec: str, *, account_id: str | None = None) -> dict[str, Any]:
        """Compiles directly into the account's private folder, if authenticated.

        Local MCP without an account keeps its historical workspace. Like
        /compiler, this path calls only compiler_dans: no second isolation
        decision and no copy of the produced backend."""
        spec = _bounded_spec(spec)
        validation = self.validate(spec)
        if not validation.valid:
            raise PlatformInputError(validation.errors[0])

        project_id = uuid.uuid4().hex
        project_dir = (project_directory(self.workspace, account_id, project_id)
                       if account_id else self.workspace / project_id)
        project_dir.mkdir(mode=0o700, exist_ok=True)
        spec_path = project_dir / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        output = io.StringIO()
        try:
            output.write(compiler_in(spec_path, project_dir))
            contract = json.loads(
                (project_dir / "frontend_contract.json").read_text(encoding="utf-8")
            )
        except Exception:
            # No partial project becomes visible: the identifier is
            # communicated only after the manifest is fully published.
            shutil.rmtree(project_dir)
            raise

        manifest = {
            "id": project_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary": contract_summary(contract),
            "files": sorted(
                str(path.relative_to(project_dir))
                for path in project_dir.rglob("*")
                if path.is_file() and path.name != ".jwt_secret"
            ),
            "compiler_output": output.getvalue(),
        }
        (project_dir / "platform-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    @staticmethod
    def compiler_isolated(spec_path: Path, project_dir: Path) -> str:
        timeout = max(5, int(os.environ.get("MONL_COMPILE_TIMEOUT_SECONDS", "45")))
        command = [sys.executable, "-m", "monl.cli", "compile", str(spec_path),
                   "--output", str(project_dir)]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "timeout": timeout,
            "check": False,
        }
        if os.name == "posix":
            kwargs["preexec_fn"] = _worker_limits
        try:
            completed = subprocess.run(command, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise PlatformExecutionError(
                f"Compilation exceeded the maximum time of {timeout} seconds."
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise PlatformExecutionError(f"The compilation worker failed: {detail[-1000:]}")
        return completed.stdout

    def _project_dir(self, project_id: str) -> Path:
        if not PROJECT_ID.fullmatch(project_id or ""):
            raise PlatformNotFoundError("Project not found.")
        # Old projects and local MCP stay readable at the root. Private
        # projects are resolved on disk, without access to the accounts.
        directory = self.workspace / project_id
        candidates = list(self.workspace.glob(
            f"accounts/*/projects/{project_id}/platform-manifest.json"))
        if len(candidates) > 1:
            raise PlatformNotFoundError("Project not found.")
        if candidates:
            account_id = candidates[0].parents[2].name
            directory = project_directory(self.workspace, account_id, project_id,
                                          create=False)
        if not (directory / "platform-manifest.json").is_file():
            raise PlatformNotFoundError("Project not found.")
        return directory

    def inspect(self, project_id: str) -> dict[str, Any]:
        directory = self._project_dir(project_id)
        return json.loads(
            (directory / "platform-manifest.json").read_text(encoding="utf-8"))

    def contract(self, project_id: str) -> dict[str, Any]:
        directory = self._project_dir(project_id)
        return json.loads(
            (directory / "frontend_contract.json").read_text(encoding="utf-8"))

    def archive(self, project_id: str) -> Path:
        directory = self._project_dir(project_id)
        archive = directory / "backend-monl.zip"
        temporary = directory / ".backend-monl.zip.tmp"
        excluded = {
            "backend-monl.zip", ".backend-monl.zip.tmp", ".jwt_secret",
            SITE_LOG_FILENAME,
        }
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.name not in excluded:
                    bundle.write(path, path.relative_to(directory))
        temporary.replace(archive)
        return archive

    def delete(self, project_id: str) -> None:
        directory = self._project_dir(project_id)
        shutil.rmtree(directory)


def compiler_in(spec_path: Path, project_dir: Path) -> str:
    """Compiles a spec into a folder and returns the compiler's output.

    SINGLE SOURCE of the isolation decision (point 162): the foundation
    (``/api/compile``) and compiling an account's project (``compilation.py``)
    both go through here. Two reads of ``MONL_ISOLATE_COMPILES`` would
    eventually diverge, and the divergence would concern the only barrier that
    prevents a supplied spec from executing in the platform's interpreter."""
    output = io.StringIO()
    if os.environ.get("MONL_ISOLATE_COMPILES", "1").lower() in {"1", "true", "yes"}:
        output.write(CompilationService.compiler_isolated(spec_path, project_dir))
    else:
        with contextlib.redirect_stdout(output):
            compile_project(str(spec_path), str(project_dir))
    return output.getvalue()


def _worker_limits() -> None:
    """Bounds of the subprocess; the container stays the second boundary."""
    import resource

    cpu = max(5, int(os.environ.get("MONL_COMPILE_CPU_SECONDS", "30")))
    memory = max(256, int(os.environ.get("MONL_COMPILE_MEMORY_MB", "768"))) * 1024 * 1024
    output = max(16, int(os.environ.get("MONL_COMPILE_OUTPUT_MB", "64"))) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output, output))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
