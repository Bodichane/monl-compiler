"""Contrats de l'analyse utilisable sans instancier le générateur."""

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from monl.ir import (
    AggregatedFieldIR,
    CounterRuleIR,
    DerivedFieldIR,
    FieldConstraintsIR,
    RelationIR,
    RelationModel,
    WorkflowIR,
)
from monl.planning import (
    plan_aggregations,
    plan_counters,
    plan_derivations,
    plan_foreign_keys,
    plan_relations,
    plan_routes,
)
from tests.support.cas import verifier_chaque_cas


def test_routes_qualifiees_fusionnent_sans_confondre_actions_et_fonctions():
    workflows: list[WorkflowIR] = [
        {"name": "Consulter", "actor": "Lecteur", "actions": [
            {"type": "Read", "target": "Note.titre"},
            {"type": "Read", "target": "Note.texte"},
            {"type": "Execute", "target": "Publier"},
        ]},
        {"name": "Moderer", "actor": "Admin", "actions": [
            {"type": "Read", "target": "Note"},
            {"type": "Update", "target": "Note"},
            {"type": "Execute", "target": "Archiver"},
            {"type": "Execute", "target": "Publier"},
        ]},
    ]
    original = deepcopy(workflows)

    routes = plan_routes(workflows)

    assert list(routes) == [
        ("Read", "Note"), ("Execute", "Publier"),
        ("Update", "Note"), ("Execute", "Archiver"),
    ]
    read = routes[("Read", "Note")]
    assert read.target == "Note.titre"
    assert read.base_target == "Note"
    assert read.actors == {"Lecteur", "Admin"}
    assert read.tags == ["Consulter", "Moderer"]
    assert routes[("Update", "Note")].actors == {"Admin"}
    assert routes[("Execute", "Publier")].actors == {"Lecteur", "Admin"}
    assert routes[("Execute", "Archiver")].actors == {"Admin"}
    assert workflows == original

    # Un consommateur qui modifie son plan ne contamine pas une autre analyse.
    read.allow("Intrus", "AjoutLocal")
    fresh = plan_routes(workflows)[("Read", "Note")]
    assert fresh.actors == {"Lecteur", "Admin"}
    assert fresh.tags == ["Consulter", "Moderer"]


def test_plusieurs_relations_vers_la_meme_entite_conservent_leur_orientation():
    relations: list[RelationIR] = [
        {"source": "Commande", "type": "hasMany", "target": "Ligne"},
        {"source": "Ligne", "type": "belongsTo", "target": "Produit"},
        {"source": "Compte", "type": "hasOne", "target": "Profil"},
    ]
    original = deepcopy(relations)
    models = plan_relations(relations)

    placements = plan_foreign_keys(models)

    assert placements == {
        "Ligne": [
            {"fk_column": "commande_id", "owner_entity": "Commande", "unique": False},
            {"fk_column": "produit_id", "owner_entity": "Produit", "unique": False},
        ],
        "Profil": [{"fk_column": "compte_id", "owner_entity": "Compte", "unique": True}],
    }
    assert relations == original
    placements["Ligne"][0]["owner_entity"] = "Autre"
    assert plan_foreign_keys(models)["Ligne"][0]["owner_entity"] == "Commande"


def test_une_analyse_vide_ne_cree_aucune_route_ni_relation():
    assert plan_routes([]) == {}
    assert plan_relations([]) == []
    assert plan_foreign_keys([]) == {}
    assert plan_derivations([], []) == {}
    assert plan_aggregations([], []).by_entity == {}
    assert plan_aggregations([], []).by_source == {}
    assert plan_counters([], [], {}) == {}


