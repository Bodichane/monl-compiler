"""The parser: from the text of a spec to a transformed tree.

The public surface did not move when it became a package —
`parse_monl_string`, `parse_monl_file` and `MonlSyntaxError` are imported
from `monl.parser` exactly as before."""

from .errors import MonlSyntaxError
from .lark_grammar import grammar
from .reading import parse_monl_file, parse_monl_string
from .transformer import MonlIndent, MonlTransformer

__all__ = [
    "MonlIndent",
    "MonlSyntaxError",
    "MonlTransformer",
    "grammar",
    "parse_monl_file",
    "parse_monl_string",
]
