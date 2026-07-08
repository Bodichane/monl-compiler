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

                has_matching_relation = any(
                    rel["type"] == "hasMany" and rel["source"] == owner_entity and rel["target"] == entity
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' référence le propriétaire "
                        f"'{owner_entity}', mais aucune relation 'relation {owner_entity} hasMany {entity}' "
                        f"n'est déclarée pour fournir la colonne de propriété."
                    )

                self.ownership_rules[(entity, act_type)] = owner_entity

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
                    if base_target not in access_matrix:
                        access_matrix[base_target] = {}
                    if act_type not in access_matrix[base_target]:
                        access_matrix[base_target][act_type] = set()
                    
                    # Enregistrement de l'acteur pour cette action précise
                    access_matrix[base_target][act_type].add(actor)

        # Analyse de la matrice : si une action d'écriture/suppression a plus d'un acteur,
        # on autorise si une règle 'sharedBy' couvre exactement cet ensemble d'acteurs,
        # sinon on lève une exception stricte pour forcer le refactoring de la spécification.
        for entity, actions in access_matrix.items():
            for act_type, authorized_actors in actions.items():
                if len(authorized_actors) > 1 and act_type in ["Create", "Update", "Delete"]:
                    key = f"{entity}.{act_type}"
                    allowed_shared = shared_permissions.get(key)

                    if allowed_shared and authorized_actors.issubset(allowed_shared):
                        print(f"🤝 [SHARED_PRIVILEGE] L'action '{act_type}' sur '{entity}' est explicitement "
                              f"partagée entre [{', '.join(sorted(authorized_actors))}] via une règle 'sharedBy'.")
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
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())}
        }
