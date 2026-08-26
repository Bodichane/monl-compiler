"""Ce qu'un enregistrement devient APRÈS son règlement.

`releases` (point 98 — atteindre une valeur défait un effet, une seule
fois, vers un état terminal) et `writableAfterPayment` (point 113, la
seule voie pour faire avancer un champ sans toucher au verrou générique
d'Update, qui reste absolu)."""

from .socle import ASTValidationError


class CycleDeVieMixin:
    """Ce qu'un enregistrement devient APRÈS son règlement."""

    def _valider_regles_liberation(self):
        """Valide les transitions qui rendent un compteur décrémenté."""
        self.release_rules = []
        for rule in self.rules:
            if rule["type"] != "releases":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' cible l'entité '{entity}' qui n'existe pas."
                )
            choices = self.enumerated_fields.get(entity, {}).get(field)
            if not choices:
                raise ASTValidationError(
                    f"Structure : 'releases' exige que '{entity}.{field}' porte un 'oneOf' — "
                    f"sans liste de valeurs, une faute de frappe donnerait une règle qui ne se déclenche jamais."
                )
            if rule["value"] not in choices:
                raise ASTValidationError(
                    f"Structure : 'releases' se déclenche sur la valeur {rule['value']!r}, "
                    f"absente du 'oneOf' de '{entity}.{field}' "
                    f"({', '.join(repr(choice) for choice in choices)}) — elle ne surviendrait jamais."
                )
            released_entity = rule["entity"]
            if released_entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'releases' nomme l'entité '{released_entity}', qui n'existe pas."
                )
            decrements = [
                item for item in self.reputation_rules
                if item["trigger_entity"] == released_entity and item["direction"] == "decrements"
            ]
            if not decrements:
                raise ASTValidationError(
                    f"Structure : 'releases {released_entity}' ne libérerait rien — cette entité ne porte "
                    f"aucune règle 'decrements'. C'est ce qu'un décompte a consommé que l'on rend."
                )
            if not any(rel["source"] == entity and rel["target"] == released_entity for rel in self.relations):
                raise ASTValidationError(
                    f"Structure : 'releases' exige une relation '{entity} hasMany {released_entity}' — "
                    f"sans elle, rien ne dit quelles lignes de {released_entity} dépendent de ce {entity}."
                )
            if any(item["entity"] == entity and item["field"] == field for item in self.release_rules):
                raise ASTValidationError(
                    f"Structure : deux règles 'releases' sur '{entity}.{field}' — la première libération "
                    f"rendrait déjà le décompte, la seconde le rendrait une deuxième fois."
                )
            self.release_rules.append({
                "entity": entity, "field": field, "value": rule["value"], "releases": released_entity,
            })

    def _valider_regle_apres_paiement(self):
        """Valide le canal d'écriture réservé qui contourne le CRUD verrouillé."""
        self.postpayment_writable = {}
        champs_vus = set()
        regles_serveur = (
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
                    f"Structure : la règle 'writableAfterPayment' doit référencer "
                    f"'Entite.champ', reçu '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' cible l'entité "
                    f"'{entity}' qui n'existe pas.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' cible le champ "
                    f"'{entity}.{field}', qui n'est pas un attribut déclaré.")
            if not any(pf["entity"] == entity for pf in self.payable_fields):
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' ne vaut que sur "
                    f"une entité 'payable' — '{entity}' ne l'est pas.")
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' sur "
                    f"'{entity}.{field}' nomme l'acteur '{actor}', qui n'est pas "
                    f"un acteur déclaré.")
            for type_regle, champs in regles_serveur:
                if any(c["entity"] == entity and c["field"] == field
                       for c in champs):
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois "
                        f"'writableAfterPayment' et '{type_regle}' — incompatible : "
                        f"'{type_regle}' interdit toute écriture cliente.")
            proprietaire = self.transitive_ownership.get(entity, {}).get("actor")
            if proprietaire is None:
                proprietaires_directs = {
                    owner for (owned_entity, _action), owner
                    in self.ownership_rules.items()
                    if owned_entity == entity and owner in self.actors
                }
                if len(proprietaires_directs) == 1:
                    proprietaire = next(iter(proprietaires_directs))
            if proprietaire == actor:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' sur "
                    f"'{entity}.{field}' nomme '{actor}', qui est déjà propriétaire "
                    f"de '{entity}' — le verrou de paiement serait contournable par "
                    f"son propriétaire.")
            config = self.postpayment_writable.get(entity)
            if config and config["actor"] != actor:
                raise ASTValidationError(
                    f"Structure : deux acteurs différents sont déclarés "
                    f"'writableAfterPayment' sur '{entity}' : "
                    f"'{config['actor']}' et '{actor}' — un seul acteur autorisé.")
            if (entity, field) in champs_vus:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'writableAfterPayment' déclarées "
                    f"pour '{entity}.{field}' — une seule autorisée.")
            champs_vus.add((entity, field))
            if config is None:
                config = {"actor": actor, "fields": []}
                self.postpayment_writable[entity] = config
            config["fields"].append(field)
