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
        
        # Structuration des entités pour accélérer les contrôles
        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(self):
        """Exécute la validation de cohérence et l'analyse statique de sécurité."""
        print(f"🔬 Analyse statique et audit de sécurité pour '{self.app_name}'...")
        
        # 1. Validations structurelles obligatoires (Phase 4 standard)
        self._validate_structures()
        
        # 2. Audit de sécurité actif (La nouvelle vision)
        security_reports = self._audit_security_rules()
        
        print("✅ Analyse de l'AST terminée.")
        return self.to_normalized_ast(security_reports)

    def _validate_structures(self):
        """Vérifie la cohérence de base du modèle (Correctif Bug n°5)."""
        # Vérification des acteurs dans les workflows
        for wf in self.workflows:
            if wf["actor"] not in self.actors:
                raise ASTValidationError(f"Structure : L'acteur '{wf['actor']}' dans le workflow '{wf['name']}' n'est pas déclaré.")
            
            # Vérification des cibles d'actions et appels d'exécution IA
            for action in wf["actions"]:
                target = action["target"]
                if action["type"] == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(f"Architecture : L'action Execute appelle '{target}', mais ce bloc custom n'est pas défini.")
                else:
                    # Correctif Bug n°5 : Gérer la notation pointée (ex: Order.status -> Order)
                    base_target = target.split(".")[0] if "." in target else target
                    if base_target not in self.entities:
                        raise ASTValidationError(f"Structure : L'action cible l'entité '{base_target}' qui n'existe pas.")

    def _audit_security_rules(self):
        """Moteur d'analyse statique traquant les vulnérabilités (Correctif Bug n°4)."""
        reports = []
        restricted_fields = {}
        
        # Extraction des restrictions déclarées
        for rule in self.rules:
            if rule["type"] == "restrictedTo":
                restricted_fields[rule["reference"]] = rule["value"]

        # Audit 1 & 2 : Analyse des Workflows et des actions critiques exposées
        # On maintient une table de correspondance : quel bloc custom est appelé par quel acteur
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

        # Audit 3 : Analyse de l'isolation des blocs de logique IA (Custom)
        for c_name, c_bloc in self.custom_logic.items():
            inputs = c_bloc.get("input", [])
            
            # Correctif Bug n°4 : On retrouve les vrais acteurs qui appellent ce bloc custom
            calling_actors = custom_callers.get(c_name, set())
            
            for inp in inputs:
                if "reference" in inp:
                    ref = inp["reference"]
                    
                    # Si le champ est restreint, on vérifie si l'UN des acteurs appelants viole la restriction
                    if ref in restricted_fields:
                        allowed_actor = restricted_fields[ref]
                        
                        # Si aucun flux n'appelle ce bloc, ou si un acteur non autorisé l'appelle
                        for caller in calling_actors:
                            if caller != allowed_actor:
                                reports.append(f"🔒 [SECURITY_AUDIT] Le bloc de logique IA '{c_name}' (exécuté par '{caller}') utilise la donnée sensible '{ref}' restreinte à l'acteur '{allowed_actor}'. Le compilateur va injecter un filtre d'anonymisation strict par défaut.")

        if not reports:
            print("🛡️  Audit : Aucune vulnérabilité ou privilège excessif détecté dans la spécification.")
        else:
            print(f"🛑 Audit : {len(reports)} point(s) de vigilance sécurité identifié(s) :")
            for r in reports:
                print(f"   {r}")
                
        return reports

    def to_normalized_ast(self, security_reports):
        """Génère l'AST sécurisé enrichi des rapports d'audit statiques."""
        return {
            "meta": {"appName": self.app_name, "security_audit_logs": security_reports},
            "schema": {"entities": self.entities, "relations": self.relations},
            "security": {"actors": list(self.actors), "rules": self.rules, "workflows": self.workflows},
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())}
        }

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    try:
        raw_json = parse_monlang_file(sample_path)
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()
    except Exception as e:
        print(f"❌ Échec de l'analyse statique : {e}")