def test_derivation_choisit_la_source_et_non_le_parent_proprietaire():
    table = [
        RelationModel("Produit", "hasMany", "Ligne"),
        RelationModel("Produit", "hasOne", "Ligne"),
        RelationModel("Ligne", "belongsTo", "Produit"),
    ]

    def cas(source_relation):
        rule: DerivedFieldIR = {
            "entity": "Ligne", "field": "sousTotal", "source_entity": "Produit",
            "source_field": "prix", "factor": "quantite",
        }
        relations = [RelationModel("Commande", "hasMany", "Ligne"), source_relation]

        plan = plan_derivations([rule], relations)["Ligne"][0]

        assert plan.source_fk == "produit_id"
        assert plan.as_ir() == rule
        rule["source_field"] = "prixModifie"
        assert plan.source_field == "prix"
        with pytest.raises(FrozenInstanceError):
            plan.source_fk = "commande_id"
        copy = plan.as_ir()
        copy["factor"] = "autreQuantite"
        assert plan.factor == "quantite"

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_derivations_conservent_plusieurs_sources_et_lordre_des_champs():
    rules: list[DerivedFieldIR] = [
        {"entity": "Ligne", "field": "livraison", "source_entity": "Transport",
         "source_field": "tarif", "factor": "colis"},
        {"entity": "Ligne", "field": "sousTotal", "source_entity": "Produit",
         "source_field": "prix", "factor": "quantite"},
        {"entity": "AutreLigne", "field": "montant", "source_entity": "Produit",
         "source_field": "prix", "factor": "nombre"},
    ]
    plans = plan_derivations(rules, [
        RelationModel("Produit", "hasMany", "Ligne"),
        RelationModel("Transport", "hasMany", "Ligne"),
        RelationModel("AutreLigne", "belongsTo", "Produit"),
    ])

    assert list(plans) == ["Ligne", "AutreLigne"]
    assert [(plan.field, plan.source_fk, plan.factor) for plan in plans["Ligne"]] == [
        ("livraison", "transport_id", "colis"),
        ("sousTotal", "produit_id", "quantite"),
    ]
    assert plans["AutreLigne"][0].source_fk == "produit_id"


def test_derivation_refuse_une_relation_absente_ou_dans_le_mauvais_sens():
    table = [[], [RelationModel("Ligne", "hasMany", "Produit")]]

    def cas(relations):
        rule: DerivedFieldIR = {
            "entity": "Ligne", "field": "sousTotal", "source_entity": "Produit",
            "source_field": "prix", "factor": "quantite",
        }
        with pytest.raises(ValueError, match=r"aucune colonne.*'Ligne'.*'Produit'.*derivedFrom"):
            plan_derivations([rule], relations)

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_aggregation_partage_un_plan_immuable_et_selectionne_le_bon_parent():
    table = [
        RelationModel("Commande", "hasMany", "Ligne"),
        RelationModel("Commande", "hasOne", "Ligne"),
        RelationModel("Ligne", "belongsTo", "Commande"),
    ]

    def cas(parent_relation):
        rule: AggregatedFieldIR = {
            "entity": "Commande", "field": "total",
            "source_entity": "Ligne", "source_field": "sousTotal",
        }
        plans = plan_aggregations([rule], [
            RelationModel("Produit", "hasMany", "Ligne"), parent_relation,
        ])
        plan = plans.by_entity["Commande"][0]
        assert plans.by_source["Ligne"][0] is plan
        assert plan.parent_fk == "commande_id"
        assert plan.as_ir() == rule
        rule["source_field"] = "quantite"
        assert plan.source_field == "sousTotal"
        with pytest.raises(FrozenInstanceError):
            plan.parent_fk = "produit_id"
        with pytest.raises(TypeError):
            plans.by_source["Ligne"] = ()

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_aggregation_indexe_plusieurs_sommes_sans_perdre_le_declencheur():
    rules: list[AggregatedFieldIR] = [
        {"entity": "Commande", "field": "total", "source_entity": "Ligne", "source_field": "prix"},
        {"entity": "Commande", "field": "poids", "source_entity": "Colis", "source_field": "poids"},
        {"entity": "Commande", "field": "nombre", "source_entity": "Ligne", "source_field": "quantite"},
    ]
    plans = plan_aggregations(rules, [
        RelationModel("Commande", "hasMany", "Ligne"),
        RelationModel("Commande", "hasMany", "Colis"),
    ])
    assert [plan.field for plan in plans.by_entity["Commande"]] == ["total", "poids", "nombre"]
    assert [plan.field for plan in plans.by_source["Ligne"]] == ["total", "nombre"]
    assert plans.by_source["Colis"][0] is plans.by_entity["Commande"][1]


