"""What a field accepts, and what it shows.

The four constraints of point 85 (`required`, `unique`, `min`, `max` — the
compiler's oldest rules, which produced NOTHING before it), `hidden`
masking, `categorized` substitution, and the `oneOf` closed list (point
96)."""

from .base import ASTValidationError


class FieldsMixin:
    """What a field accepts, and what it shows."""

    # The grammar's four VALIDATION_TYPEs, and what they bound depending on the
    # field's type. Length for text, value for a number: it is the only natural
    # reading of "min 3" on a name and "min 0" on a price, and it must be
    # written down somewhere rather than guessed.
    BOUNDS_TEXT = ("String", "Text", "Email")

    BOUNDS_NUMBER = ("Integer", "Float", "Money")

    # Maximum length of the matching SQL column (beta 3 fix): a 'max' beyond it
    # would promise data the column cannot hold.
    LONGUEUR_COLUMN = {"String": 255, "Email": 320, "Text": 20000}

    def _field_constrained(self, reference, ou):
        """(entity, field, type) targeted by a constraint, or a refusal that says
        why. Extracted from `_valider_contraintes_de_champ` (complexity ceiling);
        refusals and messages unchanged."""
        if "." not in reference:
            raise ASTValidationError(
                f"Structure: '{ou}' must reference 'Entity.field', got '{reference}'.")
        entity, field = reference.split(".", 1)
        if entity not in self.entities:
            raise ASTValidationError(
                f"Structure: '{ou}' references entity '{entity}', which does not exist. "
                f"Declared entities: {', '.join(sorted(self.entities))}.")
        type_field = self.entities[entity].get(field)
        if type_field is None:
            close = [c for c in self.entities[entity] if c.lower() == field.lower()]
            index = f" Did you mean '{close[0]}'?" if close else ""
            raise ASTValidationError(
                f"Structure: '{ou}' references field '{field}', which entity "
                f"'{entity}' does not declare.{index} Fields of {entity}: "
                f"{', '.join(self.entities[entity])}. A constraint on a nonexistent field "
                f"does not apply to anything—and suggests otherwise.")
        if type_field == "Upload":
            raise ASTValidationError(
                f"Structure: '{ou}' does not apply to '{reference}' of type Upload. "
                "Constrain an upload with 'upload max … types …', which produces "
                "real multipart rejections in the backend.")
        return entity, field, type_field

    def _validate_constraints_of_field(self):
        """POINT 85: the four rules that did nothing.

        `required`, `unique`, `min` and `max` — the compiler's oldest — were
        accepted without ANYTHING checking or enforcing them. Two findings, both
        obtained by execution:

        * a phantom reference passed silently. `rule Product.nom required` instead
          of `name`: the author believes they hold a constraint, they have none,
          and nothing says so;
        * the output was BYTE-IDENTICAL with or without these rules.
          `exemples/02_boutique.ml` declares `rule Product.price min 0`, and the
          server accepted `price: -99` — in a shop where the price is multiplied
          into a subtotal, summed into a total and sent to Stripe.

        This method closes the first half (the references), and fills
        `self.field_constraints`, whose second half the generator enforces."""
        self.field_constraints = {}
        for rule in self.rules:
            type_rule = rule["type"]
            if type_rule not in ("required", "unique", "min", "max"):
                continue
            reference = rule["reference"]
            ou = f"rule {reference} {type_rule}"
            entity, field, type_field = self._field_constrained(reference, ou)

            constraints = self.field_constraints.setdefault((entity, field), {})
            if type_rule in constraints:
                raise ASTValidationError(
                    f"Structure: '{ou}' is declared twice on the same field.")
            if type_rule in ("required", "unique"):
                constraints[type_rule] = True
                continue

            # 'min'/'max': the grammar only accepts a positive integer.
            try:
                bound = int(rule.get("value"))
            except (TypeError, ValueError):
                raise ASTValidationError(
                    f"Structure: '{ou}' expects an integer "
                    f"(got '{rule.get('value')}').") from None
            if type_field in self.BOUNDS_TEXT:
                limit = self.LONGUEUR_COLUMN[type_field]
                if bound > limit:
                    raise ASTValidationError(
                        f"Structure: '{ou} {bound}' exceeds the column length "
                        f"'{field}' ({type_field} = {limit} characters). The constraint "
                        f"would promise data the database cannot store.")
                constraints[type_rule] = {"portee": "longueur", "valeur": bound}
            elif type_field in self.BOUNDS_NUMBER:
                constraints[type_rule] = {"portee": "valeur", "valeur": bound}
            else:
                raise ASTValidationError(
                    f"Structure: '{ou}' targets '{field}' of type '{type_field}', "
                    f"which '{type_rule}' cannot bound. LENGTH bounds apply to "
                    f"{', '.join(self.BOUNDS_TEXT)}; VALUE bounds apply to "
                    f"{', '.join(self.BOUNDS_NUMBER)}.")

        for (entity, field), constraints in self.field_constraints.items():
            bas, haut = constraints.get("min"), constraints.get("max")
            if bas and haut and bas["valeur"] > haut["valeur"]:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' has min {bas['valeur']} and "
                    f"max {haut['valeur']}: no value satisfies both.")

    def _validate_fields_masques(self):
        """Validates the ``hidden`` rules and prepares the fields to mask."""
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] != "hidden":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'hidden' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'hidden' rule targets entity '{entity}' which does not exist.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: the 'hidden' rule references field '{field}', which is not a declared attribute "
                    f"of '{entity}' (or is 'id', which cannot be hidden)."
                )
            self.masked_fields.add((entity, field))

    def _validate_fields_categorized(self):
        """Validates the ``categorized`` rules after the ``hidden`` fields."""
        self.categorized_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "categorized":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'categorized' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'categorized' rule targets entity '{entity}' which does not exist.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure: 'categorized' targets field '{entity}.{field}', which must be a declared "
                    f"Integer or Float attribute (got: {field_type or 'nonexistent field'})."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and 'categorized'—incompatible: "
                    f"'hidden' removes the field, while 'categorized' replaces it with a category derived from its value."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure: multiple 'categorized' rules declared for '{entity}.{field}'—only one is allowed."
                )
            seen_fields.add((entity, field))

            clauses = rule["value"]
            self._validate_steps_categorized(entity, field, clauses)
            self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

    @staticmethod
    def _validate_steps_categorized(entity, field, clauses):
        """The tiers of a `categorized`: at least one threshold, `otherwise` last and
        only there, strictly increasing thresholds, non-empty labels. Extracted
        from `_valider_champs_categorises` (complexity ceiling); refusals and
        messages unchanged."""
        if len(clauses) < 2:
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' must declare at least one threshold ('below') "
                f"and a fallback tier ('otherwise')."
            )
        for clause in clauses[:-1]:
            if "otherwise" in clause:
                raise ASTValidationError(
                    f"Structure: 'categorized' on '{entity}.{field}'—only the LAST tier can be "
                    f"'otherwise' (fallback tier); it appeared earlier in the list."
                )
        if "otherwise" not in clauses[-1]:
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' must end with an 'otherwise' tier "
                f"(the fallback tier that covers every value beyond the last threshold)."
            )
        thresholds = [clause["below"] for clause in clauses[:-1]]
        if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' —'below' thresholds must be "
                f"strictly increasing (got: {thresholds})."
            )
        if any(not clause["label"].strip() for clause in clauses):
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' —each tier must have a non-empty label."
            )

    @staticmethod
    def _validate_list_of_choice(entity, field, values):
        """At least two values, none empty, none repeated. Extracted from
        `_valider_champs_enumeres` (complexity ceiling); refusals unchanged."""
        if len(values) < 2:
            raise ASTValidationError(
                f"Structure: 'oneOf' on '{entity}.{field}' lists only one value—"
                f"a field with only one possible value does not need to be entered."
            )
        empty_values = [value for value in values if not value.strip()]
        if empty_values:
            raise ASTValidationError(
                f"Structure: 'oneOf' on '{entity}.{field}' contains an empty value—"
                f"it would be indistinguishable from an unfilled field on screen."
            )
        duplicates = [value for value in set(values) if values.count(value) > 1]
        if duplicates:
            raise ASTValidationError(
                f"Structure: 'oneOf' on '{entity}.{field}' repeats "
                f"{', '.join(repr(duplicate) for duplicate in sorted(duplicates))}—a choice list "
                f"that offers the same option twice is a data entry error."
            )

    def _validate_fields_enumerated(self):
        """Validates the text fields limited to a list of values."""
        self.enumerated_fields = {}
        for rule in self.rules:
            if rule["type"] != "oneOf":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'oneOf' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'oneOf' rule targets entity '{entity}' which does not exist.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("String", "Text"):
                raise ASTValidationError(
                    f"Structure: 'oneOf' targets '{entity}.{field}', which must be a String or Text field "
                    f"(got: {field_type or 'nonexistent field'})—for a number, 'min'/'max' or "
                    f"'categorized' already provide this."
                )
            values = rule["value"]
            self._validate_list_of_choice(entity, field, values)
            if entity in self.enumerated_fields and field in self.enumerated_fields[entity]:
                raise ASTValidationError(
                    f"Structure: two 'oneOf' rules on '{entity}.{field}'—which list would apply?"
                )
            if any(generated["entity"] == entity and generated["field"] == field for generated in self.generated_fields):
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'generated' and 'oneOf'—"
                    f"the server writes it itself, so the choice list would never be read."
                )
            self.enumerated_fields.setdefault(entity, {})[field] = list(values)
