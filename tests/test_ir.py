"""Unit tests of the typed intermediate representation."""

from monl.ast_validator import MonlAST
from monl.frontend_contract.assemblage import build_contract
from monl.generator import MonlSecureGenerator
from monl.ir import AccessPolicy, EffectPlan, RelationModel, RoutePlan
from monl.parser import parse_monl_string

SPEC = """app Plans

entity Note
    titre: String

actor Auteur selfRegister
actor Admin

workflow Ecrire for Auteur
    Create Note
    Read Note

workflow Superviser for Admin
    Read Note
"""


def test_route_plan_merges_actors_and_workflows_without_duplicates(tmp_path):
    ir = MonlAST(parse_monl_string(SPEC)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    plans = generator._compute_route_map()
    lecture = plans[("Read", "Note")]

    assert isinstance(lecture, RoutePlan)
    assert lecture.action == "Read"
    assert lecture.key == "Note"
    assert lecture.target == "Note"
    assert lecture.base_target == "Note"
    assert lecture.actors == {"Auteur", "Admin"}
    assert lecture.tags == ["Ecrire", "Superviser"]


def test_execute_route_plan_keeps_the_qualified_target(tmp_path):
    spec = SPEC.replace(
        "workflow Superviser for Admin\n    Read Note",
        "custom Publier\n    description: \"Publie une note\"\n"
        "    input: id: Integer\n    output: ok: Boolean\n\n"
        "workflow Superviser for Admin\n    Execute Publier",
    )
    ir = MonlAST(parse_monl_string(spec)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    plan = generator._compute_route_map()[("Execute", "Publier")]

    assert plan.key == "Publier"
    assert plan.target == "Publier"
    assert plan.actors == {"Admin"}


def test_entity_model_consolidates_field_policies(tmp_path):
    spec = """app Politiques

entity Note
    titre: String
    statut: String
    auteur: String
    interne: Text
    creeLe: DateTime

actor Auteur selfRegister

rule Note.titre unique
rule Note.statut oneOf "brouillon", "publiée"
rule Note.auteur generated
rule Note.interne hidden
rule Note.creeLe timestamp

workflow Ecrire for Auteur
    Create Note
    Read Note
"""
    ir = MonlAST(parse_monl_string(spec)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    note = generator.entity_models["Note"]

    assert note.name == "Note"
    assert note.fields["titre"].constraints.unique is True
    assert note.fields["statut"].allowed_values == ("brouillon", "publiée")
    assert note.fields["auteur"].server_generated
    assert note.fields["interne"].hidden_in_reads
    assert note.fields["creeLe"].timestamped
    assert note.fields["creeLe"].server_generated


def test_relation_models_orient_the_three_relation_types(tmp_path):
    spec = """app Relations

entity Parent
    nom: String
entity Enfant
    nom: String
entity Profil
    nom: String
entity Adresse
    ville: String

relation Parent hasMany Enfant
relation Parent hasOne Profil
relation Adresse belongsTo Parent

actor Admin

workflow Gerer for Admin
    Read Parent
"""
    ir = MonlAST(parse_monl_string(spec)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    beaucoup, unique, inverse = generator.relation_models

    assert isinstance(beaucoup, RelationModel)
    assert (beaucoup.owner_entity, beaucoup.held_entity) == ("Parent", "Enfant")
    assert beaucoup.fk_column == "parent_id"
    assert not beaucoup.unique
    assert (unique.owner_entity, unique.held_entity) == ("Parent", "Profil")
    assert unique.unique
    assert (inverse.owner_entity, inverse.held_entity) == ("Parent", "Adresse")
    assert inverse.fk_column == "parent_id"

    placements = generator._compute_fk_placements()
    assert placements["Enfant"] == [{
        "fk_column": "parent_id", "owner_entity": "Parent", "unique": False,
    }]
    assert placements["Profil"][0]["unique"] is True
    assert placements["Adresse"][0]["owner_entity"] == "Parent"


def test_access_policy_reunit_visibilite_acteurs_et_propriete(tmp_path):
    spec = """app Acces

entity Auteur
    nom: String
entity Note
    titre: String
entity Page
    titre: String

relation Auteur hasMany Note

actor Auteur selfRegister

rule Note.Read ownedBy Auteur
rule Page.Read public

workflow Consulter for Auteur
    Read Note
    Read Page
"""
    ir = MonlAST(parse_monl_string(spec)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    prive = generator.access_policies[("Note", "Read")]
    public = generator.access_policies[("Page", "Read")]

    assert isinstance(prive, AccessPolicy)
    assert prive.actors == frozenset({"Auteur"})
    assert prive.owner_entity == "Auteur"
    assert not prive.public
    assert not prive.party_fields
    assert public.public
    assert public.owner_entity is None


def test_effect_plans_catalog_business_effects(tmp_path):
    spec = """app Effets

entity Produit
    prix: Money
    stock: Integer
entity Commande
    total: Money
entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Ligne.quantite required
rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.sousTotal derivedFrom Produit.prix by quantite
rule Ligne.Create decrements Produit.stock by quantite
rule Commande.total sumOf Ligne.sousTotal
rule Commande.total payable

workflow Acheter for Client
    Create Commande
    Create Ligne
    Read Commande
    Read Ligne
"""
    ir = MonlAST(parse_monl_string(spec)).validate_and_audit()
    generator = MonlSecureGenerator(ir, output_dir=str(tmp_path))

    kinds = {plan.kind for plan in generator.effect_plans}

    assert {"derive", "aggregate", "decrement", "payment_lock"} <= kinds
    assert all(isinstance(plan, EffectPlan) for plan in generator.effect_plans)
    aggregate = generator._effects("aggregate", trigger="Ligne")[0]
    assert aggregate.target_entity == "Commande"
    assert aggregate.field == "total"
    assert aggregate.source_field == "sousTotal"
    assert generator._derived_field_names("Ligne") == ["sousTotal"]
    assert generator._aggregated_field_names("Commande") == ["total"]

    # Backend and contract share the same resolved derivation plan.
    derived = generator.derived_by_entity["Ligne"][0]
    assert derived.source_fk == "produit_id"
    assert generator.compilation_plans.entity_models["Ligne"].fields[
        "sousTotal"].derived_rule is derived
    sources = generator.emitters.render()
    contract = build_contract(ir, generator.compilation_plans)
    subtotal = next(field for field in contract["entities"]["Ligne"]["fields"]
                    if field["name"] == "sousTotal")
    assert subtotal["derived_from"] == "Produit.prix"
    assert subtotal["derived_factor"] == "quantite"
    aggregation = generator.aggregated_by_entity["Commande"][0]
    assert generator.aggregations_by_source["Ligne"][0] is aggregation
    assert generator.compilation_plans.entity_models["Commande"].fields[
        "total"].aggregate_rule is aggregation
    total = next(field for field in contract["entities"]["Commande"]["fields"]
                 if field["name"] == "total")
    assert total["summed_from"] == "Ligne.sousTotal"
    counter = generator.reputation_rules_by_trigger["Ligne"][0]
    assert generator.compilation_plans.reputation_rules_by_trigger["Ligne"][0] is counter
    assert counter.target_fk == "produit_id"

    # The analysis is a snapshot: changing the raw rule after construction
    # cannot make the two emitters diverge nor change the published
    # calculation.
    ir["security"]["derived_fields"][0]["source_field"] = "autrePrix"
    ir["security"]["derived_fields"][0]["factor"] = "autreQuantite"
    ir["security"]["aggregated_fields"][0]["source_field"] = "autreSomme"
    ir["security"]["reputation_rules"][0]["amount_field"] = "autreQuantite"
    assert generator.emitters.render() == sources
    assert build_contract(ir, generator.compilation_plans) == contract
