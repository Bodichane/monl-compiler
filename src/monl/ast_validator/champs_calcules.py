"""Les champs dont le serveur calcule la valeur depuis d'autres lignes.

`derivedFrom` (point 77, né de deux exploits prouvés), `sumOf` (point 82),
les compteurs `increments`/`decrements` et l'unicité composite `oncePer`.
Un montant que le client peut écrire est un montant qu'il fixe lui-même :
c'est la raison d'être de la moitié des refus rassemblés ici."""

from ..ir import AggregatedFieldIR, CounterRuleIR, DerivedFieldIR
from .socle import ASTValidationError


class ChampsCalculesMixin:
    """Les champs dont le serveur calcule la valeur depuis d'autres lignes."""

    def _valider_champs_derives(self):
        """Valide les champs numériques calculés depuis une ligne liée."""
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
            self.derived_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
                "factor": factor,
            })

    def _valider_champs_agreges(self):
        """Valide les champs calculés par somme des lignes enfants."""
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
                    f"attribut Money, Float, or Integer attribute (received: {source_type or 'field does not exist'})."
                )
            if source_entity == entity:
                raise ASTValidationError(
                    f"Structure: 'sumOf' makes '{entity}.{field}' the sum of a field from '{entity}' itself "
                    f"-- an entity cannot sum itself. The sum must cover a CHILD entity "
                    f"(e.g. 'Order hasMany Line')."
                )
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

    def _valider_effets_compteurs(self):
        """Valide les effets de compteur déclenchés à la création."""
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
            amount_field = rule.get("amount_field")
            if amount_field:
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
            self.reputation_rules.append({
                "trigger_entity": trigger_entity, "target_entity": target_entity,
                "target_field": target_field, "amount": rule.get("amount"),
                "amount_field": amount_field, "direction": direction,
            })

    def _refuser_compteur_sur_acteur(self, direction, target_entity, target_field):
        """Refuse un compteur dont la cible porte le nom d'un acteur (issue #89).

        Les lignes d'une telle entité ne sont liées à aucun compte, alors que
        toute clé homonyme lisible par un client (`member_id` sur un post)
        porte un id de COMPTE (point 88). Le décompte viserait la fiche dont
        l'id de LIGNE coïncide avec l'id de compte reçu : mesuré, signaler
        l'auteur d'un post faisait baisser la réputation du signaleur.
        Refuser plutôt que produire une règle qui frappe au hasard (point 85).
        """
        if target_entity in self.actors:
            raise ASTValidationError(
                f"Structure: '{direction}' targets '{target_entity}.{target_field}', but "
                f"'{target_entity}' is also an actor. Its rows are not linked to any "
                f"account, and the '{target_entity.lower()}_id' keys read by a client contain "
                f"an account ID: the counter would affect an arbitrary record. Put the "
                f"counter on a business entity (e.g. '{direction} Post.score')."
            )

    def _valider_regles_once_per(self):
        """Valide l'unicité métier d'une action par compte et par cibles.

        `oncePer Member, Entry` désigne les deux relations qui composent la
        clé unique de Vote. Le parent acteur est alimenté depuis le JWT ; les
        autres parents restent fournis comme clés étrangères normales.
        """
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
            if len(parents) < 2 or len(set(parents)) != len(parents):
                raise ASTValidationError(
                    f"Structure: 'oncePer' on '{reference}' requires at least two distinct parents."
                )
            for parent in parents:
                if parent not in self.entities and parent not in self.actors:
                    raise ASTValidationError(
                        f"Structure: 'oncePer' references parent '{parent}', which does not exist."
                    )
                relie = any(
                    (rel["type"] in ("hasMany", "hasOne")
                     and rel["source"] == parent and rel["target"] == entity)
                    or (rel["type"] == "belongsTo"
                        and rel["target"] == parent and rel["source"] == entity)
                    for rel in self.relations
                )
                if not relie:
                    raise ASTValidationError(
                        f"Structure: 'oncePer' requires a relation between '{parent}' and '{entity}'."
                    )
            if not any(parent in self.actors for parent in parents):
                raise ASTValidationError(
                    f"Structure: 'oncePer' on '{reference}' must include an actor parent "
                    "to identify the current account."
                )
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{reference}' is public, so no account can enforce "
                    "the 'oncePer' uniqueness constraint."
                )
            self.once_per_rules.append({"trigger_entity": entity, "parents": parents})
