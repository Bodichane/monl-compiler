"""Shared analyses are computed once, not at every query.

This witness counts CALLS and never seconds: a time threshold does not mean
the same thing on two machines (point 160), while a number of calls is
deterministic. Without the caches, a spec of this size required 270,305
rebuilds of the same foreign key index — compilation cost became cubic in
the number of entities, and a 1,668-line spec took nearly seven minutes.
"""

from monl import planning
from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string


def _spec_a_effects(n_families):
    """A spec where each family carries a counter, a composite uniqueness and
    masking: that combination makes the same analyses queried from several
    nested loops."""
    lines = ["app BancCache", "", "entity Membre", "    pseudo: String",
              "    reputation: Integer", ""]
    for i in range(n_families):
        lines += [f"entity Publication{i}", "    auteur: String",
                   "    titre: String", "    mentions: Integer", "",
                   f"entity Appreciation{i}", "    note: Integer", ""]
    lines += ["actor Membre selfRegister", ""]
    for i in range(n_families):
        lines += [f"relation Membre hasMany Publication{i}",
                   f"relation Membre hasMany Appreciation{i}",
                   f"relation Publication{i} hasMany Appreciation{i}"]
    lines.append("")
    for i in range(n_families):
        lines += [
            f"rule Publication{i}.titre required",
            f"rule Publication{i}.auteur generated",
            f"rule Publication{i}.Update ownedBy Membre",
            f"rule Appreciation{i}.Create increments Publication{i}.mentions",
            f"rule Appreciation{i}.Create oncePer Membre, Publication{i}",
            f"rule Appreciation{i}.Read ownedBy Membre",
        ]
    lines += ["", "workflow Participer for Membre"]
    for i in range(n_families):
        for action in ("Create", "Read", "Update"):
            lines.append(f"    {action} Publication{i}")
        lines += [f"    Create Appreciation{i}", f"    Read Appreciation{i}"]
    return "\n".join(lines) + "\n"


def _compiler(monkeypatch, n_families):
    """Compiles while counting the foreign key index rebuilds."""
    calls = []
    true = planning.plan_foreign_keys

    def account(relations):
        calls.append(1)
        return true(relations)

    # The replacement targets the module where the name is LOOKED UP (point
    # 153): `model.py` imports the function, so that is where it is resolved.
    from monl.generator import model
    monkeypatch.setattr(model, "plan_foreign_keys", account)

    ir = MonlAST(parse_monl_string(_spec_a_effects(n_families))).validate_and_audit()
    generator = MonlSecureGenerator(ir)
    generator.emitters.render()
    return len(calls)


def test_the_foreign_key_index_is_built_only_once(monkeypatch, capsys):
    """A single build, whatever the spec's size."""
    small = _compiler(monkeypatch, 3)
    capsys.readouterr()
    assert small == 1, (
        f"{small} index rebuilds for 3 families: the "
        "`_compute_fk_placements` cache no longer holds.")


def test_analysis_cost_does_not_follow_spec_size(monkeypatch, capsys):
    """The number of calls must not grow with the number of entities.

    That is the property that counts, and it is measured without a stopwatch:
    if the cost became proportional (or worse) to the number of entities again,
    this witness would say so on any machine.
    """
    small = _compiler(monkeypatch, 3)
    capsys.readouterr()
    grand = _compiler(monkeypatch, 24)
    capsys.readouterr()
    assert small == grand == 1, (
        f"the index is rebuilt {small} times for 3 families and {grand} times "
        "for 24: the analysis becomes proportional to the spec size again.")


def test_identity_columns_are_deduced_only_once(capsys):
    """`_identity_fk_columns` is queried by seven emitters: it memoizes.

    The content must stay identical between two queries — a cache returning
    something else on the second call would be worse than no cache.
    """
    ir = MonlAST(parse_monl_string(_spec_a_effects(4))).validate_and_audit()
    generator = MonlSecureGenerator(ir)
    capsys.readouterr()

    first = generator._identity_fk_columns()
    second = generator._identity_fk_columns()

    assert first is second, "each query redoes the deduction"
    # Every entity created by the member carries ITS account column, the
    # appreciation included — whose second incoming relation targets the
    # counted post, excluded because the client designates it (point 99).
    expected = {f"{prefix}{i}": {"membre_id"}
               for prefix in ("Publication", "Appreciation") for i in range(4)}
    assert first == expected, first
