import os
import json
from ast_validator import MonLangAST
from parser import parse_monlang_file

class MonLangGenerator:
    def __init__(self, normalized_ast):
        self.ast = normalized_ast
        self.app_name = normalized_ast["meta"]["appName"]
        self.entities = normalized_ast["schema"]["entities"]
        self.relations = normalized_ast["schema"]["relations"]
        self.workflows = normalized_ast["security"]["workflows"]

    def generate_all(self):
        """Déclenche la génération de tous les composants techniques."""
        print(f"🏗️  Début de la génération pour l'application '{self.app_name}'...")
        
        sql_content = self._generate_sql()
        api_content = self._generate_fastapi()
        
        # Écriture des fichiers générés
        sql_path = os.path.join(os.path.dirname(__file__), "../schema.sql")
        api_path = os.path.join(os.path.dirname(__file__), "../app.py")
        
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write(sql_content)
        with open(api_path, "w", encoding="utf-8") as f:
            f.write(api_content)
            
        print("💾 Fichiers 'schema.sql' et 'app.py' générés avec succès à la racine !")

    def _map_type_to_sql(self, type_str):
        """Traduit les types sémantiques MonLang en types SQL standard."""
        mapping = {
            "String": "VARCHAR(255)",
            "Text": "TEXT",
            "Integer": "INTEGER",
            "Float": "REAL",
            "Boolean": "BOOLEAN",
            "Date": "DATE",
            "DateTime": "TIMESTAMP",
            "Email": "VARCHAR(255)",
            "UUID": "UUID",
            "Money": "NUMERIC(10, 2)"
        }
        return mapping.get(type_str, "TEXT")

    def _generate_sql(self):
        """Génère le code SQL de création des tables et des clés étrangères."""
        sql_lines = [f"-- Base de données générée automatiquement pour {self.app_name}\n"]
        
        # Génération des tables de base
        for ent_name, attrs in self.entities.items():
            sql_lines.append(f"CREATE TABLE {ent_name.lower()} (")
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f"    {attr_name} {sql_type},")
                
            # Retirer la virgule de la dernière ligne d'attribut pour la syntaxe SQL
            sql_lines[-1] = sql_lines[-1].rstrip(",")
            sql_lines.append(");\n")
            
        # Génération des clés étrangères basées sur les relations
        for rel in self.relations:
            if rel["type"] == "hasMany":
                source = rel["source"].lower()
                target = rel["target"].lower()
                sql_lines.append(f"-- Relation: {rel['source']} hasMany {rel['target']}")
                sql_lines.append(f"ALTER TABLE {target} ADD COLUMN {source}_id INTEGER;")
                sql_lines.append(f"<!-- FOREIGN KEY ({source}_id) REFERENCES {source}(id) -->;\n")
                
        return "\n".join(sql_lines)

    def _generate_fastapi(self):
        """Génère une API FastAPI complète avec routes basées sur les workflows."""
        api_lines = [
            "#, # API générée automatiquement par MonLang",
            "from fastapi import FastAPI, HTTPException",
            "from pydantic import BaseModel",
            "from typing import List, Optional\n",
            f"app = FastAPI(title='{self.app_name} API')\n",
            "# --- MODÈLES DE DONNÉES DE LA COMPILATION ---"
        ]
        
        # Génération des schémas Pydantic pour chaque entité
        for ent_name, attrs in self.entities.items():
            api_lines.append(f"class {ent_name}Schema(BaseModel):")
            for attr_name, attr_type in attrs.items():
                # Correspondance rapide des types Python
                py_type = "str"
                if attr_type in ["Integer"]: py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type in ["Boolean"]: py_type = "bool"
                api_lines.append(f"    {attr_name}: {py_type}")
            api_lines.append("    class Config:")
            api_lines.append("        from_attributes = True\n")

        # Génération des routes basées strictly sur les Workflows déclarés
        api_lines.append("# --- ROUTES SÉCURISÉES PAR WORKFLOW ---")
        for wf in self.workflows:
            wf_name = wf["name"]
            actor = wf["actor"]
            
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                
                if act_type == "Create":
                    api_lines.append(f"@app.post('/{target.lower()}', tags=['Workflow: {wf_name} ({actor})'])")
                    api_lines.append(f"async def create_{target.lower()}(data: {target}Schema):")
                    api_lines.append(f"    return {{'message': '{target} créé avec succès via le workflow {wf_name} par {actor}', 'data': data}}")
                    api_lines.append("")
                elif act_type == "Update":
                    api_lines.append(f"@app.put('/{target.lower()}/{{id}}', tags=['Workflow: {wf_name} ({actor})'])")
                    api_lines.append(f"async def update_{target.lower()}(id: int, data: {target}Schema):")
                    api_lines.append(f"    return {{'message': '{target} mis à jour', 'id': id, 'data': data}}")
                    api_lines.append("")
                elif act_type == "Delete":
                    api_lines.append(f"@app.delete('/{target.lower()}/{{id}}', tags=['Workflow: {wf_name} ({actor})'])")
                    api_lines.append(f"async def delete_{target.lower()}(id: int):")
                    api_lines.append(f"    return {{'message': '{target} supprimé', 'id': id}}")
                    api_lines.append("")
                    
        return "\n".join(api_lines)

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    
    try:
        # Chaîne complète : Pipeline 3 -> 4 -> 5
        raw_json = parse_monlang_file(sample_path)
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate()
        
        # Génération
        generator = MonLangGenerator(normalized_ast)
        generator.generate_all()
        print("\n🎉 PHASE 5 REUSSIE ! Votre code technique est prêt.")
        
    except Exception as e:
        print(f"❌ Échec de la Phase 5 : {e}")
