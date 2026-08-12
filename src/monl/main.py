import argparse
import os

from .ast_validator import MonlAST
from .errors import CompilationGenerationError, CompilationInputError, MonlError
from .generator import MonlSecureGenerator
from .ir import CompilationResult
from .parser import parse_monl_file


def compile_monl(
    file_path: str,
    output_dir: str | None = None,
    base_dir: str | None = None,
) -> CompilationResult:
    """Compile une spécification MONL sans terminer le processus appelant.

    Cette fonction est l'API de bibliothèque du compilateur : elle lève des
    erreurs MONL attendues, tandis que les entrées CLI les convertissent en
    messages et codes de sortie. Le pipeline reste déterministe et hors ligne.
    """
    if not os.path.exists(file_path):
        raise CompilationInputError(
            f"Le fichier de spécification '{file_path}' n'existe pas.")

    filename = os.path.basename(file_path)
    print("\n" + "=" * 65)
    print(f" ⚙️  COMPILATEUR MONL : {filename}")
    print("=" * 65)

    # --- ÉTAPE 1 : PARSING ---
    print("\n [1/3] Analyse syntaxique...")
    raw_json = parse_monl_file(file_path)
    print("    └─ AST de base extrait avec succès.")

    # --- ÉTAPE 2 : AUDIT STATIQUE ---
    print("\n [2/3] Audit statique d'architecture & restrictions...")
    # Le dossier de la SPEC est la référence des assets : c'est là que vivent
    # les photos, le logo et le favicon déclarés.
    reference_dir = base_dir or os.path.dirname(os.path.abspath(file_path))
    ast_manager = MonlAST(raw_json, base_dir=reference_dir)
    normalized_ast = ast_manager.validate_and_audit()

    # --- ÉTAPE 3 : GÉNÉRATION DU SOCLE ---
    print("\n [3/3] Génération du socle déterministe...")
    generator = MonlSecureGenerator(normalized_ast, output_dir=output_dir)
    try:
        generator.generate_all()
    except MonlError:
        raise
    except Exception as exc:
        raise CompilationGenerationError(
            f"La génération des artefacts a échoué : {exc}") from exc
    print("    └─ Artefacts d'infrastructure scellés.")

    has_custom = bool(normalized_ast["sandbox_ai"]["custom_functions"])

    print("\n" + "=" * 65)
    print(" 🎉 COMPILATION DE L'APPLICATION TERMINÉE !")
    print(" -> Infrastructure : app.py, schema.sql validés (init auto DB active)")
    if has_custom:
        print(" -> Blocs 'custom' : coquilles vides sûres dans sandbox_ai.py")
        print("                     (logique à écrire à la main).")
    print("=" * 65 + "\n")

    # Le contrat frontend réutilise exactement ce résultat dans la couche CLI.
    return CompilationResult(
        ir=normalized_ast,
        generator=generator,
        plans=generator.compilation_plans,
    )


def main(argv=None) -> int:
    """Point d'entrée CLI : seule cette frontière traduit les erreurs attendues."""
    parser = argparse.ArgumentParser(description="Compilateur monl.")
    parser.add_argument(
        "fichier", type=str, nargs="?",
        help="Chemin du fichier .ml à compiler (l'ancienne extension .yaml reste acceptée).",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Dossier où écrire les artefacts générés (app.py, schema.sql, "
             "sandbox_ai.py, .jwt_secret...).",
    )
    args = parser.parse_args(argv)
    fichier = args.fichier or os.path.join(
        os.path.dirname(__file__), "..", "..", "exemples", "01_portfolio.ml")
    try:
        compile_monl(fichier, output_dir=args.output)
    except MonlError as err:
        print(f"\n ❌ ÉCHEC DU COMPILATEUR : {err}")
        print("=" * 65 + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
