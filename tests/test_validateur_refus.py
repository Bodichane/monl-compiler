"""What the compiler REFUSES — ast_validator.py's guard branches.

The README displays it as the fundamental difference from an AI generator: "a
rule without effect is refused at compile time rather than silently
ignored". `tests/test_parser_errors.py` covered SYNTAX errors (Lark), and
`tests/test_exploit*.py` runtime attacks. Between the two, the fifty or so
validator refusals — the exact place where this promise is kept — were
exercised by almost nothing: `ast_validator.py` capped at 76 %, and its missing
lines were overwhelmingly `raise`s.

A mute safeguard is worse than an absent one: it reassures. A `raise` nobody
reaches is a safeguard one does not know still works.

**The witnesses are part of the test.** A broken validator refusing EVERY spec
would pass a suite made only of refusals. Each family of refusals therefore
comes with the closest possible valid spec — the one differing only in what is
faulty — and that spec must compile.
"""
import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.parser import MonlSyntaxError, parse_monl_string
from tests.support.cases import check_each_case


def _valid(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# Common base: two entities, one actor, one workflow. The cases below only
# insert the rules to test, so that the faulty line is the only difference
# between a case and its witness.
BASE = """app T

entity Note
    titre: String
    score: Integer

entity Autre
    nom: String

relation Autre hasMany Note

actor Admin selfRegister

{regles}

workflow W for Admin
    Create Note
    Read Note
"""


def _base(rules):
    return BASE.format(regles=rules)


TARGETS_NONEXISTENT = [
    ("ownedBy sur une entité absente", "rule Fantome.Update ownedBy Admin",
     "'ownedBy' rule targets entity 'Fantome'"),
    ("ownedBy sur une action inventée", "rule Note.Manger ownedBy Admin",
     "invalid action 'Manger'"),
    ("public sur une entité absente", "rule Fantome.Read public",
     "'public' rule targets entity 'Fantome'"),
    ("restrictedTo sur une entité absente", "rule Fantome.titre restrictedTo Admin",
     "'restrictedTo' rule targets entity 'Fantome'"),
    ("restrictedTo sur un champ absent", "rule Note.fantome restrictedTo Admin",
     "targets field 'Note.fantome'"),
    ("writableAfterPayment sur une entité absente",
     "rule Fantome.titre writableAfterPayment Admin",
     "'writableAfterPayment' rule targets entity 'Fantome'"),
    ("writableAfterPayment sur un champ absent",
     "rule Note.fantome writableAfterPayment Admin",
     "targets field 'Note.fantome'"),
    ("hidden sur une entité absente", "rule Fantome.titre hidden",
     "'hidden' rule targets entity 'Fantome'"),
    ("hidden sur un champ absent", "rule Note.fantome hidden",
     "references field 'fantome'"),
    ("increments vers une entité absente",
     "rule Note.Create increments Fantome.score by 1",
     "references entity 'Fantome'"),
    ("increments vers un champ absent",
     "rule Note.Create increments Autre.fantome by 1",
     "targets field 'Autre.fantome'"),
    ("payable sur une entité absente", "rule Fantome.score payable",
     "'payable' rule targets entity 'Fantome'"),
    ("payable sur un champ absent", "rule Note.fantome payable",
     "field does not exist"),
]

TYPES_INCOMPATIBLES = [
    ("categorized sur un champ texte",
     'rule Note.titre categorized: "bas" below 5, "haut" otherwise',
     "Integer or Float"),
    ("generated sur un champ numérique", "rule Note.score generated",
     "must be a declared String attribute"),
    ("increments sur un champ texte",
     "rule Note.Create increments Autre.nom by 1",
     "Integer or Float attribute"),
    # Text is not charged: the only way to get an amount out of it would be to
    # convert it, hence to guess.
    ("payable sur un champ texte", "rule Note.titre payable",
     "Money, Float, or Integer"),
]

STEPS_MAL_SHAPES = [
    ("categorized sans palier de secours",
     'rule Note.score categorized: "bas" below 5, "haut" below 10',
     "'otherwise'"),
    ("categorized à seuils décroissants",
     'rule Note.score categorized: "a" below 10, "b" below 5, "c" otherwise',
     "strictly increasing"),
]

RULES_QUI_SE_CONTRADICT = [
    ("hidden et categorized sur le même champ",
     'rule Note.score hidden\nrule Note.score categorized: "bas" below 5, "haut" otherwise',
     "is both 'hidden' and 'categorized'"),
    ("hidden et generated sur le même champ",
     "rule Note.titre generated\nrule Note.titre hidden",
     "is both 'hidden' and 'generated'"),
    # An amount that cannot be read cannot be checked by whoever pays it: they
    # would pay a figure one refuses to show them.
    ("hidden et payable sur le même champ",
     "rule Note.score hidden\nrule Note.score payable",
     "both 'hidden' and 'payable'"),
]

ALL_THE_CASE = (TARGETS_NONEXISTENT + TYPES_INCOMPATIBLES
                + STEPS_MAL_SHAPES + RULES_QUI_SE_CONTRADICT)


def test_a_faulty_rule_is_refused_naming_its_cause():
    """Refusing is not enough: the message must name what is wrong. A validator
    raising a generic error would leave the spec's author searching alone, which
    is half the work the compiler exists to avoid."""
    table = [(r, f) for _n, r, f in ALL_THE_CASE]
    names = [n for n, _r, _f in ALL_THE_CASE]

    def cas(rules, fragment):
        with pytest.raises(ASTValidationError) as refusal:
            _valid(_base(rules))
        assert fragment in str(refusal.value), str(refusal.value)

    check_each_case(table, cas, ids=names)


def test_the_same_well_formed_rule_compiles():
    """The witness. Without it, a validator refusing everything would pass the
    tests above without anyone noticing."""
    table = [
        "rule Note.Read public",
        "rule Note.titre hidden",
        'rule Note.score categorized: "bas" below 5, "haut" otherwise',
        "rule Note.titre generated",
        # `payable` is NO LONGER here: since point 79 it requires a
        # server-calculated amount, hence a source entity, a relation, a
        # `required` quantity and an owner — a structure the base does not
        # carry, and adding it would break its reason for being ("the faulty
        # line is the only difference between a case and its witness"). Its
        # witness is `test_a_single_payable_field_compiles`, on the dedicated
        # spec below.
    ]
    names = ["public", "hidden", "categorized", "generated"]

    def cas(rules):
        assert _valid(_base(rules))

    check_each_case([(valeur,) for valeur in table], cas, ids=names)


# Counters have their own witness: they require a relation between the
# triggering entity and the target entity, which the base above does not carry.
SPEC_COUNTER = """app T

entity Post
    contenu: Text
    likes: Integer

entity Like
    note: String

relation Post hasMany Like

actor Membre selfRegister

{regles}

workflow W for Membre
    Create Post
    Create Like
"""


def test_a_well_formed_counter_compiles():
    """Witness of the three `increments` cases above."""
    assert _valid(SPEC_COUNTER.format(
        regles="rule Like.Create increments Post.likes by 1"))


def test_a_counter_without_relation_between_the_two_entities_is_refused():
    """Found while building the witness, not by reading the validator: without a
    relation, there is no foreign key from which to get WHICH record to
    increment. The rule would not only be ineffective — it would be ambiguous."""
    sans_relation = SPEC_COUNTER.replace("relation Post hasMany Like\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(sans_relation.format(
            regles="rule Like.Create increments Post.likes by 1"))
    assert "requires a relation" in str(refusal.value)


