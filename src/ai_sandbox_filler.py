import os
import sys
import json
import ast
import requests
from ast_validator import MonLangAST
from parser import parse_monlang_file

def validate_generated_code_safety(ai_code: str, func_name: str):
    """
    Analyse statiquement le code généré par l'IA à l'aide de l'AST de Python.
    Bloque l'injection si des patterns interdits, des injections SQL indirectes,
    des accès réseau/système détournés, ou des boucles sans issue sont détectés.
    """
    # CORRECTIF (post-v6, roadmap point 1) : liste étendue au-delà de l'injection SQL.
    # - Ajout de modules réseau/bas niveau supplémentaires (un contournement possible
    #   du blocage de 'requests'/'urllib' était d'utiliser 'socket', 'http.client',
    #   'ftplib' ou 'smtplib' directement).
    # - Ajout de 'importlib' qui permettrait de recharger dynamiquement un module banni.
    BANNED_IMPORTS = {
        "os", "subprocess", "sys", "shutil", "builtins", "requests", "urllib",
        "socket", "http", "ftplib", "smtplib", "importlib", "ctypes", "pickle",
    }
    # - Ajout de '__import__', qui permettait de contourner le blocage des imports
    #   statiques en importation dynamique (ex: __import__('os').system(...)).
    BANNED_FUNCTIONS = {
        "eval", "exec", "open", "compile", "globals", "locals",
        "getattr", "setattr", "delattr", "__import__", "vars", "input",
    }

    try:
        root = ast.parse(ai_code)
    except SyntaxError as e:
        raise RuntimeError(f"🚨 [GUARDRAIL] Erreur de syntaxe Python dans le code de l'IA : {e}")

    for node in ast.walk(root):
        # 1. Traque les imports interdits
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                if top_level in BANNED_IMPORTS:
                    raise PermissionError(f"🛑 [SECURITY_BLOCKED] Import interdit : '{alias.name}' !")
        elif isinstance(node, ast.ImportFrom):
            top_level = (node.module or "").split(".")[0]
            if top_level in BANNED_IMPORTS:
                raise PermissionError(f"🛑 [SECURITY_BLOCKED] Import interdit depuis : '{node.module}' !")
        
        # 2. Traque les fonctions d'exécution dynamique interdites
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_FUNCTIONS:
                raise PermissionError(f"🛑 [SECURITY_BLOCKED] Appel de fonction dangereuse : '{node.func.id}' !")
            
            # --- CORRECTIF BUG v6 #2 : Traque de l'injection SQL indirecte par le LLM ---
            # On intercepte les appels de type cursor.execute() ou conn.execute()
            if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                if node.args:
                    first_arg = node.args[0]
                    
                    # Interdiction des f-strings au sein de la méthode execute()
                    if isinstance(first_arg, ast.JoinedStr):
                        raise PermissionError(f"🛑 [SQL_INJECTION_BLOCKED] L'IA a tenté d'utiliser une f-string non sécurisée au sein d'une méthode .execute() dans '{func_name}' !")
                    
                    # Interdiction des concaténations par l'opérateur modulo % (ex: "SELECT %s" % var)
                    if isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Mod):
                        raise PermissionError(f"🛑 [SQL_INJECTION_BLOCKED] L'IA a tenté d'utiliser une interpolation de chaînes par l'opérateur '%' au sein d'un .execute() dans '{func_name}' !")
                    
                    # Interdiction des concaténations par addition + (ex: "SELECT " + var)
                    if isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                        raise PermissionError(f"🛑 [SQL_INJECTION_BLOCKED] L'IA a tenté d'utiliser une concaténation de texte par l'opérateur '+' au sein d'un .execute() dans '{func_name}' !")

        # 3. CORRECTIF (post-v6, roadmap point 1) : détection heuristique des boucles
        # sans issue. Une boucle "while True"/"while 1" sans aucun "break" dans son
        # corps ne rendra jamais la main au serveur qui l'appelle (déni de service).
        # Heuristique simple, volontairement conservatrice : elle ne détecte que le
        # cas le plus évident (condition littéralement constante et vraie).
        elif isinstance(node, ast.While):
            condition_is_constant_true = (
                (isinstance(node.test, ast.Constant) and bool(node.test.value)) or
                (isinstance(node.test, ast.NameConstant) and bool(node.test.value))  # compat anciennes versions d'ast
            )
            if condition_is_constant_true:
                has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                if not has_break:
                    raise PermissionError(
                        f"🛑 [INFINITE_LOOP_BLOCKED] La fonction '{func_name}' contient une boucle "
                        f"'while True'/'while 1' sans instruction 'break' détectable — risque de "
                        f"blocage indéfini du serveur !"
                    )

    print(f"🛡️  [GUARDRAIL] Le code pour '{func_name}' a passé l'analyse statique et le contrôle anti-injection SQL.")
