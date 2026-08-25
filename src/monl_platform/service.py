from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
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

MAX_SPEC_BYTES = 256_000
PROJECT_ID = re.compile(r"^[0-9a-f]{32}$")


class PlatformInputError(ValueError):
    """Entrée refusée avant toute compilation."""


class PlatformNotFoundError(LookupError):
    """Projet compilé absent de l'espace de travail."""


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    summary: dict[str, Any] | None
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "summary": self.summary, "errors": self.errors}


def _bounded_spec(spec: str) -> str:
    if not isinstance(spec, str):
        raise PlatformInputError("La spécification doit être du texte UTF-8.")
    if not spec.strip():
        raise PlatformInputError("La spécification est vide.")
    if len(spec.encode("utf-8")) > MAX_SPEC_BYTES:
        raise PlatformInputError("La spécification dépasse la limite de 256 ko.")
    if "\x00" in spec:
        raise PlatformInputError("La spécification contient un octet NUL interdit.")
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
    """Façade sûre et sans état global pour le web et le serveur MCP."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None):
        default = os.environ.get("MONL_PLATFORM_WORKSPACE")
        self.workspace = Path(workspace or default or "platform-projects").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def contract_version(self) -> int:
        """La version de BASE du contrat frontend.

        Le contrat réellement émis peut valoir un cran de plus selon ce que la
        spec déclare : c'est le manifeste d'une compilation qui porte le
        chiffre exact, jamais celui-ci. Il sert à savoir contre quelle
        génération de contrat la plateforme compile, pas à dater un projet.
        """
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

    def compile(self, spec: str) -> dict[str, Any]:
        spec = _bounded_spec(spec)
        validation = self.validate(spec)
        if not validation.valid:
            raise PlatformInputError(validation.errors[0])

        project_id = uuid.uuid4().hex
        project_dir = self.workspace / project_id
        project_dir.mkdir(mode=0o700)
        spec_path = project_dir / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                compile_project(str(spec_path), str(project_dir))
            contract = json.loads(
                (project_dir / "frontend_contract.json").read_text(encoding="utf-8")
            )
        except Exception:
            # Aucun projet partiel ne devient visible : l'identifiant n'est
            # communiqué qu'après la publication complète du manifeste.
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

    def _project_dir(self, project_id: str) -> Path:
        if not PROJECT_ID.fullmatch(project_id or ""):
            raise PlatformNotFoundError("Projet introuvable.")
        directory = self.workspace / project_id
        if not (directory / "platform-manifest.json").is_file():
            raise PlatformNotFoundError("Projet introuvable.")
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
        excluded = {"backend-monl.zip", ".backend-monl.zip.tmp", ".jwt_secret"}
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.name not in excluded:
                    bundle.write(path, path.relative_to(directory))
        temporary.replace(archive)
        return archive

    def delete(self, project_id: str) -> None:
        directory = self._project_dir(project_id)
        shutil.rmtree(directory)