def test_a_counter_outside_creation_is_refused():
    """`increments` is only supported on `Create`: wiring it to `Update` would
    suggest a counter following updates."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_COUNTER.format(
            regles="rule Like.Update increments Post.likes by 1"))
    assert "'Create'" in str(refusal.value)


# --------------------------------- incompatibilities between two mechanisms --
def test_generated_requires_an_identified_caller(spec=None):
    """Point 30: no reliable identity, no derivable pseudonym. A `public` creation
    and a `generated` field on the same entity cannot coexist — and this refusal
    can only be seen by crossing two rules nothing links syntactically."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Post
    author: String
actor Membre selfRegister
rule Post.Create public
rule Post.author generated
workflow W for Membre
    Create Post
""")
    assert "'generated'" in str(refusal.value) and "'public'" in str(refusal.value)


# ---------------------------------------------- payment (point 74): the two --
# refusals requiring their own spec, since the base cannot carry them.
SPEC_PAYABLE = """app T

entity Article
    prix: Money

entity Commande
    quantite: Integer
    total: Money
    frais: Money

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

{regles}

workflow W for Client
    Create Commande
    Read Commande
"""

# What point 79 makes mandatory alongside any `payable`: an amount the client
# cannot write. The refusal cases below do NOT include it when their own
# refusal fires before (two `payable` fields, `public` creation) — their
# safeguard lives in the `payable` loop, upstream of the final cross-check.
DERIVE = "rule Commande.total derivedFrom Article.prix by quantite"


def test_a_single_payable_field_per_entity():
    """Two amounts on the same entity, and nothing says any more which one to
    charge. The compiler cannot decide in the author's place — adding would be an
    invention, taking the first a coin toss. Witness below: the same spec with a
    single `payable` compiles."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_PAYABLE.format(
            regles="rule Commande.total payable\nrule Commande.frais payable"))
    assert "multiple 'payable' fields" in str(refusal.value)


