import os
import sys
import argparse
from parser import parse_monlang_file
from ast_validator import MonLangAST
from generator import MonLangSecureGenerator
from ai_sandbox_filler import run_ai_filler

def compile_monlang(file_path):
    """Orchestre le pipeline MonLang avec un rendu CLI épuré et professionnel."""
    if not os.path.exists(file_path):
        print(f"❌ Erreur : Le fichier de spécification '{file_path}' n'existe pas.")
        sys.exit(1)
        
    filename = os.path.basename(file_path)
    
    print("\n" + "=" * 65)
    print(f" ⚙️  COMPILATEUR MONLANG : {filename}")
    print("=" * 65)
    
    try:
        # --- ÉTAPE 1 : PARSING ---
        print("\n [1/4] Analyse syntaxique...")
        raw_json = parse_monlang_file(file_path)
        print("    └─ AST de base extrait avec succès.")
        
        # --- ÉTAPE 2 : AUDIT DE SÉCURITÉ ---
        print("\n [2/4] Audit statique d'architecture & restrictions...")
        ast_manager = MonLangAST(raw_json)
        # On capture l'AST normalisé. Les alertes de sécurité s'afficheront ici de manière lisible
        normalized_ast = ast_manager.validate_and_audit()
        
        # --- ÉTAPE 3 : GÉNÉRATION DU SOCLE ---
        print("\n [3/4] Génération du socle déterministe...")
        generator = MonLangSecureGenerator(normalized_ast)
        
        # Redirection temporaire des print internes du générateur pour épurer la CLI
        # (Seul le message final du socle sera visible)
        generator.generate_all()
        
        # --- ÉTAPE 4 : ACTIVATION DE L'IA ---
        print("\n [4/4] Activation de l'échappatoire IA...")
        run_ai_filler(file_path)
        
        # --- SCELLÉ FINAL ---
        print("\n" + "=" * 65)
        print(" 🎉 COMPILATION ET INJECTION RÉUSSIES avec succès !")
        print(" -> Artefacts sécurisés par défaut : app.py, schema.sql, sandbox_ai.py")
        print("=" * 65 + "\n")
        
    except Exception as e:
        print(f"\n ❌ ÉCHEC CRITIQUE DU COMPILATEUR : {e}")
        print("=" * 65 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compilateur Industriel MonLang.")
    parser.add_argument("fichier", type=str, nargs="?", help="Chemin du fichier .yaml à compiler.")
    args = parser.parse_args()
    
    if not args.fichier:
        default_sample = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
        compile_monlang(default_sample)
    else:
        compile_monlang(args.fichier)
