import os
import sys
import json
import ast
import requests

from ast_validator import MonLangAST
from parser import parse_monlang_file

def validate_generated_code_safety(ai_code: str, func_name: str):
    """Analyse statiquement le code généré par l'IA à l'aide de l'AST de Python."""
    BANNED_IMPORTS = {"os", "subprocess", "sys", "shutil", "builtins", "requests", "urllib"}
    BANNED_FUNCTIONS = {"eval", "exec", "open", "compile", "globals", "locals", "getattr", "setattr"}

    try:
        root = ast.parse(ai_code)
    except SyntaxError as e:
        raise RuntimeError(f"🚨 [GUARDRAIL] Erreur de syntaxe Python dans le code de l'IA : {e}")

    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BANNED_IMPORTS:
                    raise PermissionError(f"🛑 [SECURITY_BLOCKED] Import interdit : '{alias.name}' !")
        elif isinstance(node, ast.ImportFrom):
            if node.module in BANNED_IMPORTS:
                raise PermissionError(f"🛑 [SECURITY_BLOCKED] Import interdit depuis : '{node.module}' !")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_FUNCTIONS:
                raise PermissionError(f"🛑 [SECURITY_BLOCKED] Appel de fonction dangereuse : '{node.func.id}' !")
    print(f"🛡️  [GUARDRAIL] Le code pour '{func_name}' a passé l'analyse statique.")

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
        "code": "title = context.get('Todo.title', '')\\nif '[Archive]' in title:\\n    return {{'status': 'archived'}}\\nreturn {{'status': 'active'}}"
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
    # unparse() garantit que le if et ses return enfants auront l'indentation exacte exigée par Python
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
