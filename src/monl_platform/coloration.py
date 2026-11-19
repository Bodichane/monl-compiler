"""Syntax highlighting of a monl specification, on the SERVER side.

There was nothing to highlight on the home page, and elsewhere the
`<span>`s were written BY HAND in the strings — hence two classes in all,
`.kw` and `.cm`, and the same gold for every keyword of every spec, on
every page. That is what brought the accent color back everywhere.

**No keyword is written here.** The three tables are DERIVED from the
terminals of the real grammar (`monl.parser.lark_grammar.grammar`): a brick
that adds a keyword sees it highlighted without anyone thinking of it, and
a word that leaves the grammar stops being highlighted. A copied list
would have diverged at the first journal point — it is the reproach of
point 146, applied to highlighting.

Rendering is done on the server, without a line of JavaScript: a page
that runs nothing already shows the highlighted code, and the platform
adds no highlighting dependency."""

from __future__ import annotations

import html
import re

from monl.parser.lark_grammar import grammar


def _terminal(nom: str) -> frozenset:
    """The literal alternatives of a grammar terminal.

    Fails rather than returning an empty set: a renamed terminal would
    otherwise leave a whole family of words without color, silently — and
    missing highlighting does not look like a failure."""
    trouve = re.search(rf"^\s*{nom}:\s*(.+)$", grammar, re.M)
    if not trouve:
        raise RuntimeError(f"terminal {nom} not found in the grammar")
    alternatives = frozenset(re.findall(r'"([^"]+)"', trouve.group(1)))
    if not alternatives:
        raise RuntimeError(f"terminal {nom} has no literal alternative")
    return alternatives


TYPES = _terminal("TYPE")
ACTIONS = _terminal("ACTION_TYPE") | {"Execute"}   # Execute lives outside the terminal
VALIDATIONS = _terminal("VALIDATION_TYPE")
RELATIONS = _terminal("RELATION_TYPE")

# All the rest of the grammar's literals are keywords. Taking the complement
# rather than a list guarantees no word slips through: a new keyword is
# highlighted the day it enters the grammar.
_LITTERAUX = frozenset(re.findall(r'"([a-zA-Z][a-zA-Z_]{1,24})"', grammar))
MOTS_CLES = _LITTERAUX - TYPES - ACTIONS

_MOTIF = re.compile(
    r"""(?P<commentaire>\#[^\n]*)
      | (?P<chaine>"[^"\n]*")
      | (?P<nombre>\b\d+(?:\.\d+)?\b)
      | (?P<mot>[A-Za-z_][A-Za-z0-9_]*)""",
    re.VERBOSE,
)

_CLASSES = {
    "commentaire": "s-cm",
    "chaine": "s-str",
    "nombre": "s-num",
}


def _classe_du_mot(mot: str) -> str | None:
    if mot in TYPES:
        return "s-type"
    if mot in ACTIONS:
        return "s-act"
    if mot in VALIDATIONS or mot in RELATIONS or mot in MOTS_CLES:
        return "s-kw"
    # A capitalized identifier is a DECLARED name (entity, actor, workflow).
    # The rest — field names, free values — keeps the block's ink: highlighting
    # everything no longer distinguishes anything.
    if mot[:1].isupper():
        return "s-nom"
    return None


def coloriser(source: str) -> str:
    """Renders a monl specification as highlighted, escaped HTML.

    Escaping happens HERE and not before: the text is walked raw, and each
    piece is escaped at the moment it is written. Escaping first would make
    the string pattern see `&quot;`, and it would no longer recognize
    anything."""
    morceaux, position = [], 0
    for trouve in _MOTIF.finditer(source):
        morceaux.append(html.escape(source[position:trouve.start()]))
        genre = trouve.lastgroup
        texte = trouve.group()
        classe = _CLASSES.get(genre) or _classe_du_mot(texte)
        morceaux.append(f'<span class="{classe}">{html.escape(texte)}</span>'
                        if classe else html.escape(texte))
        position = trouve.end()
    morceaux.append(html.escape(source[position:]))
    return "".join(morceaux)


def en_lignes(source: str) -> str:
    """The same highlighting, rendered with `<br>` rather than in a `<pre>`.

    The hero's terminal is not a preformatted block: it carried its OWN
    highlighting, in gold `<b>`, hence a third place where gold marked every
    keyword. One more function is better than one more convention."""
    lignes = []
    for ligne in coloriser(source).split("\n"):
        # All the leading WHITESPACE, whatever it is: outside a `<pre>`
        # consecutive spaces collapse into one, and the spec's indentation
        # would disappear without a sound.
        creux = len(ligne) - len(ligne.lstrip(" "))
        lignes.append("&nbsp;" * creux + ligne[creux:])
    return "<br>".join(lignes)


def bloc(source: str, classes: str = "codeblock") -> str:
    """A complete `<pre>`, ready to place in a page."""
    return f'<pre class="{classes}"><code>{coloriser(source)}</code></pre>'
