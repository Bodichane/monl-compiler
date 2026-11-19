"""The transformer, recomposed from mixins, and the indenter.

A new production is added in its family's mixin — framework, rule, or
top-level block — never here."""

from lark import Transformer, v_args
from lark.indenter import DedentError, PythonIndenter

from .transformer_blocks import BlocsMixin
from .transformer_rules import ReglesMixin
from .transformer_structure import StructureMixin


@v_args(inline=True)
class MonlTransformer(StructureMixin, ReglesMixin, BlocsMixin,
                      Transformer):
    """The Lark tree transformed into Python dictionaries.

    All productions live in the three mixins; this class only brings them
    together. The decorator stays here for form — it finds nothing left to
    wrap, each mixin having its own."""


class MonlIndenter(PythonIndenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4

    def handle_NL(self, token):
        """Point 204: Lark raises `DedentError` WITHOUT a position, and outside the
        `UnexpectedInput` family that reading translates — a line returning to a
        column no block opened reached the user raw. The token's line and column
        are attached to it so it can be located."""
        try:
            yield from super().handle_NL(token)
        except DedentError as err:
            err.line = token.end_line
            err.column = len(token.rsplit("\n", 1)[1]) + 1
            raise
