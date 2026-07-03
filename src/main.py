import os
import sys
import argparse
from parser import parse_monlang_file
from ast_validator import MonLangAST
from generator import MonLangGenerator

def compile_monlang(file_path):
    """Orchestre la boucle complète de compilation de MonLang."""
    if not os.path.exists(file_path):
        print(f"❌ Erreur : Le fichier spécifié '{file_path}' n'existe pas.")
        sys.exit(1)
        
    print("=" * 60)
    print(f"🚀 COMPILATION MONLANG : {os.path.basename(file_path)}")
    print("=" * 60)
    
    try:
        # Step 1 : Parsing (Phase 3)
        print("\n[Étape 1/3] Analyse syntaxique (Parsing)...")
        raw_json = parse_monlang_file(file_path)
        print(" -> Syntaxe validée.")
        
        # Step 2 : Validation Sémantique & AST (Phase 4)
        print("\n[Étape 2/3] Validation logique et construction de l'AST...")
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate()
        
        # Step 3 : Génération Technique (Phase 5)
        print("\n[Étape 3/3] Génération du schéma DB et des routes de l'API...")
        generator = MonLangGenerator(normalized_ast)
        generator.generate_all()
        
        print("\n" + "=" * 60)
        print("🎉 PIPELINE RÉUSSI ! Votre application a été compilée avec succès.")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ÉCHEC DU COMPILATEUR : {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Configuration du CLI pour accepter n'est-ce qu'un chemin de fichier en entrée
    parser = argparse.ArgumentParser(description="Compilateur MonLang : Transformez vos intentions en logiciel.")
    parser.add_argument("fichier", type=str, help="Le chemin vers le fichier .yaml MonLang à compiler.")
    
    # Si aucun argument n'est fourni, on utilise par défaut notre Todo List pour le test rapide
    if len(sys.argv) == 1:
        default_sample = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
        compile_monlang(default_sample)
    else:
        args = parser.parse_args()
        compile_monlang(args.fichier)
