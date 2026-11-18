"""Public errors of the compiler and its tools.

Library functions raise these exceptions; only the CLI boundaries turn
them into messages and exit codes. The historical subclasses
(``MonlSyntaxError``, ``ASTValidationError``...) stay the detailed errors
callers already know."""


class MonlError(Exception):
    """Common base of the errors a MONL caller expects."""


class CompilationError(MonlError):
    """Error raised in the compilation pipeline."""


class ParseError(CompilationError):
    """The source cannot be turned into a raw AST."""


class ValidationError(CompilationError):
    """The raw AST violates a language or security rule."""


class GenerationError(CompilationError):
    """Generating an artifact failed after validation."""


class ProjectStateError(MonlError):
    """A project's state or publication is unusable."""


class ToolError(MonlError):
    """Expected error from a CLI helper tool."""


class FrontendError(ToolError):
    """Error from a provider or a frontend agent."""


class CompilationInputError(CompilationError):
    """The spec or an input path is unusable."""


class CompilationGenerationError(GenerationError):
    """Detailed version of the generation failure for the compilation API."""
