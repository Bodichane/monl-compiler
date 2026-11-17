"""Traduire une erreur Lark en phrase lisible par un humain."""

import os

from ..errors import ParseError


class MonlSyntaxError(ParseError):
    """AJOUT (roadmap, erreurs lisibles) : erreur de syntaxe monl avec
    ligne/colonne du FICHIER SOURCE (pas du texte nettoyé des commentaires),
    extrait de la ligne fautive, curseur, et suggestions quand Lark les
    connaît. Avant : l'utilisateur recevait l'exception Lark brute
    (UnexpectedToken avec numéro de ligne décalé si la spec contenait des
    lignes de commentaire)."""

    def __init__(self, message, line=None, column=None, source_line=None, file_path=None):
        self.line = line
        self.column = column
        self.file_path = file_path
        parts = []
        location = ""
        if file_path:
            location = os.path.basename(file_path)
        if line is not None:
            location += f"{':' if location else 'ligne '}{line}"
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
    """Point 204 : un nombre que la grammaire accepte mais qu'aucune base ne
    stocke (`1e999900` vaut l'infini). Levé pendant la transformation, donc
    enveloppé par Lark ; `lecture.py` le traduit en `MonlSyntaxError`."""


# Traduction des noms de tokens de la grammaire vers le vocabulaire du DSL,
# pour que "attendu : ..." parle à l'utilisateur plutôt qu'au mainteneur.
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
        # Reporte la ligne du texte nettoyé sur la ligne du fichier original.
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
