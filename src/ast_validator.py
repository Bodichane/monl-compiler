import os
import json
from parser import parse_monlang_file

class ASTValidationError(Exception):
    pass

class MonLangAST:
    def __init__(self, raw_json):
        self.raw = raw_json
        self.app_name = raw_json.get("app")
        self.entities = {}
        self.actors = set(raw_json.get("actors", []))
        self.relations = raw_json.get("relations", [])
        self.rules = raw_json.get("rules", [])
        self.workflows = raw_json.get("workflows", [])
        self.custom_logic = {c["name"]: c for c in raw_json.get("custom_logic", [])}
        self.ownership_rules = {}
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
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
        
        print("✅ Analyse de l'AST terminée.")
        return self.to_normalized_ast(security_reports)

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

        # AJOUT (roadmap, front marketing) : validation du bloc optionnel
        # 'landing'. Volontairement strict sur ce qui touche à la sécurité
        # (chemin de template ne pouvant pas s'échapper du projet — même
        # logique que n'importe quelle validation de chemin fourni par
        # l'utilisateur, pour empêcher un '../../etc/passwd' de finir lu par
        # le générateur), mais permissif sur le reste (un 'mode' inconnu
        # retombe silencieusement sur le gabarit déterministe, à l'image du
        # nom de thème inconnu du bloc 'ui').
        self.landing = None
        if self.landing_raw is not None:
            mode = self.landing_raw.get("mode", "ai")
            if mode not in ("ai", "template"):
                mode = "ai"
            template = self.landing_raw.get("template")
            if mode == "template":
                if not template:
                    raise ASTValidationError(
                        "Structure : 'landing / mode: template' exige aussi une clé 'template: \"chemin/vers/fichier.html\"'."
                    )
                normalized = template.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    raise ASTValidationError(
                        f"Sécurité : 'landing / template' doit être un chemin relatif à l'intérieur du projet "
                        f"(reçu '{template}', un chemin absolu ou remontant via '..' est refusé)."
                    )
            self.landing = {
                "mode": mode,
                "template": template,
                "brief": self.landing_raw.get("brief"),
            }

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
                "actors": list(self.actors), "rules": self.rules, "workflows": self.workflows,
                "ownership": {f"{k[0]}.{k[1]}": v for k, v in self.ownership_rules.items()},
                "public": [f"{e}.{a}" for e, a in self.public_actions],
                "hidden_fields": [f"{e}.{f}" for e, f in self.masked_fields],
                "reputation_rules": self.reputation_rules,
                "categorized_fields": self.categorized_fields,
                "generated_fields": self.generated_fields,
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())},
            "ui": self.ui_overrides,
            "landing": self.landing,
            "capabilities": self.capabilities,
        }
