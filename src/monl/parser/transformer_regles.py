"""Les `rule` — une production NOMMÉE par règle.

Le piège qui a fondé cette forme (point 6) : un mot-clé littéral anonyme est
filtré par Lark AVANT le transformateur, donc une production partagée ne
sait pas quelle règle elle traite. `restrictedTo` n'atteignait jamais le
Transformer, et l'audit de sécurité ne se déclenchait donc jamais."""

import ast as py_ast

from lark import Transformer, v_args


@v_args(inline=True)
class ReglesMixin(Transformer):
    """Les `rule` — une production NOMMÉE par règle.

    HÉRITE DE ``Transformer`` À DESSEIN, et porte son PROPRE ``@v_args``.
    Lark applique ce décorateur en SAUTANT tout nom déjà présent dans la MRO
    au-dessus de la classe décorée : les méthodes d'un mixin nu ne seraient
    donc jamais enveloppées, et recevraient une LISTE d'enfants au lieu
    d'arguments inlinés. Rien ne planterait — le sens du parsing changerait.
    """

    def constraint_rule(self, reference, valid_type, value=None):
        data = {"reference": str(reference), "type": str(valid_type)}
        if value is not None:
            data["value"] = str(value)
        return {"rule": data}

    def oneof_rule(self, reference, *valeurs):
        return {"rule": {"reference": str(reference), "type": "oneOf",
                         "value": [str(v).strip('"') for v in valeurs]}}

    def release_rule(self, reference, valeur, entite):
        return {"rule": {"reference": str(reference), "type": "releases",
                         "value": str(valeur).strip('"'), "entity": str(entite)}}

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
                # Le lexer a déjà garanti un STRING_LITERAL. Ce repli garde un
                # diagnostic de validation lisible si une future évolution de
                # la grammaire accepte une séquence d'échappement inconnue.
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

    def _quantite(self, amount):
        """« by 3 » ou « by quantity » — l'un est une constante, l'autre un champ
        de l'entité déclenchante (brique 14, point 86). Le type du jeton Lark
        les distingue : ne pas le perdre ici, le validateur en a besoin."""
        if amount is None:
            return {"amount": 1, "amount_field": None}
        if getattr(amount, "type", None) == "INT" or str(amount).isdigit():
            return {"amount": int(amount), "amount_field": None}
        return {"amount": None, "amount_field": str(amount)}

    def decrement_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "decrements",
            "value": str(target_ref), **self._quantite(amount),
        }}

    def increment_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "increments",
            "value": str(target_ref), **self._quantite(amount),
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

    def numbering_rule(self, reference, gabarit):
        token = str(gabarit)
        return {"rule": {"reference": str(reference), "type": "numbered",
                         "value": token[1:-1].replace('\\"', '"')
                                             .replace('\\\\', '\\')}}

    def requirement_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "requiresOwn",
                         "value": str(owner_entity)}}
