import os
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
        print(f"🏗️  Génération du socle déterministe réel pour '{self.app_name}'...")
        
        sql_content = self._generate_sql()
        api_content = self._generate_secure_fastapi()
        sandbox_content = self._generate_ai_sandbox()
        
        # Détermination des chemins physiques
        base_dir = os.path.dirname(__file__)
        sql_path = os.path.join(base_dir, "../schema.sql")
        api_path = os.path.join(base_dir, "../app.py")
        sandbox_path = os.path.join(base_dir, "../sandbox_ai.py")
        
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
        """Génère un schéma SQL déterministe préservant les données existantes (Bug #3)."""
        sql_lines = [f"-- Socle DB Déterministe généré automatiquement pour {self.app_name}\n"]
        for ent_name, attrs in self.entities.items():
            # Remplacement par IF NOT EXISTS pour éviter les plantages au redémarrage
            sql_lines.append(f"CREATE TABLE IF NOT EXISTS {ent_name.lower()} (")
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f"    {attr_name} {sql_type},")
            
            for rel in self.relations:
                if rel["type"] == "hasMany" and rel["target"].lower() == ent_name.lower():
                    source_table = rel["source"].lower()
                    sql_lines.append(f"    {source_table}_id INTEGER,")
                    sql_lines.append(f"    FOREIGN KEY ({source_table}_id) REFERENCES {source_table}(id),")
            
            sql_lines[-1] = sql_lines[-1].rstrip(",")
            sql_lines.append(");\n")
        return "\n".join(sql_lines)

    def _generate_secure_fastapi(self):
        """Génère l'API avec persistance SQLite, authentification JWT et schémas IA stricts."""
        api_lines = [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            "from fastapi import FastAPI, HTTPException, Header, Depends",
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
            "from pydantic import BaseModel",
            "from typing import List, Optional, Any",
            "import sqlite3",
            "import jwt",
            "import datetime",
            "import sandbox_ai  # Importation de l'échappatoire IA isolé\n",
            f"app = FastAPI(title='{self.app_name} - Secure Core')",
            "DB_FILE = 'app.db'",
            "JWT_SECRET = 'SUPER_SECRET_KEY_MONLANG_INDUSTRIAL_SAFETY_2026'",
            "JWT_ALGORITHM = 'HS256'\n",
            "security_bearer = HTTPBearer()\n",
            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    try:",
            "        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "        return payload.get('actor')",
            "    except jwt.PyJWTError:",
            "        raise HTTPException(status_code=401, detail='Token invalide ou expiré')\n",
            
            "@app.on_event('startup')",
            "def init_db():",
            "    conn = sqlite3.connect(DB_FILE)",
            "    try:",
            "        with open('schema.sql', 'r', encoding='utf-8') as f:",
            "            conn.executescript(f.read())",
            "    except Exception as e:",
            "        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')",
            "    finally:",
            "        conn.close()\n",
            
            "class LoginRequest(BaseModel):",
            "    username: str",
            "    actor: str\n",
            "@app.post('/login', tags=['Authentication'])",
            "async def login(req: LoginRequest):",
            "    payload = {",
            "        'sub': req.username,",
            "        'actor': req.actor,",
            "        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)",
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            "    return {'access_token': token, 'token_type': 'bearer'}\n",
            "# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---"
        ]
        
        # 1. Génération des schémas CRUD standards
        for ent_name, attrs in self.entities.items():
            api_lines.append(f"class {ent_name}Schema(BaseModel):")
            for attr_name, attr_type in attrs.items():
                py_type = "str"
                if attr_type == "Integer": py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type == "Boolean": py_type = "bool"
                api_lines.append(f"    {attr_name}: {py_type}")
            api_lines.append("\n")

        # 2. Génération de schémas stricts pour les entrées de la Sandbox IA (Bug #4)
        api_lines.append("# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---")
        for func in self.custom_functions:
            func_name = func["name"]
            inputs = func.get("input", [])
            
            api_lines.append(f"class {func_name}InputSchema(BaseModel):")
            if not inputs:
                api_lines.append("    pass")
            else:
                for inp in inputs:
                    if "reference" in inp:
                        ref = inp["reference"]
                        ent, attr = ref.split(".") if "." in ref else (ref, "id")
                        attr_type = self.entities.get(ent, {}).get(attr, "String")
                        py_type = "int" if attr_type == "Integer" else ("float" if attr_type in ["Float", "Money"] else ("bool" if attr_type == "Boolean" else "str"))
                        api_lines.append(f"    {attr.replace('.', '_')}: {py_type}")
                    else:
                        inp_name = inp.get("name", "context")
                        inp_type = inp.get("type", "String")
                        py_type = "int" if inp_type == "Integer" else ("float" if inp_type in ["Float", "Money"] else ("bool" if inp_type == "Boolean" else "str"))
                        api_lines.append(f"    {inp_name}: {py_type}")
            api_lines.append("\n")

        api_lines.append("# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---")
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]
            
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".")[0] if "." in target else target
                
                security_check = f'    if current_actor != "{required_actor}": raise HTTPException(status_code=403, detail="Contrôle d\'accès : Rôle {required_actor} requis")'
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
                
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
                    api_lines.append(f"    return {{'status': 'success', 'id': row_id}}")
                    api_lines.append("")
                    
                elif act_type == "Read":
                    api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{wf_name}'])")
                    api_lines.append(f"async def read_{base_target.lower()}(id: int, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    api_lines.append(f"    cursor.execute('SELECT * FROM {base_target.lower()} WHERE id = ?', (id,))")
                    api_lines.append("    row = cursor.fetchone(); conn.close()")
                    api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
                    api_lines.append("    return {'status': 'success', 'data': row}")
                    api_lines.append("")
                    
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
                    api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                    api_lines.append("")

                elif act_type == "Delete":
                    api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{wf_name}'])")
                    api_lines.append(f"async def delete_{base_target.lower()}(id: int, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                    api_lines.append(f"    cursor.execute('DELETE FROM {base_target.lower()} WHERE id = ?', (id,))")
                    api_lines.append("    conn.commit(); conn.close()")
                    api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                    api_lines.append("")
                    
                elif act_type == "Execute":
                    api_lines.append(f"@app.post('/workflow/{wf_name.lower()}/{target.lower()}', tags=['{wf_name}'])")
                    api_lines.append(f"async def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
                    api_lines.append(security_check)
                    api_lines.append(f"    result = sandbox_ai.{target}(payload.dict())")
                    api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
                    api_lines.append("")
                    
        return "\n".join(api_lines)

    def _generate_ai_sandbox(self):
        """Balise les frontières d'isolation pour le code généré par l'IA."""
        sb_lines = ["# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX\n"]
        for func in self.custom_functions:
            name = func["name"]
            desc = func.get("description", "Logique métier custom.").strip()
            sb_lines.append(f"def {name}(context: dict) -> dict:\n    \"\"\"\n    CONSIGNE IA : {desc}\n    \"\"\"\n    # TODO:\n    return {{'message': 'Coquille vide déterministe pour {name}'}}\n")
        return "\n".join(sb_lines)

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../todo.yaml")
    try:
        raw_json = parse_monlang_file(sample_path)
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
    except Exception as e:
        print(f"❌ Échec : {e}")
