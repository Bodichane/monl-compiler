"""Erreurs publiques du compilateur et de ses outils.

Les fonctions de bibliothèque lèvent ces exceptions ; seules les frontières
CLI les traduisent en messages et codes de sortie. Les sous-classes historiques
(``MonlSyntaxError``, ``ASTValidationError``...) restent les erreurs détaillées
que les appelants connaissent déjà.
"""


class MonlError(Exception):
    """Base commune des erreurs attendues par un appelant de MONL."""


class CompilationError(MonlError):
    """Erreur survenue dans le pipeline de compilation."""


class ParseError(CompilationError):
    """La source ne peut pas être transformée en AST brut."""


class ValidationError(CompilationError):
    """L'AST brut viole une règle du langage ou de sécurité."""


class GenerationError(CompilationError):
    """La génération d'un artefact a échoué après validation."""


class ProjectStateError(MonlError):
    """L'état ou la publication d'un projet est inexploitable."""


class ToolError(MonlError):
    """Erreur attendue d'un outil auxiliaire du CLI."""


class FrontendError(ToolError):
    """Erreur d'un fournisseur ou d'un agent frontend."""


class CompilationInputError(CompilationError):
    """La spec ou un chemin d'entrée est inexploitable."""


class CompilationGenerationError(GenerationError):
    """Version détaillée de l'échec de génération pour l'API de compilation."""
