"""Composed facade for the historical backend emitters.

The mixins are kept as compatible implementations during the migration.
This facade nevertheless gives the orchestrator a single output contract: a
complete set of sources, ready to be written to staging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _GeneratorBackend(Protocol):
    def _generate_sql(self) -> str: ...

    def _generate_secure_fastapi(self) -> str: ...

    def _generate_ai_sandbox(self) -> str: ...

    def _generate_manage_cli(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BackendSources:
    """Complete sources produced before any disk write."""

    schema: str
    app: str
    sandbox: str
    manage: str


class BackendEmitter:
    """Composes the specialized emitters behind a single contract."""

    def __init__(self, generator: _GeneratorBackend):
        self.generator = generator

    def render(self) -> BackendSources:
        return BackendSources(
            schema=self.generator._generate_sql(),
            app=self.generator._generate_secure_fastapi(),
            sandbox=self.generator._generate_ai_sandbox(),
            manage=self.generator._generate_manage_cli(),
        )
