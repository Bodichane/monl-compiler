import os
import json
from parser import parse_monlang_file

class ASTValidationError(Exception):
    """Exception personnalisée pour les erreurs sémantiques de MonLang."""
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
        
        # Structuration rapide pour faciliter les validations
        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate(self):
        """Exécute tous les tests de cohérence sémantique."""
        print(f"🔍 Validation sémantique de l'application '{self.app_name}'...")
        self._validate_relations()
        self._validate_rules()
        self._validate_workflows()
        print("✅ AST validé avec succès ! Aucune incohérence détectée.")
        return self.to_normalized_ast()

    def _validate_relations(self):
        """Vérifie que les relations pointent vers des entités existantes."""
        for rel in self.relations:
            source = rel["source"]
            target = rel["target"]
            if source not in self.entities:
                raise ASTValidationError(f"Erreur Relation : L'entité source '{source}' n'existe pas.")
            if target not in self.entities:
                raise ASTValidationError(f"Erreur Relation : L'entité cible '{target}' n'existe pas.")

    def _validate_rules(self):
        """Vérifie que les règles s'appliquent sur des entités et attributs réels."""
        for rule in self.rules:
            ref = rule["reference"]
            if "." not in ref:
                raise ASTValidationError(f"Erreur Règle : La référence '{ref}' doit être au format Entite.attribut.")
            
            ent_name, attr_name = ref.split(".")
            if ent_name not in self.entities:
                raise ASTValidationError(f"Erreur Règle : L'entité '{ent_name}' ciblée par la règle '{ref}' n'existe pas.")
            if attr_name not in self.entities[ent_name]:
                raise ASTValidationError(f"Erreur Règle : L'attribut '{attr_name}' n'existe pas dans l'entité '{ent_name}'.")

    def _validate_workflows(self):
        """Vérifie que les workflows lient des acteurs existants à des actions valides."""
        for wf in self.workflows:
            actor = wf["actor"]
            if actor not in self.actors:
                raise ASTValidationError(f"Erreur Workflow : L'acteur '{actor}' défini dans le workflow '{wf['name']}' n'existe pas.")
            
            for action in wf["actions"]:
                target = action["target"]
                # Une action peut cibler soit une entité complète (ex: Create Todo), soit un champ (ex: Update Order.status)
                base_target = target.split(".")[0]
                if base_target not in self.entities:
                    raise ASTValidationError(f"Erreur Workflow : L'action '{action['type']}' cible '{target}', mais l'entité '{base_target}' n'existe pas.")

    def to_normalized_ast(self):
        """Génère un AST enrichi et normalisé, prêt pour la génération de code."""
        return {
            "meta": {
                "appName": self.app_name,
                "version": "1.0.0"
            },
            "schema": {
                "entities": self.entities,
                "relations": self.relations
            },
            "security": {
                "actors": list(self.actors),
                "rules": self.rules,
                "workflows": self.workflows
            }
        }

if __name__ == "__main__":
    # Récupération du fichier d'exemple TodoList compilé en Phase 3
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    
    try:
        # 1. Parsing (Phase 3)
        raw_json = parse_monlang_file(sample_path)
        
        # 2. Validation et Construction de l'AST (Phase 4)
        ast_manager = MonLangAST(raw_json)
        normalized_json = ast_manager.validate()
        
        # Affichage de l'AST final normalisé
        print("\n📂 AST NORMALISÉ ET PRÊT POUR LA GÉNÉRATION :")
        print(json.dumps(normalized_json, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ Échec de la Phase 4 : {e}")
