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
    """Compiles a MONL specification without terminating the calling process.

    This function is the compiler's library API: it raises expected MONL
    errors, while the CLI entry points turn them into messages and exit codes.
    The pipeline stays deterministic and offline."""
    if not os.path.exists(file_path):
        raise CompilationInputError(
            f"Specification file '{file_path}' does not exist.")

    filename = os.path.basename(file_path)
    print("\n" + "=" * 65)
    print(f" ⚙️  MONL COMPILER: {filename}")
    print("=" * 65)

    # --- STEP 1: PARSING ---
    print("\n [1/3] Parsing...")
    raw_json = parse_monl_file(file_path)
    print("    └─ Base AST extracted successfully.")

    # --- STEP 2: STATIC AUDIT ---
    print("\n [2/3] Static architecture and restrictions audit...")
    # The SPEC's folder is the reference for assets: that is where the declared
    # photos, logo and favicon live.
    reference_dir = base_dir or os.path.dirname(os.path.abspath(file_path))
    ast_manager = MonlAST(raw_json, base_dir=reference_dir)
    normalized_ast = ast_manager.validate_and_audit()

    # --- STEP 3: GENERATING THE FOUNDATION ---
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

    # The frontend contract reuses exactly this result in the CLI layer.
    return CompilationResult(
        ir=normalized_ast,
        generator=generator,
        plans=generator.compilation_plans,
    )


def main(argv=None) -> int:
    """CLI entry point: only this boundary translates the expected errors."""
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
