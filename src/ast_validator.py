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
        """Vérifie la cohérence de base et traque les collisions multi-acteurs (Bug #5)."""
        # Matrice globale pour traquer les conflits d'autorisations (Entité -> Action -> Ensemble d'acteurs)
        access_matrix = {}

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

        # Analyse de la matrice : si une action d'écriture/suppression a plus d'un acteur, on lève une alerte ou on bloque
        for entity, actions in access_matrix.items():
            for act_type, authorized_actors in actions.items():
                if len(authorized_actors) > 1 and act_type in ["Create", "Update", "Delete"]:
                    # Lever une exception stricte pour forcer le refactoring de la spécification
                    actors_list = ", ".join(list(authorized_actors))
                    raise ASTValidationError(
                        f"🔒 [CRITICAL_COLLISION] Conflit d'autorité sur l'entité '{entity}' : "
                        f"les acteurs [{actors_list}] ont tous le droit d'exécuter l'action '{act_type}'. "
                        f"La spécification doit séparer ces privilèges de manière étanche."
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
            "security": {"actors": list(self.actors), "rules": self.rules, "workflows": self.workflows},
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())}
        }
