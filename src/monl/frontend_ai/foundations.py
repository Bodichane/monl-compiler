"""What the whole package reads, and which reads nothing back."""

from ..errors import FrontendError

ALLOWED_EXTENSIONS = (".html", ".css", ".js", ".svg", ".json")

MAX_TOTAL_BYTES = 2_000_000

# The two EVOLUTION briefs (as opposed to FRONTEND_PROMPT.md, which describes a
# new build). Named here rather than at their producer: frontend_ai is what
# consumes them, and cli.py imports them — the reverse would make the AI layer
# depend on the command layer.
UPDATE_PROMPT_FILENAME = "docs/FRONTEND_UPDATE_PROMPT.md"

RETOUCH_PROMPT_FILENAME = "FRONTEND_RETOUCHE_PROMPT.md"

class FrontendAIError(FrontendError):
    pass

class _ChunkOutputLimitError(FrontendAIError):
    """A retry is impossible: the model still cuts off at the ceiling."""

class _ChunkGenerationError(FrontendAIError):
    """A file's local retries are exhausted.

    This error must never trigger the second full generation: the previous
    files have already been paid for and the faulty file has already had its
    targeted retries."""
