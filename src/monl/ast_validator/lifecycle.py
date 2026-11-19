"""What a record becomes AFTER its payment.

`releases` (point 98 — reaching a value undoes an effect, only once,
toward a terminal state) and `writableAfterPayment` (point 113, the only
way to move a field forward without touching the generic Update lock,
which stays absolute)."""

from .base import ASTValidationError


def _refuse_field_server(rules_server, entity, field):
    """A field the server fills cannot also be written after payment.
    Extracted from `_valider_regle_apres_paiement` (complexity ceiling)."""
    for type_rule, fields in rules_server:
        if any(c["entity"] == entity and c["field"] == field
               for c in fields):
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is both "
                f"'writableAfterPayment' and '{type_rule}' — incompatible: "
                f"'{type_rule}' forbids all client writes.")


class CycleOfVieMixin:
    """What a record becomes AFTER its payment."""

    def _refuse_first_state_released(self, entity, field):
        """A new object cannot be born in its terminal state."""
        choice = self.enumerated_fields.get(entity, {}).get(field)
        release = next((item for item in self.release_rules
                           if item["entity"] == entity
                           and item["field"] == field), None)
        if choice and release and choice[0] == release["value"]:
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' would be created with the value "
                f"{choice[0]!r}, which also triggers 'releases' — a record "
                f"created already released would have consumed nothing. "
                f"First declare the initial state in the 'oneOf' of "
                f"'{entity}.{field}'.")

    def _check_entity_released(self, entity, released_entity):
        """The released entity exists, carries a `decrements`, and depends on
        `entity`. Extracted from `_valider_regles_liberation` (complexity
        ceiling); refusals and messages unchanged."""
        if released_entity not in self.entities:
            raise ASTValidationError(
                f"Structure: 'releases' names entity '{released_entity}', which does not exist."
            )
        decrements = [
            item for item in self.reputation_rules
            if item["trigger_entity"] == released_entity and item["direction"] == "decrements"
        ]
        if not decrements:
            raise ASTValidationError(
                f"Structure: 'releases {released_entity}' would release nothing — this entity has "
                f"no 'decrements' rule. It is what a decrement consumed that gets returned."
            )
        if not any(rel["source"] == entity and rel["target"] == released_entity for rel in self.relations):
            raise ASTValidationError(
                f"Structure: 'releases' requires a '{entity} hasMany {released_entity}' relation — "
                f"without it, nothing specifies which {released_entity} rows depend on this {entity}."
            )

    def _validate_rules_release(self):
        """Validates the transitions that give back a decremented counter."""
        self.release_rules = []
        for rule in self.rules:
            if rule["type"] != "releases":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'releases' rule must reference 'Entity.field', "
                    f"received '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'releases' rule targets entity '{entity}', which does not exist."
                )
            choices = self.enumerated_fields.get(entity, {}).get(field)
            if not choices:
                raise ASTValidationError(
                    f"Structure: 'releases' requires '{entity}.{field}' to have a 'oneOf' — "
                    f"without a list of values, a typo would create a rule that never triggers."
                )
            if rule["value"] not in choices:
                raise ASTValidationError(
                    f"Structure: 'releases' triggers on value {rule['value']!r}, "
                    f"which is absent from the 'oneOf' of '{entity}.{field}' "
                    f"({', '.join(repr(choice) for choice in choices)}) — it would never occur."
                )
            released_entity = rule["entity"]
            self._check_entity_released(entity, released_entity)
            if any(item["entity"] == entity and item["field"] == field for item in self.release_rules):
                raise ASTValidationError(
                    f"Structure: two 'releases' rules on '{entity}.{field}' — the first release "
                    f"would already return the decrement, and the second would return it a second time."
                )
            self.release_rules.append({
                "entity": entity, "field": field, "value": rule["value"], "releases": released_entity,
            })

    def _refuse_owner_after_payment(self, entity, field, actor):
        """The named actor must not be the entity's owner, who could then
        bypass the payment lock. Extracted from `_valider_regle_apres_paiement`
        (complexity ceiling); same check, same message."""
        owner_entity = self.transitive_ownership.get(entity, {}).get("actor")
        if owner_entity is None:
            owners_directs = {
                owner for (owned_entity, _action), owner
                in self.ownership_rules.items()
                if owned_entity == entity and owner in self.actors
            }
            if len(owners_directs) == 1:
                owner_entity = next(iter(owners_directs))
        if owner_entity == actor:
            raise ASTValidationError(
                f"Structure: the 'writableAfterPayment' rule on "
                f"'{entity}.{field}' names '{actor}', who already owns "
                f"'{entity}' — its owner could bypass the payment lock.")

    def _validate_rule_after_payment(self):
        """Validates the reserved write channel that bypasses the locked CRUD."""
        self.postpayment_writable = {}
        fields_seen = set()
        rules_server = (
            ("generated", self.generated_fields),
            ("derivedFrom", self.derived_fields),
            ("sumOf", self.aggregated_fields),
            ("timestamp", self.timestamp_fields),
            ("numbered", self.numbered_fields),
        )
        for rule in self.rules:
            if rule["type"] != "writableAfterPayment":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: the 'writableAfterPayment' rule must reference "
                    f"'Entity.field', received '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'writableAfterPayment' rule targets entity "
                    f"'{entity}', which does not exist.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: the 'writableAfterPayment' rule targets field "
                    f"'{entity}.{field}', which is not a declared attribute.")
            if not any(pf["entity"] == entity for pf in self.payable_fields):
                raise ASTValidationError(
                    f"Structure: the 'writableAfterPayment' rule only applies to "
                    f"a 'payable' entity — '{entity}' is not one.")
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure: the 'writableAfterPayment' rule on "
                    f"'{entity}.{field}' names actor '{actor}', which is not "
                    f"a declared actor.")
            _refuse_field_server(rules_server, entity, field)
            self._refuse_owner_after_payment(entity, field, actor)
            config = self.postpayment_writable.get(entity)
            if config and config["actor"] != actor:
                raise ASTValidationError(
                    f"Structure: two different actors are declared for "
                    f"'writableAfterPayment' on '{entity}': "
                    f"'{config['actor']}' and '{actor}' — only one actor is allowed.")
            if (entity, field) in fields_seen:
                raise ASTValidationError(
                    f"Structure: multiple 'writableAfterPayment' rules are declared "
                    f"for '{entity}.{field}' — only one is allowed.")
            self._refuse_first_state_released(entity, field)
            fields_seen.add((entity, field))
            if config is None:
                config = {"actor": actor, "fields": []}
                self.postpayment_writable[entity] = config
            config["fields"].append(field)
