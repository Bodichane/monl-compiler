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
                        f"Structure : la règle 'ownedBy' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                owner_entity = rule["value"]

                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'ownedBy' cible l'entité '{entity}' qui n'existe pas.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure : action '{act_type}' invalide dans la règle 'ownedBy' sur '{entity}'.")
                # CORRECTIF (bêta 3) : 'Create' était accepté alors que le
                # générateur n'en fait rien — une règle de sécurité acceptée
                # puis silencieusement ignorée est pire que son absence, car
                # l'auteur de la spec croit la protection en place. À la
                # création, le propriétaire est l'appelant par construction :
                # la règle n'a rien à restreindre.
                if act_type == "Create":
                    raise ASTValidationError(
                        f"Structure : 'ownedBy' n'a pas de sens sur '{entity}.Create' — "
                        "à la création, le propriétaire est l'appelant par construction. "
                        "Utiliser 'ownedBy' sur Read, Update ou Delete.")

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
                        f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' référence le propriétaire "
                        f"'{owner_entity}', mais aucune relation compatible ('{owner_entity} hasMany {entity}', "
                        f"'{owner_entity} hasOne {entity}', ou '{entity} belongsTo {owner_entity}') n'est déclarée."
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
                        f"Structure : la chaîne de propriété de '{entity}' boucle à '{maillon}' "
                        f"('{entity}' -> {' -> '.join(chaine)} ...) -- le serveur ne peut la "
                        f"résoudre. Couper le cycle."
                    )
                vus.add(maillon)
                chaine.append(maillon)
                parents = proprietaires_par_entite.get(maillon, set())
                if not parents:
                    raise ASTValidationError(
                        f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' désigne "
                        f"'{owner_entity}' comme propriétaire, mais la chaîne '{entity}' -> "
                        f"{' -> '.join(chaine)} ne remonte à AUCUN acteur -- le serveur ne peut "
                        f"vérifier À QUI appartient un '{entity}'. Ajouter une règle "
                        f"'<dernier maillon>.Read ownedBy <Acteur>', ou rattacher '{entity}' "
                        f"directement à un acteur."
                    )
                if len(parents) > 1:
                    raise ASTValidationError(
                        f"Structure : la chaîne de propriété de '{entity}' est ambiguë à "
                        f"'{maillon}' : celui-ci est possédé par plusieurs entités différentes "
                        f"({', '.join(sorted(parents))}) -- le serveur ne saurait pas laquelle "
                        f"vérifier. N'en désigner qu'une seule sur '{maillon}'."
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
                    f"Structure : '{entity}' est possédé à travers '{owner_entity}' (propriété "
                    f"transitive) mais déclare aussi '{', '.join(sorted(autres))}' comme propriétaire "
                    f"-- sa clé étrangère de propriété serait à la fois fournie par le client et "
                    f"déduite du jeton. Ne désigner qu'un seul propriétaire pour '{entity}'."
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
                    f"Structure : la règle 'accessibleBy' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            columns = rule["value"]

            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'accessibleBy' cible l'entité '{entity}' qui n'existe pas.")
            if act_type not in ("Read", "Update", "Delete"):
                raise ASTValidationError(
                    f"Structure : action '{act_type}' invalide dans la règle 'accessibleBy' sur '{entity}' "
                    f"(seules Read/Update/Delete portent sur un enregistrement existant dont on peut vérifier les parties)."
                )
            if len(set(columns)) < 2:
                raise ASTValidationError(
                    f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' doit lister au moins deux "
                    f"colonnes DISTINCTES — avec une seule partie, utiliser 'ownedBy'."
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
                        f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' référence la colonne "
                        f"'{col}', qui n'est ni un champ déclaré de '{entity}', ni une colonne de relation "
                        f"entrante ({', '.join(sorted(relation_fk_columns)) or 'aucune relation entrante'})."
                    )
                if declared_type != "Integer":
                    raise ASTValidationError(
                        f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' exige que '{col}' soit "
                        f"de type Integer (identifiant d'utilisateur), reçu '{declared_type}'."
                    )

            if (entity, act_type) in self.ownership_rules:
                raise ASTValidationError(
                    f"Conflit : '{entity}.{act_type}' porte à la fois 'ownedBy' et 'accessibleBy' — "
                    f"choisir l'un des deux ('accessibleBy' généralise 'ownedBy' à plusieurs parties)."
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
                            f"Structure : le rôle superviseur '{role}' de la règle "
                            f"'sharedBy' sur '{ref}' n'est pas un acteur déclaré."
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
                        f"Structure : la règle 'public' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'public' cible l'entité '{entity}' qui n'existe pas.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure : action '{act_type}' invalide dans la règle 'public' sur '{entity}'.")
                self.public_actions.add((entity, act_type))
            elif rule["type"] == "publicWhen":
                reference = rule["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' doit référencer 'Entite.Read', reçu '{reference}'."
                    )
                entity, act_type = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' cible l'entité '{entity}' qui n'existe pas."
                    )
                if act_type != "Read":
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' ne vaut que sur 'Read' (reçu '{reference}')."
                    )
                field = rule.get("field")
                if field not in self.entities[entity]:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' cible le champ '{field}' qui n'existe pas sur '{entity}'."
                    )
                if self.entities[entity][field] not in ("String", "Text", "Email", "UUID"):
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' exige un champ texte, reçu '{entity}.{field}' "
                        f"de type '{self.entities[entity][field]}'."
                    )
                if (entity, act_type) in self.public_actions:
                    raise ASTValidationError(
                        f"Structure : '{reference}' est à la fois 'public' et 'publicWhen' — "
                        "une seule politique de visibilité est autorisée."
                    )
                if (entity, act_type) in self.public_conditions:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'publicWhen' sur '{reference}' — "
                        "la condition serait ambiguë."
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
