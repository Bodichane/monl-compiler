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
            f"Specification file '{file_path}' does not exist.")

    filename = os.path.basename(file_path)
    print("\n" + "=" * 65)
    print(f" ⚙️  MONL COMPILER: {filename}")
    print("=" * 65)

    # --- ÉTAPE 1 : PARSING ---
    print("\n [1/3] Parsing...")
    raw_json = parse_monl_file(file_path)
    print("    └─ Base AST extracted successfully.")

    # --- ÉTAPE 2 : AUDIT STATIQUE ---
    print("\n [2/3] Static architecture and restrictions audit...")
    # Le dossier de la SPEC est la référence des assets : c'est là que vivent
    # les photos, le logo et le favicon déclarés.
    reference_dir = base_dir or os.path.dirname(os.path.abspath(file_path))
    ast_manager = MonlAST(raw_json, base_dir=reference_dir)
    normalized_ast = ast_manager.validate_and_audit()

    # --- ÉTAPE 3 : GÉNÉRATION DU SOCLE ---
    print("\n [3/3] Generating deterministic foundation...")
    generator = MonlSecureGenerator(normalized_ast, output_dir=output_dir)
    try:
        generator.generate_all()
    except MonlError:
        raise
    except Exception as exc:
        raise CompilationGenerationError(
            f"Artifact generation failed: {exc}") from exc
    print("    └─ Infrastructure artifacts sealed.")

    has_custom = bool(normalized_ast["sandbox_ai"]["custom_functions"])

    print("\n" + "=" * 65)
    print(" 🎉 APPLICATION COMPILATION COMPLETE!")
    print(" -> Infrastructure: app.py, schema.sql validated (automatic DB initialization active)")
    if has_custom:
        print(" -> 'custom' blocks: safe empty shells in sandbox_ai.py")
        print("                     (logic to be written by hand).")
    print("=" * 65 + "\n")

    # Le contrat frontend réutilise exactement ce résultat dans la couche CLI.
    return CompilationResult(
        ir=normalized_ast,
        generator=generator,
        plans=generator.compilation_plans,
    )


def main(argv=None) -> int:
    """Point d'entrée CLI : seule cette frontière traduit les erreurs attendues."""
    parser = argparse.ArgumentParser(description="monl compiler.")
    parser.add_argument(
        "fichier", type=str, nargs="?", metavar="file",
        help="Path to the .ml file to compile (the legacy .yaml extension is still accepted).",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Directory for generated artifacts (app.py, schema.sql, "
             "sandbox_ai.py, .jwt_secret...).",
    )
    args = parser.parse_args(argv)
    fichier = args.fichier or os.path.join(
        os.path.dirname(__file__), "..", "..", "exemples", "01_portfolio.ml")
    try:
        compile_monl(fichier, output_dir=args.output)
    except MonlError as err:
        print(f"\n ❌ COMPILER FAILED: {err}")
        print("=" * 65 + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
