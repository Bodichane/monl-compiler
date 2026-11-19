"""Turn a Lark error into a sentence a human can read."""

import os

from ..errors import ParseError


class MonlSyntaxError(ParseError):
    """ADDED (roadmap, readable errors): monl syntax error with the line/column
    of the SOURCE FILE (not of the text stripped of comments), an excerpt of
    the faulty line, a cursor, and suggestions when Lark knows them. Before:
    the user received the raw Lark exception (UnexpectedToken with a shifted
    line number if the spec contained comment lines)."""

    def __init__(self, message, line=None, column=None, source_line=None, file_path=None):
        self.line = line
        self.column = column
        self.file_path = file_path
        parts = []
        location = ""
        if file_path:
            location = os.path.basename(file_path)
        if line is not None:
            location += f"{':' if location else 'line '}{line}"
            if column is not None:
                location += f":{column}"
        if location:
            parts.append(f"monl syntax error ({location}): {message}")
        else:
            parts.append(f"monl syntax error: {message}")
        if source_line is not None:
            parts.append(f"    {source_line}")
            if column is not None:
                parts.append("    " + " " * max(column - 1, 0) + "^")
        super().__init__("\n".join(parts))


class NombreHorsLimites(ValueError):
    """Point 204: a number the grammar accepts but no database stores
    (`1e999900` is infinity). Raised during transformation, hence wrapped by
    Lark; `reading.py` translates it into `MonlSyntaxError`."""


# Translation of the grammar's token names into the DSL's vocabulary, so that
# "expected: ..." speaks to the user rather than to the maintainer.
_TOKEN_LABELS = {
    "NAME": "a name (entity, actor, field...)",
    "TYPE": "a type (String, Integer, Boolean, Email, Float...)",
    "REFERENCE": "an Entity.field or Entity.Action reference",
    "RELATION_TYPE": "hasMany / hasOne / belongsTo",
    "_NL": "a newline",
    "_INDENT": "an indented block",
    "_DEDENT": "the end of the indented block",
    "ESCAPED_STRING": "a quoted string",
    "NUMBER": "a number",
    "$END": "the end of the file",
    "COLON": "':'",
    "COMMA": "','",
}


def _format_lark_error(err, original_content, line_map, file_path=None):
    from lark.exceptions import UnexpectedCharacters, UnexpectedToken
    from lark.indenter import DedentError
    original_lines = original_content.split("\n")
    line = getattr(err, "line", None)
    column = getattr(err, "column", None)
    real_line = None
    source_line = None
    if isinstance(line, int) and line >= 1:
        # Carries the line of the cleaned text over to the line of the original
        # file.
        real_line = line_map[line - 1] if line - 1 < len(line_map) else line
        if real_line - 1 < len(original_lines):
            source_line = original_lines[real_line - 1]
    if isinstance(err, UnexpectedToken):
        token_repr = "end of file" if err.token.type == "$END" else f"'{err.token}'"
        expected = sorted(
            {_TOKEN_LABELS.get(t, t) for t in (err.accepts or err.expected or [])}
        )
        message = f"unexpected element: {token_repr}."
        if expected:
            message += " Expected here: " + "; ".join(expected) + "."
    elif isinstance(err, DedentError):
        message = ("inconsistent indentation: this line returns to a column "
                   "where no open block begins. Align it with the block "
                   "it continues (same number of spaces as neighboring lines).")
    elif isinstance(err, UnexpectedCharacters):
        message = f"unexpected character: '{err.char}'."
    else:
        message = str(err).split("\n")[0]
    return MonlSyntaxError(message, line=real_line, column=column,
                              source_line=source_line, file_path=file_path)
