"""The parser: from the text of a spec to a transformed tree.

The public surface did not move when it became a package —
`parse_monl_string`, `parse_monl_file` and `MonlSyntaxError` are imported
from `monl.parser` exactly as before."""

from .erreurs import MonlSyntaxError
from .grammaire import grammar
from .lecture import parse_monl_file, parse_monl_string
from .transformer import MonlIndenter, MonlTransformer

__all__ = [
    "MonlIndenter",
    "MonlSyntaxError",
    "MonlTransformer",
    "grammar",
    "parse_monl_file",
    "parse_monl_string",
]
