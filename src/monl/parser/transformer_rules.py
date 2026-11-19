"""The `rule`s — one NAMED production per rule.

The trap that founded this shape (point 6): an anonymous literal keyword
is filtered by Lark BEFORE the transformer, so a shared production does
not know which rule it handles. `restrictedTo` never reached the
Transformer, so the security audit never fired."""

import ast as py_ast

from lark import Transformer, v_args


@v_args(inline=True)
class RulesMixin(Transformer):
    """The `rule`s — one NAMED production per rule.

    INHERITS FROM ``Transformer`` ON PURPOSE, and carries its OWN
    ``@v_args``. Lark applies this decorator by SKIPPING any name already
    present in the MRO above the decorated class: a bare mixin's methods would
    therefore never be wrapped, and would receive a LIST of children instead
    of inlined arguments. Nothing would crash — the meaning of the parse would
    change."""

    def constraint_rule(self, reference, valid_type, value=None):
        data = {"reference": str(reference), "type": str(valid_type)}
        if value is not None:
            data["value"] = str(value)
        return {"rule": data}

    def oneof_rule(self, reference, *values):
        return {"rule": {"reference": str(reference), "type": "oneOf",
                         "value": [str(v).strip('"') for v in values]}}

    def release_rule(self, reference, valeur, entity):
        return {"rule": {"reference": str(reference), "type": "releases",
                         "value": str(valeur).strip('"'), "entity": str(entity)}}

    def upload_rule(self, reference, maximum, *types):
        return {"rule": {
            "reference": str(reference), "type": "upload",
            "max_bytes": int(maximum),
            "accepted_types": [str(value).strip('"') for value in types],
        }}

    def send_rule(self, reference, subject, body):
        def decode(token):
            try:
                return str(py_ast.literal_eval(str(token)))
            except (SyntaxError, ValueError):
                # The lexer has already guaranteed a STRING_LITERAL. This
                # fallback keeps a readable validation diagnostic if a future
                # grammar change accepts an unknown escape sequence.
                return str(token)[1:-1]

        return {"rule": {
            "reference": str(reference), "type": "sends",
            "subject": decode(subject), "body": decode(body),
        }}

    def filter_rule(self, reference, field):
        return {"rule": {"reference": str(reference), "type": "filter",
                          "field": str(field)}}

    def sort_rule(self, reference, field):
        return {"rule": {"reference": str(reference), "type": "sort",
                          "field": str(field)}}

    def restriction_rule(self, reference, actor_name):
        return {"rule": {"reference": str(reference), "type": "restrictedTo", "value": str(actor_name)}}

    def postpayment_rule(self, reference, actor_name):
        return {"rule": {"reference": str(reference), "type": "writableAfterPayment",
                         "value": str(actor_name)}}

    def sharing_rule(self, reference, *actor_names):
        return {"rule": {"reference": str(reference), "type": "sharedBy", "value": [str(a) for a in actor_names]}}

    def ownership_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "ownedBy", "value": str(owner_entity)}}

    def access_rule(self, reference, *party_columns):
        return {"rule": {"reference": str(reference), "type": "accessibleBy",
                         "value": [str(c) for c in party_columns]}}

    def visibility_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "public"}}

    def conditional_visibility_rule(self, reference, field, value):
        return {"rule": {"reference": str(reference), "type": "publicWhen",
                          "field": str(field),
                          "value": str(value).strip('"')}}

    def uniqueness_rule(self, reference, *parents):
        return {"rule": {"reference": str(reference), "type": "oncePer",
                          "parents": [str(parent) for parent in parents]}}

    def masking_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "hidden"}}

    def _quantity(self, amount):
        """"by 3" or "by quantity" — one is a constant, the other a field of the
        triggering entity (brick 14, point 86). The Lark token's type tells them
        apart: do not lose it here, the validator needs it."""
        if amount is None:
            return {"amount": 1, "amount_field": None}
        if getattr(amount, "type", None) == "INT" or str(amount).isdigit():
            return {"amount": int(amount), "amount_field": None}
        return {"amount": None, "amount_field": str(amount)}

    def decrement_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "decrements",
            "value": str(target_ref), **self._quantity(amount),
        }}

    def increment_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "increments",
            "value": str(target_ref), **self._quantity(amount),
        }}

    def category_below(self, label, threshold):
        return {"label": str(label).strip('"'), "below": int(threshold)}

    def category_otherwise(self, label):
        return {"label": str(label).strip('"'), "otherwise": True}

    def categorization_rule(self, reference, *clauses):
        return {"rule": {
            "reference": str(reference), "type": "categorized",
            "value": list(clauses),
        }}

    def generation_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "generated"}}

    def payable_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "payable"}}

    def derivation_rule(self, reference, source_ref, factor):
        return {"rule": {
            "reference": str(reference), "type": "derivedFrom",
            "value": str(source_ref), "factor": str(factor),
        }}

    def aggregation_rule(self, reference, source_ref):
        return {"rule": {
            "reference": str(reference), "type": "sumOf",
            "value": str(source_ref),
        }}

    def timestamp_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "timestamp"}}

    def numbering_rule(self, reference, template):
        token = str(template)
        return {"rule": {"reference": str(reference), "type": "numbered",
                         "value": token[1:-1].replace('\\"', '"')
                                             .replace('\\\\', '\\')}}

    def requirement_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "requiresOwn",
                         "value": str(owner_entity)}}