def test_a_single_payable_field_compiles():
    """The previous test's witness: without it, a validator refusing every
    `payable` rule would pass just as well. It is also, since point 79, the
    witness of the COMPLETE form a charge requires — server-calculated amount
    included."""
    assert _valid(SPEC_PAYABLE.format(
        regles=f"{DERIVE}\nrule Commande.total payable"))


def test_payable_refuses_an_amount_the_client_can_write():
    """Point 79's refusal, and the guarantee point 74 did not hold.

    `payable` promised "the amount comes from the database, never the request
    body". It was true of the ROUTE and false of the system: the creator of a
    record becomes its owner (its foreign key is filled with `current_user_id`),
    and the payment route only accepts the owner — so the payer wrote what they
    paid themselves. Two exploits of three requests were enough to charge one cent
    for 945 euros.

    The refusal is BREAKING and that is intended: every shop compiled before it
    could be robbed."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_PAYABLE.format(regles="rule Commande.total payable"))
    message = str(refusal.value)
    assert "the client can write it" in message
    # The message must name the way out, not only the problem.
    assert "derivedFrom" in message


def test_payable_requires_an_identified_caller():
    """Same reason as at point 30 for `generated`, but with money at the end: a
    `public` creation has no identity to attach the payment to — nor anyone to
    refund. This refusal only shows when crossing two rules nothing links
    syntactically."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_PAYABLE.format(
            regles="rule Commande.Create public\nrule Commande.total payable"))
    assert "'payable'" in str(refusal.value) and "'public'" in str(refusal.value)


def test_ownedby_and_accessibleby_cannot_govern_the_same_action():
    """Point 31: `accessibleBy` generalizes `ownedBy`. Combining them would leave
    two competing access checks on one route, whose application order would
    decide the result."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Msg
    corps: Text
    dest_id: Integer
entity Membre
    nom: String
relation Membre hasMany Msg
actor Membre selfRegister
rule Msg.Read ownedBy Membre
rule Msg.Read accessibleBy membre_id, dest_id
workflow W for Membre
    Read Msg
""")
    assert "ownedBy" in str(refusal.value) and "accessibleBy" in str(refusal.value)


def test_restrictedto_on_an_undeclared_actor():
    """Point 112: before, nothing checked that the actor named by 'restrictedTo'
    exists — a typo disabled the restriction silently, without any warning
    appearing."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
rule Note.titre restrictedTo Fantome
workflow W for Admin
    Read Note
""")
    assert "restrictedTo" in str(refusal.value) and "Fantome" in str(refusal.value)


def test_restrictedto_bien_forme_compile():
    """The witness: without it, a validator refusing every 'restrictedTo' would
    also pass the previous test."""
    assert _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
rule Note.titre restrictedTo Admin
workflow W for Admin
    Read Note
""")


def test_ownedby_without_matching_relation_is_refused():
    """An ownership rule without a relation to get the owner from would protect
    nothing. It is the textbook case of the "rule without effect" the README
    promises to refuse rather than ignore."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(_base("rule Note.Update ownedBy Admin"))
    assert "no compatible relationship" in str(refusal.value)


def test_two_actors_on_the_same_write_do_not_compile():
    """Point 1, the founding rule: shared authority must be declared
    (`sharedBy`), never accidental."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
actor Editeur selfRegister
workflow A for Admin
    Update Note
workflow B for Editeur
    Update Note
""")
    assert "CRITICAL_COLLISION" in str(refusal.value)


# --------------------------------------------------- workflows et blocs annexes --
def test_a_workflow_cannot_target_an_undeclared_actor():
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Inconnu
    Create Note
""")
    assert "'Inconnu'" in str(refusal.value)


def test_a_workflow_cannot_target_a_missing_entity():
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Admin
    Create Fantome
""")
    assert "'Fantome'" in str(refusal.value)


def test_execute_requires_the_custom_block_to_exist():
    """Without this refusal, `Execute` on a missing block would produce an app.py
    calling a function sandbox_ai.py does not contain — an ImportError at startup
    rather than a compile error."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Admin
    Execute CalculMagique
""")
    assert "CalculMagique" in str(refusal.value)


