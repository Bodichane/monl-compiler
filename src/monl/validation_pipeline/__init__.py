"""The validation driver: the ORDER in which refusals apply.

Each pass names the validator method it triggers. It is this precedence
that made splitting the validator obvious at point 152: the boundaries
already existed, written here.

The public surface did not move when it became a package."""

from .contrats import ValidationPipeline
from .defaut import DEFAULT_VALIDATION_PIPELINE

__all__ = [
    "DEFAULT_VALIDATION_PIPELINE",
    "ValidationPipeline",
]
