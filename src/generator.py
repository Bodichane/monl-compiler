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
        # AJOUT (post-v6, roadmap) : map "Entite.Action" -> entité propriétaire,
        # issue des règles 'ownedBy' validées par ast_validator.py.
        self.ownership = normalized_ast["security"].get("ownership", {})

    def _get_incoming_relation(self, entity):
        """Retourne la relation 'hasMany' entrante sur 'entity' (celle qui fournit
        la colonne de clé étrangère <source>_id dans schema.sql), ou None s'il
        n'y en a pas. Utilisé à la fois pour peupler cette colonne à la création
        (gap corrigé au passage : elle n'était jamais renseignée auparavant) et
        pour le contrôle d'accès par propriété ('ownedBy')."""
        for rel in self.relations:
            if rel["type"] == "hasMany" and rel["target"] == entity:
                return {"source": rel["source"], "fk_column": f"{rel['source'].lower()}_id"}
        return None

    def generate_all(self):
        """Déclenche la génération déterministe et balise l'échappatoire IA."""
        print(f"🏗️  Génération du socle déterministe réel pour '{self.app_name}'...")
        
        sql_content = self._generate_sql()
        api_content = self._generate_secure_fastapi()
        sandbox_content = self._generate_ai_sandbox()
        frontend_content = self._generate_frontend()
        
        # Détermination des chemins physiques
        base_dir = os.path.dirname(__file__)
        sql_path = os.path.join(base_dir, "../schema.sql")
        api_path = os.path.join(base_dir, "../app.py")
        sandbox_path = os.path.join(base_dir, "../sandbox_ai.py")
        frontend_path = os.path.join(base_dir, "../frontend.html")
        
        with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
        with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
        with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)
        with open(frontend_path, "w", encoding="utf-8") as f: f.write(frontend_content)
            
        print("💾 Socle généré : 'schema.sql', 'app.py', 'sandbox_ai.py' et 'frontend.html' sont prêts !")

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

            # AJOUT (post-v6, roadmap) : dépendance séparée pour récupérer l'identité
            # numérique (user_id) portée par le token, utilisée par le contrôle
            # d'accès par propriété ('ownedBy') et par le peuplement automatique
            # des colonnes de clé étrangère à la création d'un enregistrement.
            "def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:",
            "    try:",
            "        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "        return payload.get('user_id', 0)",
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

            # CORRECTIF (post-v6, roadmap point 4a) : redirection de la racine vers
            # la documentation Swagger/OpenAPI auto-générée par FastAPI. Ça donne un
            # « front minimal » gratuit — utilisable au navigateur, sans écrire une
            # seule requête HTTP à la main — en attendant un vrai front dédié.
            "from fastapi.responses import RedirectResponse, HTMLResponse\n",
            "@app.get('/', include_in_schema=False)",
            "async def root():",
            "    return RedirectResponse(url='/docs')\n",

            # AJOUT (post-v6, roadmap point 4a) : sert le front minimal généré
            # (frontend.html) sur la route /ui, en même origine que l'API — ce
            # qui évite tout souci de CORS pour les appels fetch() du front.
            "@app.get('/ui', include_in_schema=False, response_class=HTMLResponse)",
            "async def ui():",
            "    try:",
            "        with open('frontend.html', 'r', encoding='utf-8') as f:",
            "            return HTMLResponse(content=f.read())",
            "    except FileNotFoundError:",
            "        return HTMLResponse(content='<h1>frontend.html introuvable</h1>', status_code=404)\n",
            
            "class LoginRequest(BaseModel):",
            "    username: str",
            "    actor: str",
            "    # AJOUT (post-v6, roadmap) : identifiant numérique auto-déclaré par le",
            "    # client, utilisé pour le contrôle d'accès par propriété ('ownedBy').",
            "    # LIMITE CONNUE (prototype) : comme pour 'actor', ce projet n'a pas de",
            "    # registre d'utilisateurs réel — ce user_id est déclaré par le client,",
            "    # pas vérifié contre une base d'authentification. Voir docs/design_decisions.md.",
            "    user_id: int = 1\n",
            "@app.post('/login', tags=['Authentication'])",
            "async def login(req: LoginRequest):",
            "    payload = {",
            "        'sub': req.username,",
            "        'actor': req.actor,",
            "        'user_id': req.user_id,",
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

        # CORRECTIF (post-v6) : les routes sont désormais regroupées par couple
        # (type d'action, cible), et non plus générées une fois par workflow.
        # Raison : avant ce correctif, deux workflows différents visant la même
        # action sur la même entité (ex. deux acteurs autorisés à faire "Delete Post"
        # via une règle 'sharedBy') produisaient deux définitions de route FastAPI
        # sur le même chemin ('@app.delete(\"/post/{id}\")' deux fois) — seule la
        # première déclarée restait effectivement joignable, la seconde était
        # silencieusement masquée, et son acteur recevait un 403 malgré une spec
        # valide. Le regroupement ci-dessous fusionne les acteurs autorisés en un
        # seul contrôle d'accès par route, listant tous les acteurs légitimes.
        route_map = {}
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]

            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".")[0] if "." in target else target
                route_key = (act_type, base_target if act_type != "Execute" else target)

                if route_key not in route_map:
                    route_map[route_key] = {"actors": set(), "tags": [], "target": target, "base_target": base_target}
                route_map[route_key]["actors"].add(required_actor)
                if wf_name not in route_map[route_key]["tags"]:
                    route_map[route_key]["tags"].append(wf_name)

        for (act_type, _key), info in route_map.items():
            allowed_actors = sorted(info["actors"])
            base_target = info["base_target"]
            target = info["target"]
            tag = info["tags"][0]

            if len(allowed_actors) == 1:
                security_check = (f'    if current_actor != "{allowed_actors[0]}": '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle {allowed_actors[0]} requis")')
            else:
                allowed_set_literal = ", ".join(f'"{a}"' for a in allowed_actors)
                security_check = (f'    if current_actor not in {{{allowed_set_literal}}}: '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle parmi [{", ".join(allowed_actors)}] requis")')
            dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
                
            if act_type == "Create":
                # AJOUT (post-v6, roadmap) : si l'entité a une relation entrante
                # (ex. "relation User hasMany Todo"), la colonne de clé étrangère
                # correspondante (ex. "user_id") est désormais réellement peuplée
                # à la création, à partir de l'identité JWT de l'appelant.
                # CORRECTIF DE GAP PRÉ-EXISTANT : cette colonne était déjà générée
                # dans schema.sql depuis les toutes premières versions, mais
                # jamais incluse dans la requête INSERT — elle restait NULL pour
                # tout enregistrement créé, rendant les relations inertes au
                # runtime malgré leur présence dans le schéma.
                owner_info = self._get_incoming_relation(base_target)
                create_deps = dependency_injection
                if owner_info:
                    create_deps += ", current_user_id: int = Depends(get_current_user_id)"

                api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
                api_lines.append(f"async def create_{base_target.lower()}(data: {base_target}Schema, {create_deps}):")
                api_lines.append(security_check)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                fields = list(self.entities[base_target].keys())
                insert_columns = list(fields)
                value_exprs = [f"data.{f}" for f in fields]
                if owner_info:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append("current_user_id")
                columns = ", ".join(insert_columns)
                placeholders = ", ".join(["?"] * len(insert_columns))
                api_lines.append(f"    query = 'INSERT INTO {base_target.lower()} ({columns}) VALUES ({placeholders})'")
                values_list = ", ".join(value_exprs)
                api_lines.append(f"    cursor.execute(query, ({values_list},))")
                api_lines.append("    conn.commit(); row_id = cursor.lastrowid; conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': row_id}}")
                api_lines.append("")
                
            elif act_type == "Read":
                api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def read_{base_target.lower()}(id: int, {dependency_injection}):")
                api_lines.append(security_check)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                api_lines.append(f"    cursor.execute('SELECT * FROM {base_target.lower()} WHERE id = ?', (id,))")
                api_lines.append("    row = cursor.fetchone(); conn.close()")
                api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
                api_lines.append("    return {'status': 'success', 'data': row}")
                api_lines.append("")
                
            elif act_type == "Update":
                # AJOUT (post-v6, roadmap) : si une règle 'ownedBy' cible cette
                # action, un contrôle supplémentaire vérifie que l'acteur courant
                # est bien le propriétaire de l'enregistrement, en plus du
                # contrôle de rôle habituel.
                owner_entity = self.ownership.get(f"{base_target}.Update")
                update_deps = dependency_injection
                ownership_check_lines = []
                if owner_entity:
                    fk_col = f"{owner_entity.lower()}_id"
                    update_deps += ", current_user_id: int = Depends(get_current_user_id)"
                    ownership_check_lines = [
                        "    _owner_conn = sqlite3.connect(DB_FILE); _owner_cur = _owner_conn.cursor()",
                        f"    _owner_cur.execute('SELECT {fk_col} FROM {base_target.lower()} WHERE id = ?', (id,))",
                        "    _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                        "    if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                        "    if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
                    ]

                api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def update_{base_target.lower()}(id: int, data: {base_target}Schema, {update_deps}):")
                api_lines.append(security_check)
                api_lines.extend(ownership_check_lines)
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
                owner_entity = self.ownership.get(f"{base_target}.Delete")
                delete_deps = dependency_injection
                ownership_check_lines = []
                if owner_entity:
                    fk_col = f"{owner_entity.lower()}_id"
                    delete_deps += ", current_user_id: int = Depends(get_current_user_id)"
                    ownership_check_lines = [
                        "    _owner_conn = sqlite3.connect(DB_FILE); _owner_cur = _owner_conn.cursor()",
                        f"    _owner_cur.execute('SELECT {fk_col} FROM {base_target.lower()} WHERE id = ?', (id,))",
                        "    _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                        "    if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                        "    if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
                    ]

                api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def delete_{base_target.lower()}(id: int, {delete_deps}):")
                api_lines.append(security_check)
                api_lines.extend(ownership_check_lines)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                api_lines.append(f"    cursor.execute('DELETE FROM {base_target.lower()} WHERE id = ?', (id,))")
                api_lines.append("    conn.commit(); conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                api_lines.append("")
                
            elif act_type == "Execute":
                api_lines.append(f"@app.post('/workflow/{tag.lower()}/{target.lower()}', tags=['{tag}'])")
                api_lines.append(f"async def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
                api_lines.append(security_check)
                api_lines.append(f"    result = sandbox_ai.{target}(payload.dict())")
                api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
                api_lines.append("")
                    
        return "\n".join(api_lines)

    def _compute_entity_actions(self):
        """Reconstruit, pour chaque entité, l'ensemble des actions CRUD exposées
        par au moins un workflow (utilisé par le front minimal généré pour ne
        proposer que les formulaires réellement utilisables)."""
        entity_actions = {}
        execute_actions = []
        for wf in self.workflows:
            for action in wf["actions"]:
                if action["type"] == "Execute":
                    execute_actions.append({"target": action["target"], "tag": wf["name"]})
                else:
                    base = action["target"].split(".")[0] if "." in action["target"] else action["target"]
                    entity_actions.setdefault(base, set()).add(action["type"])
        return entity_actions, execute_actions

    def _generate_frontend(self):
        """AJOUT (post-v6, roadmap point 4a) : génère un front minimal, en une
        seule page HTML/JS autonome, servi par l'application elle-même sur la
        route /ui. Objectif : permettre d'utiliser l'application générée sans
        écrire de requêtes HTTP à la main et sans dépendre d'un outil externe
        comme Swagger — un formulaire de connexion, puis un formulaire par
        entité (créer / lire / modifier / supprimer par identifiant), et un
        bouton par fonction 'custom' exécutable. Ce n'est pas un remplacement
        d'un vrai front applicatif, seulement un filet d'utilisabilité minimal."""
        entity_actions, execute_actions = self._compute_entity_actions()
        actors = sorted({wf["actor"] for wf in self.workflows})

        def field_input_html(attr_name, attr_type):
            if attr_type == "Boolean":
                return f'<label><input type="checkbox" data-field="{attr_name}" data-type="Boolean"> {attr_name}</label>'
            input_type = "number" if attr_type in ("Integer", "Float", "Money") else "text"
            step = ' step="any"' if attr_type in ("Float", "Money") else ""
            return (f'<label>{attr_name}<br>'
                    f'<input type="{input_type}"{step} data-field="{attr_name}" data-type="{attr_type}" '
                    f'placeholder="{attr_type}"></label>')

        sections = []
        for entity, actions in entity_actions.items():
            attrs = self.entities.get(entity, {})
            fields_html = "\n            ".join(field_input_html(a, t) for a, t in attrs.items())
            buttons = []
            if "Create" in actions:
                buttons.append(f'<button onclick="createRecord(\'{entity}\')">Créer</button>')
            if "Read" in actions:
                buttons.append(f'<button onclick="readRecord(\'{entity}\')">Lire (par ID)</button>')
            if "Update" in actions:
                buttons.append(f'<button onclick="updateRecord(\'{entity}\')">Modifier (par ID)</button>')
            if "Delete" in actions:
                buttons.append(f'<button onclick="deleteRecord(\'{entity}\')">Supprimer (par ID)</button>')

            sections.append(f"""
        <section class="entity-card">
            <h3>{entity}</h3>
            <label>ID (pour Lire / Modifier / Supprimer)<br>
                <input type="number" id="{entity}_id" placeholder="id"></label>
            <div class="fields">
            {fields_html}
            </div>
            <div class="actions">{' '.join(buttons)}</div>
            <pre id="{entity}_result" class="result"></pre>
        </section>""")

        execute_sections = []
        for exe in execute_actions:
            target = exe["target"]
            func = next((f for f in self.custom_functions if f["name"] == target), {})
            inputs = func.get("input", [])
            input_fields = []
            for inp in inputs:
                if "reference" in inp:
                    field_name = inp["reference"].replace(".", "_")
                else:
                    field_name = inp.get("name", "value")
                input_fields.append(f'<label>{field_name}<br><input type="text" data-execfield="{field_name}"></label>')
            execute_sections.append(f"""
        <section class="entity-card">
            <h3>⚙️ {target}</h3>
            <p class="hint">{func.get("description", "")}</p>
            <div class="fields" id="{target}_fields">
            {' '.join(input_fields)}
            </div>
            <div class="actions"><button onclick="executeCustom('{target}', '{exe["tag"]}')">Exécuter</button></div>
            <pre id="{target}_result" class="result"></pre>
        </section>""")

        actor_options = "\n".join(f'<option value="{a}">{a}</option>' for a in actors)

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>{self.app_name} — Front minimal</title>
<style>
    body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; background: #f7f7f8; color: #1a1a1a; }}
    h1 {{ font-size: 1.4rem; }}
    section.entity-card {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; }}
    .fields label {{ display: inline-block; margin: 0.4rem 0.8rem 0.4ren 0; font-size: 0.85rem; }}
    input {{ padding: 0.35rem; border: 1px solid #ccc; border-radius: 4px; margin-top: 0.2rem; }}
    button {{ padding: 0.4rem 0.9rem; margin: 0.3rem 0.4rem 0 0; border: none; border-radius: 6px; background: #2563eb; color: white; cursor: pointer; }}
    button:hover {{ background: #1d4ed8; }}
    pre.result {{ background: #f0f0f0; padding: 0.5rem; border-radius: 4px; font-size: 0.8rem; white-space: pre-wrap; margin-top: 0.5rem; min-height: 1.2rem; }}
    #login-card {{ background: #111827; color: white; }}
    #login-card input, #login-card select {{ color: #111; }}
    .hint {{ color: #666; font-size: 0.85rem; }}
    #status {{ font-size: 0.85rem; margin-left: 1rem; }}
</style>
</head>
<body>
<h1>{self.app_name} <span style="font-weight:normal;font-size:0.9rem;color:#666">— front minimal généré par MonLang</span></h1>
<p class="hint">Ce front est un filet d'utilisabilité minimal — pour une exploration complète des routes, voir <a href="/docs">/docs</a> (Swagger).</p>

<section class="entity-card" id="login-card">
    <h3>Connexion</h3>
    <label>Nom d'utilisateur<br><input type="text" id="login_username" value="demo"></label>
    <label>Acteur<br><select id="login_actor">{actor_options}</select></label>
    <label>user_id (pour les fonctionnalités liées à la propriété)<br><input type="number" id="login_user_id" value="1"></label>
    <div class="actions"><button onclick="login()">Se connecter</button></div>
    <span id="status">Non connecté</span>
</section>

{"".join(sections)}
{"".join(execute_sections)}

<script>
let authToken = null;

async function login() {{
    const body = {{
        username: document.getElementById('login_username').value,
        actor: document.getElementById('login_actor').value,
        user_id: parseInt(document.getElementById('login_user_id').value || '1', 10),
    }};
    const res = await fetch('/login', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify(body) }});
    const data = await res.json();
    if (res.ok) {{
        authToken = data.access_token;
        document.getElementById('status').textContent = `Connecté en tant que ${{body.actor}} (user_id=${{body.user_id}})`;
    }} else {{
        document.getElementById('status').textContent = 'Échec de connexion';
    }}
}}

function authHeaders(extra) {{
    const headers = Object.assign({{'Content-Type': 'application/json'}}, extra || {{}});
    if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
    return headers;
}}

function collectFields(entity) {{
    const card = document.getElementById(entity + '_id').closest('section');
    const data = {{}};
    card.querySelectorAll('[data-field]').forEach(el => {{
        const type = el.dataset.type;
        if (type === 'Boolean') {{ data[el.dataset.field] = el.checked; }}
        else if (type === 'Integer') {{ data[el.dataset.field] = parseInt(el.value || '0', 10); }}
        else if (type === 'Float' || type === 'Money') {{ data[el.dataset.field] = parseFloat(el.value || '0'); }}
        else {{ data[el.dataset.field] = el.value; }}
    }});
    return data;
}}

async function showResult(entity, res) {{
    const out = document.getElementById(entity + '_result');
    let body;
    try {{ body = await res.json(); }} catch (e) {{ body = {{}}; }}
    out.textContent = `HTTP ${{res.status}} — ` + JSON.stringify(body);
}}

async function createRecord(entity) {{
    const res = await fetch('/' + entity.toLowerCase(), {{ method: 'POST', headers: authHeaders(), body: JSON.stringify(collectFields(entity)) }});
    await showResult(entity, res);
}}

async function readRecord(entity) {{
    const id = document.getElementById(entity + '_id').value;
    const res = await fetch('/' + entity.toLowerCase() + '/' + id, {{ headers: authHeaders() }});
    await showResult(entity, res);
}}

async function updateRecord(entity) {{
    const id = document.getElementById(entity + '_id').value;
    const res = await fetch('/' + entity.toLowerCase() + '/' + id, {{ method: 'PUT', headers: authHeaders(), body: JSON.stringify(collectFields(entity)) }});
    await showResult(entity, res);
}}

async function deleteRecord(entity) {{
    const id = document.getElementById(entity + '_id').value;
    const res = await fetch('/' + entity.toLowerCase() + '/' + id, {{ method: 'DELETE', headers: authHeaders() }});
    await showResult(entity, res);
}}

async function executeCustom(target, tag) {{
    const container = document.getElementById(target + '_fields');
    const data = {{}};
    container.querySelectorAll('[data-execfield]').forEach(el => {{ data[el.dataset.execfield] = el.value; }});
    const res = await fetch('/workflow/' + tag.toLowerCase() + '/' + target.toLowerCase(), {{ method: 'POST', headers: authHeaders(), body: JSON.stringify(data) }});
    const out = document.getElementById(target + '_result');
    let body; try {{ body = await res.json(); }} catch (e) {{ body = {{}}; }}
    out.textContent = `HTTP ${{res.status}} — ` + JSON.stringify(body);
}}
</script>
</body>
</html>
"""


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
