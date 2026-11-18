"""Typed SQL emission — the generator's security boundary (point 108).

WHY IT EXISTS. Brick 24 (point 107) shipped an access check that
answered 500 on every creation: a client-supplied value
(`data.<fk>`) had been pasted into the SQL TEXT instead of being bound as a
parameter. The fix took two lines, but the *possibility* of the defect
remained — any caller could pass a value as a text fragment again. This
module removes it at the root.

INVARIANT, single and impossible to bypass: a VALUE enters a query only
through `bind()`, which emits it as a `?` and keeps aside the Python
expression that will bind it. No function here places a value in the SQL
text — there is literally no API for it. An identifier (table, column)
enters only through `ident()`, double-quoted and refused if it itself
contains a quote (a validated entity or column never does).

A `Sql` fragment carries its TEXT (fixed SQL where each value is a `?`) and
its PARAMETERS: the ORDERED list of Python source expressions that the
generated code will pass to `cursor.execute`, in the order the `?` appear.
Fragments are composed with `cat`, never mutated. By construction, a
fragment's number of `?` always equals its number of parameters."""


class Sql:
    """A SQL fragment and its bound parameters. `text` is fixed SQL where each
    value is a `?`; `params` is the ordered list of Python source expressions
    to bind, in the order the `?` appear."""

    __slots__ = ("params", "text")

    def __init__(self, text, params=()):
        self.text = text
        self.params = tuple(params)


def kw(text):
    """FIXED SQL: keywords, punctuation, parentheses, internal aliases. Refuses a
    `?` — a parameter is written only with `bind()`, so that no value can slip
    into a fragment believed to have no parameter."""
    if "?" in text:
        raise ValueError("A '?' is written only with bind(), never inside kw()")
    return Sql(text)


def ident(name):
    """SQL identifier (table, column) in double quotes. Refuses an inner quote
    rather than escaping it silently: a validated entity or column never
    carries one, and guessing the escape would hide an upstream divergence."""
    if '"' in name:
        raise ValueError(f"Invalid SQL identifier: {name!r} contains a quote")
    return Sql(f'"{name}"')


def bind(py_expr):
    """THE ONLY entry point for a value: `?` in the text, `py_expr` (Python
    source) kept for binding. `py_expr` is the expression the generated code
    will evaluate at runtime (e.g. `data.commande_id`, `current_user_id`,
    `named_row.get('commande_id')`)."""
    py_expr = py_expr.strip()
    if not py_expr:
        raise ValueError("bind() requires a non-empty Python expression")
    return Sql("?", (py_expr,))


def cat(*frags):
    """Concatenates fragments: texts end to end, parameters in the order the `?`
    appear."""
    return Sql(
        "".join(f.text for f in frags),
        tuple(p for f in frags for p in f.params),
    )


def _check(query):
    # Safeguard: by construction the number of '?' equals the number of
    # parameters; checking it at emission time makes it impossible to publish
    # an
    # unbalanced query if a builder were ever written wrong.
    if query.text.count("?") != len(query.params):
        raise ValueError(
            f"Unbalanced query: {query.text.count('?')} '?' for "
            f"{len(query.params)} parameter(s) — {query.text!r}")


def params_tuple(query):
    """The parameter tuple, as Python source, as written in the generated code's
    `cursor.execute`: `(expr1, expr2, )`, or `()` if none."""
    _check(query)
    return "(" + "".join(p + ", " for p in query.params) + ")"


def execute_args(query, prefix="", suffix=""):
    """Returns the pair (SQL literal, parameter tuple literal) ready to write
    into `cursor.execute(...)`. `prefix`/`suffix` frame the text (e.g.
    `prefix='SELECT '`). Text and parameters leave TOGETHER from a single
    object: the caller can no longer separate them — which is what allowed the
    point 107 defect."""
    _check(query)
    return repr(prefix + query.text + suffix), params_tuple(query)
