"""From the validated AST to the model the generator works with."""

from ..ir import EffectPlan, ForeignKeyPlacement
from ..planning import plan_foreign_keys


class TemplateMixin:
    """From the validated AST to the model the generator works with."""


    def _build_effect_plans(self) -> tuple[EffectPlan, ...]:
        """Gathers the validated effects into one shared, ordered catalog."""
        plans = []
        for entity, rules in self.derived_by_entity.items():
            plans.extend(EffectPlan(
                kind="derive", trigger_entity=entity, target_entity=entity,
                field=rule.field, source_entity=rule.source_entity,
                source_field=rule.source_field, config=rule.as_ir(),
            ) for rule in rules)
        for source, rules in self.aggregations_by_source.items():
            plans.extend(EffectPlan(
                kind="aggregate", trigger_entity=source,
                target_entity=rule.entity, field=rule.field,
                source_entity=source, source_field=rule.source_field, config=rule.as_ir(),
            ) for rule in rules)
        for trigger, rules in self.reputation_rules_by_trigger.items():
            plans.extend(EffectPlan(
                kind="increment" if rule.direction == "increments" else "decrement",
                trigger_entity=trigger, target_entity=rule.target_entity,
                field=rule.target_field, source_entity=None,
                source_field=rule.amount_field, config=rule.as_ir(),
            ) for rule in rules)
        for entity, rules in self.release_rules_by_entity.items():
            plans.extend(EffectPlan(
                kind="release", trigger_entity=entity,
                target_entity=rule["releases"], field=rule["field"],
                source_entity=None, source_field=None, config=rule,
            ) for rule in rules)
        plans.extend(EffectPlan(
            kind="payment_lock", trigger_entity=entity, target_entity=entity,
            field=field, source_entity=None, source_field=None,
            config={"entity": entity, "field": field},
        ) for entity, field in self.payable_by_entity.items())
        plans.extend(EffectPlan(
            kind="postpayment_write", trigger_entity=entity, target_entity=entity,
            field=None, source_entity=None, source_field=None, config=config,
        ) for entity, config in self.postpayment_writable_by_entity.items())
        plans.extend(EffectPlan(
            kind="message", trigger_entity=rule["trigger_entity"],
            target_entity=rule["trigger_entity"], field=None,
            source_entity=None, source_field=None, config=rule,
        ) for rule in self.message_rules_by_trigger.values())
        return tuple(plans)

    def _effects(self, kind, *, trigger=None, target=None):
        return [plan for plan in self.effect_plans
                if plan.kind == kind
                and (trigger is None or plan.trigger_entity == trigger)
                and (target is None or plan.target_entity == target)]

    def _compute_fk_placements(self) -> dict[str, list[ForeignKeyPlacement]]:
        """Adapter from the emitters to the typed foreign key analysis.

        The placement depends only on `relation_models`, frozen at construction:
        it is therefore computed ONCE. The emitters query it from nested loops —
        measured at 270,305 calls for a 1,668-line spec, i.e. 102 s spent
        rebuilding the same index. Recomputing it on every call made compilation
        cost cubic in the number of entities."""
        if self._fk_placements_caches is None:
            self._fk_placements_caches = plan_foreign_keys(self.relation_models)
        return self._fk_placements_caches

    def _compute_seed_data(self):
        """ADDED (frontend roadmap, 'seed' block): groups demo data by table name
        (lowercase), in declaration order. Returns {table: [ {field: value}, ...
        ]}. Several 'seed' blocks targeting the same entity are concatenated.

        'generated' fields (e.g. an anonymous author pseudonym) are not filled in
        by the user in the seed (the validator tolerates it because they are
        removed from the input schema); as at a real creation they are assigned by
        the server, so they get a deterministic synthetic value here ('Anon#1000',
        'Anon#1001'…) so the seed produces complete records consistent with the
        rendering (social feed, etc.).

        BRICK 21 (point 100): each entry is now a PAIR
        {"values": {...}, "parent": None | {...}}, no longer the row alone.
        A child's attachment cannot be resolved here: the parent's `id` exists only
        once the row is inserted, and the foundation seeds a table only if it is
        EMPTY — a parent already populated with real data would therefore not be
        reinserted, and a rank computed at compile time would designate the wrong
        row. The designation travels as is and is resolved by a SELECT at startup."""
        seed_data = {}
        for seed in self.seeds:
            entity = seed["entity"]
            table = entity.lower()
            generated = self.generated_fields_by_entity.get(entity, [])
            parent = seed.get("parent")
            attachment = None
            if parent:
                attachment = {
                    "column": f"{parent['entity'].lower()}_id",
                    "table": parent["entity"].lower(),
                    "field": parent["field"],
                    "value": parent["value"],
                }
            seed_data.setdefault(table, [])
            for row in seed["rows"]:
                filled = dict(row)
                for gfield in generated:
                    if gfield not in filled:
                        # Stable synthetic pseudonym, unique per row.
                        filled[gfield] = f"Anon#{1000 + len(seed_data[table])}"
                seed_data[table].append({"values": filled, "parent": attachment})
        return seed_data
