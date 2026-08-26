"""Plateforme légère autour du compilateur déterministe Monl.

La plateforme n'est pas un second compilateur. Le web et MCP délèguent tous
deux à :class:`CompilationService`, qui appelle le pipeline public de Monl.
"""

from .service import CompilationService

__all__ = ["CompilationService"]

