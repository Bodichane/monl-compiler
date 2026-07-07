import os
import sys
import json
import requests
from ast_validator import MonLangAST
from parser import parse_monlang_file

def generate_custom_logic_with_ai(func_name, description, inputs, output):
    """Interroge Ollama au format JSON strict pour obtenir le corps du code (Timeout augmenté à 90s)."""
    print(f"🤖 L'IA locale (Qwen) génère le code métier pour '{func_name}'...")
    url = "http://localhost:11434/api/chat"
    
    prompt = f"""
    Tu es un module d'écriture de code. Tu dois générer uniquement le CORPS d'une fonction Python.
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
        # Augmentation du timeout à 90 secondes pour absorber la charge d'initialisation sur 8 Go de RAM
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        ai_json = json.loads(response.json()["message"]["content"])
        return ai_json["code"]
    except Exception as e:
        raise RuntimeError(f"Erreur d'API : {e}")

def inject_code_into_sandbox(func_name, ai_code):
    """Injecte et aligne géométriquement le code ligne par ligne sans Regex."""
    sandbox_path = os.path.join(os.path.dirname(__file__), "../sandbox_ai.py")
    
    if not os.path.exists(sandbox_path):
        print(f"❌ Erreur : Le fichier '{sandbox_path}' n'existe pas.")
        return

    with open(sandbox_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    inside_target_func = False
    docstring_count = 0
    in_docstring = False
    code_injected = False

    for line in lines:
        if line.startswith(f"def {func_name}("):
            inside_target_func = True
            new_lines.append(line)
            continue
            
        if inside_target_func and not code_injected:
            if '"""' in line:
                docstring_count += 1
                in_docstring = not in_docstring
                new_lines.append(line)
                
                # Dès qu'on ferme la docstring de description, on injecte le code de l'IA
                if docstring_count == 2:
                    # Traitement géométrique des lignes de l'IA
                    indent_level = 4
                    for ai_line in ai_code.split("\n"):
                        stripped = ai_line.strip()
                        
                        # Sécurité : Éliminer la ligne "def" parasite si l'IA l'a générée
                        if stripped.startswith("def ") or stripped.startswith("```") or not stripped:
                            continue
                            
                        # Gestion de l'indentation relative des blocs
                        if stripped.startswith("elif ") or stripped.startswith("else:"):
                            new_lines.append(f"    {stripped}\n")
                            indent_level = 8
                            continue
                            
                        if stripped.startswith("return ") and indent_level == 8:
                            new_lines.append(f"        {stripped}\n")
                            # Après un return dans un bloc, on réinitialise l'indentation
                            indent_level = 4
                            continue
                            
                        new_lines.append(f"    {stripped}\n")
                        if stripped.endswith(":"):
                            indent_level = 8
                    
                    code_injected = True
                continue
                
            if in_docstring:
                new_lines.append(line)
                continue
                
            # On ignore l'ancien contenu (TODO, vieux return) tant que le code n'est pas injecté
            continue

        if inside_target_func and line.startswith("def "):
            # Sortie de la fonction cible
            inside_target_func = False

        if inside_target_func and code_injected:
            # On ignore l'ancien code résiduel de la fonction cible
            continue

        new_lines.append(line)

    with open(sandbox_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    print(f"🔒 Injection réussie ! Le code de l'IA a été scellé et aligné pour '{func_name}'.")

def run_ai_filler(file_path):
    """Extrait les fonctions custom de l'AST et pilote le remplissage par l'IA."""
    # Utilisation dynamique du fichier passé par l'orchestrateur main.py
    raw_json = parse_monlang_file(file_path)
    ast_manager = MonLangAST(raw_json)
    normalized_ast = ast_manager.validate_and_audit()
    
    custom_funcs = normalized_ast["sandbox_ai"]["custom_functions"]
    for func in custom_funcs:
        description = func.get("description", "Analyse le titre et archive automatiquement")
        ai_code = generate_custom_logic_with_ai(func["name"], description, func.get("input", []), func.get("output", []))
        inject_code_into_sandbox(func["name"], ai_code)


if __name__ == "__main__":
    try:
        run_ai_filler()
    except Exception as e:
        print(f"❌ Échec de la Phase 7 : {e}")
