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
        """Vérifie la cohérence de base du modèle."""
        # Vérification des acteurs dans les workflows
        for wf in self.workflows:
            if wf["actor"] not in self.actors:
                raise ASTValidationError(f"Structure : L'acteur '{wf['actor']}' dans le workflow '{wf['name']}' n'est pas déclaré.")
            
            # Vérification des cibles d'actions et appels d'exécution IA
            for action in wf["actions"]:
                if action["type"] == "Execute":
                    if action["target"] not in self.custom_logic:
                        raise ASTValidationError(f"Architecture : L'action Execute appelle '{action['target']}', mais ce bloc custom n'est pas défini.")
                else:
                    if action["target"] not in self.entities:
                        raise ASTValidationError(f"Structure : L'action cible l'entité '{action['target']}' qui n'existe pas.")

    def _audit_security_rules(self):
        """Moteur d'analyse statique traquant les vulnérabilités de spécification."""
        reports = []
        restricted_fields = {}
        
        # Extraction des restrictions déclarées
        for rule in self.rules:
            if rule["type"] == "restrictedTo":
                restricted_fields[rule["reference"]] = rule["value"]

        # Audit 1 & 2 : Analyse des Workflows et des actions critiques exposées
        for wf in self.workflows:
            actor = wf["actor"]
            for action in wf["actions"]:
                if action["type"] == "Delete" and actor != "Admin":
                    # Si un droit de suppression est donné à quelqu'un d'autre que l'Admin sans restriction explicite
                    reports.append(f"⚠️  [CRITICAL_WARNING] Le workflow '{wf['name']}' permet à l'acteur '{actor}' de supprimer l'entité '{action['target']}'. Assurez-vous que cette action est hautement sécurisée au niveau infra.")
                
        # Audit 3 : Analyse de l'isolation des blocs de logique IA (Custom)
        for c_name, c_bloc in self.custom_logic.items():
            inputs = c_bloc.get("input", [])
            for inp in inputs:
                if "reference" in inp:
                    ref = inp["reference"]
                    # Alerte si l'IA touche à une variable privée non protégée
                    if ref in restricted_fields and restricted_fields[ref] != actor:
                        reports.append(f"🔒 [SECURITY_AUDIT] Le bloc de logique IA '{c_name}' utilise la donnée sensible '{ref}', restreinte à l'acteur '{restricted_fields[ref]}'. Le compilateur va injecter un filtre d'anonymisation strict par défaut.")

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
