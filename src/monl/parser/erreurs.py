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
            parts.append(f"Erreur de syntaxe monl ({location}) : {message}")
        else:
            parts.append(f"Erreur de syntaxe monl : {message}")
        if source_line is not None:
            parts.append(f"    {source_line}")
            if column is not None:
                parts.append("    " + " " * max(column - 1, 0) + "^")
        super().__init__("\n".join(parts))


# Traduction des noms de tokens de la grammaire vers le vocabulaire du DSL,
# pour que "attendu : ..." parle à l'utilisateur plutôt qu'au mainteneur.
_TOKEN_LABELS = {
    "NAME": "un nom (entité, acteur, champ...)",
    "TYPE": "un type (String, Integer, Boolean, Email, Float...)",
    "REFERENCE": "une référence Entite.champ ou Entite.Action",
    "RELATION_TYPE": "hasMany / hasOne / belongsTo",
    "_NL": "un retour à la ligne",
    "_INDENT": "un bloc indenté",
    "_DEDENT": "la fin du bloc indenté",
    "ESCAPED_STRING": "une chaîne entre guillemets",
    "NUMBER": "un nombre",
    "$END": "la fin du fichier",
    "COLON": "':'",
    "COMMA": "','",
}


def _format_lark_error(err, original_content, line_map, file_path=None):
    from lark.exceptions import UnexpectedCharacters, UnexpectedToken
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
        token_repr = "fin de fichier" if err.token.type == "$END" else f"'{err.token}'"
        expected = sorted(
            {_TOKEN_LABELS.get(t, t) for t in (err.accepts or err.expected or [])}
        )
        message = f"élément inattendu : {token_repr}."
        if expected:
            message += " Attendu ici : " + " ; ".join(expected) + "."
    elif isinstance(err, UnexpectedCharacters):
        message = f"caractère inattendu : '{err.char}'."
    else:
        message = str(err).split("\n")[0]
    return MonlSyntaxError(message, line=real_line, column=column,
                              source_line=source_line, file_path=file_path)
