"""Le transformateur, recomposé par mixins, et l'indenteur.

Une production nouvelle s'ajoute dans le mixin de sa famille — charpente,
règle, ou bloc de premier niveau — jamais ici."""

from lark import Transformer, v_args
from lark.indenter import PythonIndenter

from .transformer_blocs import BlocsMixin
from .transformer_regles import ReglesMixin
from .transformer_structure import StructureMixin


@v_args(inline=True)
class MonlTransformer(StructureMixin, ReglesMixin, BlocsMixin,
                      Transformer):
    """L'arbre Lark transformé en dictionnaires Python.

    Toutes les productions vivent dans les trois mixins ; cette classe
    ne fait que les réunir. Le décorateur reste ici pour la forme —
    il ne trouve plus rien à envelopper, chaque mixin ayant le sien.
    """


class MonlIndenter(PythonIndenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4