def generate_custom_logic_with_ai(func_name, description, inputs, output):
    """Interroge Ollama au format JSON strict pour obtenir le corps du code."""
    print(f"🤖 L'IA locale (Qwen) génère le code métier pour '{func_name}'...")
    url = "http://localhost:11434/api/chat"
    
    prompt = f"""
    Tu es un module d'écriture de code. Tu dois générer uniquement le CORPS interne d'une fonction Python.
    La fonction reçoit un dictionnaire nommé 'context'.
    
    Spécification :
    - Nom de la fonction : {func_name}
    - Consigne métier : {description}
    - Variables dans 'context' : {inputs}
    - Résultat attendu : un dictionnaire avec la clé pour le paramètre de sortie '{output}'
    
    Tu dois impérativement répondre au format JSON avec une seule clé "code" contenant les lignes de code Python pur, sans aucune indentation de départ tout à gauche (pas de ligne 'def').
    Exemple de JSON attendu :
    {{
        "code": "title = context.get('title', '')\nif '[Archive]' in title:\n    return {{'status': 'archived'}}\nreturn {{'status': 'active'}}"
    }}
    """

    payload = {
        "model": "qwen2.5-coder:3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1}
    }

    try:
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        ai_json = json.loads(response.json()["message"]["content"])
        return ai_json["code"]
    except Exception as e:
        raise RuntimeError(f"Erreur d'API : {e}")

def inject_code_into_sandbox(func_name, ai_code):
    """Injecte le code et applique une correction d'indentation via l'AST natif de Python."""
    sandbox_path = os.path.join(os.path.dirname(__file__), "../sandbox_ai.py")
    
    if not os.path.exists(sandbox_path):
        print(f"❌ Erreur : Le fichier '{sandbox_path}' n'existe pas.")
        return

    with open(sandbox_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Génération géométrique et standard du bloc de code via l'AST Python
    parsed_ai_ast = ast.parse(ai_code)
    standard_formatted_code = ast.unparse(parsed_ai_ast)

    new_lines = []
    inside_target_func = False
    todo_replaced = False

    for line in lines:
        if line.startswith(f"def {func_name}("):
            inside_target_func = True
            new_lines.append(line)
            continue
        
        if inside_target_func and "# TODO:" in line and not todo_replaced:
            # On applique un décalage de 4 espaces sur l'ensemble du bloc re-généré proprement par l'AST
            for ai_line in standard_formatted_code.split("\n"):
                if ai_line.strip():
                    new_lines.append(f"    {ai_line}\n")
                else:
                    new_lines.append("\n")
            todo_replaced = True
            continue
            
        if inside_target_func and line.startswith("def "):
            inside_target_func = False

        if inside_target_func and "return {'message':" in line and todo_replaced:
            continue

        new_lines.append(line)

    with open(sandbox_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    print(f"🔒 Injection réussie ! L'indentation de '{func_name}' a été corrigée selon les normes de l'AST Python.")

def run_ai_filler(file_path):
    raw_json = parse_monlang_file(file_path)
    ast_manager = MonLangAST(raw_json)
    normalized_ast = ast_manager.validate_and_audit()
    
    custom_funcs = normalized_ast["sandbox_ai"]["custom_functions"]
    for func in custom_funcs:
        description = func.get("description", "Analyse le titre et archive automatiquement")
        ai_code = generate_custom_logic_with_ai(func["name"], description, func.get("input", []), func.get("output", []))
        validate_generated_code_safety(ai_code, func["name"])
        inject_code_into_sandbox(func["name"], ai_code)
