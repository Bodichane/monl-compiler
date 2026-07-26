"""Générateur monl : spec validée (AST) -> schema.sql, app.py, sandbox_ai.py.

Package issu du découpage de l'ancien module monolithique du même nom.
L'import historique `from generator import MonlSecureGenerator` reste valide.
"""

from .core import MonlSecureGenerator

__all__ = ["MonlSecureGenerator"]
