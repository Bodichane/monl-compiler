"""Charging: who pays, for what, and on which amount.

`payable` (brick 9) and the `requiresOwn` prerequisite (point 90). The
breaking refusal of point 79 lives here: an amount the client can write
makes compilation fail, because the owner is the only one who can pay —
so a writable amount is an amount the payer sets."""

from .socle import ASTValidationError


class CommerceMixin:
    """Charging: who pays, for what, and on which amount."""

    def _valider_requires_own_et_payable(self):
        """'requiresOwn' (brick 17) and 'payable' (payment brick) — the creation
        prerequisites that protect who can act and who can charge (point 111).
        Extracted together because they share the ownership, public visibility
        and hidden field prerequisites."""
        # ADDED (roadmap, capability ecosystem -- brick 17, point 90):
        # validation of 'requiresOwn'. The caller must ALREADY own a record of
        # the named entity to be able to create this one.
        #
        # The finding that gave birth to it, on a real shop: two orders carried
        # an account WITHOUT any customer profile. Nothing required creating
        # one before ordering, and the accounts registry is exposed by no route
        # — so the administrator saw an order they could attribute to nobody.
        # For a shop, that is not a display defect: it is an order that cannot
        # be shipped.
        self.required_profiles = {}
        for rule in self.rules:
            if rule["type"] != "requiresOwn":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'requiresOwn' rule must reference 'Entity.Action', "
                    f"received '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            requise = rule["value"]
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'requiresOwn' rule targets entity '{entity}', which does not exist."
                )
            # Only creation can require it: it is the moment the record is born
            # without a named owner. On Read/Update/Delete, the record already
            # exists — requiring a profile after the fact would make data one
            # owns inaccessible.
            if act_type != "Create":
                raise ASTValidationError(
                    f"Structure: 'requiresOwn' only applies to '{entity}.Create' "
                    f"(received '{entity}.{act_type}') -- on a read or modification "
                    f"action, the record already exists and its profile can no longer "
                    f"prevent anything."
                )
            if requise not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'requiresOwn' rule on '{entity}.Create' requires "
                    f"'{requise}', which is not a declared entity."
                )
            if requise == entity:
                raise ASTValidationError(
                    f"Structure: '{entity}.Create requiresOwn {entity}' -- an entity "
                    f"cannot require itself: the first record could never be created."
                )
            # The required entity must be owned DIRECTLY by an actor: "owning
            # one" only makes sense if ownership is deduced from the token. A
            # transitively owned entity (brick 11) does not say which ACCOUNT
            # it belongs to without a join, and an entity with no owner at all
            # belongs to nobody.
            proprietaires = {v for (ent, _act), v in self.ownership_rules.items()
                             if ent == requise}
            if not (proprietaires & set(self.actors)):
                raise ASTValidationError(
                    f"Structure: '{entity}.Create requiresOwn {requise}', but "
                    f"'{requise}' is not owned by any actor -- 'owning one' would "
                    f"then have no meaning. Add a rule "
                    f"'rule {requise}.Read ownedBy <Acteur>'."
                )
            # A public creation has no identity: impossible to look up "its"
            # profile. Same refusal as 'generated' and 'payable', same reason.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{entity}.Create' is 'public' but still requires an "
                    f"owned '{requise}' -- incompatible: without an identified caller, "
                    f"no profile can be looked up."
                )
            if entity in self.required_profiles:
                raise ASTValidationError(
                    f"Structure: multiple 'requiresOwn' rules declared for "
                    f"'{entity}.Create' -- only one is allowed."
                )
            self.required_profiles[entity] = requise

        # ADDED (roadmap, payment brick -- point 74): validation of 'payable'.
        # The rule names the field that carries the AMOUNT; the entity
        # containing it is the one being charged. The refusals below are the
        # heart of the brick: a badly declared payment must fail at compile
        # time, never at charging time.
        self.payable_fields = []
        for rule in self.rules:
            if rule["type"] != "payable":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'payable' rule must reference 'Entity.field', received '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'payable' rule targets entity '{entity}', which does not exist."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure: 'payable' targets field '{entity}.{field}', which must be a declared "
                    f"Money, Float, or Integer attribute (received: {field_type or 'field does not exist'}) -- "
                    f"text cannot be charged."
                )
            # A hidden amount would be unverifiable by the paying client: they
            # could not compare what is asked of them with what they ordered.
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and 'payable' -- incompatible: "
                    f"a payer cannot verify an amount they cannot read."
                )
            if any(p["entity"] == entity for p in self.payable_fields):
                raise ASTValidationError(
                    f"Structure: '{entity}' has multiple 'payable' fields -- only one amount per entity, "
                    f"otherwise nothing specifies which one to charge."
                )
            # Charging requires knowing WHO pays: a public creation has no
            # identity to attach to the payment, nor anyone to refund.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is 'payable', but '{entity}.Create' is 'public' -- "
                    f"incompatible: a payment requires an identified caller."
                )
            # SECURITY FIX: without an incoming relation, the generator can
            # determine NO owner for the payment route, which then accepts any
            # authenticated caller for any record (IDOR). Same requirement as
            # for 'increments'/'decrements' below -- a relation must exist to
            # know WHO owns the row being charged.
            has_owner_relation = any(
                (rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity)
                or (rel["type"] == "belongsTo" and rel["source"] == entity)
                for rel in self.relations
            )
            if not has_owner_relation:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is 'payable', but no relation identifies who "
                    f"owns a '{entity}' record (e.g. 'Client hasMany {entity}') -- without it, "
                    f"the payment route could not verify who is allowed to pay."
                )
            # LIFTED AT POINT 87. Point 81 refused any TRANSITIVELY owned
            # entity here, because the payment route compared the ownership
            # foreign key with `current_user_id` — yet under a chain that
            # column carries an intermediate record id, not an account id. The
            # refusal therefore protected against a wrong comparison, not an
            # impossibility: the same brick 11 already provided, in
            # `_owner_lookup_sql`, the join that gives the ACCOUNT id. The
            # route now uses it, and the comparison is exact again.
            #
            # What keeps the brick safe has not moved: the chain must climb to
            # an actor (point 81 refusal, above), the amount must stay
            # impossible for the client to compute (point 79 refusal, in the
            # cross-check below), and an incoming relation must exist (just
            # above). None of these three refusals is weakened.
            self.payable_fields.append({"entity": entity, "field": field})

    def _valider_securite_calculs_paiement(self):
        """Recoupe champs serveur, bornes et montants encaissables."""
        derived = {(item["entity"], item["field"]) for item in self.derived_fields}
        sums = {(item["entity"], item["field"]): item for item in self.aggregated_fields}
        server_fields = (
            derived
            | set(sums)
            | {(item["entity"], item["field"]) for item in self.generated_fields}
            | {(item["entity"], item["field"]) for item in self.timestamp_fields}
            | {(item["entity"], item["field"]) for item in self.numbered_fields}
        )
        for (entity, field), constraints in sorted(self.field_constraints.items()):
            if (entity, field) not in server_fields:
                continue
            bounds = [name for name in ("min", "max") if name in constraints]
            if bounds:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' has "
                    f"'{ '/'.join(bounds) }' even though the SERVER calculates this field: it "
                    f"is absent from the request body, so the bound would apply to "
                    f"nothing. Remove it, or bound the field the value comes from."
                )
            if "required" in constraints:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is 'required' even though the SERVER "
                    f"calculates it: the client cannot provide it, and the contract "
                    f"would say both 'fill this in' and 'do not send it'."
                )

        for payable in self.payable_fields:
            self._verifier_montant_calcule(payable["entity"], payable["field"], derived, sums)

    @staticmethod
    def _verifier_montant_calcule(entity, field, derived, sums):
        """A `payable` amount must be calculated by the server, and a sum must only
        add up lines that are themselves calculated. Extracted from
        `_valider_securite_calculs_paiement` (complexity ceiling)."""
        if (entity, field) not in derived and (entity, field) not in sums:
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is 'payable' but the client can write it -- "
                f"the creator of a '{entity}' becomes its owner, and therefore the payer: they "
                f"would set the amount they pay. Add a rule that makes the server calculate the "
                f"amount, for example "
                f"'rule {entity}.{field} derivedFrom Product.price by quantity', or "
                f"'rule {entity}.{field} sumOf OrderLine.subtotal' for a cart."
            )
        total = sums.get((entity, field))
        if total is None:
            return
        source = (total["source_entity"], total["source_field"])
        if source not in derived and source not in sums:
            raise ASTValidationError(
                f"Structure: '{entity}.{field}' is 'payable' and sums "
                f"'{total['source_entity']}.{total['source_field']}', which the client can "
                f"write -- adding an amount supplied by the payer still lets the payer set "
                f"the total, with one extra addition. Make the line calculated by the "
                f"server, for example 'rule {total['source_entity']}."
                f"{total['source_field']} derivedFrom Product.price by quantity'."
            )

    def _valider_proprietaire_paiement(self):
        """Checks that a payable amount really climbs up to an account."""
        for payable in self.payable_fields:
            entity = payable["entity"]
            if entity in self.transitive_ownership:
                continue
            targets = {
                rule["target_entity"] for rule in self.reputation_rules
                if rule["trigger_entity"] == entity
            }
            actor_parents = {
                (rel["source"] if rel["type"] in ("hasMany", "hasOne") else rel["target"])
                for rel in self.relations
                if (rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity)
                or (rel["type"] == "belongsTo" and rel["source"] == entity)
            } & set(self.actors) - targets
            if not actor_parents:
                raise ASTValidationError(
                    f"Structure: '{entity}.{payable['field']}' is 'payable', but no "
                    f"ACTOR owns a '{entity}' record. A relation to a business table is "
                    f"not enough: the column it creates contains that row's ID, not an "
                    f"account ID, and the payment route compares it to the caller. Declare "
                    f"'an_actor hasMany {entity}', or attach '{entity}' to an actor through its parent "
                    f"('rule {entity}.Read ownedBy <Parent>')."
                )
