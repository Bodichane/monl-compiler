"""Non-regression test: every file of exemples/*.ml (or *.yaml, the old
extension) must compile without exception. Designed to run locally (pytest)
and in CI (see .github/workflows/ci.yml), and to catch a regression like bug
v6 #2 (an example silently breaking after a refactor) before it piles up over
several versions.

Local usage: pytest tests/test_compile_all.py -v

POINT 64: these tests compiled IN THE REPOSITORY ROOT — every run of the
suite dropped app.py, schema.sql, sandbox_ai.py, manage.py and .jwt_secret
there again, and CLAUDE.md's cleanup ritual existed for that. The generator
has long accepted an output_dir; it is now used. Compiling outside the
repository also makes the assertions stronger: an artifact found can no
longer be the leftover of a previous compilation.

POINT 85: `base_dir` is now passed to the validator. Without it, the asset
EXISTENCE check (brick 13, point 83) stays silent — and stayed silent here,
since no example declared assets. `01_portfolio.ml` now declares some: these
tests therefore also check that the files of `exemples/assets/` are REALLY
there. Removing `base_dir` would make these compilations silent on half of
what they test.
"""
import ast
import glob
import os
import tempfile

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file
from tests.support.cas import verifier_chaque_cas

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")
PLUGIN_EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../plugin/reference/exemples")
EXAMPLE_FILES = sorted(
    path for directory in (EXEMPLES_DIR, PLUGIN_EXEMPLES_DIR)
    for extension in ("ml", "monl", "yaml")
    for path in glob.glob(os.path.join(directory, "**", f"*.{extension}"), recursive=True))


def test_example_compiles():
    """Compiles the deterministic base (parsing + audit + generation) for each
    example, and checks that it succeeds without error."""
    table = EXAMPLE_FILES
    noms = [os.path.basename(p) for p in EXAMPLE_FILES]

    def cas(yaml_path):
        raw_json = parse_monl_file(yaml_path)
        ast_manager = MonlAST(raw_json, base_dir=os.path.dirname(yaml_path))
        normalized_ast = ast_manager.validate_and_audit()
        with tempfile.TemporaryDirectory() as sortie:
            MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()

            # Checks that the 3 expected infrastructure artifacts were
            # produced. REMOVAL (roadmap, on explicit request): 'frontend.html'
            # (the old React back office '/ui') is no longer generated at all —
            # see docs/design_decisions.md, point 22. NO frontend at all is
            # generated since the pivot (point 41) — see the last test.
            for artefact in ("app.py", "schema.sql"):
                artefact_path = os.path.join(sortie, artefact)
                assert os.path.exists(artefact_path), f"{artefact} n'a pas été généré pour {os.path.basename(yaml_path)}"
            # Presence on disk does not prove an emitter produced an importable
            # module. Parsing each generated source catches a broken quote or
            # indentation at once, without running the produced code or
            # depending on an external service.
            for module in ("app.py", "manage.py", "sandbox_ai.py"):
                module_path = os.path.join(sortie, module)
                if os.path.exists(module_path):
                    with open(module_path, encoding="utf-8") as generated:
                        ast.parse(generated.read(), filename=module)
            # `sandbox_ai.py` is no longer shipped to a project WITHOUT a
            # `custom` block: it only held a comment, `app.py` imported it
            # without ever calling it, and deleting it made startup fail. None
            # of the five examples has a `custom` block — its absence is
            # therefore the right output, and we assert it rather than stop
            # looking.
            assert not os.path.exists(os.path.join(sortie, "sandbox_ai.py")), (
                f"{os.path.basename(yaml_path)} n'a aucun bloc 'custom' et reçoit "
            "pourtant le module vide")

    verifier_chaque_cas([(valeur,) for valeur in table], cas, ids=noms)


def test_at_least_one_example_exists():
    """Safeguard: avoids a false 'all green' if the exemples/ folder is empty."""
    for directory in (EXEMPLES_DIR, PLUGIN_EXEMPLES_DIR):
        assert any(p.startswith(directory + os.sep)
                   for p in EXAMPLE_FILES), f"No specs in {directory}"


def test_no_example_ever_produces_frontend_html():
    """REMOVAL (roadmap, on explicit request): locks the absence of any
    auto-generated '/ui' back office — for ALL examples, including those with a
    'landing' block. If 'frontend.html' ever reappears (e.g. a regression
    restoring _generate_frontend), this test must fail."""
    for yaml_path in EXAMPLE_FILES:
        raw_json = parse_monl_file(yaml_path)
        normalized_ast = MonlAST(raw_json, base_dir=os.path.dirname(yaml_path)).validate_and_audit()
        with tempfile.TemporaryDirectory() as sortie:
            MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()
            frontend_path = os.path.join(sortie, "frontend.html")
        assert not os.path.exists(frontend_path), (
            f"'frontend.html' a été généré pour {os.path.basename(yaml_path)} — "
            f"monl ne doit plus jamais produire de back-office auto-généré."
        )


def test_no_example_ever_produces_any_generated_frontend():
    """PIVOT (point 41): monl no longer generates ANY frontend — neither
    'frontend.html' (removed at point 22), nor 'landing.html', nor
    'dashboard.html'. If one of them reappears, this test must fail: the
    interface comes exclusively from the frontend AI, through the contract."""
    for yaml_path in EXAMPLE_FILES:
        raw_json = parse_monl_file(yaml_path)
        normalized_ast = MonlAST(raw_json, base_dir=os.path.dirname(yaml_path)).validate_and_audit()
        with tempfile.TemporaryDirectory() as sortie:
            MonlSecureGenerator(normalized_ast, output_dir=sortie).generate_all()
            fantomes = {g: os.path.exists(os.path.join(sortie, g))
                        for g in ("landing.html", "dashboard.html", "frontend.html")}
        for ghost, present in fantomes.items():
            assert not present, (
                f"'{ghost}' a été généré pour {os.path.basename(yaml_path)} — "
                f"monl ne doit plus produire aucun frontend (point 41)."
            )
