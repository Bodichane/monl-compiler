"""Le parseur : du texte d'une spec à un arbre transformé.

La surface publique n'a pas bougé en devenant un paquet — `parse_monl_string`,
`parse_monl_file` et `MonlSyntaxError` s'importent depuis `monl.parser`
exactement comme avant."""

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