def test_annex_blocks_are_validated_like_rules():
    """`ui` and `seed` carry no security — but a typo going unnoticed there is
    paid at render or startup, far from its cause."""
    table = [
        ("ui Fantome\n    primary: titre", "targets an entity that does not exist"),
        ("ui Note\n    primary: fantome", "primary: fantome"),
        ("ui Note\n    order: titre, fantome", "unknown fields in 'order'"),
        ("seed Fantome\n    titre: \"a\"", "targets entity 'Fantome'"),
        ("seed Note\n    titre: \"a\", fantome: \"b\"", "references field 'fantome'"),
    ]
    names = ["ui-entité", "ui-primary", "ui-order", "seed-entité", "seed-champ"]

    def cas(block, fragment):
        with pytest.raises(ASTValidationError) as refusal:
            _valid(_base(block))
        assert fragment in str(refusal.value)

    check_each_case(table, cas, ids=names)


def test_a_well_formed_ui_block_compiles():
    """Witness of the five cases above."""
    assert _valid(_base("ui Note\n    primary: titre\n    order: titre, score"))


def test_accessibleby_with_fewer_than_two_columns_is_stopped_by_the_grammar():
    """Point 31's safeguard ("at least two distinct columns, otherwise
    `ownedBy`") is NOT in the validator: the grammar requires the comma, so a
    single column never reaches ast_validator.py. The test says so rather than
    looking for an ASTValidationError that will not come — knowing which layer
    holds a safeguard is what keeps one from moving it by mistake."""
    with pytest.raises(MonlSyntaxError):
        _valid(_base("rule Note.Read accessibleBy titre"))


def test_payable_without_field_is_stopped_by_the_grammar():
    """Same situation as above, and it must be said for the same reason:
    `ast_validator.py` carries a refusal for a `payable` rule not naming
    `Entite.champ`, but the grammar's REFERENCE terminal REQUIRES the dot. This
    `raise` is therefore unreachable, and the real safeguard is in `parser.py`.
    Letting the validator believe it holds it risks moving it there some day while
    thinking to strengthen it."""
    with pytest.raises(MonlSyntaxError):
        _valid(_base("rule Note payable"))


# ------------------------------- brique 10 : derivedFrom (point 77) ----------

# Dedicated base: a calculated entity that has an owner AND a distinct source,
# that is the minimal form the brick requires. The cases below change only one
# line at a time.
BASE_DERIVE = """app D

entity Article
    nom: String
    prix: Money

entity Commande
    quantite: Integer
    total: Money

entity Client
    displayName: String

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

{regles}

workflow Acheter for Client
    Create Commande
    Read Commande
"""


def _base_derive(rules=""):
    return BASE_DERIVE.format(regles=rules)


RULE_VALID = "rule Commande.total derivedFrom Article.prix by quantite"


def test_a_well_formed_derivation_compiles():
    """Witness of the refusals below: without it, a validator refusing EVERY
    derivation would make them all pass."""
    normalise = _valid(_base_derive(RULE_VALID))
    assert normalise["security"]["derived_fields"] == [{
        "entity": "Commande", "field": "total",
        "source_entity": "Article", "source_field": "prix",
        "factor": "quantite",
    }]


def test_malformed_derivations_are_refused():
    """A badly declared calculation must fail at COMPILE time: it is an amount to
    charge, failing at runtime would cost money."""
    table = [
        ("rule Fantome.total derivedFrom Article.prix by quantite",
         "targets entity 'Fantome'"),
        ("rule Commande.total derivedFrom Fantome.prix by quantite",
         "reads entity 'Fantome'"),
        ("rule Commande.fantome derivedFrom Article.prix by quantite",
         "field does not exist"),
        ("rule Commande.total derivedFrom Article.nom by quantite",
         "reads 'Article.nom'"),
        (RULE_VALID + "\nrule Commande.total derivedFrom Article.prix by quantite",
         "multiple 'derivedFrom' rules"),
        # `quantite` is Integer, hence acceptable both as a calculated field
        # and as a multiplier: it is the only setup that REACHES this refusal.
        # With `total` (Money), the multiplier's type check refuses first —
        # rightly, but it is not the safeguard we claim to test.
        ("rule Commande.quantite derivedFrom Article.prix by quantite",
         "cannot be its own multiplier"),
        ("rule Commande.total derivedFrom Article.prix by nom",
         "field does not exist"),
        (RULE_VALID + "\nrule Commande.total hidden",
         "is both 'hidden' and 'derivedFrom'"),
    ]
    names = ["entité-calculée-absente", "entité-source-absente", "champ-absent",
        "source-non-numérique", "deux-règles", "auto-multiplicateur",
        "multiplicateur-absent", "cumul-hidden"]

    def cas(rules, fragment):
        with pytest.raises(ASTValidationError) as refusal:
            _valid(_base_derive(rules))
        assert fragment in str(refusal.value)

    check_each_case(table, cas, ids=names)


