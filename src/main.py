import os
import sys
import argparse
from parser import parse_monlang_file
from ast_validator import MonLangAST
from generator import MonLangSecureGenerator
from ai_sandbox_filler import run_ai_filler

def compile_monlang(file_path):
    """Orchestre le pipeline MonLang avec gestion non bloquante de l'IA (Bug #3)."""
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
        normalized_ast = ast_manager.validate_and_audit()
        
        # --- ÉTAPE 3 : GÉNÉRATION DU SOCLE ---
        print("\n [3/4] Génération du socle déterministe...")
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
        print("    └─ Artefacts d'infrastructure scellés.")
        
        # --- ÉTAPE 4 : ACTIVATION DE L'IA (NON BLOQUANTE) ---
        print("\n [4/4] Activation de l'échappatoire IA...")
        try:
            run_ai_filler(file_path)
            ai_status = "Enrichie par l'IA locale (Qwen)"
        except (RuntimeError, Exception) as ai_err:
            # CORRECTIF BUG v4 n°3 : Interception de la panne Ollama
            print("\n ⚠️  [AVERTISSEMENT IA NO-BLOCK]")
            print(f"    Le remplissage automatique de la Sandbox a échoué : {ai_err}")
            print("    -> Le socle déterministe est conservé intact.")
            print("    -> La fonction custom reste disponible sous forme de coquille vide sécurisée.")
            ai_status = "Coquille vide déterministe (Serveur IA hors-ligne)"
        
        # --- SCELLÉ FINAL ---
        print("\n" + "=" * 65)
        print(" 🎉 COMPILATION DE L'APPLICATION TERMINÉE !")
        print(f" -> Statut Infrastructure : app.py, schema.sql validés (Init auto DB active)")
        print(f" -> Statut Sandbox IA     : {ai_status}")
        print("=" * 65 + "\n")
        
    except Exception as e:
        print(f"\n ❌ ÉCHEC CRITIQUE DU COMPILATEUR : {e}")
        print("=" * 65 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compilateur Industriel MonLang.")
    parser.add_argument("fichier", type=str, nargs="?", help="Chemin du fichier .yaml à compiler.")
    parser.add_argument("--prompt", type=str, default=None,
                         help="Décrire l'application en langage naturel au lieu de fournir un fichier "
                              "(nécessite un serveur Ollama local, voir README.md).")
    parser.add_argument("--model", type=str, default="qwen2.5-coder:3b",
                         help="Nom du modèle Ollama à utiliser avec --prompt (défaut : qwen2.5-coder:3b).")
    parser.add_argument("--save-spec-as", type=str, default=None,
                         help="Chemin où sauvegarder la spec générée par --prompt "
                              "(défaut : ../generated_from_prompt.yaml).")
    args = parser.parse_args()

    if args.prompt:
        from ai_translator import prompt_to_monlang, save_spec_to_file
        try:
            spec_text = prompt_to_monlang(args.prompt, model=args.model)
        except RuntimeError as e:
            print(f"\n{e}")
            sys.exit(1)
        output_path = args.save_spec_as or os.path.join(
            os.path.dirname(__file__), "../generated_from_prompt.yaml"
        )
        save_spec_to_file(spec_text, output_path)
        compile_monlang(output_path)
    elif not args.fichier:
        default_sample = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
        compile_monlang(default_sample)
    else:
        compile_monlang(args.fichier)
