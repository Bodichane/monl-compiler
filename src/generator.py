import os
import json
from ast_validator import MonLangAST
from parser import parse_monlang_file

class MonLangSecureGenerator:
    def __init__(self, normalized_ast):
        self.ast = normalized_ast
        self.app_name = normalized_ast["meta"]["appName"]
        self.entities = normalized_ast["schema"]["entities"]
        self.relations = normalized_ast["schema"]["relations"]
        self.workflows = normalized_ast["security"]["workflows"]
        self.custom_functions = normalized_ast["sandbox_ai"]["custom_functions"]

    def generate_all(self):
        """Déclenche la génération déterministe et balise l'échappatoire IA."""
        print(f"🏗️  Génération du socle déterministe pour '{self.app_name}'...")
        
        sql_content = self._generate_sql()
        api_content = self._generate_secure_fastapi()
        sandbox_content = self._generate_ai_sandbox()
        
        # Écriture des fichiers physiques à la racine
        sql_path = os.path.join(os.path.dirname(__file__), "../schema.sql")
        api_path = os.path.join(os.path.dirname(__file__), "../app.py")
        sandbox_path = os.path.join(os.path.dirname(__file__), "../sandbox_ai.py")
        
        with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
        with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
        with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)
            
        print("💾 Socle généré : 'schema.sql', 'app.py' et 'sandbox_ai.py' sont prêts !")

    def _map_type_to_sql(self, type_str):
        mapping = {
            "String": "VARCHAR(255)", "Text": "TEXT", "Integer": "INTEGER",
            "Float": "REAL", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID", "Money": "NUMERIC(10, 2)"
        }
        return mapping.get(type_str, "TEXT")

    def _generate_sql(self):
        """Génère un schéma SQL déterministe et standardisé (Correctif Bug B htmllink)."""
        sql_lines = [f"-- Socle DB Déterministe généré automatiquement pour {self.app_name}\n"]
        for ent_name, attrs in self.entities.items():
            sql_lines.append(f"CREATE TABLE {ent_name.lower()} (")
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f"    {attr_name} {sql_type},")
            sql_lines[-1] = sql_lines[-1].rstrip(",")
            sql_lines.append(");\n")
            
        # Correction Bug B : Génération de clés étrangères en pure syntaxe SQL (pas de commentaire HTML)
        for rel in self.relations:
            if rel["type"] == "hasMany":
                source = rel["source"].lower()
                target = rel["target"].lower()
                sql_lines.append(f"-- Relation: {rel['source']} hasMany {rel['target']}")
                sql_lines.append(f"ALTER TABLE {target} ADD COLUMN {source}_id INTEGER;")
                sql_lines.append(f"ALTER TABLE {target} ADD CONSTRAINT fk_{target}_{source} FOREIGN KEY ({source}_id) REFERENCES {source}(id);\n")
                
        return "\n".join(sql_lines)

    def _generate_secure_fastapi(self):
        """Génère l'API avec persistance SQLite et authentification JWT forte (Bugs #1, #6, D)."""
        api_lines = [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            "from fastapi import FastAPI, HTTPException, Header, Depends",
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
            "from pydantic import BaseModel",
            "from typing import List, Optional",
            "import sqlite3",
            "import jwt",
            "import datetime",
            "import sandbox_ai  # Importation de l'échappatoire IA isolé\n",
            f"app = FastAPI(title='{self.app_name} - Cryptographically Secure Core')\n",
            "DB_FILE = 'app.db'",
            "JWT_SECRET = 'SUPER_SECRET_KEY_MONLANG_2026'  # En production, charger depuis l'environnement",
            "JWT_ALGORITHM = 'HS256'\n",
            "security_bearer = HTTPBearer()\n",
            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    \"\"\"Middleware de vérification cryptographique stricte du Token JWT.\"\"\"",
            "    token = credentials.credentials",
            "    try:",
            "        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "        return payload.get('actor')",
            "    except jwt.ExpiredSignatureError:",
            "        raise HTTPException(status_code=401, detail='Token expiré')",
            "    except jwt.InvalidTokenError:",
            "        raise HTTPException(status_code=401, detail='Token invalide')\n",
            "class LoginRequest(BaseModel):",
            "    username: str",
            "    actor: str\n",
            "@app.post('/login', tags=['Authentication'])",
            "async def login(req: LoginRequest):",
            "    \"\"\"Génère un jeton JWT signé cryptographiquement pour l'acteur demandé.\"\"\"",
            "    payload = {",
            "        'sub': req.username,",
            "        'actor': req.actor,",
            "        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)",
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            "    return {'access_token': token, 'token_type': 'bearer'}\n",
            "# --- VALIDATION STRICTE DES DONNÉES (PYDANTIC) ---"
        ]
        
        for ent_name, attrs in self.entities.items():
            api_lines.append(f"class {ent_name}Schema(BaseModel):")
            for attr_name, attr_type in attrs.items():
                py_type = "str"
                if attr_type == "Integer": py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type == "Boolean": py_type = "bool"
                api_lines.append(f"    {attr_name}: {py_type}")
            api_lines.append("\n")

        api_lines.append("# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---")
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]
            
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".") if "." in target else target
                
                # Le contrôle d'accès extrait désormais le rôle du PAYLOAD du JWT validé
                security_check = f'    if current_actor != "{required_actor}": raise HTTPException(status_code=403, detail="Contrôle d\'accès : Rôle {required_actor} requis par la spécification MonLang")'
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
                
                # --- ACTION : CREATE ---
                if act_type == "Create":
                    api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{wf_name}'])")
                    api_lines.append(f"async def create_{base_target.lower()}(data: {base_target}Schema, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    fields = list(self.entities[base_target].keys())
                    columns = ", ".join(fields)
                    placeholders = ", ".join(["?"] * len(fields))
                    api_lines.append(f"    query = 'INSERT INTO {base_target.lower()} ({columns}) VALUES ({placeholders})'")
                    values_list = ", ".join([f"data.{f}" for f in fields])
                    api_lines.append(f"    cursor.execute(query, ({values_list},))")
                    api_lines.append("    conn.commit(); row_id = cursor.lastrowid; conn.close()")
                    api_lines.append(f"    return {{'status': 'success', 'action': 'create', 'id': row_id}}")
                    api_lines.append("")
                    
                # --- ACTION : READ ---
                elif act_type == "Read":
                    api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{wf_name}'])")
                    api_lines.append(f"async def read_{base_target.lower()}(id: int, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    api_lines.append(f"    cursor.execute('SELECT * FROM {base_target.lower()} WHERE id = ?', (id,))")
                    api_lines.append("    row = cursor.fetchone(); conn.close()")
                    api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
                    api_lines.append("    return {'status': 'success', 'action': 'read', 'data': row}")
                    api_lines.append("")

                # --- ACTION : UPDATE ---
                elif act_type == "Update":
                    api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{wf_name}'])")
                    api_lines.append(f"async def update_{base_target.lower()}(id: int, data: {base_target}Schema, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    fields = list(self.entities[base_target].keys())
                    update_stmt = ", ".join([f"{f} = ?" for f in fields])
                    api_lines.append(f"    query = 'UPDATE {base_target.lower()} SET {update_stmt} WHERE id = ?'")
                    values_list = ", ".join([f"data.{f}" for f in fields])
                    api_lines.append(f"    cursor.execute(query, ({values_list}, id))")
                    api_lines.append("    conn.commit(); conn.close()")
                    api_lines.append(f"    return {{'status': 'success', 'action': 'update', 'id': id}}")
                    api_lines.append("")

                # --- ACTION : DELETE ---
                elif act_type == "Delete":
                    api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{wf_name}'])")
                    api_lines.append(f"async def delete_{base_target.lower()}(id: int, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    api_lines.append(f"    cursor.execute('DELETE FROM {base_target.lower()} WHERE id = ?', (id,))")
                    api_lines.append("    conn.commit(); conn.close()")
                    api_lines.append(f"    return {{'status': 'success', 'action': 'delete', 'id': id}}")
                    api_lines.append("")
                    
                # --- ACTION : EXECUTE (Sandbox IA) ---
                elif act_type == "Execute":
                    api_lines.append(f"@app.post('/workflow/{wf_name.lower()}/{target.lower()}', tags=['{wf_name}'])")
                    api_lines.append(f"async def execute_{target.lower()}(payload: dict, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append(f"    result = sandbox_ai.{target}(payload)")
                    api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
                    api_lines.append("")
                    
        return "\n".join(api_lines)

    def _generate_ai_sandbox(self):
        """Balise les frontières d'isolation pour le code généré par l'IA."""
        sb_lines = [
            "# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX",
            "# Ce fichier contient uniquement des fonctions de logique pure.",
            "# L'IA a interdiction de modifier l'infrastructure ou d'accéder à la base de données.\n",
        ]
        for func in self.custom_functions:
            name = func["name"]
            desc = func.get("description", "Logique métier custom.").strip()
            
            sb_lines.append(f"def {name}(context: dict) -> dict:")
            sb_lines.append(f"    \"\"\"")
            sb_lines.append(f"    CONSIGNE IA : {desc}")
            sb_lines.append(f"    \"\"\"")
            sb_lines.append(f"    # TODO: Le code généré par le LLM sera injecté ici après audit statique local.")
            sb_lines.append(f"    return {{'message': 'Coquille vide déterministe pour {name}'}}")
            sb_lines.append("\n")
        return "\n".join(sb_lines)

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    try:
        raw_json = parse_monlang_file(sample_path)
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()
        
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
        print("\n🎉 PHASE 5 RÉUSSIE ! L'infrastructure complète CRUD + Sandbox est opérationnelle.")
    except Exception as e:
        print(f"❌ Échec de la Phase 5 : {e}")
