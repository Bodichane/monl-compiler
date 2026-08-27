"""Lire une spec : nettoyage amont, parseur en cache, points d'entrée.

POINT 110 : le parseur Lark est construit UNE fois (`_get_parser`). La
construction coûtait ~50 ms et dominait le parsing ; en cache, 0,4 ms par
analyse. Ne pas le reconstruire ailleurs."""

import re

from lark import Lark

from .erreurs import _format_lark_error
from .grammaire import grammar
from .transformer import MonlIndenter, MonlTransformer

# CORRECTIF (roadmap, découvert en assemblant le réseau social anonyme,
# point 29 de docs/design_decisions.md) : une ligne de commentaire SEULE
# (rien d'autre que des espaces avant le '#') casse la fusion contiguë du
# terminal _NL -- son regex (`(\r?\n[\t ]*)+`) ne peut matcher que des
# retours à la ligne consécutifs, et le texte du commentaire interrompt
# cette contiguïté, produisant DEUX tokens _NL séparés au lieu d'un seul.
# Au niveau racine, ça laissait passer un Tree('block', []) non transformé
# (voir le correctif défensif dans app() ci-dessus) ; À L'INTÉRIEUR d'un
# bloc indenté (entity/workflow/...), ça faisait carrément échouer le
# parsing (`UnexpectedToken`), car aucune des règles `attribute+`/`action+`
# etc. n'a d'alternative pour absorber un _NL isolé.
# CORRIGÉ EN AMONT DU LEXER plutôt que règle de grammaire par règle (5
# endroits différents à corriger et tester séparément, avec le risque de
# perturber l'indenteur sur chacun) : toute ligne qui n'est QUE du
# commentaire est retirée du texte source avant même que Lark ne le voie --
# la ligne disparaît complètement, comme si elle n'avait jamais existé,
# donc la contiguïté du run de retours à la ligne qui l'entourait est
# restaurée. Les commentaires en fin de ligne réelle (ex.
# "rule Post.author hidden  # note") ne sont PAS concernés par cette regex
# (il y a du contenu non-blanc avant le '#') -- ils restent gérés par
# `%ignore COMMENT` dans la grammaire, comme avant.
_STANDALONE_COMMENT_LINE = re.compile(r"^[ \t]*#[^\n]*$")

def _strip_standalone_comment_lines(content):
    """Retire les lignes qui ne sont QUE du commentaire (voir bloc de
    commentaires ci-dessus) et retourne (texte_nettoye, table_de_lignes) où
    table_de_lignes[i] = numéro (1-based) de la ligne ORIGINALE correspondant
    à la ligne i+1 du texte nettoyé. AJOUT (roadmap, erreurs lisibles) : la
    table permet de reporter les erreurs de syntaxe sur la vraie ligne du
    fichier de l'utilisateur, pas sur la ligne du texte nettoyé."""
    kept_lines = []
    line_map = []
    for idx, line in enumerate(content.split("\n")):
        if _STANDALONE_COMMENT_LINE.match(line):
            continue
        kept_lines.append(line)
        line_map.append(idx + 1)
    return "\n".join(kept_lines), line_map


_PARSER = None


def _get_parser():
    """Le parseur Lark, construit UNE fois et réutilisé (point 110).

    Sa construction — la compilation de la grammaire LALR — coûte ~50 ms ; la
    refaire à chaque appel dominait le temps de parsing (mesuré : parseur en
    cache 0,4 ms/parse contre 50 ms en le reconstruisant). Un parseur Lark est
    réutilisable entre parses ; seul le Transformer est réinstancié à chaque
    appel, pour rester sans état."""
    global _PARSER
    if _PARSER is None:
        _PARSER = Lark(grammar, parser='lalr', postlex=MonlIndenter())
    return _PARSER


def parse_monl_string(content, file_path=None):
    """Parse une chaîne monl directement (sans passer par un fichier).
    Utilisé par parse_monl_file pour valider
    une spec générée par l'IA avant de l'écrire sur disque.
    Lève MonlSyntaxError (message localisé : fichier, ligne, colonne,
    extrait) plutôt que l'exception Lark brute."""
    from lark.exceptions import UnexpectedInput
    parser = _get_parser()
    original = content + "\n"
    stripped, line_map = _strip_standalone_comment_lines(original)
    if not stripped.endswith("\n"):
        stripped += "\n"
        line_map.append(line_map[-1] + 1 if line_map else 1)
    try:
        tree = parser.parse(stripped)
    except UnexpectedInput as err:
        raise _format_lark_error(err, original, line_map, file_path=file_path) from None
    return MonlTransformer().transform(tree)

def parse_monl_file(file_path):
    with open(file_path, encoding='utf-8') as f:
        content = f.read()
    return parse_monl_string(content, file_path=file_path)
