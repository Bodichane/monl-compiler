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
                    f"Structure : la règle '{kind}' doit référencer "
                    f"'Entite.Read', reçu '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle '{kind}' cible l'entité "
                    f"'{entity}' qui n'existe pas."
                )
            if action != "Read":
                raise ASTValidationError(
                    f"Structure : '{kind}' ne vaut que sur une route Read "
                    f"(reçu '{reference}')."
                )
            if entity not in has_read:
                raise ASTValidationError(
                    f"Structure : '{reference}' n'a aucune route de lecture "
                    f"dans les workflows."
                )
            field = rule.get("field")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : '{kind}' cible le champ '{entity}.{field}', "
                    "qui n'est pas un attribut déclaré."
                )
            if field in self.LIST_QUERY_RESERVED:
                raise ASTValidationError(
                    f"Structure : le champ '{entity}.{field}' ne peut pas être "
                    f"{kind} : son nom est réservé aux paramètres de liste "
                    "(limit, offset, sort, direction)."
                )
            return entity, field

        def refuser_oracle(entity, field, kind):
            type_champ = self.entities[entity][field]
            if (entity, field) in self.masked_fields:
                raison = "hidden : le compter révélerait une valeur masquée"
            elif any(item["entity"] == entity and item["field"] == field
                     for item in self.categorized_fields):
                raison = "categorized : le compter révélerait le nombre remplacé par un libellé"
            elif type_champ == "Upload":
                raison = "Upload : le compter révélerait l'existence d'un fichier"
            else:
                compact = field.lower().replace("-", "_")
                if any(part in compact for part in self.LIST_QUERY_SECRET_PARTS):
                    raison = "nom de secret : le compter révélerait une donnée sensible"
                else:
                    return type_champ
            raise ASTValidationError(
                f"Sécurité : '{entity}.{field}' ne peut pas être {kind} : "
                f"{raison}. Un filtre ou un tri est un oracle ; déclarer un "
                "champ visible et non transformé."
            )

        for rule in self.rules:
            kind = rule["type"]
            if kind not in ("filter", "sort"):
                continue
            entity, field = reference_parts(rule, kind)
            type_champ = refuser_oracle(entity, field, kind)
            if type_champ not in self.LIST_QUERY_TYPES:
                raise ASTValidationError(
                    f"Structure : '{kind}' ne peut viser que les champs scalaires "
                    f"déclarés ({', '.join(self.LIST_QUERY_TYPES)}), reçu "
                    f"'{entity}.{field}: {type_champ}'."
                )
            cible = (entity, field)
            if kind == "filter":
                if cible in seen_filters:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'filter' sur "
                        f"'{entity}.{field}' -- une seule déclaration suffit."
                    )
                seen_filters.add(cible)
                self.filterable_fields.append({"entity": entity, "field": field})
            else:
                if cible in seen_sorts:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'sort' sur "
                        f"'{entity}.{field}' -- une seule déclaration suffit."
                    )
                seen_sorts.add(cible)
                self.sortable_fields.append({"entity": entity, "field": field})
