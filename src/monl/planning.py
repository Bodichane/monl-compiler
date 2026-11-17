"""Analyse pure des workflows, relations et dérivations déjà validés.

Les plans ne dépendent ni des émetteurs, ni du système de fichiers. L'ordre
de déclaration est conservé pour stabiliser les routes, leurs tags et le SQL.
Chaque appel crée ses propres conteneurs sans modifier l'IR d'entrée.
"""

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .ir import (
    AggregatedFieldIR,
    AggregatePlan,
    AggregationPlans,
    CounterPlan,
    CounterRuleIR,
    DerivedFieldIR,
    DerivedPlan,
    FieldConstraintsIR,
    ForeignKeyPlacement,
    RelationIR,
    RelationModel,
    RoutePlan,
    WorkflowIR,
)


def plan_routes(workflows: Sequence[WorkflowIR]) -> dict[tuple[str, str], RoutePlan]:
    """Fusionne les droits CRUD par entité et les Execute par cible complète."""
    routes: dict[tuple[str, str], RoutePlan] = {}
    for workflow in workflows:
        for action in workflow["actions"]:
            kind = action["type"]
            target = action["target"]
            base_target = target.split(".", 1)[0]
            key = (kind, target if kind == "Execute" else base_target)
            if key not in routes:
                routes[key] = RoutePlan(
                    action=kind, key=key[1], target=target, base_target=base_target,
                    actors=set(), tags=[],
                )
            routes[key].allow(workflow["actor"], workflow["name"])
    return routes


def plan_relations(relations: Sequence[RelationIR]) -> list[RelationModel]:
    """Oriente les relations de l'IR sans état de générateur intermédiaire."""
    return [RelationModel(source=relation["source"], kind=relation["type"],
                          target=relation["target"]) for relation in relations]


def plan_foreign_keys(
    relations: Sequence[RelationModel],
) -> dict[str, list[ForeignKeyPlacement]]:
    """Place les clés du côté enfant ; hasOne ajoute la contrainte d'unicité."""
    placements: dict[str, list[ForeignKeyPlacement]] = {}
    for relation in relations:
        placements.setdefault(relation.held_entity, []).append({
            "fk_column": relation.fk_column,
            "owner_entity": relation.owner_entity,
            "unique": relation.unique,
        })
    return placements


def _foreign_key_index(relations: Sequence[RelationModel]) -> dict[tuple[str, str], str]:
    """Index (enfant, parent) commun aux analyses des champs calculés."""
    foreign_keys: dict[tuple[str, str], str] = {}
    for entity, placements in plan_foreign_keys(relations).items():
        for placement in placements:
            foreign_keys.setdefault(
                (entity, placement["owner_entity"]), placement["fk_column"])
    return foreign_keys


def plan_derivations(
    fields: Sequence[DerivedFieldIR], relations: Sequence[RelationModel],
) -> dict[str, tuple[DerivedPlan, ...]]:
    """Résout une fois la clé de la ligne source de chaque calcul.

    L'IR est déjà validée. Une relation absente indique une divergence entre
    validation et analyse : on refuse de produire un calcul sans ligne source.
    Les règles sont copiées dans des plans immuables, dans l'ordre déclaré.
    """
    foreign_keys = _foreign_key_index(relations)
    plans: dict[str, list[DerivedPlan]] = {}
    for rule in fields:
        entity, source = rule["entity"], rule["source_entity"]
        fk = foreign_keys.get((entity, source))
        if fk is None:
            raise ValueError(
                f"Generation: no foreign-key column on '{entity}' references "
                f"'{source}', although the validator required it "
                f"for 'derivedFrom'.")
        plans.setdefault(entity, []).append(DerivedPlan(
            entity=entity, field=rule["field"], source_entity=source,
            source_field=rule["source_field"], factor=rule["factor"], source_fk=fk,
        ))
    return {entity: tuple(values) for entity, values in plans.items()}


def plan_aggregations(
    fields: Sequence[AggregatedFieldIR], relations: Sequence[RelationModel],
) -> AggregationPlans:
    """Résout les sommes par parent et par événement sur une ligne enfant."""
    foreign_keys = _foreign_key_index(relations)
    by_entity: dict[str, list[AggregatePlan]] = {}
    by_source: dict[str, list[AggregatePlan]] = {}
    for rule in fields:
        entity, source = rule["entity"], rule["source_entity"]
        fk = foreign_keys.get((source, entity))
        if fk is None:
            raise ValueError(
                f"Generation: no foreign-key column on "
                f"'{source}' references '{entity}', although "
                "the validator required it for 'sumOf'.")
        plan = AggregatePlan(
            entity=entity, field=rule["field"], source_entity=source,
            source_field=rule["source_field"], parent_fk=fk,
        )
        by_entity.setdefault(entity, []).append(plan)
        by_source.setdefault(source, []).append(plan)
    return AggregationPlans(
        by_entity=MappingProxyType({key: tuple(values) for key, values in by_entity.items()}),
        by_source=MappingProxyType({key: tuple(values) for key, values in by_source.items()}),
    )


def plan_counters(
    rules: Sequence[CounterRuleIR], relations: Sequence[RelationModel],
    constraints: Mapping[tuple[str, str], FieldConstraintsIR],
) -> Mapping[str, tuple[CounterPlan, ...]]:
    """Résout les effets de stock et de réputation indépendamment des routes."""
    foreign_keys = _foreign_key_index(relations)
    plans: dict[str, list[CounterPlan]] = {}
    for rule in rules:
        trigger, target = rule["trigger_entity"], rule["target_entity"]
        fk = foreign_keys.get((trigger, target))
        if fk is None:
            raise ValueError(
                f"Generation: no foreign key on '{trigger}' references "
                f"'{target}', although the counter effect requires it.")
        bound = constraints.get((target, rule["target_field"]), {}).get("min")
        plans.setdefault(trigger, []).append(CounterPlan(
            trigger_entity=trigger, target_entity=target, target_field=rule["target_field"],
            amount=rule["amount"], amount_field=rule["amount_field"], direction=rule["direction"],
            target_fk=fk, minimum=bound["valeur"] if bound is not None else None,
        ))
    return MappingProxyType({entity: tuple(values) for entity, values in plans.items()})
