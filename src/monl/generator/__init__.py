"""monl generator: validated spec (AST) -> schema.sql, app.py, sandbox_ai.py.

Package born from splitting the former monolithic module of the same name.
The historical import `from generator import MonlSecureGenerator` still works."""

from .core import MonlSecureGenerator

__all__ = ["MonlSecureGenerator"]