def test_aggregation_refuse_un_parent_sans_cle_etrangere_sur_lenfant():
    table = [[], [RelationModel("Ligne", "hasMany", "Commande")]]

    def cas(relations):
        rule: AggregatedFieldIR = {
            "entity": "Commande", "field": "total",
            "source_entity": "Ligne", "source_field": "sousTotal",
        }
        with pytest.raises(ValueError, match=r"aucune colonne.*'Ligne'.*'Commande'.*sumOf"):
            plan_aggregations([rule], relations)

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_compteur_resout_la_cible_et_conserve_le_plancher_zero():
    table = [
        RelationModel("Produit", "hasMany", "Ligne"),
        RelationModel("Produit", "hasOne", "Ligne"),
        RelationModel("Ligne", "belongsTo", "Produit"),
    ]

    def cas(relation):
        rule: CounterRuleIR = {
            "trigger_entity": "Ligne", "target_entity": "Produit", "target_field": "stock",
            "direction": "decrements", "amount": None, "amount_field": "quantite",
        }
        constraints: dict[tuple[str, str], FieldConstraintsIR] = {
            ("Produit", "stock"): {"min": {"portee": "valeur", "valeur": 0}},
        }
        plans = plan_counters([rule], [RelationModel("Commande", "hasMany", "Ligne"), relation], constraints)
        plan = plans["Ligne"][0]
        assert plan.target_fk == "produit_id"
        assert plan.minimum == 0
        assert plan.amount is None
        assert plan.amount_field == "quantite"
        assert plan.as_ir() == rule
        rule["amount_field"] = "autreQuantite"
        constraints[("Produit", "stock")]["min"]["valeur"] = 10
        assert plan.minimum == 0
        assert plan.amount_field == "quantite"
        with pytest.raises(FrozenInstanceError):
            plan.target_fk = "commande_id"
        with pytest.raises(TypeError):
            plans["Ligne"] = ()

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_compteurs_constants_et_variables_ne_se_confondent_pas():
    rules: list[CounterRuleIR] = [
        {"trigger_entity": "Vote", "target_entity": "Publication", "target_field": "score",
         "direction": "increments", "amount": 2, "amount_field": None},
        {"trigger_entity": "Vote", "target_entity": "Membre", "target_field": "credits",
         "direction": "decrements", "amount": None, "amount_field": "cout"},
    ]
    plans = plan_counters(rules, [
        RelationModel("Membre", "hasMany", "Vote"),
        RelationModel("Publication", "hasMany", "Vote"),
    ], {})["Vote"]
    assert [(plan.target_fk, plan.direction, plan.amount, plan.amount_field) for plan in plans] == [
        ("publication_id", "increments", 2, None),
        ("membre_id", "decrements", None, "cout"),
    ]
    assert all(plan.minimum is None for plan in plans)


def test_compteur_refuse_une_relation_absente_ou_inversee():
    table = [[], [RelationModel("Ligne", "hasMany", "Produit")]]

    def cas(relations):
        rule: CounterRuleIR = {
            "trigger_entity": "Ligne", "target_entity": "Produit", "target_field": "stock",
            "direction": "decrements", "amount": 1, "amount_field": None,
        }
        with pytest.raises(ValueError, match=r"aucune clé étrangère.*'Ligne'.*'Produit'"):
            plan_counters([rule], relations, {})

    verifier_chaque_cas([(valeur,) for valeur in table], cas)