def test_the_multiplier_must_be_declared_required():
    """Without `required`, a client omitting the quantity would make the
    calculation run on nothing — and the amount to charge would be zero or wrong."""
    spec = _base_derive(RULE_VALID).replace(
        "rule Commande.quantite required\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "required" in str(refusal.value)


def test_the_source_cannot_be_the_owner():
    """The owner's foreign key is filled from the TOKEN, never chosen by the
    client: if the source owned the entity, no row could be designated at
    creation."""
    spec = _base_derive("rule Commande.total derivedFrom Client.remise by quantite")
    spec = spec.replace("entity Client\n    displayName: String",
                        "entity Client\n    displayName: String\n    remise: Float")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "owner" in str(refusal.value)


def test_an_entity_without_owner_cannot_derive():
    """The owner is what distinguishes the foreign key filled by the server from
    the one the client provides to designate the row to read."""
    spec = _base_derive(RULE_VALID).replace(
        "rule Commande.Read ownedBy Client\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "owner" in str(refusal.value)


def test_a_source_without_relation_is_refused():
    """Without a relation, nothing says WHICH source row to read — same
    requirement as for 'increments' (point 27)."""
    spec = _base_derive(RULE_VALID).replace(
        "relation Article hasMany Commande\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "requires a relation" in str(refusal.value)


# ------------------------- ownership: the chain must lead back to an ACCOUNT -
#
# Point 80 then 81. `ownedBy <Entity>` originally compiled silently, producing
# inconsistent code: a foreign key announced towards the accounts table, the
# caller's id written in place of the requested attachment, a read filter
# comparing a record id with an account id. Point 80 refused it; point 81 made
# it a brick (TRANSITIVE ownership), on one condition: the chain must end at an
# actor. What follows checks the cases where it does not.

SPEC_OWNERSHIP = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne

actor Client selfRegister

{regles}

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""

CHAINE_COMPLETE = "rule Commande.Read ownedBy Client"


def test_an_ownership_chain_leading_to_an_actor_compiles():
    """The brick itself (point 81): "a line belongs to whoever owns its order".
    The witness of all the refusals below — without it, a validator refusing every
    chain would pass them all."""
    assert _valid(SPEC_OWNERSHIP.format(
        regles=CHAINE_COMPLETE + "\nrule Ligne.Read ownedBy Commande"))


def test_an_intermediate_without_owner_leads_to_no_account():
    """Without `ownedBy` on the intermediate, nothing links the line to an
    account: the server would have no column to compare. It is the exact case
    point 80 had found compiling."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_OWNERSHIP.format(regles="rule Ligne.Read ownedBy Commande"))
    message = str(refusal.value)
    assert "does not lead to ANY actor" in message
    # The message must say what is missing, not only what is wrong.
    assert "ownedBy" in message


def test_a_two_level_chain_is_now_resolved():
    """BRICK 24 (point 107): this case was REFUSED ("more than one level"), the
    generated join only going up one link. The walk now goes up the full depth to
    an actor, link by link. Point 80's defect class does NOT reappear for all
    that: cycle, dead end and ambiguous link stay refused (dedicated tests in
    tests/test_transitive_profondeur.py), and depth 2 is tested against a real
    server in the same file."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Detail
    note: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Ligne hasMany Detail

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Detail.Read ownedBy Ligne

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Create Detail
    Read Detail
"""
    ast = _valid(spec)
    transitive = ast["security"]["transitive_ownership"]
    assert transitive["Ligne"] == {"chain": ["Commande"], "actor": "Client"}
    assert transitive["Detail"] == {"chain": ["Ligne", "Commande"], "actor": "Client"}


def test_an_intermediate_with_two_owners_makes_the_chain_ambiguous():
    """Two owners on the intermediate: the server would not know which one to
    check. Choosing by the spec's writing order is exactly what beta 3's fix had
    already refused elsewhere."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Vendeur hasMany Commande
relation Commande hasMany Ligne

actor Client selfRegister
actor Vendeur

rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Vendeur
rule Ligne.Read ownedBy Commande

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne

workflow V for Vendeur
    Update Commande
"""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "is ambiguous at" in str(refusal.value)


def test_mixing_direct_and_transitive_ownership_is_refused():
    """The ownership column would be both filled from the token (for one rule)
    and provided by the client (for the other): two contradictory treatments on a
    single column."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Client hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Client

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Update Ligne
"""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "Designate only one owner" in str(refusal.value)


def test_payable_on_a_transitively_owned_entity_now_compiles():
    """POINT 87: this case was REFUSED (point 81), and the refusal was lifted.

    It did not protect from an impossibility but from a wrong comparison: the
    payment route compared `current_user_id` with a foreign key that, under a
    transitive chain, carries an intermediate record id. Brick 11 already provided
    the join returning the ACCOUNT id — the route uses it.

    This test therefore guards the opposite of what it guarded. The three refusals
    that make `payable` safe are checked elsewhere and have not moved: chain
    leading back to an actor (point 81), amount not computable by the client
    (point 79), mandatory incoming relation (point 75)."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    statut: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Ligne.sousTotal payable

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    ast = _valid(spec)
    assert ast["security"]["payable_fields"] == [{"entity": "Ligne", "field": "sousTotal"}]
    assert ast["security"]["transitive_ownership"]["Ligne"] == {"chain": ["Commande"], "actor": "Client"}


def test_transitive_payable_still_requires_an_amount_the_client_cannot_compute():
    """The witness of the test above: lifting point 81's refusal does NOT lift
    point 79's. Without `derivedFrom`, the payer would still write what they pay —
    and transitive ownership changes nothing, since a line's creator must own the
    order they attach it to."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    statut: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal payable

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "the client can write it" in str(refusal.value)


# ------------------------- aggregation: summing a total (brick 12) -----------
#
# Point 82. `derivedFrom` only reads ONE linked row: an order with several
# items did not know what it cost. `sumOf` sums it. The refusal carrying
# everything else is the last of this section: summing an amount the client
# writes would give the payer back control over what they pay — point 77's
# flaw, back through the cart, exactly as point 80's scoping feared.

SPEC_CART = """app P

entity Article
    prix: Money

entity Commande
    total: Money
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
{regles}

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""

SOMME = "rule Commande.total sumOf Ligne.sousTotal"


def test_a_well_formed_sum_compiles():
    """The witness of this whole section: without it, a validator refusing every
    `sumOf` rule would pass each of the refusals below."""
    assert _valid(SPEC_CART.format(regles=SOMME))


def test_a_summed_cart_is_chargeable():
    """Point 82, and the outcome of points 77 to 81: until now, `payable` only
    accepted a `derivedFrom` field, hence a ONE-item order. A summed total is
    calculated by the server, so it satisfies point 79's refusal."""
    assert _valid(SPEC_CART.format(
        regles=SOMME + "\nrule Commande.total payable"))


# ---------------- supervised write after payment -----------------------------

SPEC_AFTER_PAYMENT = SPEC_CART.replace(
    "    libelle: String", "    libelle: String\n    statut: String\n    creeLe: DateTime\n"
    "    reference: String\n    quantite: Integer\n    calcule: Money"
).replace(
    "relation Client hasMany Commande",
    "relation Client hasMany Commande\nrelation Article hasMany Commande"
).replace(
    "actor Client selfRegister", "actor Client selfRegister\nactor Superviseur"
)


def _after_payment(rules):
    base = (SOMME + "\nrule Commande.total payable"
            "\nrule Commande.quantite required")
    return SPEC_AFTER_PAYMENT.format(regles=base + "\n" + rules)


def test_writable_after_payment_on_undeclared_actor_is_refused():
    with pytest.raises(ASTValidationError) as refusal:
        _valid(_after_payment(
            "rule Commande.statut writableAfterPayment Fantome"))
    assert "writableAfterPayment" in str(refusal.value)
    assert "Fantome" in str(refusal.value)


def test_writable_after_payment_requires_a_payable_entity():
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_CART.format(
            regles=SOMME
            + "\nrule Commande.libelle writableAfterPayment Client"))
    assert "only applies to a 'payable' entity" in str(refusal.value)


def test_writable_after_payment_refuses_a_server_written_field():
    table = [
        "rule Commande.statut generated",
        "rule Commande.calcule derivedFrom Article.prix by quantite",
        "rule Commande.creeLe timestamp",
        'rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"',
    ]
    names = ["generated", "derivedFrom", "timestamp", "numbered"]

    def cas(rule_server):
        target = {
            "generated": "statut",
            "derivedFrom": "calcule",
            "timestamp": "creeLe",
            "numbered": "reference",
        }[rule_server.split()[2]]
        spec = _after_payment(
            rule_server
            + f"\nrule Commande.{target} writableAfterPayment Superviseur")
        with pytest.raises(ASTValidationError) as refusal:
            _valid(spec)
        assert "writableAfterPayment" in str(refusal.value)
        assert rule_server.split()[2] in str(refusal.value)

    check_each_case([(valeur,) for valeur in table], cas, ids=names)


def test_writable_after_payment_refuses_a_summed_field():
    """`sumOf` was missing from the list of server families above: a 'payable'
    entity whose amount is 'sumOf' (the multi-line cart, the only form tested
    since point 82 for a chargeable total) could declare 'writableAfterPayment'
    on THAT SAME field. The resulting dedicated route writes the total to the
    database without recalculation AND without the payment lock — exactly the flaw
    of points 77/82 reopened by a combination of rules nothing reported at compile
    time."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(_after_payment(
            "rule Commande.total writableAfterPayment Superviseur"))
    assert "writableAfterPayment" in str(refusal.value)
    assert "sumOf" in str(refusal.value)


def test_writable_after_payment_refuses_the_owner():
    with pytest.raises(ASTValidationError) as refusal:
        _valid(_after_payment(
            "rule Commande.statut writableAfterPayment Client"))
    assert "who already owns 'Commande'" in str(refusal.value)


def test_writable_after_payment_refuses_two_actors_per_entity():
    spec = _after_payment(
        "actor AutreSuperviseur\n"
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment AutreSuperviseur")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    assert "Superviseur" in str(refusal.value)
    assert "AutreSuperviseur" in str(refusal.value)


def test_writable_after_payment_refuses_a_duplicate_field():
    rule = "rule Commande.statut writableAfterPayment Superviseur"
    with pytest.raises(ASTValidationError) as refusal:
        _valid(_after_payment(rule + "\n" + rule))
    assert "multiple 'writableAfterPayment' rules are declared" in str(refusal.value)


def test_well_formed_writable_after_payment_compiles_and_normalizes():
    ast = _valid(_after_payment(
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment Superviseur"))
    assert ast["security"]["writable_after_payment"] == {
        "Commande": {
            "actor": "Superviseur",
            "fields": ["statut", "libelle"],
        }
    }


def test_writable_after_payment_breaks_neither_create_nor_update(tmp_path):
    """A field absent from the generic schema must never be read on `data`.

    CodexShop's real checkout otherwise revealed an AttributeError even before the
    order was inserted: the tracking fields, reserved to the supervisor,
    legitimately do not exist yet at creation.
    """
    from monl.generator import MonlSecureGenerator

    spec = _after_payment(
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment Superviseur")
    spec = spec.replace(
        "rule Commande.Read ownedBy Client",
        "rule Commande.Read ownedBy Client\nrule Commande.Update ownedBy Client",
    ).replace("    Read Commande\n", "    Read Commande\n    Update Commande\n")
    ast = _valid(spec)
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    generated = (tmp_path / "app.py").read_text(encoding="utf-8")
    creation = generated.split("def create_commande(", 1)[1].split("@app.", 1)[0]
    modification = generated.split("def update_commande(", 1)[1].split("@app.", 1)[0]

    assert "data.statut" not in creation
    assert "data.libelle" not in creation
    assert "data.statut" not in modification
    assert "data.libelle" not in modification
    assert "if enregistrement[1] != 'payee':" in generated
    assert "only after the payment is confirmed" in generated


def test_malformed_sum_refusals():
    table = [
        ("rule Fantome.total sumOf Ligne.sousTotal", "does not exist"),
        ("rule Commande.total sumOf Fantome.sousTotal", "does not exist"),
        ("rule Commande.libelle sumOf Ligne.sousTotal", "Money, Float, or Integer"),
        ("rule Commande.absent sumOf Ligne.sousTotal", "field does not exist"),
        # The whole sentence: this branch read "must be a attribut Money…"
        # while every case only checked its tail.
        ("rule Commande.total sumOf Ligne.quantiteAbsente",
         "which must be a declared Money, Float, or Integer attribute "
         "(received: field does not exist)"),
        # An entity cannot sum itself.
        ("rule Commande.total sumOf Commande.total", "cannot sum itself"),
        # Without a parent-child relation, the sum would cover the whole table.
        ("rule Commande.total sumOf Article.prix", "parent-child relation"),
    ]

    def cas(rule, expected):
        with pytest.raises(ASTValidationError) as refusal:
            _valid(SPEC_CART.format(regles=rule))
        assert expected in str(refusal.value)

    check_each_case(table, cas)


def test_a_hidden_sum_is_refused():
    """Same reason as for `payable` and `derivedFrom`: a total that cannot be read
    cannot be checked by whoever pays it."""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_CART.format(
            regles=SOMME + "\nrule Commande.total hidden"))
    assert "hidden" in str(refusal.value) and "sumOf" in str(refusal.value)


def test_two_competing_calculations_on_the_same_field_are_refused():
    """`derivedFrom` reads ONE linked row, `sumOf` adds up children. Both on the
    same field are two writes contradicting each other.

    Dedicated spec: to REACH this cross-check, the `derivedFrom` rule must itself
    be valid (linked source entity, `required` Integer multiplier on the
    calculated entity). My first try put it on the common spec, where `Commande`
    has no multiplier: the factor check answered, and the test proved nothing about
    the cross-check."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    total: Money
    quantite: Integer

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Article hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Commande.quantite required
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total sumOf Ligne.sousTotal

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec)
    message = str(refusal.value)
    assert "has both 'derivedFrom' and 'sumOf'" in message
    assert "choose one" in message


def test_two_sums_on_the_same_field_are_refused():
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_CART.format(regles=SOMME + "\n" + SOMME))
    assert "only one sum is allowed per field" in str(refusal.value)


