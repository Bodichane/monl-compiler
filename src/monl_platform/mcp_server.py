from __future__ import annotations

import json
import sys
from typing import Any

from .identity import IdentityStore
from .service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    PlatformNotFoundError,
)

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "monl_list_templates",
        "description": "Liste les modèles métier disponibles pour orienter une spécification Monl.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "monl_validate_spec",
        "description": "Valide une spécification Monl sans produire d'artefact.",
        "inputSchema": {
            "type": "object",
            "properties": {"spec": {"type": "string", "description": "Spécification .ml"}},
            "required": ["spec"],
            "additionalProperties": False,
        },
    },
    {
        "name": "monl_compile_backend",
        "description": "Compile une spec validée en backend déterministe et contrat frontend.",
        "inputSchema": {
            "type": "object",
            "properties": {"spec": {"type": "string", "description": "Spécification .ml"}},
            "required": ["spec"],
            "additionalProperties": False,
        },
    },
    {
        "name": "monl_inspect_contract",
        "description": "Retourne le résumé du backend et le contrat frontend complet d'une compilation.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
]


def _text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


class MCPDispatcher:
    def __init__(self, service: CompilationService, identities: IdentityStore | None = None):
        self.service = service
        self.identities = identities

    def dispatch(self, message: dict[str, Any], user_id: str | None = None) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            return None
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "monl-compiler", "version": "0.1.0"},
                    "instructions": (
                        "Utilisez Monl pour valider et compiler les règles métier. "
                        "Le frontend reste libre et consomme frontend_contract.json."
                    ),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(message.get("params") or {}, user_id)
            else:
                return self._error(request_id, -32601, f"Méthode inconnue : {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (PlatformExecutionError, PlatformInputError, PlatformNotFoundError,
                KeyError) as exc:
            return {"jsonrpc": "2.0", "id": request_id,
                    "result": _text_result(str(exc), is_error=True)}
        except Exception as exc:
            return self._error(request_id, -32603, f"Erreur interne Monl : {exc}")

    def _call_tool(self, params: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "monl_list_templates":
            return _text_result({"templates": self.service.list_templates()})
        if name == "monl_validate_spec":
            return _text_result(self.service.validate(arguments["spec"]).as_dict())
        if name == "monl_compile_backend":
            manifest = self.service.compile(arguments["spec"])
            if self.identities and user_id:
                self.identities.add_project(
                    user_id, manifest["id"], manifest["summary"]["app"])
            return _text_result({
                "project_id": manifest["id"],
                "summary": manifest["summary"],
                "download_path": f"/api/projects/{manifest['id']}/download",
                "next": "Appelez monl_inspect_contract avec project_id.",
            })
        if name == "monl_inspect_contract":
            project_id = arguments["project_id"]
            if self.identities and (not user_id or not self.identities.owns_project(
                    user_id, project_id)):
                raise PlatformNotFoundError("Projet introuvable.")
            return _text_result({
                "project": self.service.inspect(project_id),
                "contract": self.service.contract(project_id),
            })
        raise PlatformInputError(f"Outil inconnu : {name}")

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": code, "message": message}}


def run_stdio(service: CompilationService | None = None) -> None:
    """Serveur MCP stdio, une trame JSON compacte par ligne."""
    dispatcher = MCPDispatcher(service or CompilationService())
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = dispatcher.dispatch(message)
        except json.JSONDecodeError as exc:
            response = MCPDispatcher._error(None, -32700, f"JSON invalide : {exc}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
