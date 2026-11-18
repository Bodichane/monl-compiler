"""The home page demo: a spec that compiles FOR REAL.

Before this module, the "PetiteBoutique" card announced 3 entities, 17
routes and 12 files, listed a `README.md`, and stated in so many words
that "the metrics below are verified by recompiling the spec in the
tests".

Measured: no test compiled this spec, `PetiteBoutique` existed nowhere in
the code, the displayed fragment could not compile (no `app`, no `actor`,
no `workflow`), and of the three figures two were wrong — 14 routes and 15
files. It is the defect of point 164, where the `/mcp` page announced four
nonexistent tools because the list was written by hand; worse, since the
page here claimed a verification that did not exist.

The spec below is therefore the REAL one: `tests/test_platform_landing.py`
compiles it and compares each figure and each file name of the tree with
the result. The page can no longer name a file the compiler does not
produce.

The excerpt shown on screen is CUT from this spec, never copied next to
it: two texts to keep in agreement always diverge."""

from __future__ import annotations

#: It compiles. The `required` on the multiplier is not decorative: the
#: compiler REFUSES `derivedFrom` without it (point 77), and writing it here
#: shows precisely what the page promises — an inconsistent rule is refused.
SPEC_VITRINE = """app LittleShop

entity Product
    name: String
    price: Money
    stock: Integer

entity Order
    total: Money
    placedAt: DateTime

entity OrderLine
    quantity: Integer
    amount: Money

actor Customer selfRegister

relation Customer hasMany Order
relation Order hasMany OrderLine
relation Product hasMany OrderLine

rule Product.price min 0
rule Product.stock min 0
rule Product.Read public
rule Order.Read ownedBy Customer
rule OrderLine.Read ownedBy Order
rule OrderLine.quantity required
rule OrderLine.amount derivedFrom Product.price by quantity
rule Order.total sumOf OrderLine.amount
rule Order.placedAt timestamp
rule Order.total payable
rule OrderLine.Create decrements Product.stock by quantity

workflow Buy for Customer
    Create Order
    Create OrderLine
    Read Product
    Read Order
"""

#: The displayed excerpt: everything concerning ONE entity, cut from the real
#: spec. The cut is made by what the lines CONCERN and not by position bounds —
#: a line number shifts at the first added rule, silently, and the excerpt
#: would then show something else.
ENTITE_MONTREE = "Product"


def extrait_affiche() -> str:
    """The entity block and its rules, taken from `SPEC_VITRINE`.

    FAILS rather than returning an empty string: an excerpt that cannot be
    found would show an empty frame, which looks like a styling defect and
    not like a spec that changed shape."""
    lignes = SPEC_VITRINE.splitlines()
    bloc, dans_entite = [], False
    for ligne in lignes:
        if ligne.startswith(f"entity {ENTITE_MONTREE}"):
            dans_entite = True
            bloc.append(ligne)
        elif dans_entite and ligne.startswith((" ", "\t")):
            bloc.append(ligne)
        elif dans_entite and not ligne.strip():
            dans_entite = False
        elif ligne.startswith(f"rule {ENTITE_MONTREE}."):
            bloc.append(ligne)
    regles = [ligne for ligne in bloc if ligne.startswith("rule ")]
    if not regles or len(bloc) == len(regles):
        raise AssertionError(
            f"empty excerpt or no rule for {ENTITE_MONTREE}: the spec has "
            "changed shape, the card would show an empty frame")
    champs = [ligne for ligne in bloc if ligne not in regles]
    return "\n".join(champs) + "\n\n" + "\n".join(regles)


#: The figures the card announces. They are here to be COMPARED: the witness
#: compiles `SPEC_VITRINE` and requires equality, so correcting them by hand
#: without recompiling turns the suite red.
ENTITES = 3
ROUTES = 14
FICHIERS = 15

#: The tree shown. Each name must exist in the produced archive — that is what
#: the witness checks, and it is the whole point of this module. The list stays
#: a readable EXCERPT: fifteen lines are not shown in a card.
ARBRE = (
    ("app.py", "API FastAPI"),
    ("schema.sql", "database"),
    ("frontend_contract.json", "permissions and routes"),
    ("manage.py", "administration"),
    # `README.md` was already in the original mockup — but the compiler did not
    # produce it, so the card promised a missing file. It has existed since
    # point 176: the line becomes true again, and it is the witness that allows
    # it rather than a reread.
    ("README.md", "getting started"),
)
