
class ASTValidationError(Exception):
    pass

class MonlAST:
    def __init__(self, raw_json):
        self.raw = raw_json
        self.app_name = raw_json.get("app")
        self.entities = {}
        # CORRECTIF (bêta 3, déterminisme) : la liste des acteurs était un
        # 'set', dont l'ordre d'itération dépend de PYTHONHASHSEED — deux
        # compilations de la même spec pouvaient produire un 'VALID_ACTORS'
        # différent dans app.py, ce qui contredisait la garantie « même
        # entrée, même sortie à l'octet près ». L'ordre de déclaration est
        # désormais conservé (dédoublonné).
        self.actors = list(dict.fromkeys(raw_json.get("actors", [])))
        # AJOUT (bêta 3) : acteurs ouverts à l'inscription libre (marqueur
        # 'selfRegister'). Les autres sont provisionnés hors ligne.
        self.self_register_actors = [
            a for a in dict.fromkeys(raw_json.get("self_register_actors", []))
            if a in self.actors
        ]
        self.relations = raw_json.get("relations", [])
        self.rules = raw_json.get("rules", [])
        self.workflows = raw_json.get("workflows", [])
        self.custom_logic = {c["name"]: c for c in raw_json.get("custom_logic", [])}
        self.ownership_rules = {}
        self.access_party_rules = {}
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
        self.seeds_raw = raw_json.get("seeds", [])
        self.public_actions = set()

        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(self):
        """Exécute la validation de cohérence et l'analyse statique de sécurité."""
        print(f"🔬 Analyse statique et audit de sécurité pour '{self.app_name}'...")

        # 1. Validations structurelles obligatoires
        self._validate_structures()

        # 2. Audit de sécurité actif
        security_reports = self._audit_security_rules()

        # 3. AJOUT (bêta 3) : audit du périmètre d'inscription libre. Un rôle
        #    non marqué 'selfRegister' ne peut pas être choisi par un client à
        #    l'inscription — c'est ce qui empêche l'élévation de privilège par
        #    simple création de compte. On le rend visible à la compilation :
        #    silence = personne ne s'inscrit, ce qui est sûr mais rarement
        #    voulu ; rôle privilégié ouvert = choix explicite, tracé ici.
        security_reports.extend(self._audit_self_registration())

        print("✅ Analyse de l'AST terminée.")
        return self.to_normalized_ast(security_reports)

    def _audit_self_registration(self):
        """Rapporte le périmètre d'inscription libre déclaré par la spec."""
        reports = []
        provisioned = [a for a in self.actors if a not in self.self_register_actors]
        if self.self_register_actors:
            print(f"🔓 Inscription libre : [{', '.join(self.self_register_actors)}]"
                  + (f" — provisionnés hors ligne : [{', '.join(provisioned)}]."
                     if provisioned else " (tous les rôles)."))
        elif self.actors:
            print("🔒 Aucun acteur 'selfRegister' : '/register' refusera toute inscription "
                  "(comptes à créer via 'python3 manage.py adduser').")
        if not self.self_register_actors:
            reports.append(
                "[SECURITY_NOTE] Aucun acteur n'est marqué 'selfRegister' : "
                "'POST /register' refusera toutes les inscriptions et les comptes "
                "devront être créés hors ligne (python3 manage.py adduser). "
                f"Pour ouvrir l'inscription d'un rôle : 'actor {self.actors[0]} selfRegister'."
                if self.actors else
                "[SECURITY_NOTE] Aucun acteur déclaré."
            )
        else:
            reports.append(
                "[SECURITY_NOTE] Inscription libre ouverte à "
                f"[{', '.join(self.self_register_actors)}]"
                + (f" ; rôles provisionnés hors ligne : [{', '.join(provisioned)}]."
                   if provisioned else " (tous les rôles déclarés).")
            )
        return reports

    def _validate_structures(self):
        """Vérifie la cohérence de base et traque les collisions multi-acteurs (Bug #5),
        sauf exemption explicite via une règle 'sharedBy'. Valide aussi les règles
        'ownedBy' (roadmap : contrôle d'accès par propriété)."""
        # Matrice globale pour traquer les conflits d'autorisations (Entité -> Action -> Ensemble d'acteurs)
        access_matrix = {}

        # CORRECTIF (post-v6) : les règles 'sharedBy' déclarent explicitement qu'un
        # ensemble précis d'acteurs peut se partager un même droit d'écriture sur
        # une entité, ex. : "rule Post.Delete sharedBy Admin, Moderator"
        shared_permissions = {}
        for rule in self.rules:
            if rule["type"] == "sharedBy":
                shared_permissions[rule["reference"]] = set(rule["value"])

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

                self.ownership_rules[(entity, act_type)] = owner_entity

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

        # AJOUT (roadmap, écosystème de capacités -- brique 2) : validation
        # des règles 'hidden' -- retire un champ de toutes les réponses de
        # lecture de son entité (voir le commentaire de grammaire dans
        # parser.py pour la distinction avec 'restrictedTo'). Vérifie que le
        # champ référencé est un attribut réellement déclaré sur l'entité
        # (donc jamais 'id', qui n'apparaît pas dans self.entities -- un
        # champ structurellement nécessaire à la navigation CRUD ne peut pas
        # être masqué, la règle échoue proprement plutôt que de casser
        # silencieusement les routes Update/Delete/Read-par-ID).
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] == "hidden":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure : la règle 'hidden' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                    )
                entity, field = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'hidden' cible l'entité '{entity}' qui n'existe pas.")
                if field not in self.entities[entity]:
                    raise ASTValidationError(
                        f"Structure : la règle 'hidden' référence le champ '{field}', qui n'est pas un attribut "
                        f"déclaré de '{entity}' (ou est 'id', qui ne peut pas être masqué)."
                    )
                self.masked_fields.add((entity, field))

        # AJOUT (roadmap, écosystème de capacités -- brique 5) : validation
        # des règles 'categorized' -- remplace un champ Integer/Float par un
        # libellé de catégorie (ex. "peu"/"populaire"/"viral") dans toutes
        # les réponses de lecture, sur le même principe que 'hidden' mais en
        # substituant une donnée dérivée plutôt qu'en supprimant purement.
        self.categorized_fields = []
        _categorized_seen_fields = set()
        for rule in self.rules:
            if rule["type"] == "categorized":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure : la règle 'categorized' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                    )
                entity, field = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'categorized' cible l'entité '{entity}' qui n'existe pas.")
                field_type = self.entities.get(entity, {}).get(field)
                if field_type not in ("Integer", "Float"):
                    raise ASTValidationError(
                        f"Structure : 'categorized' cible le champ '{entity}.{field}', qui doit être un attribut "
                        f"Integer ou Float déclaré (reçu : {field_type or 'champ inexistant'})."
                    )
                # Incompatible avec 'hidden' sur le même champ : 'hidden' retire
                # le champ, 'categorized' le remplace par une valeur dérivée --
                # les deux ne peuvent pas s'appliquer en même temps sans que
                # l'un des deux comportements soit silencieusement ignoré.
                if (entity, field) in self.masked_fields:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'categorized' -- incompatible : "
                        f"'hidden' retire le champ, 'categorized' le remplace par une catégorie dérivée de sa valeur."
                    )
                if (entity, field) in _categorized_seen_fields:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'categorized' déclarées pour '{entity}.{field}' -- une seule autorisée."
                    )
                _categorized_seen_fields.add((entity, field))

                clauses = rule["value"]
                if len(clauses) < 2:
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' doit déclarer au moins un seuil ('below') "
                        f"et un palier de secours ('otherwise')."
                    )
                for clause in clauses[:-1]:
                    if "otherwise" in clause:
                        raise ASTValidationError(
                            f"Structure : 'categorized' sur '{entity}.{field}' -- seul le DERNIER palier peut être "
                            f"'otherwise' (palier de secours), reçu ailleurs dans la liste."
                        )
                if "otherwise" not in clauses[-1]:
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' doit se terminer par un palier 'otherwise' "
                        f"(palier de secours qui couvre toute valeur au-delà du dernier seuil)."
                    )
                thresholds = [c["below"] for c in clauses[:-1]]
                if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- les seuils 'below' doivent être "
                        f"strictement croissants (reçu : {thresholds})."
                    )
                if any(not c["label"].strip() for c in clauses):
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- chaque palier doit avoir un libellé non vide."
                    )
                self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

        # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
        # validation des règles 'generated' -- retire un champ String du
        # corps de requête Create attendu, peuplé côté serveur par le
        # pseudonyme anonyme stable du compte courant (voir /register et
        # /login dans generator.py) plutôt que fourni par le client.
        self.generated_fields = []
        _generated_seen_fields = set()
        for rule in self.rules:
            if rule["type"] == "generated":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure : la règle 'generated' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                    )
                entity, field = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'generated' cible l'entité '{entity}' qui n'existe pas.")
                field_type = self.entities.get(entity, {}).get(field)
                if field_type != "String":
                    raise ASTValidationError(
                        f"Structure : 'generated' cible le champ '{entity}.{field}', qui doit être un attribut "
                        f"String déclaré (reçu : {field_type or 'champ inexistant'}) -- un pseudonyme est toujours "
                        f"du texte court."
                    )
                # Incompatible avec 'hidden' sur le même champ : 'generated'
                # existe précisément pour produire une valeur sûre à
                # afficher (un pseudonyme, jamais l'identité réelle) -- la
                # masquer entièrement en plus n'aurait aucun sens, ce serait
                # alors juste ne pas déclarer le champ du tout.
                if (entity, field) in self.masked_fields:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'generated' -- incompatible : "
                        f"'generated' produit déjà une valeur sûre à afficher, la masquer en plus n'a pas de sens."
                    )
                if (entity, field) in _generated_seen_fields:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'generated' déclarées pour '{entity}.{field}' -- une seule autorisée."
                    )
                _generated_seen_fields.add((entity, field))
                # Incompatible avec une action 'Create' 'public' sur la même
                # entité : 'generated' peuple le champ depuis l'identité de
                # l'appelant authentifié -- une route publique n'a par
                # définition aucune identité fiable à partir de laquelle
                # dériver un pseudonyme.
                if (entity, "Create") in self.public_actions:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est 'generated', mais '{entity}.Create' est 'public' -- "
                        f"incompatible : 'generated' exige un appelant authentifié dont dériver le pseudonyme."
                    )
                self.generated_fields.append({"entity": entity, "field": field})

        # AJOUT (roadmap, écosystème de capacités -- brique 3, généralisée en
        # brique 4) : validation des règles 'decrements'/'increments' --
        # même mécanique dans les deux sens (réputation qui baisse sur
        # signalement, compteur qui monte sur appréciation), donc une seule
        # boucle partagée, distinguée par 'direction'. Trois conditions :
        # (1) le déclencheur est bien 'Entite.Create' sur une entité
        # existante -- seule l'action 'Create' est prise en charge pour
        # l'instant, volontairement (une suppression ne "défait" pas l'effet,
        # ce serait une mécanique différente à concevoir à part) ; (2) la
        # cible est un champ Integer/Float réellement déclaré sur son
        # entité ; (3) une relation existe entre les deux entités permettant
        # de savoir quelle ligne de l'entité cible modifier (même
        # vérification que pour 'ownedBy', point 5 -- répliquée ici plutôt
        # que partagée, cette validation est encore trop jeune pour factoriser
        # sans risquer de rigidifier les deux prématurément).
        self.reputation_rules = []
        for rule in self.rules:
            if rule["type"] in ("decrements", "increments"):
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
                has_matching_relation = any(
                    (rel["type"] in ("hasMany", "hasOne") and rel["source"] == target_entity and rel["target"] == trigger_entity)
                    or (rel["type"] == "belongsTo" and rel["target"] == target_entity and rel["source"] == trigger_entity)
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure : '{direction}' sur '{trigger_entity}.Create' vers '{target_entity}.{target_field}' "
                        f"exige une relation entre les deux (ex. '{target_entity} hasMany {trigger_entity}'), absente ici."
                    )
                self.reputation_rules.append({
                    "trigger_entity": trigger_entity, "target_entity": target_entity,
                    "target_field": target_field, "amount": rule["amount"], "direction": direction,
                })

        # AJOUT (roadmap, contrôle du rendu visuel) : validation du bloc 'ui'
        # optionnel — vérifie que l'entité et les champs référencés existent
        # bien, pour éviter qu'une faute de frappe dans 'primary'/'order'
        # passe silencieusement inaperçue jusqu'au rendu du front. Le nom du
        # thème n'est volontairement pas validé ici (cosmétique, pas
        # sécuritaire) — un nom de thème inconnu sera simplement ignoré par
        # le générateur, qui retombera sur la sélection automatique.
        self.ui_overrides = {}
        for override in self.ui_overrides_raw:
            entity = override["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : le bloc 'ui {entity}' cible une entité qui n'existe pas.")
            primary = override.get("primary")
            if primary and primary not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : 'ui {entity}' référence 'primary: {primary}', qui n'est pas un attribut de '{entity}'."
                )
            order = override.get("order")
            if order:
                unknown = [f for f in order if f not in self.entities[entity]]
                if unknown:
                    raise ASTValidationError(
                        f"Structure : 'ui {entity}' référence des champs inconnus dans 'order' : {unknown}."
                    )
            self.ui_overrides[entity] = {
                "theme": override.get("theme"), "primary": primary, "order": order,
            }

        # PIVOT (point 41) : monl ne génère plus de landing — le bloc
        # 'landing' reste ACCEPTÉ pour ne casser aucune spec existante, mais
        # seul son 'brief' est conservé : il alimente désormais le contrat
        # frontend (FRONTEND_PROMPT.md) destiné à l'IA qui construit
        # l'interface. Les clés 'mode' et 'template', devenues sans effet,
        # sont signalées (jamais une régression silencieuse).
        self.landing = None
        if self.landing_raw is not None:
            for obsolete in ("mode", "template"):
                if self.landing_raw.get(obsolete):
                    print(f"⚠️  'landing / {obsolete}' est obsolète depuis le pivot "
                          f"(point 41 de docs/design_decisions.md) : monl ne génère "
                          f"plus de page d'accueil — seul 'brief' est transmis à l'IA frontend.")
            # AJOUT (point 55) : les sections éditoriales, seul contenu
            # statique que le contrat sache porter. Un titre vide donnerait
            # une rubrique sans nom dans l'interface : refusé à la
            # compilation plutôt que découvert à l'écran.
            sections = []
            for section in self.landing_raw.get("sections") or []:
                titre = (section.get("title") or "").strip()
                corps = (section.get("body") or "").strip()
                if not titre or not corps:
                    raise ValueError(
                        "SEMANTIC_ERROR: une 'section' de 'landing' exige un "
                        "titre ET un texte non vides (trouvé : "
                        f"titre={titre!r}, texte={corps!r}).")
                sections.append({"title": titre, "body": corps})
            self.landing = {"brief": self.landing_raw.get("brief"),
                            "sections": sections}
        # AJOUT (roadmap, écosystème de capacités -- brique 1) : validation
        # du bloc optionnel 'capability'. Volontairement strict (liste
        # blanche de noms connus, contrairement à 'ui / theme' qui retombe
        # silencieusement sur un défaut) : une capacité mal orthographiée
        # doit être signalée à la compilation, pas ignorée en silence --
        # comportement déjà établi pour tout ce qui touche à la sécurité
        # (collision de privilèges, restriction de champ) dans ce compilateur.
        # 'auth' est la seule capacité connue pour l'instant (brique 1,
        # purement déclarative -- aucun effet sur la génération à ce stade).
        KNOWN_CAPABILITIES = {"auth"}
        unknown = [c for c in self.capabilities_raw if c not in KNOWN_CAPABILITIES]
        if unknown:
            raise ASTValidationError(
                f"Structure : capacité(s) inconnue(s) déclarée(s) avec 'capability' : {', '.join(unknown)}. "
                f"Capacités reconnues : {', '.join(sorted(KNOWN_CAPABILITIES))}."
            )
        self.capabilities = list(dict.fromkeys(self.capabilities_raw))  # dédoublonne, garde l'ordre

        # AJOUT (roadmap frontend, bloc 'seed') : validation des données de
        # démonstration. Chaque enregistrement doit cibler une entité
        # déclarée, ne référencer que des champs existants de cette entité,
        # et respecter grossièrement leur type (nombre pour Integer/Float/
        # Money, chaîne sinon). Strict comme le reste du compilateur : une
        # coquille dans un seed doit échouer à la compilation, pas produire
        # une INSERT invalide au démarrage du serveur.
        NUMERIC_TYPES = {"Integer", "Float", "Money"}
        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : le bloc 'seed' cible l'entité '{entity}' qui n'existe pas."
                )
            entity_fields = self.entities[entity]
            for i, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    if field not in entity_fields:
                        raise ASTValidationError(
                            f"Structure : le bloc 'seed {entity}' (ligne {i}) référence le champ "
                            f"'{field}', qui n'est pas déclaré sur '{entity}'."
                        )
                    declared_type = entity_fields[field]
                    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
                    if declared_type in NUMERIC_TYPES and not is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {i}), champ '{field}' de type "
                            f"{declared_type} attend un nombre, reçu une chaîne."
                        )
                    if declared_type not in NUMERIC_TYPES and is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {i}), champ '{field}' de type "
                            f"{declared_type} attend une chaîne entre guillemets, reçu un nombre."
                        )
            self.seeds.append(seed)

        for wf in self.workflows:
            actor = wf["actor"]
            if actor not in self.actors:
                raise ASTValidationError(f"Structure : L'acteur '{actor}' dans le workflow '{wf['name']}' n'est pas déclaré.")

            for action in wf["actions"]:
                target = action["target"]
                act_type = action["type"]

                if act_type == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(f"Architecture : L'action Execute appelle '{target}', mais ce bloc custom n'est pas défini.")
                else:
                    base_target = target.split(".")[0] if "." in target else target
                    if base_target not in self.entities:
                        raise ASTValidationError(f"Structure : L'action cible l'entité '{base_target}' qui n'existe pas.")

                    # --- CORRECTIF BUG v6 #5 : Détection des collisions de privilèges ---
                    # AJOUT (roadmap, public) : une action marquée 'public' ne
                    # vérifie plus aucune identité au runtime — peu importe
                    # combien de workflows/acteurs différents la déclarent,
                    # ça n'a plus de sens de la faire remonter dans la
                    # matrice de collision, qui ne concerne que les actions
                    # réellement soumises à un contrôle de rôle.
                    if (base_target, act_type) in self.public_actions:
                        continue

                    if base_target not in access_matrix:
                        access_matrix[base_target] = {}
                    if act_type not in access_matrix[base_target]:
                        access_matrix[base_target][act_type] = set()

                    # Enregistrement de l'acteur pour cette action précise
                    access_matrix[base_target][act_type].add(actor)

        # Analyse de la matrice : si une action d'écriture/suppression a plus d'un acteur,
        # on autorise si une règle 'sharedBy' couvre exactement cet ensemble d'acteurs,
        # ou si une règle 'ownedBy' protège déjà cette action au niveau de chaque
        # enregistrement (auquel cas plusieurs acteurs peuvent légitimement partager
        # le droit, puisque chacun ne peut de toute façon agir que sur ses propres
        # données) — sinon on lève une exception stricte pour forcer le refactoring.
        for entity, actions in access_matrix.items():
            for act_type, authorized_actors in actions.items():
                if len(authorized_actors) > 1 and act_type in ["Create", "Update", "Delete"]:
                    key = f"{entity}.{act_type}"
                    allowed_shared = shared_permissions.get(key)

                    if allowed_shared and authorized_actors.issubset(allowed_shared):
                        print(f"🤝 [SHARED_PRIVILEGE] L'action '{act_type}' sur '{entity}' est explicitement "
                              f"partagée entre [{', '.join(sorted(authorized_actors))}] via une règle 'sharedBy'.")
                        continue

                    # AJOUT (roadmap) : combinaison ownedBy + sharedBy implicite.
                    if (entity, act_type) in self.ownership_rules:
                        print(f"🔐 [SHARED_PRIVILEGE_VIA_OWNERSHIP] L'action '{act_type}' sur '{entity}' est partagée "
                              f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                              f"enregistrement par la règle 'ownedBy' (propriétaire : "
                              f"{self.ownership_rules[(entity, act_type)]}).")
                        continue

                    actors_list = ", ".join(sorted(authorized_actors))
                    suggestion = f"'rule {entity}.{act_type} sharedBy {actors_list}'"
                    extra = ""
                    if allowed_shared:
                        not_covered = authorized_actors - allowed_shared
                        extra = (f" Une règle 'sharedBy' existe déjà pour '{key}' mais ne couvre pas : "
                                 f"[{', '.join(sorted(not_covered))}].")

                    raise ASTValidationError(
                        f"🔒 [CRITICAL_COLLISION] Conflit d'autorité sur l'entité '{entity}' : "
                        f"les acteurs [{actors_list}] ont tous le droit d'exécuter l'action '{act_type}'. "
                        f"Séparez ces privilèges, ou déclarez explicitement le partage avec : {suggestion}.{extra}"
                    )

    def _audit_security_rules(self):
        """Moteur d'analyse statique traquant les vulnérabilités complexes."""
        reports = []
        restricted_fields = {}

        for rule in self.rules:
            if rule["type"] == "restrictedTo":
                restricted_fields[rule["reference"]] = rule["value"]

        custom_callers = {}
        for wf in self.workflows:
            actor = wf["actor"]
            for action in wf["actions"]:
                target = action["target"]
                if action["type"] == "Delete" and actor != "Admin":
                    reports.append(f"⚠️  [CRITICAL_WARNING] Le workflow '{wf['name']}' permet à l'acteur '{actor}' de supprimer l'entité '{target}'. Assurez-vous que cette action est hautement sécurisée au niveau infra.")

                if action["type"] == "Execute":
                    if target not in custom_callers:
                        custom_callers[target] = set()
                    custom_callers[target].add(actor)

        for c_name, c_bloc in self.custom_logic.items():
            inputs = c_bloc.get("input", [])
            calling_actors = custom_callers.get(c_name, set())

            for inp in inputs:
                if "reference" in inp:
                    ref = inp["reference"]
                    if ref in restricted_fields:
                        allowed_actor = restricted_fields[ref]
                        for caller in calling_actors:
                            if caller != allowed_actor:
                                reports.append(f"🔒 [SECURITY_AUDIT] Le bloc de logique IA '{c_name}' (exécuté par '{caller}') utilise la donnée sensible '{ref}' restreinte à l'acteur '{allowed_actor}'.")

        if not reports:
            print("🛡️  Audit : Aucune vulnérabilité ou privilège excessif détecté dans la spécification.")
        else:
            print(f"🛑 Audit : {len(reports)} point(s) de vigilance sécurité identifié(s) :")
            for r in reports:
                print(f"   {r}")

        return reports

    def to_normalized_ast(self, security_reports):
        return {
            "meta": {"appName": self.app_name, "security_audit_logs": security_reports},
            "schema": {"entities": self.entities, "relations": self.relations},
            "security": {
                "actors": list(self.actors),
                "self_register_actors": list(self.self_register_actors),
                "rules": self.rules, "workflows": self.workflows,
                "ownership": {f"{k[0]}.{k[1]}": v for k, v in self.ownership_rules.items()},
                "access_parties": {f"{k[0]}.{k[1]}": v for k, v in self.access_party_rules.items()},
                "public": [f"{e}.{a}" for e, a in sorted(self.public_actions)],
                "hidden_fields": [f"{e}.{f}" for e, f in sorted(self.masked_fields)],
                "reputation_rules": self.reputation_rules,
                "categorized_fields": self.categorized_fields,
                "generated_fields": self.generated_fields,
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())},
            "ui": self.ui_overrides,
            "landing": self.landing,
            "capabilities": self.capabilities,
            "seeds": self.seeds,
        }
