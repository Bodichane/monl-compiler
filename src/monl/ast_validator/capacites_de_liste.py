"""Le filtrage et le tri déclarés sur une route de liste (brique B3).

Seuls les types dont une égalité ou un tri a une sémantique de donnée
ordinaire sont acceptés : `Image` reste un chemin d'asset et `Upload` une
référence de fichier — ni l'un ni l'autre ne devient un critère par
accident."""

from .socle import ASTValidationError


class CapacitesDeListeMixin:
    """Le filtrage et le tri déclarés sur une route de liste (brique B3)."""

    # BRIQUE B3 : ce sont les seuls types dont une égalité ou un tri a une
    # sémantique de donnée ordinaire. `Image` reste un chemin d'asset, et
    # `Upload` une référence de fichier : ni l'un ni l'autre ne devient un
    # critère d'énumération par accident.
    LIST_QUERY_TYPES = (
        "String", "Text", "Integer", "Float", "Boolean", "Date", "DateTime",
        "Email", "UUID", "Money",
    )

    LIST_QUERY_RESERVED = {"limit", "offset", "sort", "direction"}

    LIST_QUERY_SECRET_PARTS = (
        "password", "passwd", "secret", "token", "apikey", "api_key",
    )

    def _valider_capacites_de_liste(self):
        """Valide les filtres et tris déclarés, sans ouvrir un langage de requête.

        BRIQUE B3. La route ne reçoit ni opérateur, ni expression, ni champ
        libre : chaque paramètre de filtre et chaque colonne de tri sont
        nommés dans la spec. Les champs retirés ou transformés en lecture sont
        refusés ici, car un filtre exact permettrait d'en déduire la valeur par
        différence de compte (oracle), même si la réponse ne contient jamais
        le champ.
        """
        self.filterable_fields = []
        self.sortable_fields = []
        seen_filters = set()
        seen_sorts = set()
        has_read = {
            action["target"].split(".", 1)[0]
            for workflow in self.workflows
            for action in workflow["actions"]
            if action["type"] == "Read"
        }

        def reference_parts(rule, kind):
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: rule '{kind}' must reference "
                    f"'Entity.Read', received '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: rule '{kind}' targets entity "
                    f"'{entity}', which does not exist."
                )
            if action != "Read":
                raise ASTValidationError(
                    f"Structure: '{kind}' is only valid on a Read route "
                    f"(received '{reference}')."
                )
            if entity not in has_read:
                raise ASTValidationError(
                    f"Structure: '{reference}' has no read route "
                    f"in the workflows."
                )
            field = rule.get("field")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: '{kind}' targets field '{entity}.{field}', "
                    "which is not a declared attribute."
                )
            if field in self.LIST_QUERY_RESERVED:
                raise ASTValidationError(
                    f"Structure: field '{entity}.{field}' cannot be used for "
                    f"{kind}: its name is reserved for list parameters "
                    "(limit, offset, sort, direction)."
                )
            return entity, field

        def refuser_oracle(entity, field, kind):
            type_champ = self.entities[entity][field]
            if (entity, field) in self.masked_fields:
                raison = "hidden: counting it would reveal a masked value"
            elif any(item["entity"] == entity and item["field"] == field
                     for item in self.categorized_fields):
                raison = "categorized: counting it would reveal the number replaced by a label"
            elif type_champ == "Upload":
                raison = "Upload: counting it would reveal whether a file exists"
            else:
                compact = field.lower().replace("-", "_")
                if any(part in compact for part in self.LIST_QUERY_SECRET_PARTS):
                    raison = "secret name: counting it would reveal sensitive data"
                else:
                    return type_champ
            raise ASTValidationError(
                f"Security: '{entity}.{field}' cannot be used for {kind}: "
                f"{raison}. A filter or sort is an oracle; declare a "
                "visible, untransformed field."
            )

        for rule in self.rules:
            kind = rule["type"]
            if kind not in ("filter", "sort"):
                continue
            entity, field = reference_parts(rule, kind)
            type_champ = refuser_oracle(entity, field, kind)
            if type_champ not in self.LIST_QUERY_TYPES:
                raise ASTValidationError(
                    f"Structure: '{kind}' can only target declared scalar fields "
                    f"({', '.join(self.LIST_QUERY_TYPES)}), received "
                    f"'{entity}.{field}: {type_champ}'."
                )
            cible = (entity, field)
            if kind == "filter":
                if cible in seen_filters:
                    raise ASTValidationError(
                        f"Structure: multiple 'filter' rules for "
                        f"'{entity}.{field}' -- one declaration is enough."
                    )
                seen_filters.add(cible)
                self.filterable_fields.append({"entity": entity, "field": field})
            else:
                if cible in seen_sorts:
                    raise ASTValidationError(
                        f"Structure: multiple 'sort' rules for "
                        f"'{entity}.{field}' -- one declaration is enough."
                    )
                seen_sorts.add(cible)
                self.sortable_fields.append({"entity": entity, "field": field})
