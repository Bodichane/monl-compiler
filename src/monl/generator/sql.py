"""Émission SQL typée — la frontière de sécurité du générateur (point 108).

RAISON D'ÊTRE. La brique 24 (point 107) a livré un contrôle d'accès qui
répondait 500 à chaque création : une valeur fournie par le client
(`data.<fk>`) avait été collée dans le TEXTE SQL au lieu d'être liée en
paramètre. Le correctif tenait en deux lignes, mais la *possibilité* du défaut
restait — n'importe quel appelant pouvait repasser une valeur comme fragment de
texte. Ce module la supprime à la racine.

INVARIANT, unique et non contournable : une VALEUR n'entre dans une requête que
par `bind()`, qui l'émet comme un `?` et retient à part l'expression Python qui
la liera. Aucune fonction ici ne place une valeur dans le texte SQL — il
n'existe littéralement pas d'API pour le faire. Un identifiant (table, colonne)
n'entre que par `ident()`, mis entre guillemets doubles et refusé s'il contient
lui-même un guillemet (une entité ou une colonne validée n'en porte jamais).

Un fragment `Sql` porte son TEXTE (du SQL fixe où chaque valeur est un `?`) et
ses PARAMÈTRES : la liste ORDONNÉE des expressions Python source que le code
généré passera à `cursor.execute`, dans l'ordre d'apparition des `?`. On compose
des fragments avec `cat`, on ne les mute pas. Par construction, le nombre de `?`
d'un fragment égale toujours le nombre de ses paramètres.
"""


class Sql:
    """Un fragment SQL et ses paramètres liés. `text` est du SQL fixe où chaque
    valeur est un `?` ; `params` est la liste ordonnée des expressions Python
    source à lier, dans l'ordre d'apparition des `?`."""

    __slots__ = ("params", "text")

    def __init__(self, text, params=()):
        self.text = text
        self.params = tuple(params)


def kw(text):
    """SQL FIXE : mots-clés, ponctuation, parenthèses, alias internes. Refuse un
    `?` — un paramètre ne s'écrit qu'avec `bind()`, pour qu'aucune valeur ne
    puisse se glisser dans un fragment réputé sans paramètre."""
    if "?" in text:
        raise ValueError("Un '?' ne s'écrit qu'avec bind(), jamais dans kw()")
    return Sql(text)


def ident(name):
    """Identifiant SQL (table, colonne) entre guillemets doubles. Refuse un
    guillemet interne plutôt que de l'échapper en silence : une entité ou une
    colonne validée n'en porte jamais, et deviner l'échappement masquerait une
    divergence en amont."""
    if '"' in name:
        raise ValueError(f"Identifiant SQL invalide : {name!r} contient un guillemet")
    return Sql(f'"{name}"')


def bind(py_expr):
    """LA SEULE porte d'entrée d'une valeur : `?` dans le texte, `py_expr`
    (source Python) retenu pour la liaison. `py_expr` est l'expression que le
    code généré évaluera à l'exécution (ex. `data.commande_id`,
    `current_user_id`, `named_row.get('commande_id')`)."""
    py_expr = py_expr.strip()
    if not py_expr:
        raise ValueError("bind() exige une expression Python non vide")
    return Sql("?", (py_expr,))


def cat(*frags):
    """Concatène des fragments : textes bout à bout, paramètres dans l'ordre
    d'apparition des `?`."""
    return Sql(
        "".join(f.text for f in frags),
        tuple(p for f in frags for p in f.params),
    )


def _check(query):
    # Garde-fou : par construction le nombre de '?' égale le nombre de
    # paramètres ; le vérifier au moment de l'émission rend impossible de
    # publier une requête déséquilibrée si un builder venait à être mal écrit.
    if query.text.count("?") != len(query.params):
        raise ValueError(
            f"Requête déséquilibrée : {query.text.count('?')} '?' pour "
            f"{len(query.params)} paramètre(s) — {query.text!r}")


def params_tuple(query):
    """Le tuple de paramètres, en source Python, tel qu'on l'écrit dans
    `cursor.execute` du code généré : `(expr1, expr2, )`, ou `()` si aucun."""
    _check(query)
    return "(" + "".join(p + ", " for p in query.params) + ")"


def execute_args(query, prefix="", suffix=""):
    """Rend le couple (littéral SQL, littéral tuple de paramètres) prêt à écrire
    dans `cursor.execute(...)`. `prefix`/`suffix` encadrent le texte (ex.
    `prefix='SELECT '`). Texte et paramètres sortent ENSEMBLE d'un seul objet :
    l'appelant ne peut plus les désolidariser — c'est ce qui a permis le défaut
    du point 107."""
    _check(query)
    return repr(prefix + query.text + suffix), params_tuple(query)
