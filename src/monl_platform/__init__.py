"""Lightweight platform around the deterministic Monl compiler.

The platform is not a second compiler. The web and MCP both delegate to
:class:`CompilationService`, which calls Monl's public pipeline."""

from .service import CompilationService

__all__ = ["CompilationService"]

