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


def _spec_a_effets(n_familles):
    """A spec where each family carries a counter, a composite uniqueness and
    masking: that combination makes the same analyses queried from several
    nested loops."""
    lignes = ["app BancCache", "", "entity Membre", "    pseudo: String",
              "    reputation: Integer", ""]
    for i in range(n_familles):
        lignes += [f"entity Publication{i}", "    auteur: String",
                   "    titre: String", "    mentions: Integer", "",
                   f"entity Appreciation{i}", "    note: Integer", ""]
    lignes += ["actor Membre selfRegister", ""]
    for i in range(n_familles):
        lignes += [f"relation Membre hasMany Publication{i}",
                   f"relation Membre hasMany Appreciation{i}",
                   f"relation Publication{i} hasMany Appreciation{i}"]
    lignes.append("")
    for i in range(n_familles):
        lignes += [
            f"rule Publication{i}.titre required",
            f"rule Publication{i}.auteur generated",
            f"rule Publication{i}.Update ownedBy Membre",
            f"rule Appreciation{i}.Create increments Publication{i}.mentions",
            f"rule Appreciation{i}.Create oncePer Membre, Publication{i}",
            f"rule Appreciation{i}.Read ownedBy Membre",
        ]
    lignes += ["", "workflow Participer for Membre"]
    for i in range(n_familles):
        for action in ("Create", "Read", "Update"):
            lignes.append(f"    {action} Publication{i}")
        lignes += [f"    Create Appreciation{i}", f"    Read Appreciation{i}"]
    return "\n".join(lignes) + "\n"


def _compiler(monkeypatch, n_familles):
    """Compiles while counting the foreign key index rebuilds."""
    appels = []
    vrai = planning.plan_foreign_keys

    def account(relations):
        appels.append(1)
        return vrai(relations)

    # The replacement targets the module where the name is LOOKED UP (point
    # 153): `modele.py` imports the function, so that is where it is resolved.
    from monl.generator import modele
    monkeypatch.setattr(modele, "plan_foreign_keys", account)

    ir = MonlAST(parse_monl_string(_spec_a_effets(n_familles))).validate_and_audit()
    generateur = MonlSecureGenerator(ir)
    generateur.emitters.render()
    return len(appels)


def test_the_foreign_key_index_is_built_only_once(monkeypatch, capsys):
    """A single build, whatever the spec's size."""
    petit = _compiler(monkeypatch, 3)
    capsys.readouterr()
    assert petit == 1, (
        f"{petit} reconstructions de l'index pour 3 familles : le cache de "
        "`_compute_fk_placements` ne porte plus.")


def test_analysis_cost_does_not_follow_spec_size(monkeypatch, capsys):
    """The number of calls must not grow with the number of entities.

    That is the property that counts, and it is measured without a stopwatch:
    if the cost became proportional (or worse) to the number of entities again,
    this witness would say so on any machine.
    """
    petit = _compiler(monkeypatch, 3)
    capsys.readouterr()
    grand = _compiler(monkeypatch, 24)
    capsys.readouterr()
    assert petit == grand == 1, (
        f"l'index est reconstruit {petit} fois pour 3 familles et {grand} fois "
        "pour 24 : l'analyse redevient proportionnelle à la taille de la spec.")


def test_identity_columns_are_deduced_only_once(capsys):
    """`_identity_fk_columns` is queried by seven emitters: it memoizes.

    The content must stay identical between two queries — a cache returning
    something else on the second call would be worse than no cache.
    """
    ir = MonlAST(parse_monl_string(_spec_a_effets(4))).validate_and_audit()
    generateur = MonlSecureGenerator(ir)
    capsys.readouterr()

    premier = generateur._identity_fk_columns()
    second = generateur._identity_fk_columns()

    assert premier is second, "chaque interrogation refait la déduction"
    # Every entity created by the member carries ITS account column, the
    # appreciation included — whose second incoming relation targets the
    # counted post, excluded because the client designates it (point 99).
    attendu = {f"{prefixe}{i}": {"membre_id"}
               for prefixe in ("Publication", "Appreciation") for i in range(4)}
    assert premier == attendu, premier
