"""Politiques de champs et d'accès, indépendantes du rendu SQL et HTTP."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .ir import (
    AccessPolicy,
    AggregatePlan,
    DerivedPlan,
    EntityFields,
    EntityModel,
    FieldBound,
    FieldConstraints,
    FieldConstraintsIR,
    FieldPolicy,
    NumberingPlan,
    PublicCondition,
    RoutePlan,
    SecurityIR,
    TransitiveOwnership,
    UploadPlan,
)

FieldKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _FieldDirectives:
    generated: frozenset[FieldKey]
    hidden: frozenset[str]
    categorized: frozenset[FieldKey]
    timestamped: frozenset[FieldKey]
    postpayment: frozenset[FieldKey]
    numbered: Mapping[FieldKey, NumberingPlan]
    uploads: Mapping[FieldKey, UploadPlan]


def event_counter_fields(security: SecurityIR) -> frozenset[FieldKey]:
    """Point 202 : événements constants uniquement, jamais un budget réglable."""
    events: set[FieldKey] = set()
    budgets: set[FieldKey] = set()
    for rule in security.get("reputation_rules", []):
        key = (rule["target_entity"], rule["target_field"])
        if rule["direction"] == "increments" and not rule.get("amount_field"):
            events.add(key)
        else:
            budgets.add(key)
    return frozenset(events - budgets)


def event_counters_by_entity(security: SecurityIR) -> dict[str, list[str]]:
    """Les compteurs d'événements groupés par entité, que la création met à 0."""
    groupes: dict[str, list[str]] = {}
    for entity, field in sorted(event_counter_fields(security)):
        groupes.setdefault(entity, []).append(field)
    return groupes


def _field_directives(security: SecurityIR) -> _FieldDirectives:
    return _FieldDirectives(
        generated=frozenset((r["entity"], r["field"]) for r in security["generated_fields"]),
        hidden=frozenset(security["hidden_fields"]),
        categorized=frozenset((r["entity"], r["field"]) for r in security["categorized_fields"]),
        timestamped=frozenset((r["entity"], r["field"]) for r in security["timestamp_fields"]),
        postpayment=frozenset((entity, name) for entity, config in security["writable_after_payment"].items()
                             for name in config["fields"]),
        numbered=MappingProxyType({(r["entity"], r["field"]): NumberingPlan(r["format"], r["periode"])
                                  for r in security["numbered_fields"]}),
        uploads=MappingProxyType({(r["entity"], r["field"]): UploadPlan(r["max_bytes"], tuple(r["accepted_types"]))
                                 for r in security["upload_fields"]}),
    )


def _field_constraints(raw: FieldConstraintsIR) -> FieldConstraints:
    minimum, maximum = raw.get("min"), raw.get("max")
    return FieldConstraints(
        required=raw.get("required", False), unique=raw.get("unique", False),
        minimum=FieldBound(minimum["portee"], minimum["valeur"]) if minimum is not None else None,
        maximum=FieldBound(maximum["portee"], maximum["valeur"]) if maximum is not None else None,
    )


def plan_entity_models(
    entities: Mapping[str, EntityFields], security: SecurityIR,
    derivations: Mapping[str, tuple[DerivedPlan, ...]],
    aggregations: Mapping[str, tuple[AggregatePlan, ...]],
) -> Mapping[str, EntityModel]:
    """Consolide les marqueurs validés sans lire l'état d'un générateur."""
    directives = _field_directives(security)
    events = event_counter_fields(security)
    models: dict[str, EntityModel] = {}
    for entity, fields in entities.items():
        derived = {r.field: r for r in derivations.get(entity, ())}
        aggregated = {r.field: r for r in aggregations.get(entity, ())}
        policies: dict[str, FieldPolicy] = {}
        for name, type_ in fields.items():
            key = (entity, name)
            policies[name] = FieldPolicy(
                name=name, type=type_, hidden_in_reads=f"{entity}.{name}" in directives.hidden,
                server_generated=(key in events or key in directives.generated or name in derived or name in aggregated
                                  or key in directives.numbered or key in directives.timestamped),
                categorized_in_reads=key in directives.categorized,
                postpayment_only=key in directives.postpayment,
                allowed_values=tuple(security["enumerated_fields"].get(entity, {}).get(name, [])),
                constraints=_field_constraints(security["field_constraints"].get(key, {})),
                derived_rule=derived.get(name), aggregate_rule=aggregated.get(name),
                timestamped=key in directives.timestamped,
                numbering_rule=directives.numbered.get(key), upload_rule=directives.uploads.get(key),
            )
        models[entity] = EntityModel(name=entity, fields=MappingProxyType(policies))
    return MappingProxyType(models)


def plan_access_policies(
    security: SecurityIR, routes: Mapping[tuple[str, str], RoutePlan],
) -> Mapping[tuple[str, str], AccessPolicy]:
    """Fige les décisions d'accès et copie leurs paramètres métier."""
    policies: dict[tuple[str, str], AccessPolicy] = {}
    public = frozenset(security["public"])
    for (action, _key), route in routes.items():
        entity = route.base_target
        reference = f"{entity}.{action}"
        condition = security["public_conditions"].get(reference) if action == "Read" else None
        ownership = security["transitive_ownership"].get(entity)
        policies[(entity, action)] = AccessPolicy(
            entity=entity, action=action, actors=frozenset(route.actors),
            public=reference in public or condition is not None,
            public_condition=PublicCondition(condition["field"], condition["value"]) if condition is not None else None,
            owner_entity=security["ownership"].get(reference),
            transitive_ownership=TransitiveOwnership(ownership["actor"], tuple(ownership["chain"])) if ownership is not None else None,
            party_fields=tuple(security["access_parties"].get(reference, [])),
            supervisors=frozenset(security["access_supervisors"].get(reference, [])),
        )
    return MappingProxyType(policies)
