"""Les champs dont le serveur calcule la valeur depuis d'autres lignes.

`derivedFrom` (point 77, né de deux exploits prouvés), `sumOf` (point 82),
les compteurs `increments`/`decrements` et l'unicité composite `oncePer`.
Un montant que le client peut écrire est un montant qu'il fixe lui-même :
c'est la raison d'être de la moitié des refus rassemblés ici."""

from .socle import ASTValidationError


class ChampsCalculesMixin:
    """Les champs dont le serveur calcule la valeur depuis d'autres lignes."""

    def _valider_champs_derives(self):
        """Valide les champs numériques calculés depuis une ligne liée."""
        self.derived_fields = []
        for rule in self.rules:
            if rule["type"] != "derivedFrom":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            factor = rule["factor"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' doit référencer 'Entite.champ derivedFrom Entite.champ by champ', "
                    f"reçu '{reference} derivedFrom {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : 'derivedFrom' cible l'entité '{entity}' qui n'existe pas.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure : 'derivedFrom' lit l'entité '{source_entity}' qui n'existe pas.")
            field_type = self.entities[entity].get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' calcule '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            source_type = self.entities[source_entity].get(source_field)
            if source_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}.{source_field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {source_type or 'champ inexistant'})."
                )
            factor_type = self.entities[entity].get(factor)
            if factor_type != "Integer":
                raise ASTValidationError(
                    f"Structure : 'derivedFrom ... by {factor}' exige que '{entity}.{factor}' soit un attribut "
                    f"Integer déclaré (reçu : {factor_type or 'champ inexistant'}) -- on multiplie par une quantité."
                )
            required_fields = {r["reference"] for r in self.rules if r.get("type") == "required"}
            if f"{entity}.{factor}" not in required_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{factor}' sert de multiplicateur à 'derivedFrom' et doit donc porter "
                    f"'rule {entity}.{factor} required' -- sinon un client qui l'omet ferait calculer sur du vide."
                )
            if factor == field:
                raise ASTValidationError(f"Structure : '{entity}.{field}' ne peut pas être son propre multiplicateur.")
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'derivedFrom' -- incompatible : "
                    f"un montant calculé qu'on ne peut pas lire ne peut pas être vérifié."
                )
            if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'derivedFrom' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'derivedFrom' -- un seul calcul par champ."
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
                    f"Structure : 'derivedFrom' lit '{source_entity}.{source_field}' depuis '{entity}', ce qui exige "
                    f"une relation entre les deux (ex. '{source_entity} hasMany {entity}'), absente ici -- sans "
                    f"elle, rien ne dit QUELLE ligne de '{source_entity}' lire."
                )
            owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == entity}
            if owners and source_entity in owners:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}', qui est aussi le propriétaire de "
                    f"'{entity}' (règle 'ownedBy') -- sa clé étrangère vient du jeton, pas du client, donc "
                    f"aucune ligne de '{source_entity}' ne peut être désignée à la création."
                )
            if not owners:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' sur '{entity}.{field}' exige que '{entity}' ait un propriétaire "
                    f"(une règle 'ownedBy') -- c'est lui qui distingue la clé étrangère peuplée par le serveur "
                    f"de celle que le client fournit pour désigner la ligne à lire."
                )
            self.derived_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
                "factor": factor,
            })

    def _valider_champs_agreges(self):
        """Valide les champs calculés par somme des lignes enfants."""
        self.aggregated_fields = []
        for rule in self.rules:
            if rule["type"] != "sumOf":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure : 'sumOf' doit référencer 'Entite.champ sumOf Entite.champ', "
                    f"reçu '{reference} sumOf {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : 'sumOf' cible l'entité '{entity}' qui n'existe pas.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure : 'sumOf' additionne l'entité '{source_entity}' qui n'existe pas.")
            field_type = self.entities[entity].get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'sumOf' calcule '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            source_type = self.entities[source_entity].get(source_field)
            if source_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne '{source_entity}.{source_field}', qui doit être un "
                    f"attribut Money, Float ou Integer déclaré (reçu : {source_type or 'champ inexistant'})."
                )
            if source_entity == entity:
                raise ASTValidationError(
                    f"Structure : 'sumOf' fait de '{entity}.{field}' la somme d'un champ de '{entity}' lui-même "
                    f"-- une entité ne peut pas s'additionner. La somme porte sur une entité ENFANT "
                    f"(ex. 'Commande hasMany Ligne')."
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
                    f"Structure : 'sumOf' additionne '{source_entity}' depuis '{entity}', ce qui exige "
                    f"une relation parent-enfant (ex. '{entity} hasMany {source_entity}'), absente ici -- "
                    f"sans elle, rien ne dit QUELLES lignes de '{source_entity}' additionner, et la somme "
                    f"porterait sur la table entière."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'sumOf' -- incompatible : "
                    f"un total calculé qu'on ne peut pas lire ne peut pas être vérifié."
                )
            if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'sumOf' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte à la fois 'derivedFrom' et 'sumOf' -- deux "
                    f"calculs concurrents pour un seul champ. 'derivedFrom' lit UNE ligne liée, 'sumOf' "
                    f"additionne des enfants : choisir lequel."
                )
            if any(a["entity"] == entity and a["field"] == field for a in self.aggregated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'sumOf' -- une seule somme par champ."
                )
            source_owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == source_entity}
            if not source_owners:
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne '{source_entity}', qui n'a pas de propriétaire "
                    f"(une règle 'ownedBy') -- c'est lui qui distingue la clé étrangère peuplée par le "
                    f"serveur de celle que le client fournit pour désigner le parent. Sans elle, "
                    f"n'importe quel compte pourrait ajouter une ligne au total d'un tiers."
                )
            self.aggregated_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
            })

    def _valider_effets_compteurs(self):
        """Valide les effets de compteur déclenchés à la création."""
        self.reputation_rules = []
        for rule in self.rules:
            if rule["type"] not in ("decrements", "increments"):
                continue
            direction = rule["type"]
            trigger_ref, target_ref = rule["reference"], rule["value"]
            if "." not in trigger_ref or "." not in target_ref:
                raise ASTValidationError(
                    f"Structure : la règle '{direction}' doit référencer 'Entite.Create {direction} Entite.champ', "
                    f"reçu '{trigger_ref} {direction} {target_ref}'."
                )
            trigger_entity, trigger_action = trigger_ref.split(".", 1)
            target_entity, target_field = target_ref.split(".", 1)
            if trigger_entity not in self.entities:
                raise ASTValidationError(f"Structure : '{direction}' référence l'entité '{trigger_entity}' qui n'existe pas.")
            if trigger_action != "Create":
                raise ASTValidationError(
                    f"Structure : '{direction}' n'est pris en charge que sur 'Create' pour l'instant "
                    f"(reçu '{trigger_entity}.{trigger_action}')."
                )
            if target_entity not in self.entities:
                raise ASTValidationError(f"Structure : '{direction}' référence l'entité '{target_entity}' qui n'existe pas.")
            target_type = self.entities[target_entity].get(target_field)
            if target_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure : '{direction}' cible le champ '{target_entity}.{target_field}', qui doit être "
                    f"un attribut Integer ou Float déclaré (reçu : {target_type or 'champ inexistant'})."
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
                    f"Structure : '{direction}' sur '{trigger_entity}.Create' vers '{target_entity}.{target_field}' "
                    f"exige une relation entre les deux (ex. '{target_entity} hasMany {trigger_entity}'), absente ici."
                )
            amount_field = rule.get("amount_field")
            if amount_field:
                amount_type = self.entities[trigger_entity].get(amount_field)
                if amount_type != "Integer":
                    raise ASTValidationError(
                        f"Structure : '{direction} ... by {amount_field}' désigne un champ de "
                        f"'{trigger_entity}' qui doit être un Integer déclaré "
                        f"(reçu : {amount_type or 'champ inexistant'})."
                    )
                required = {r["reference"] for r in self.rules if r.get("type") == "required"}
                if f"{trigger_entity}.{amount_field}" not in required:
                    raise ASTValidationError(
                        f"Structure : '{trigger_entity}.{amount_field}' sert de quantité à "
                        f"'{direction}' : il lui faut 'rule {trigger_entity}.{amount_field} "
                        f"required', sinon un client qui l'omet ferait décompter sur du vide."
                    )
            self.reputation_rules.append({
                "trigger_entity": trigger_entity, "target_entity": target_entity,
                "target_field": target_field, "amount": rule.get("amount"),
                "amount_field": amount_field, "direction": direction,
            })

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
                    f"Structure : 'oncePer' doit référencer 'Entite.Create', reçu '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'oncePer' cible l'entité '{entity}' qui n'existe pas."
                )
            if action != "Create":
                raise ASTValidationError(
                    f"Structure : 'oncePer' ne vaut que sur 'Create' (reçu '{reference}')."
                )
            parents = list(rule.get("parents") or [])
            if len(parents) < 2 or len(set(parents)) != len(parents):
                raise ASTValidationError(
                    f"Structure : 'oncePer' sur '{reference}' exige au moins deux parents distincts."
                )
            for parent in parents:
                if parent not in self.entities and parent not in self.actors:
                    raise ASTValidationError(
                        f"Structure : 'oncePer' référence le parent '{parent}', qui n'existe pas."
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
                        f"Structure : 'oncePer' exige une relation entre '{parent}' et '{entity}'."
                    )
            if not any(parent in self.actors for parent in parents):
                raise ASTValidationError(
                    f"Structure : 'oncePer' sur '{reference}' doit inclure un parent acteur "
                    "pour identifier le compte courant."
                )
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{reference}' est public, donc aucun compte ne peut porter "
                    "l'unicité 'oncePer'."
                )
            self.once_per_rules.append({"trigger_entity": entity, "parents": parents})
