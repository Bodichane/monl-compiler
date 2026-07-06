import os
import sys
import argparse
from parser import parse_monlang_file
from ast_validator import MonLangAST
from generator import MonLangSecureGenerator

def compile_monlang(file_path):
    """Orchestre la boucle complète de compilation sécurisée de MonLang."""
    if not os.path.exists(file_path):
        print(f"❌ Erreur : Le fichier spécifié '{file_path}' n'existe pas.")
        sys.exit(1)
        
    print("=" * 60)
    print(f"🚀 COMPILATEUR SECURISE MONLANG : {os.path.basename(file_path)}")
    print("=" * 60)
    
    try:
        # Étape 1 : Parsing Extensible (Phase 3)
        print("\n[Étape 1/3] Analyse syntaxique (Parsing)...")
        raw_json = parse_monlang_file(file_path)
        print(" -> Structure syntaxique extraite avec succès.")
        
        # Étape 2 : Validation Sémantique & Analyse Statique de Sécurité (Phase 4)
        print("\n[Étape 2/3] Validation logique et audit statique des vulnérabilités...")
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()
        
        # Étape 3 : Génération du Socle Déterministe et Isolation IA (Phase 5)
        print("\n[Étape 3/3] Génération du socle d'infrastructure (DB, API & Sandbox)...")
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
        
        print("\n" + "=" * 60)
        print("🎉 COMPILATION REUSSIE ! L'infrastructure et la sandbox IA sont scellées.")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ÉCHEC CRITIQUE DU COMPILATEUR : {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compilateur MonLang : Vibe coding traçable et sécurisé.")
    parser.add_argument("fichier", type=str, nargs="?", help="Le chemin vers le fichier de spécification .yaml à compiler.")
    
    args = parser.parse_args()
    
    # Par défaut, si aucun argument n'est fourni, on compile notre exemple TodoList révisé
    if not args.fichier:
        default_sample = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
        compile_monlang(default_sample)
    else:
        compile_monlang(args.fichier)