def test_summing_an_entity_without_owner_is_refused():
    """Without a declared owner on the line, the column linking it to its order
    can receive an ACCOUNT id (see _identity_fk_columns) and the sum would be
    recalculated on the wrong parent. And a line without an owner could be created
    by anyone: a third party's total would become movable at will.

    The sum here covers `Ligne.quantite`, an ORDINARY field, and the spec also
    loses its `derivedFrom` rule: on `Ligne.sousTotal`, `derivedFrom`'s owner
    requirement (point 78) answered first, and the test validated another brick's
    guard."""
    spec = (SPEC_CART
            .replace("rule Ligne.Read ownedBy Commande\n", "")
            .replace("rule Ligne.sousTotal derivedFrom Article.prix by quantite\n", ""))
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec.format(regles="rule Commande.total sumOf Ligne.quantite"))
    message = str(refusal.value)
    assert "has no owner" in message
    assert "ownedBy" in message


def test_charging_a_sum_of_client_written_amounts_is_refused():
    """THE brick's refusal — point 77's flaw closed before it comes back through
    the cart.

    A `sumOf` field is calculated by the server, so it satisfies point 79's
    refusal. But adding up lines whose amount comes from the client does not
    produce a safe total: it produces a total the client controls, with one more
    addition. The payer regains control over what they pay.

    The refusal lives in the cross-check with `payable`, and not in the `sumOf`
    loop, because summing a client field stays legitimate outside payment:
    `Commande.nbArticles sumOf Ligne.quantite` counts items, it charges nothing.
    The COMBINATION is at fault, not the sum."""
    spec = SPEC_CART.replace(
        "rule Ligne.sousTotal derivedFrom Article.prix by quantite\n", "")
    with pytest.raises(ASTValidationError) as refusal:
        _valid(spec.format(regles=SOMME + "\nrule Commande.total payable"))
    message = str(refusal.value)
    assert "which the client can write" in message
    # The message must name the faulty line and suggest the fix.
    assert "Ligne.sousTotal" in message
    assert "derivedFrom" in message


