import argparse
import os
import sys

from ast_validator import MonlAST
from generator import MonlSecureGenerator
from parser import parse_monl_file


def compile_monl(file_path, output_dir=None):
    """Compile une spécification .ml en backend complet.

    Le pipeline est entièrement DÉTERMINISTE et HORS-LIGNE : parsing, audit
    statique, puis génération du schéma, de l'API, du contrôle d'accès et de
    l'authentification. Aucune IA n'intervient. Les blocs 'custom' éventuels
    sont générés sous forme de coquilles vides sûres dans sandbox_ai.py, que
    le développeur complète à la main (voir docs/SECURITE.md)."""
    if not os.path.exists(file_path):
        print(f"❌ Erreur : Le fichier de spécification '{file_path}' n'existe pas.")
        sys.exit(1)

    filename = os.path.basename(file_path)

    print("\n" + "=" * 65)
    print(f" ⚙️  COMPILATEUR MONL : {filename}")
    print("=" * 65)

    try:
        # --- ÉTAPE 1 : PARSING ---
        print("\n [1/3] Analyse syntaxique...")
        raw_json = parse_monl_file(file_path)
        print("    └─ AST de base extrait avec succès.")

        # --- ÉTAPE 2 : AUDIT STATIQUE ---
        print("\n [2/3] Audit statique d'architecture & restrictions...")
        ast_manager = MonlAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()

        # --- ÉTAPE 3 : GÉNÉRATION DU SOCLE ---
        print("\n [3/3] Génération du socle déterministe...")
        generator = MonlSecureGenerator(normalized_ast, output_dir=output_dir)
        generator.generate_all()
        print("    └─ Artefacts d'infrastructure scellés.")

        has_custom = bool(normalized_ast["sandbox_ai"]["custom_functions"])

        # --- SCELLÉ FINAL ---
        print("\n" + "=" * 65)
        print(" 🎉 COMPILATION DE L'APPLICATION TERMINÉE !")
        print(" -> Infrastructure : app.py, schema.sql validés (init auto DB active)")
        if has_custom:
            print(" -> Blocs 'custom' : coquilles vides sûres dans sandbox_ai.py")
            print("                     (logique à écrire à la main).")
        print("=" * 65 + "\n")

    except Exception as e:
        print(f"\n ❌ ÉCHEC CRITIQUE DU COMPILATEUR : {e}")
        print("=" * 65 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compilateur monl.")
    parser.add_argument("fichier", type=str, nargs="?",
                        help="Chemin du fichier .ml à compiler "
                             "(l'ancienne extension .yaml reste acceptée).")
    parser.add_argument("--output", type=str, default=None,
                        help="Dossier où écrire les artefacts générés (app.py, schema.sql, "
                             "sandbox_ai.py, .jwt_secret...). Par défaut : racine du dépôt. "
                             "Permet de compiler plusieurs specs sans qu'elles s'écrasent — "
                             "lancer ensuite le serveur DEPUIS ce dossier "
                             "(cd DIR && python3 -m uvicorn app:app).")
    args = parser.parse_args()

    if not args.fichier:
        default_sample = os.path.join(os.path.dirname(__file__), "../exemples/01_portfolio.ml")
        compile_monl(default_sample, output_dir=args.output)
    else:
        compile_monl(args.fichier, output_dir=args.output)
