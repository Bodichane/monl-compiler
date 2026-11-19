"""The fields whose value the server calculates from other rows.

`derivedFrom` (point 77, born from two proven exploits), `sumOf` (point
82), the `increments`/`decrements` counters and the `oncePer` composite
uniqueness. An amount the client can write is an amount they set
themselves: that is the reason for half the refusals gathered here."""

from ..ir import AggregatedFieldIR, CounterRuleIR, DerivedFieldIR
from .base import ASTValidationError


class ChampsCalculesMixin:
    """The fields whose value the server calculates from other rows."""

    def _valider_champs_derives(self):
        """Validates the numeric fields calculated from a linked row."""
        self.derived_fields: list[DerivedFieldIR] = []
        for rule in self.rules:
            if rule["type"] != "derivedFrom":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            factor = rule["factor"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure: 'derivedFrom' must reference 'Entity.field derivedFrom Entity.field by field', "
                    f"received '{reference} derivedFrom {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: 'derivedFrom' targets entity '{entity}', which does not exist.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure: 'derivedFrom' reads entity '{source_entity}', which does not exist.")
            self._exiger_types_derives(entity, field, source_entity, source_field)
            self._exiger_multiplicateur(entity, field, factor)
            self._refuser_double_calcul_derive(entity, field)
            self._exiger_ligne_source(entity, field, source_entity, source_field)
            self.derived_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
                "factor": factor,
            })

    def _exiger_types_derives(self, entity, field, source_entity, source_field):
        """Both sides of a derivation are numeric."""
        field_type = self.entities[entity].get(field)
        if field_type not in ("Money", "Float", "Integer"):
            raise ASTValidationError(
                f"Structure: 'derivedFrom' calculates '{entity}.{field}', which must be a declared "
                f"Money, Float, or Integer attribute (received: {field_type or 'field does not exist'})."
            )
        source_type = self.entities[source_entity].get(source_field)
        if source_type not in ("Money", "Float", "Integer"):
            raise ASTValidationError(
                f"Structure: 'derivedFrom' reads '{source_entity}.{source_field}', which must be a declared "
                f"Money, Float, or Integer attribute (received: {source_type or 'field does not exist'})."
            )

    def _exiger_multiplicateur(self, entity, field, factor):
        """The multiplier is a required Integer quantity, other than the field."""
        factor_type = self.entities[entity].get(factor)
        if factor_type != "Integer":
            raise ASTValidationError(
                f"Structure: 'derivedFrom ... by {factor}' requires '{entity}.{factor}' to be a declared "
                f"Integer attribute (received: {factor_type or 'field does not exist'}) -- multiplication uses a quantity."
            )
        required_fields = {r["reference"] for r in self.rules if r.get("type") == "required"}
        if f"{entity}.{factor}" not in required_fields:
            raise ASTValidationError(
                f"Structure: '{entity}.{factor}' is used as the multiplier for 'derivedFrom' and must therefore have "
                f"'rule {entity}.{factor} required' -- otherwise, a client omitting it would trigger a calculation with no value."
            )
        if factor == field:
            raise ASTValidationError(f"Structure: '{entity}.{field}' cannot be its own multiplier.")

    def _refuser_double_calcul_derive(self, entity, field):
        """One server calculation per field, and an amount that stays readable."""
        if (entity, field) in self.masked_fields:
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is both 'hidden' and 'derivedFrom' -- incompatible: "
                f"a calculated amount that cannot be read cannot be verified."
            )
        if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is both 'generated' and 'derivedFrom' -- two competing ways "
                f"to populate it on the server; choose one."
            )
        if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' has multiple 'derivedFrom' rules -- only one calculation is allowed per field."
            )

    def _exiger_ligne_source(self, entity, field, source_entity, source_field):
        """The source row is linked, and chosen by the client, never the token."""
        has_source_relation = any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == source_entity and rel["target"] == entity)
            or (rel["type"] == "belongsTo"
                and rel["source"] == entity and rel["target"] == source_entity)
            for rel in self.relations
        )
        if not has_source_relation:
            raise ASTValidationError(
                f"Structure: 'derivedFrom' reads '{source_entity}.{source_field}' from '{entity}', which requires "
                f"a relation between them (e.g. '{source_entity} hasMany {entity}'), which is missing here -- without "
                f"it, there is no way to know WHICH row of '{source_entity}' to read."
            )
        owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == entity}
        if owners and source_entity in owners:
            raise ASTValidationError(
                f"Structure: 'derivedFrom' reads '{source_entity}', which is also the owner of "
                f"'{entity}' ('ownedBy' rule) -- its foreign key comes from the token, not the client, so "
                f"no row from '{source_entity}' can be selected at creation time."
            )
        if not owners:
            raise ASTValidationError(
                f"Structure: 'derivedFrom' on '{entity}.{field}' requires '{entity}' to have an owner "
                f"(an 'ownedBy' rule) -- this distinguishes the foreign key populated by the server "
                f"from the one supplied by the client to select the row to read."
            )

    def _valider_champs_agreges(self):
        """Validates the fields calculated as a sum of child rows."""
        self.aggregated_fields: list[AggregatedFieldIR] = []
        for rule in self.rules:
            if rule["type"] != "sumOf":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure: 'sumOf' must reference 'Entity.field sumOf Entity.field', "
                    f"received '{reference} sumOf {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: 'sumOf' targets entity '{entity}', which does not exist.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure: 'sumOf' sums entity '{source_entity}', which does not exist.")
            self._exiger_types_de_somme(entity, field, source_entity, source_field)
            self._exiger_relation_enfant(entity, source_entity)
            self._refuser_double_calcul_de_somme(entity, field)
            source_owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == source_entity}
            if not source_owners:
                raise ASTValidationError(
                    f"Structure: 'sumOf' sums '{source_entity}', which has no owner "
                    f"(an 'ownedBy' rule) -- this distinguishes the foreign key populated by the "
                    f"server from the one supplied by the client to select the parent. Without it, "
                    f"any account could add a row to someone else's total."
                )
            self.aggregated_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
            })

    def _exiger_types_de_somme(self, entity, field, source_entity, source_field):
        """A sum is numeric on both sides, and never of an entity over itself."""
        field_type = self.entities[entity].get(field)
        if field_type not in ("Money", "Float", "Integer"):
            raise ASTValidationError(
                f"Structure: 'sumOf' calculates '{entity}.{field}', which must be a declared "
                f"Money, Float, or Integer attribute (received: {field_type or 'field does not exist'})."
            )
        source_type = self.entities[source_entity].get(source_field)
        if source_type not in ("Money", "Float", "Integer"):
            raise ASTValidationError(
                f"Structure: 'sumOf' sums '{source_entity}.{source_field}', which must be a "
                f"declared Money, Float, or Integer attribute (received: {source_type or 'field does not exist'})."
            )
        if source_entity == entity:
            raise ASTValidationError(
                f"Structure: 'sumOf' makes '{entity}.{field}' the sum of a field from '{entity}' itself "
                f"-- an entity cannot sum itself. The sum must cover a CHILD entity "
                f"(e.g. 'Order hasMany Line')."
            )

    def _exiger_relation_enfant(self, entity, source_entity):
        """The summed rows must be CHILDREN of the entity carrying the total."""
        child_relation = any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == entity and rel["target"] == source_entity)
            or (rel["type"] == "belongsTo"
                and rel["source"] == source_entity and rel["target"] == entity)
            for rel in self.relations
        )
        if not child_relation:
            raise ASTValidationError(
                f"Structure: 'sumOf' sums '{source_entity}' from '{entity}', which requires "
                f"a parent-child relation (e.g. '{entity} hasMany {source_entity}'), which is missing here -- "
                f"without it, there is no way to know WHICH rows of '{source_entity}' to sum, and the sum "
                f"would cover the entire table."
            )

    def _refuser_double_calcul_de_somme(self, entity, field):
        """One server calculation per field, and a total that stays readable."""
        if (entity, field) in self.masked_fields:
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is both 'hidden' and 'sumOf' -- incompatible: "
                f"a calculated total that cannot be read cannot be verified."
            )
        if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is both 'generated' and 'sumOf' -- two competing ways "
                f"to populate it on the server; choose one."
            )
        if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' has both 'derivedFrom' and 'sumOf' -- two "
                f"competing calculations for one field. 'derivedFrom' reads ONE related row; 'sumOf' "
                f"sums children: choose one."
            )
        if any(a["entity"] == entity and a["field"] == field for a in self.aggregated_fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' has multiple 'sumOf' rules -- only one sum is allowed per field."
            )

    # The next two methods are extracted from `_valider_effets_compteurs`
    # (complexity ceiling): same checks, same order, same messages.
    def _exiger_relation_de_compteur(self, direction, trigger_entity,
                                     target_entity, target_field):
        """A counter needs a relation between the triggering and the target
        entity — it is the foreign key the effect follows."""
        matching_relation = any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == target_entity and rel["target"] == trigger_entity)
            or (rel["type"] == "belongsTo"
                and rel["target"] == target_entity and rel["source"] == trigger_entity)
            for rel in self.relations
        )
        if not matching_relation:
            raise ASTValidationError(
                f"Structure: '{direction}' on '{trigger_entity}.Create' to '{target_entity}.{target_field}' "
                f"requires a relation between them (e.g. '{target_entity} hasMany {trigger_entity}'), which is missing here."
            )

    def _valider_quantite_de_compteur(self, direction, trigger_entity, amount_field):
        """`by <field>`: an Integer of the triggering entity, and required."""
        if not amount_field:
            return
        amount_type = self.entities[trigger_entity].get(amount_field)
        if amount_type != "Integer":
            raise ASTValidationError(
                f"Structure: '{direction} ... by {amount_field}' refers to a field on "
                f"'{trigger_entity}' which must be a declared Integer "
                f"(received: {amount_type or 'field does not exist'})."
            )
        required = {r["reference"] for r in self.rules if r.get("type") == "required"}
        if f"{trigger_entity}.{amount_field}" not in required:
            raise ASTValidationError(
                f"Structure: '{trigger_entity}.{amount_field}' is used as the quantity for "
                f"'{direction}': it requires 'rule {trigger_entity}.{amount_field} "
                f"required', otherwise a client omitting it would trigger a decrement with no value."
            )

    def _valider_effets_compteurs(self):
        """Validates the counter effects triggered at creation."""
        self.reputation_rules: list[CounterRuleIR] = []
        for rule in self.rules:
            if rule["type"] not in ("decrements", "increments"):
                continue
            direction = rule["type"]
            trigger_ref, target_ref = rule["reference"], rule["value"]
            if "." not in trigger_ref or "." not in target_ref:
                raise ASTValidationError(
                    f"Structure: rule '{direction}' must reference 'Entity.Create {direction} Entity.field', "
                    f"received '{trigger_ref} {direction} {target_ref}'."
                )
            trigger_entity, trigger_action = trigger_ref.split(".", 1)
            target_entity, target_field = target_ref.split(".", 1)
            if trigger_entity not in self.entities:
                raise ASTValidationError(f"Structure: '{direction}' references entity '{trigger_entity}', which does not exist.")
            if trigger_action != "Create":
                raise ASTValidationError(
                    f"Structure: '{direction}' is only supported on 'Create' for now "
                    f"(received '{trigger_entity}.{trigger_action}')."
                )
            if target_entity not in self.entities:
                raise ASTValidationError(f"Structure: '{direction}' references entity '{target_entity}', which does not exist.")
            self._refuser_compteur_sur_acteur(direction, target_entity, target_field)
            target_type = self.entities[target_entity].get(target_field)
            if target_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure: '{direction}' targets field '{target_entity}.{target_field}', which must be "
                    f"a declared Integer or Float attribute (received: {target_type or 'field does not exist'})."
                )
            self._exiger_relation_de_compteur(
                direction, trigger_entity, target_entity, target_field)
            amount_field = rule.get("amount_field")
            self._valider_quantite_de_compteur(direction, trigger_entity, amount_field)
            self.reputation_rules.append({
                "trigger_entity": trigger_entity, "target_entity": target_entity,
                "target_field": target_field, "amount": rule.get("amount"),
                "amount_field": amount_field, "direction": direction,
            })

    def _refuser_compteur_sur_acteur(self, direction, target_entity, target_field):
        """Refuses a counter whose target is named like an actor (issue #89).

        The rows of such an entity are linked to no account, whereas any
        same-named key readable by a client (`member_id` on a post) carries an
        ACCOUNT id (point 88). The count would hit the profile whose ROW id
        matches the account id received: measured, reporting a post's author
        lowered the reporter's reputation. Refuse rather than produce a rule that
        strikes at random (point 85)."""
        if target_entity in self.actors:
            raise ASTValidationError(
                f"Structure: '{direction}' targets '{target_entity}.{target_field}', but "
                f"'{target_entity}' is also an actor. Its rows are not linked to any "
                f"account, and the '{target_entity.lower()}_id' keys read by a client contain "
                f"an account ID: the counter would affect an arbitrary record. Put the "
                f"counter on a business entity (e.g. '{direction} Post.score')."
            )

    def _verifier_parents_once_per(self, reference, entity, parents):
        """At least two distinct, existing parents, linked to `entity`, one of them
        an actor. Extracted from `_valider_regles_once_per` (complexity ceiling);
        the relation is read through `_relation_parent_enfant`, the same as for a
        `seed` attachment, rather than a second copy."""
        if len(parents) < 2 or len(set(parents)) != len(parents):
            raise ASTValidationError(
                f"Structure: 'oncePer' on '{reference}' requires at least two distinct parents."
            )
        for parent in parents:
            if parent not in self.entities and parent not in self.actors:
                raise ASTValidationError(
                    f"Structure: 'oncePer' references parent '{parent}', which does not exist."
                )
            if not self._relation_parent_enfant(parent, entity):
                raise ASTValidationError(
                    f"Structure: 'oncePer' requires a relation between '{parent}' and '{entity}'."
                )
        if not any(parent in self.actors for parent in parents):
            raise ASTValidationError(
                f"Structure: 'oncePer' on '{reference}' must include an actor parent "
                "to identify the current account."
            )

    def _valider_regles_once_per(self):
        """Validates the business uniqueness of an action per account and per
        targets.

        `oncePer Member, Entry` designates the two relations that make up Vote's
        unique key. The actor parent is filled from the JWT; the other parents
        are still supplied as normal foreign keys."""
        self.once_per_rules = []
        for rule in self.rules:
            if rule["type"] != "oncePer":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: 'oncePer' must reference 'Entity.Create', received '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: 'oncePer' targets entity '{entity}', which does not exist."
                )
            if action != "Create":
                raise ASTValidationError(
                    f"Structure: 'oncePer' only applies to 'Create' (received '{reference}')."
                )
            parents = list(rule.get("parents") or [])
            self._verifier_parents_once_per(reference, entity, parents)
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{reference}' is public, so no account can enforce "
                    "the 'oncePer' uniqueness constraint."
                )
            self.once_per_rules.append({"trigger_entity": entity, "parents": parents})
