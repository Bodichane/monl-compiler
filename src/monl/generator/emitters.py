"""Façade composée pour les émetteurs backend historiques.

Les mixins restent conservés comme implémentations compatibles pendant la
migration. Cette façade donne toutefois à l'orchestrateur un seul contrat de
sortie : un jeu complet de sources, prêt à être écrit dans le staging.
"""

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
    """Sources complètes produites avant toute écriture disque."""

    schema: str
    app: str
    sandbox: str
    manage: str


class BackendEmitter:
    """Compose les émetteurs spécialisés derrière un contrat unique."""

    def __init__(self, generator: _GeneratorBackend):
        self.generator = generator

    def render(self) -> BackendSources:
        return BackendSources(
            schema=self.generator._generate_sql(),
            app=self.generator._generate_secure_fastapi(),
            sandbox=self.generator._generate_ai_sandbox(),
            manage=self.generator._generate_manage_cli(),
        )
