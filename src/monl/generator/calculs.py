"""Rendering of the calculations from the resolved business plans.

The keys of derivations, aggregations and counters are determined by
`planning`. The create, update and delete emitters read the same plans to
keep each effect's target."""

from string import Template


class CalculsMixin:
    """What the server CALCULATES: derivation, sum, counters."""

    def _valeur_initiale_postpaiement(self, entity, field):
        """First closed state, or the legitimate absence of a known value."""
        choix = self.enumerated_fields.get(entity, {}).get(field)
        return repr(choix[0]) if choix else "None"

    def _derived_field_names(self, entity: str) -> list[str]:
        """Fields of 'entity' calculated by the server (brick 10, point 77).

        They must be treated like 'generated' fields wherever the client could
        supply them: absent from the Pydantic schema, and excluded from the write
        values read from `data`."""
        return [plan.field for plan in self.derived_by_entity.get(entity, ())]

    def _aggregated_field_names(self, entity: str) -> list[str]:
        """Fields of 'entity' that are a SUM of its children (brick 12).

        Treated everywhere like 'derivedFrom' fields: absent from the Pydantic
        schema, and never read from `data`."""
        return [plan.field for plan in self.aggregated_by_entity.get(entity, ())]

    def _aggregation_recomputes(self, source_entity):
        """Sums to recompute after any write on 'source_entity'.

        The query recomputes the parent's lines inside the write's transaction.
        COALESCE gives zero to an empty cart and ROUND keeps the monetary rounding
        the existing routes expect."""
        recalculs = []
        for plan in self.aggregations_by_source.get(source_entity, ()):
            fk = plan.parent_fk
            recalculs.append({
                "fk_column": fk,
                "sql": (Template(r"""UPDATE "${entity}" SET "${field}" = (SELECT ROUND(COALESCE(SUM("${source_field}"), 0), 2) FROM "${source_entity}" WHERE "${fk}" = ?) WHERE id = ?""").substitute(entity=plan.entity.lower(), field=plan.field, source_field=plan.source_field, source_entity=source_entity.lower(), fk=fk)),
            })
        return recalculs

    def _lignes_restitution(self, enfant, fk_enfant, indent="    "):
        """Gives back to the parent what its child lines had consumed.

        SINGLE source of brick 20's restoration, shared by the TWO routes that can
        flip a field to its releasing value: the generic Update and, when
        `writableAfterPayment` has taken the field from it, the post-payment
        route. Copying it into the second would reopen the point 92 door — an
        effect where each branch keeps its own version ends up diverging.

        No floor: we restore a state that existed and was valid."""
        lignes = []
        for decompte in self.reputation_rules_by_trigger.get(enfant, []):
            if decompte.direction != "decrements":
                continue
            champ = decompte.amount_field
            quantite = "_l[1]" if champ else str(decompte.amount)
            colonnes = (Template(r'''"${target_fk}", "${champ}"''').substitute(target_fk=decompte.target_fk, champ=champ) if champ
                        else Template(r'''"${target_fk}"''').substitute(target_fk=decompte.target_fk))
            lignes.extend([
                Template(r"""${indent}cursor.execute('SELECT ${colonnes} FROM "${enfant}" WHERE "${fk_enfant}" = ?', (id,))""").substitute(indent=indent, colonnes=colonnes, enfant=enfant.lower(), fk_enfant=fk_enfant),
                Template(r"""${indent}for _l in cursor.fetchall():""").substitute(indent=indent),
                Template(r"""${indent}    cursor.execute('UPDATE "${target_entity}" SET "${target_field}" = "${target_field_2}" + ? WHERE id = ?', (int(${quantite} or 0), _l[0]))""").substitute(indent=indent, target_entity=decompte.target_entity.lower(), target_field=decompte.target_field, target_field_2=decompte.target_field, quantite=quantite),
            ])
        return lignes

    def _fk_enfant_libere(self, parent, enfant):
        """Child column designating the parent whose state flips."""
        return next(
            (p["fk_column"] for p in self._compute_fk_placements().get(enfant, [])
             if p["owner_entity"] == parent), None)

    def _counter_fk_columns(self, trigger_entity: str) -> list[str]:
        """Keys chosen by the client, deduplicated in effect order."""
        return list(dict.fromkeys(
            plan.target_fk for plan in self.reputation_rules_by_trigger.get(trigger_entity, ())
        ))

    def _emit_categorization_lines(self, categorized_field, row_var, indent):
        """ADDED (roadmap, capability ecosystem -- brick 5): generates the Python
        source that replaces, on an already-named row dict (row_var), a numeric
        field with its category label (e.g. 'likes' -> 'likes_category'). The
        validation in ast_validator.py guarantees that 'clauses' always ends with
        exactly one 'otherwise' tier, and that every preceding 'below' tier is
        strictly increasing -- so the if/elif/.../else chain generated here is
        always syntactically valid and necessarily covers every possible value."""
        field = categorized_field["field"]
        clauses = categorized_field["clauses"]
        cat_key = Template(r"""${field}_category""").substitute(field=field)
        # repr() rather than manual interpolation between quotes: the label
        # comes from a user STRING_LITERAL and may contain
        # apostrophes/backslashes -- repr() always produces a syntactically
        # valid Python literal, whatever the content.
        lines = [Template(r"""${indent}_v = ${row_var}.pop('${field}')""").substitute(indent=indent, row_var=row_var, field=field)]
        for i, clause in enumerate(clauses):
            label_literal = repr(clause["label"])
            if "otherwise" in clause:
                lines.append(Template(r"""${indent}else: ${row_var}['${cat_key}'] = ${label_literal}""").substitute(indent=indent, row_var=row_var, cat_key=cat_key, label_literal=label_literal))
            else:
                keyword = "if" if i == 0 else "elif"
                lines.append(Template(r"""${indent}${keyword} _v < ${value}: ${row_var}['${cat_key}'] = ${label_literal}""").substitute(indent=indent, keyword=keyword, value=clause['below'], row_var=row_var, cat_key=cat_key, label_literal=label_literal))
        return lines