def test_summing_a_client_field_stays_allowed_outside_payment():
    """The witness of the refusal above: the combination with `payable` is
    forbidden, not the sum of a client-provided field. Counting a cart's items is
    legitimate and charges nothing."""
    spec = SPEC_CART.replace("entity Commande\n    total: Money",
                               "entity Commande\n    total: Money\n    nbArticles: Integer")
    assert _valid(spec.format(
        regles="rule Commande.nbArticles sumOf Ligne.quantite"))


# Issue #89: a counter on an entity named like an actor. Its rows are linked to
# no account, while the `membre_id` keys a client reads carry an ACCOUNT id:
# measured on 03_reseau_social, reporting a post's author lowered the
# reporter's reputation.
SPEC_COUNTER_ACTOR = """app T

entity {cible}
    nom: String
    reputation: Integer

entity Signalement
    motif: String

relation {cible} hasMany Signalement

actor Membre selfRegister

rule Signalement.Create decrements {cible}.reputation by 10

workflow W for Membre
    Create {cible}
    Create Signalement
"""


def test_a_counter_on_an_actor_entity_is_refused():
    with pytest.raises(ASTValidationError) as refusal:
        _valid(SPEC_COUNTER_ACTOR.format(cible="Membre"))
    assert "is also an actor" in str(refusal.value)


def test_the_same_counter_on_a_business_entity_compiles():
    """Witness: only the target's name changes, and the rule compiles."""
    assert _valid(SPEC_COUNTER_ACTOR.format(cible="Profil"))
