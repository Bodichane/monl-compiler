"""De l'AST validé au modèle que le générateur manipule."""

from ..ir import AccessPolicy, EffectPlan, EntityModel, FieldPolicy


class ModeleMixin:
    """De l'AST validé au modèle que le générateur manipule."""

    def _build_entity_models(self) -> dict[str, EntityModel]:
        """Consolide une fois les politiques réparties dans l'IR validée."""
        models = {}
        for entity, fields in self.entities.items():
            derived = {r["field"]: r for r in self.derived_by_entity.get(entity, [])}
            aggregated = {
                r["field"]: r for r in self.aggregated_by_entity.get(entity, [])
            }
            numbered = {
                r["field"]: r for r in self.numbered_fields_by_entity.get(entity, [])
            }
            generated = set(self.generated_fields_by_entity.get(entity, []))
            hidden = set(self.hidden_fields_by_entity.get(entity, []))
            categorized = {
                r["field"] for r in self.categorized_fields_by_entity.get(entity, [])
            }
            timestamped = set(self.timestamp_fields_by_entity.get(entity, []))
            postpayment = set(
                self.postpayment_writable_by_entity.get(entity, {}).get("fields", [])
            )
            policies = {}
            for name, type_ in fields.items():
                derived_rule = derived.get(name)
                aggregate_rule = aggregated.get(name)
                numbering_rule = numbered.get(name)
                upload_rule = next(
                    (u for u in self.upload_fields_by_entity.get(entity, [])
                     if u["field"] == name), None)
                server_generated = (
                    name in generated
                    or derived_rule is not None
                    or aggregate_rule is not None
                    or numbering_rule is not None
                    or name in timestamped
                )
                policies[name] = FieldPolicy(
                    name=name,
                    type=type_,
                    hidden_in_reads=name in hidden,
                    server_generated=server_generated,
                    categorized_in_reads=name in categorized,
                    postpayment_only=name in postpayment,
                    allowed_values=tuple(
                        self.enumerated_fields.get(entity, {}).get(name, [])
                    ),
                    constraints=self.field_constraints.get(entity, {}).get(name, {}),
                    derived_rule=derived_rule,
                    aggregate_rule=aggregate_rule,
                    timestamped=name in timestamped,
                    numbering_rule=numbering_rule,
                    upload_rule=upload_rule,
                )
            models[entity] = EntityModel(name=entity, fields=policies)
        return models

    def _build_access_policies(self) -> dict[tuple[str, str], AccessPolicy]:
        """Consolide les sources de contrôle d'accès par route logique."""
        policies = {}
        for (action, _key), route in self._compute_route_map().items():
            entity = route.base_target
            reference = f"{entity}.{action}"
            condition = self.public_conditions.get((entity, "Read")) \
                if action == "Read" else None
            policies[(entity, action)] = AccessPolicy(
                entity=entity,
                action=action,
                actors=frozenset(route.actors),
                public=((entity, action) in self.public_actions or condition is not None),
                public_condition=condition,
                owner_entity=self.ownership.get(reference),
                transitive_ownership=self.transitive_ownership.get(entity),
                party_fields=tuple(self.access_parties.get(reference, [])),
                supervisors=frozenset(self.access_supervisors.get(reference, [])),
            )
        return policies

    def _build_effect_plans(self) -> tuple[EffectPlan, ...]:
        """Réunit les effets validés dans un catalogue commun et ordonné."""
        plans = []
        for entity, rules in self.derived_by_entity.items():
            plans.extend(EffectPlan(
                kind="derive", trigger_entity=entity, target_entity=entity,
                field=rule["field"], source_entity=rule["source_entity"],
                source_field=rule["source_field"], config=rule,
            ) for rule in rules)
        for source, rules in self.aggregations_by_source.items():
            plans.extend(EffectPlan(
                kind="aggregate", trigger_entity=source,
                target_entity=rule["entity"], field=rule["field"],
                source_entity=source, source_field=rule["source_field"], config=rule,
            ) for rule in rules)
        for trigger, rules in self.reputation_rules_by_trigger.items():
            plans.extend(EffectPlan(
                kind="increment" if rule["direction"] == "increments" else "decrement",
                trigger_entity=trigger, target_entity=rule["target_entity"],
                field=rule["target_field"], source_entity=None,
                source_field=rule.get("amount_field"), config=rule,
            ) for rule in rules)
        for entity, rules in self.release_rules_by_entity.items():
            plans.extend(EffectPlan(
                kind="release", trigger_entity=entity,
                target_entity=rule["releases"], field=rule["field"],
                source_entity=None, source_field=None, config=rule,
            ) for rule in rules)
        plans.extend(EffectPlan(
            kind="payment_lock", trigger_entity=entity, target_entity=entity,
            field=field, source_entity=None, source_field=None,
            config={"entity": entity, "field": field},
        ) for entity, field in self.payable_by_entity.items())
        plans.extend(EffectPlan(
            kind="postpayment_write", trigger_entity=entity, target_entity=entity,
            field=None, source_entity=None, source_field=None, config=config,
        ) for entity, config in self.postpayment_writable_by_entity.items())
        plans.extend(EffectPlan(
            kind="message", trigger_entity=rule["trigger_entity"],
            target_entity=rule["trigger_entity"], field=None,
            source_entity=None, source_field=None, config=rule,
        ) for rule in self.message_rules_by_trigger.values())
        return tuple(plans)

    def _effects(self, kind, *, trigger=None, target=None):
        return [plan for plan in self.effect_plans
                if plan.kind == kind
                and (trigger is None or plan.trigger_entity == trigger)
                and (target is None or plan.target_entity == target)]

    def _compute_fk_placements(self):
        """CORRECTIF (roadmap) : jusqu'ici, seul le type de relation 'hasMany'
        produisait réellement une colonne de clé étrangère — 'belongsTo' et
        'hasOne' étaient acceptés par la grammaire mais totalement ignorés par
        le générateur (aucune colonne, aucun effet). Cette méthode calcule,
        pour les 3 types de relation, quelle entité porte la colonne de clé
        étrangère et vers quelle entité "propriétaire" elle pointe :
          - hasMany  : "A hasMany B" -> B porte la colonne a_id (A est parent)
          - hasOne   : idem hasMany, avec en plus une contrainte UNIQUE (1-1)
          - belongsTo: "A belongsTo B" -> A porte la colonne b_id (B est parent)
        Retourne : {entité_qui_porte_la_colonne: [{"fk_column", "owner_entity", "unique"}]}
        """
        placements = {}
        for relation in self.relation_models:
            placements.setdefault(relation.held_entity, []).append({
                "fk_column": relation.fk_column,
                "owner_entity": relation.owner_entity,
                "unique": relation.unique,
            })
        return placements

    def _compute_seed_data(self):
        """AJOUT (roadmap frontend, bloc 'seed') : regroupe les données de
        démonstration par nom de table (lowercase), dans l'ordre de
        déclaration. Retourne {table: [ {champ: valeur}, ... ]}. Plusieurs
        blocs 'seed' visant la même entité sont concaténés.

        Les champs 'generated' (ex. pseudonyme anonyme d'auteur) ne sont pas
        renseignés par l'utilisateur dans le seed (le validateur le tolère
        car ils sont retirés du schéma d'entrée) ; comme à la création réelle
        ils sont assignés par le serveur, on leur donne ici une valeur
        synthétique déterministe ('Anon#1000', 'Anon#1001'…) pour que le seed
        produise des enregistrements complets et cohérents avec le rendu
        (fil social, etc.).

        BRIQUE 21 (point 100) : chaque entrée est désormais un COUPLE
        {"values": {...}, "parent": None | {...}}, et non plus la seule ligne.
        Le rattachement d'un enfant ne peut pas être résolu ici : l'`id` du
        parent n'existe qu'une fois la ligne insérée, et le socle ne sème une
        table que si elle est VIDE — un parent déjà peuplé par de vraies données
        ne serait donc pas réinséré, et un rang calculé à la compilation
        désignerait la mauvaise ligne. La désignation voyage telle quelle et se
        résout par un SELECT au démarrage."""
        seed_data = {}
        for seed in self.seeds:
            entity = seed["entity"]
            table = entity.lower()
            generated = self.generated_fields_by_entity.get(entity, [])
            parent = seed.get("parent")
            rattachement = None
            if parent:
                rattachement = {
                    "column": f"{parent['entity'].lower()}_id",
                    "table": parent["entity"].lower(),
                    "field": parent["field"],
                    "value": parent["value"],
                }
            seed_data.setdefault(table, [])
            for row in seed["rows"]:
                filled = dict(row)
                for gfield in generated:
                    if gfield not in filled:
                        # Pseudonyme synthétique stable, unique par ligne.
                        filled[gfield] = f"Anon#{1000 + len(seed_data[table])}"
                seed_data[table].append({"values": filled, "parent": rattachement})
        return seed_data
