"""L'encaissement : qui paie, quoi, et sur quel montant.

`payable` (brique 9) et le préalable `requiresOwn` (point 90). Le refus
cassant du point 79 vit ici : un montant que le client peut écrire fait
échouer la compilation, parce que le propriétaire est le seul à pouvoir
payer — donc un montant écrivable est un montant que le payeur fixe."""

from .socle import ASTValidationError


class CommerceMixin:
    """L'encaissement : qui paie, quoi, et sur quel montant."""

    def _valider_requires_own_et_payable(self):
        """'requiresOwn' (brique 17) et 'payable' (brique paiement) — les
        prérequis de création qui protègent qui peut agir et qui peut encaisser
        (point 111). Extraits ensemble parce qu'ils partagent les prérequis de
        propriété, de visibilité publique et de champs masqués."""
        # AJOUT (roadmap, écosystème de capacités -- brique 17, point 90) :
        # validation de 'requiresOwn'. L'appelant doit DÉJÀ posséder un
        # enregistrement de l'entité nommée pour pouvoir créer celui-ci.
        #
        # Le constat qui l'a fait naître, sur une boutique réelle : deux
        # commandes portaient un compte SANS aucune fiche client. Rien
        # n'obligeait à en créer une avant de commander, et le registre des
        # comptes n'est exposé par aucune route — l'administrateur voyait donc
        # une commande qu'il ne pouvait attribuer à personne. Pour une boutique,
        # ce n'est pas un défaut d'affichage : c'est une commande inexpédiable.
        self.required_profiles = {}
        for rule in self.rules:
            if rule["type"] != "requiresOwn":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' doit référencer 'Entite.Action', "
                    f"reçu '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            requise = rule["value"]
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' cible l'entité '{entity}' qui n'existe pas."
                )
            # Seule la création peut l'exiger : c'est le moment où
            # l'enregistrement naît sans propriétaire nommé. Sur Read/Update/
            # Delete, l'enregistrement existe déjà — exiger une fiche a
            # posteriori rendrait inaccessibles des données qu'on possède.
            if act_type != "Create":
                raise ASTValidationError(
                    f"Structure : 'requiresOwn' ne vaut que sur '{entity}.Create' "
                    f"(reçu '{entity}.{act_type}') -- sur une action de lecture ou de "
                    f"modification, l'enregistrement existe déjà et sa fiche ne peut "
                    f"plus rien empêcher."
                )
            if requise not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' sur '{entity}.Create' exige un "
                    f"'{requise}', qui n'est pas une entité déclarée."
                )
            if requise == entity:
                raise ASTValidationError(
                    f"Structure : '{entity}.Create requiresOwn {entity}' -- une entité ne "
                    f"peut pas exiger d'elle-même : le premier enregistrement ne pourrait "
                    f"jamais être créé."
                )
            # L'entité exigée doit être possédée DIRECTEMENT par un acteur :
            # « en posséder un » n'a de sens que si la propriété se déduit du
            # jeton. Une entité possédée transitivement (brique 11) ne dit pas
            # à quel COMPTE elle appartient sans jointure, et une entité sans
            # propriétaire du tout n'appartient à personne.
            proprietaires = {v for (ent, _act), v in self.ownership_rules.items()
                             if ent == requise}
            if not (proprietaires & set(self.actors)):
                raise ASTValidationError(
                    f"Structure : '{entity}.Create requiresOwn {requise}', mais "
                    f"'{requise}' n'est possédé par aucun acteur -- « en posséder un » "
                    f"ne veut alors rien dire. Ajouter une règle "
                    f"'rule {requise}.Read ownedBy <Acteur>'."
                )
            # Une création publique n'a aucune identité : impossible de chercher
            # « sa » fiche. Même refus que 'generated' et 'payable', même raison.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.Create' est 'public' et exige pourtant un "
                    f"'{requise}' possédé -- incompatible : sans appelant identifié, "
                    f"aucune fiche ne peut être cherchée."
                )
            if entity in self.required_profiles:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'requiresOwn' déclarées pour "
                    f"'{entity}.Create' -- une seule autorisée."
                )
            self.required_profiles[entity] = requise

        # AJOUT (roadmap, brique paiement -- point 74) : validation de
        # 'payable'. La règle nomme le champ qui porte le MONTANT ; l'entité
        # qui le contient est celle qu'on encaisse. Les refus ci-dessous sont
        # le cœur de la brique : un paiement mal déclaré doit échouer à la
        # compilation, jamais au moment d'encaisser.
        self.payable_fields = []
        for rule in self.rules:
            if rule["type"] != "payable":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'payable' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'payable' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'payable' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'}) -- "
                    f"on n'encaisse pas du texte."
                )
            # Un montant masqué serait invérifiable par le client qui paie :
            # il ne pourrait pas confronter ce qu'on lui demande à ce qu'il a
            # commandé.
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'payable' -- incompatible : "
                    f"un montant qu'on ne peut pas lire ne peut pas être vérifié par celui qui le règle."
                )
            if any(p["entity"] == entity for p in self.payable_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}' porte plusieurs champs 'payable' -- un seul montant par entité, "
                    f"sinon rien ne dit lequel encaisser."
                )
            # Encaisser exige de savoir QUI paie : une création publique n'a
            # aucune identité à rattacher au règlement, ni personne à qui
            # rendre l'argent.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable', mais '{entity}.Create' est 'public' -- "
                    f"incompatible : un paiement exige un appelant identifié."
                )
            # CORRECTIF SÉCURITÉ : sans relation entrante, le générateur ne
            # peut déterminer AUCUN propriétaire pour la route de règlement,
            # qui accepte alors n'importe quel appelant authentifié pour
            # n'importe quel enregistrement (IDOR). Même exigence que pour
            # 'increments'/'decrements' ci-dessous -- une relation doit
            # exister pour savoir QUI possède la ligne qu'on encaisse.
            has_owner_relation = any(
                (rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity)
                or (rel["type"] == "belongsTo" and rel["source"] == entity)
                for rel in self.relations
            )
            if not has_owner_relation:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable', mais aucune relation ne désigne qui "
                    f"possède un enregistrement de '{entity}' (ex. 'Client hasMany {entity}') -- sans elle, "
                    f"la route de règlement ne pourrait vérifier qui a le droit de payer."
                )
            # LEVÉ AU POINT 87. Le point 81 refusait ici toute entité possédée
            # TRANSITIVEMENT, parce que la route de règlement comparait la clé
            # étrangère de propriété à `current_user_id` — or sous chaîne cette
            # colonne porte un id d'enregistrement intermédiaire, pas un id de
            # compte. Le refus protégeait donc d'une comparaison fausse, pas
            # d'une impossibilité : la même brique 11 fournissait déjà, dans
            # `_owner_lookup_sql`, la jointure qui rend l'id de COMPTE. La route
            # l'emploie désormais, et la comparaison redevient exacte.
            #
            # Ce qui garde la brique sûre n'a pas bougé : la chaîne doit
            # remonter à un acteur (refus du point 81, plus haut), le montant
            # doit rester incalculable par le client (refus du point 79, dans le
            # recoupement plus bas), et une relation entrante doit exister
            # (juste au-dessus). Aucun de ces trois refus n'est affaibli.
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
                    f"Structure : '{entity}.{field}' porte "
                    f"'{ '/'.join(bounds) }' alors que le SERVEUR calcule ce champ : il "
                    f"est absent du corps de requête, donc la borne ne s'appliquerait "
                    f"à rien. La retirer, ou borner le champ d'où la valeur vient."
                )
            if "required" in constraints:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'required' alors que le SERVEUR "
                    f"le calcule : le client ne peut pas le fournir, et le contrat "
                    f"dirait à la fois « à remplir » et « à ne pas envoyer »."
                )

        for payable in self.payable_fields:
            entity, field = payable["entity"], payable["field"]
            if (entity, field) not in derived and (entity, field) not in sums:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable' mais le client peut l'écrire -- "
                    f"le créateur d'un '{entity}' en devient le propriétaire, donc le payeur : il "
                    f"fixerait lui-même ce qu'il règle. Ajouter une règle qui fait calculer le "
                    f"montant par le serveur, par exemple "
                    f"'rule {entity}.{field} derivedFrom Article.prix by quantite', ou "
                    f"'rule {entity}.{field} sumOf Ligne.sousTotal' pour un panier."
                )
            total = sums.get((entity, field))
            if total is not None:
                source = (total["source_entity"], total["source_field"])
                if source not in derived and source not in sums:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est 'payable' et somme "
                        f"'{total['source_entity']}.{total['source_field']}', que le client peut "
                        f"écrire -- additionner un montant fourni par le payeur donne un total que le "
                        f"payeur fixe encore, en une addition de plus. Faire calculer la ligne par le "
                        f"serveur, par exemple 'rule {total['source_entity']}."
                        f"{total['source_field']} derivedFrom Article.prix by quantite'."
                    )

    def _valider_proprietaire_paiement(self):
        """Vérifie qu'un montant payable remonte réellement jusqu'à un compte."""
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
                    f"Structure : '{entity}.{payable['field']}' est 'payable', mais aucun "
                    f"ACTEUR ne possède un enregistrement de '{entity}'. Une relation vers "
                    f"une table métier ne suffit pas : la colonne qu'elle produit porte "
                    f"l'id de cette ligne, pas celui d'un compte, et la route de règlement "
                    f"la compare à l'appelant. Déclarer 'un_acteur hasMany {entity}', ou "
                    f"rattacher '{entity}' à un acteur à travers son parent "
                    f"('rule {entity}.Read ownedBy <Parent>')."
                )
