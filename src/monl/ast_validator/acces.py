"""Le contrôle d'accès : QUI a le droit, et sur QUELLES lignes.

POINT 109 : le modèle de contrôle d'accès vit ici et nulle part ailleurs —
`ownedBy` (direct et transitif), `accessibleBy`, le superviseur, et la
visibilité anonyme. C'est le versant DÉCISION de la sécurité ; le versant
ÉMISSION est `generator/sql.py` (point 108)."""

from .socle import ASTValidationError


class AccesMixin:
    """Le contrôle d'accès : QUI a le droit, et sur QUELLES lignes."""

    def _valider_controle_dacces(self):
        """Le noyau du contrôle d'accès — frontière de sécurité (point 109).

        Rassemble, dans une passe dédiée du pipeline, TOUT ce qui décide QUI
        peut toucher QUOI : les règles 'ownedBy' (propriété
        directe), la résolution de la chaîne transitive jusqu'à un acteur
        (briques 11 et 24), les règles 'accessibleBy' (accès à plusieurs
        parties) et le rôle superviseur (brique 23). Peuple self.ownership_rules,
        self.transitive_ownership et self.access_supervisors, lus ensuite par le
        générateur via _transitive_chain / _owner_lookup_sql.

        N'utilise que self.* et constitue une frontière autonome du pipeline.
        """
        # AJOUT (post-v6, roadmap) : les règles 'ownedBy' restreignent une action
        # au seul enregistrement appartenant à l'acteur courant. Elles nécessitent
        # qu'une relation 'hasMany' existe entre l'entité "propriétaire" déclarée
        # et l'entité cible, pour fournir la colonne de clé étrangère qui stocke
        # le propriétaire (générée automatiquement en <source>_id).
        self.ownership_rules = {}
        for rule in self.rules:
            if rule["type"] == "ownedBy":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule must reference 'Entity.Action', got '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                owner_entity = rule["value"]

                if entity not in self.entities:
                    raise ASTValidationError(f"Structure: the 'ownedBy' rule targets entity '{entity}', which does not exist.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure: invalid action '{act_type}' in the 'ownedBy' rule on '{entity}'.")
                # CORRECTIF (bêta 3) : 'Create' était accepté alors que le
                # générateur n'en fait rien — une règle de sécurité acceptée
                # puis silencieusement ignorée est pire que son absence, car
                # l'auteur de la spec croit la protection en place. À la
                # création, le propriétaire est l'appelant par construction :
                # la règle n'a rien à restreindre.
                if act_type == "Create":
                    raise ASTValidationError(
                        f"Structure: 'ownedBy' is not meaningful on '{entity}.Create' — "
                        "on creation, the owner is the caller by definition. "
                        "Use 'ownedBy' on Read, Update, or Delete.")

                # CORRECTIF (roadmap) : la vérification de la relation nécessaire
                # est désormais généralisée aux 3 types (hasMany, hasOne,
                # belongsTo), cohérente avec _compute_fk_placements() dans
                # generator.py — avant, seul 'hasMany' était reconnu ici, alors
                # que 'belongsTo'/'hasOne' fournissent aussi une colonne de
                # propriété valide selon leur propre convention de placement.
                has_matching_relation = any(
                    (rel["type"] in ("hasMany", "hasOne") and rel["source"] == owner_entity and rel["target"] == entity)
                    or (rel["type"] == "belongsTo" and rel["target"] == owner_entity and rel["source"] == entity)
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule on '{entity}.{act_type}' references owner "
                        f"'{owner_entity}', but no compatible relationship ('{owner_entity} hasMany {entity}', "
                        f"'{owner_entity} hasOne {entity}', or '{entity} belongsTo {owner_entity}') is declared."
                    )

                # Le propriétaire nommé est soit un ACTEUR (propriété directe,
                # brique historique), soit une ENTITÉ (propriété TRANSITIVE,
                # brique 11 / point 81) -- ce second cas est résolu après cette
                # boucle, qui a besoin de connaître TOUTES les règles 'ownedBy'
                # pour remonter la chaîne jusqu'à un compte.
                self.ownership_rules[(entity, act_type)] = owner_entity

        # AJOUT (roadmap, écosystème de capacités -- brique 11, point 81) :
        # propriété TRANSITIVE. « Cette ligne de commande appartient à qui
        # possède sa commande » : le propriétaire nommé est une ENTITÉ, pas un
        # acteur, et la chaîne remonte jusqu'à un compte par la règle 'ownedBy'
        # de cet intermédiaire.
        #
        # Pourquoi cette résolution vit APRÈS la boucle : elle a besoin des
        # règles 'ownedBy' de l'intermédiaire, qui peuvent être déclarées plus
        # bas dans la spec que celle qui s'y réfère. Même motif que le
        # recoupement du point 79.
        #
        # Ce que le point 80 avait trouvé, et qui reste refusé ici : nommer une
        # entité qui ne remonte à AUCUN compte compilait en silence et
        # produisait du code incohérent — clé étrangère annoncée vers la table
        # des comptes, identifiant de l'appelant écrit à la place du
        # rattachement demandé, filtre de lecture comparant un id
        # d'enregistrement à un id de compte. Vérifié à l'exécution : une ligne
        # de commande se rattachait au compte de l'acheteur, jamais à la
        # commande nommée. La chaîne doit donc aboutir, sinon refus.
        self.transitive_ownership = {}
        proprietaires_par_entite = {}
        for (ent, _act), owner in self.ownership_rules.items():
            proprietaires_par_entite.setdefault(ent, set()).add(owner)

        for (entity, act_type), owner_entity in sorted(self.ownership_rules.items()):
            if owner_entity in self.actors:
                continue

            # AJOUT (brique 24, point 107) : la chaîne remontait jadis UN seul
            # intermédiaire ('{entity} -> via -> acteur'). Elle remonte
            # désormais toute la profondeur, maillon par maillon, jusqu'à un
            # ACTEUR. Chaque maillon doit être possédé par UN SEUL propriétaire
            # (sinon ambiguïté : quel chemin vérifier ?) et la marche ne doit
            # ni boucler ni aboutir dans le vide.
            maillon = owner_entity
            vus = set()
            chaine = []
            while maillon not in self.actors:
                if maillon in vus:
                    raise ASTValidationError(
                        f"Structure: the ownership chain for '{entity}' loops at '{maillon}' "
                        f"('{entity}' -> {' -> '.join(chaine)} ...) -- the server cannot resolve it. "
                        f"Break the cycle."
                    )
                vus.add(maillon)
                chaine.append(maillon)
                parents = proprietaires_par_entite.get(maillon, set())
                if not parents:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule on '{entity}.{act_type}' designates "
                        f"'{owner_entity}' as owner, but the chain '{entity}' -> "
                        f"{' -> '.join(chaine)} does not lead to ANY actor -- the server cannot "
                        f"verify WHO owns a '{entity}'. Add a rule "
                        f"'<last link>.Read ownedBy <Actor>', or attach '{entity}' "
                        f"directly to an actor."
                    )
                if len(parents) > 1:
                    raise ASTValidationError(
                        f"Structure: the ownership chain for '{entity}' is ambiguous at "
                        f"'{maillon}': it is owned by multiple different entities "
                        f"({', '.join(sorted(parents))}) -- the server cannot determine which one "
                        f"to check. Designate only one on '{maillon}'."
                    )
                maillon = next(iter(parents))
            acteur = maillon
            # Mélanger propriété directe et transitive sur la MÊME entité
            # rendrait sa clé étrangère à la fois peuplée depuis le jeton (pour
            # l'une des règles) et fournie par le client (pour l'autre) : deux
            # traitements contradictoires sur une seule colonne.
            autres = proprietaires_par_entite.get(entity, set()) - {owner_entity}
            if autres:
                raise ASTValidationError(
                    f"Structure: '{entity}' is owned through '{owner_entity}' (transitive "
                    f"ownership) but also designates '{', '.join(sorted(autres))}' as owner "
                    f"-- its ownership foreign key would be supplied by the client and "
                    f"derived from the token. Designate only one owner for '{entity}'."
                )
            self.transitive_ownership[entity] = {"chain": chaine, "actor": acteur}

        # AJOUT (roadmap, écosystème de capacités -- brique "accès à deux
        # parties") : les règles 'accessibleBy' restreignent une action aux
        # seuls enregistrements dont l'une des colonnes listées contient
        # l'identifiant de l'appelant. Cas d'usage canonique : messagerie
        # privée (expéditeur via la colonne de relation auto-peuplée,
        # destinataire via un champ Integer déclaré). Chaque colonne doit
        # être soit un champ Integer déclaré de l'entité, soit la colonne de
        # clé étrangère dérivée d'une relation entrante (ex. 'user_id').
        self.access_party_rules = {}
        for rule in self.rules:
            if rule["type"] != "accessibleBy":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule must reference 'Entity.Action', got '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            columns = rule["value"]

            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'accessibleBy' rule targets entity '{entity}', which does not exist.")
            if act_type not in ("Read", "Update", "Delete"):
                raise ASTValidationError(
                    f"Structure: invalid action '{act_type}' in the 'accessibleBy' rule on '{entity}' "
                    f"(only Read/Update/Delete apply to an existing record whose parties can be checked)."
                )
            if len(set(columns)) < 2:
                raise ASTValidationError(
                    f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' must list at least two "
                    f"distinct columns — with only one party, use 'ownedBy'."
                )

            # Colonnes de clé étrangère qu'une relation entrante fournit à
            # cette entité (même convention que _compute_fk_placements dans
            # generator.py : '<source>_id').
            relation_fk_columns = set()
            for rel in self.relations:
                if rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity:
                    relation_fk_columns.add(f"{rel['source'].lower()}_id")
                elif rel["type"] == "belongsTo" and rel["source"] == entity:
                    relation_fk_columns.add(f"{rel['target'].lower()}_id")

            for col in columns:
                declared_type = self.entities[entity].get(col)
                if col in relation_fk_columns:
                    continue
                if declared_type is None:
                    raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' references column "
                        f"'{col}', which is neither a declared field of '{entity}' nor an incoming relationship column "
                        f"({', '.join(sorted(relation_fk_columns)) or 'no incoming relationship'})."
                    )
                if declared_type != "Integer":
                    raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' requires '{col}' to be "
                        f"of type Integer (user identifier), got '{declared_type}'."
                    )

            if (entity, act_type) in self.ownership_rules:
                raise ASTValidationError(
                    f"Conflict: '{entity}.{act_type}' has both 'ownedBy' and 'accessibleBy' — "
                    f"choose one ('accessibleBy' generalizes 'ownedBy' to multiple parties)."
                )

            self.access_party_rules[(entity, act_type)] = list(columns)

            # AJOUT (brique 23, point 106) : un rôle SUPERVISEUR peut
            # transpercer ce contrôle par colonnes. Syntaxe : une règle
            # 'sharedBy' portant la MÊME référence — 'rule Message.Delete
            # sharedBy Moderator' posé à côté de 'rule Message.Delete
            # accessibleBy member_id, recipient_id'. Le rôle ainsi nommé
            # voit/supprime/modifie tous les enregistrements ; les parties,
            # elles, restent confinées aux leurs. C'est pour 'accessibleBy' le
            # pendant exact du superviseur déjà acquis pour 'ownedBy' au
            # point 88 ('rule X.Update sharedBy Proprietaire, Patron'). Les
            # rôles nommés doivent être des acteurs déclarés.
            superviseurs = self._superviseurs_declares(entity, act_type)
            if superviseurs:
                self.access_supervisors[(entity, act_type)] = superviseurs

    def _superviseurs_declares(self, entity, act_type):
        """Les rôles nommés par un 'sharedBy' portant la référence exacte.

        Source UNIQUE du superviseur, partagée par 'accessibleBy' (brique 23,
        point 106) et par 'publicWhen' (point 116). Deux résolutions
        parallèles finiraient par diverger sur la validation des rôles — et
        c'est justement cette validation qui empêche qu'une faute de frappe
        désactive silencieusement la supervision (même leçon qu'au point 112).
        """
        ref = f"{entity}.{act_type}"
        superviseurs = []
        for r in self.rules:
            if r["type"] == "sharedBy" and r["reference"] == ref:
                for role in r["value"]:
                    if role not in self.actors:
                        raise ASTValidationError(
                            f"Structure: supervisor role '{role}' in the 'sharedBy' rule "
                            f"on '{ref}' is not a declared actor."
                        )
                    if role not in superviseurs:
                        superviseurs.append(role)
        return superviseurs

    def _valider_regle_public(self):
        """La règle 'public' — une action qui n'exige plus d'authentification
        (point 111). N'utilise que self.rules, self.entities,
        self.public_actions."""
        # AJOUT (roadmap, cas d'usage portfolio) : validation des règles
        # 'public' — une action ainsi marquée n'exige plus d'authentification
        # sur la route générée (ex. lecture d'un portfolio sans compte,
        # envoi d'un message de contact sans compte).
        for rule in self.rules:
            if rule["type"] == "public":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure: the 'public' rule must reference 'Entity.Action', got '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure: the 'public' rule targets entity '{entity}', which does not exist.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure: invalid action '{act_type}' in the 'public' rule on '{entity}'.")
                self.public_actions.add((entity, act_type))
            elif rule["type"] == "publicWhen":
                reference = rule["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' must reference 'Entity.Read', got '{reference}'."
                    )
                entity, act_type = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' targets entity '{entity}', which does not exist."
                    )
                if act_type != "Read":
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' only applies to 'Read' (got '{reference}')."
                    )
                field = rule.get("field")
                if field not in self.entities[entity]:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' targets field '{field}', which does not exist on '{entity}'."
                    )
                if self.entities[entity][field] not in ("String", "Text", "Email", "UUID"):
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' requires a text field, got '{entity}.{field}' "
                        f"of type '{self.entities[entity][field]}'."
                    )
                if (entity, act_type) in self.public_actions:
                    raise ASTValidationError(
                        f"Structure: '{reference}' is both 'public' and 'publicWhen' — "
                        "only one visibility policy is allowed."
                    )
                if (entity, act_type) in self.public_conditions:
                    raise ASTValidationError(
                        f"Structure: multiple 'publicWhen' rules on '{reference}' — "
                        "the condition would be ambiguous."
                    )
                self.public_actions.add((entity, act_type))
                self.public_conditions[(entity, act_type)] = {
                    "field": field, "value": rule.get("value", "")
                }
                # POINT 116 : un 'sharedBy' sur la MÊME référence nomme les
                # rôles qui transpercent la condition — même mot-clé et même
                # sens que le superviseur d'accessibleBy (brique 23). Sans
                # lui, masquer un contenu le retirait AUSSI au modérateur qui
                # venait de le masquer : il ne pouvait plus ni le relire ni
                # revenir en arrière.
                superviseurs = self._superviseurs_declares(entity, act_type)
                if superviseurs:
                    self.access_supervisors[(entity, act_type)] = superviseurs
