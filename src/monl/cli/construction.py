"""Compiler, initialiser, migrer."""

import importlib.util
import os
import re
import sys

from .. import artifacts
from ..artifacts import (
    copy_preserved_files,
    publish_files,
    sans_sandbox,
    staging_directory,
)
from ..design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    ensure_design_artifacts,
)
from ..frontend_contract import (
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    generate_frontend_contract,
)
from ..frontend_contract.project import (
    LEGACY_AGENTS_FILENAME,
    PROJECT_CLAUDE_MD_MARKER,
)
from . import container, location, nomenclature

#: What moved. Written out here in full and never derived from the current
#: constants: an "old location" describes the PAST, it cannot be deduced from
#: the present — the lesson of the inherited Dockerfiles (point 164).
_DOCUMENTS_RANGES = (
    PROMPT_FILENAME,
    "docs/FRONTEND_UPDATE_PROMPT.md",
    DESIGN_SYSTEM_FILENAME,
    DESIGN_SPEC_FILENAME,
    ASSET_MANIFEST_FILENAME,
)


def _ranger_les_documents(project_dir):
    """Tidies up a project compiled by an earlier version, only once.

    Two moves, for the same reason: leave nothing stale next to the file that
    replaces it. Writing to the new location without moving the old one would
    produce two truths, one of them false — and it is the false one an agent
    would read, since it is at the root."""
    moved = list(artifacts.move_vers_docs(project_dir, _DOCUMENTS_RANGES))
    old = os.path.join(project_dir, LEGACY_AGENTS_FILENAME)
    new = os.path.join(project_dir, nomenclature.AGENTS_FILENAME)
    # A CLAUDE.md WITHOUT our marker belongs to the user: it stays where it is,
    # intact. Renaming it would move their work under a name monl overwrites on
    # the next compilation.
    if os.path.isfile(old) and not os.path.exists(new):
        with open(old, encoding="utf-8") as fh:
            if PROJECT_CLAUDE_MD_MARKER in fh.read():
                os.replace(old, new)
                moved.append(nomenclature.AGENTS_FILENAME)
    if moved:
        print(" -> Documents moved       : " + ", ".join(moved))
    return moved


# ---------------------------------------------------------------- compile --
def compile_project(spec_path, project_dir, base_dir=None, save_state=True):
    """Full pipeline: spec → backend + frontend contract + state. Reuses
    compile_monl (main.py) for the backend and its validated result, then
    adds the contract layer without reparsing or a second audit.

    POINT 103: `base_dir` and `save_state` exist for `monl diff`, which
    compiles into a THROWAWAY folder. The declared assets live in the real
    project — looking for them in the temporary folder would make compilation
    fail for a reason that does not exist. Outside `diff`, the reference
    project defaults to the spec's folder, not the output folder: that is what
    lets `monl compile spec.ml --output build/` work with assets next to the
    spec. A dry run has no business leaving a state behind."""
    from ..main import compile_monl
    reference_dir = base_dir or os.path.dirname(os.path.abspath(spec_path))
    spec_abs = os.path.abspath(spec_path)
    proj_abs = os.path.abspath(project_dir)
    spec_rel = (os.path.relpath(spec_abs, proj_abs)
                if spec_abs.startswith(proj_abs + os.sep) else spec_abs)
    # Tidy up BEFORE copying what is preserved: a hand-edited DESIGN_SPEC.md
    # stays at the root until it is moved, and the preserved copy would look
    # for it in `docs/`, where it is not yet. Human work would then be moved
    # into oblivion and replaced by a brand-new document.
    _ranger_les_documents(proj_abs)
    with staging_directory(proj_abs) as temporary:
        # The secret, the welcome documents and the two container artifacts are
        # never regenerated from scratch in staging: they survive compilation
        # and stay protected against accidental replacement.
        copy_preserved_files(
            proj_abs, temporary,
            (".jwt_secret", nomenclature.AGENTS_FILENAME,
             nomenclature.README_FILENAME, DESIGN_SYSTEM_FILENAME,
             DESIGN_SPEC_FILENAME, ASSET_MANIFEST_FILENAME,
             *nomenclature.CONTAINER_ARTIFACTS),
        )
        compilation = compile_monl(
            spec_path, output_dir=temporary, base_dir=reference_dir)
        contract = generate_frontend_contract(
            compilation.ir, compilation.plans, temporary, spec_rel)
        direction = ensure_design_artifacts(proj_abs, temporary, contract)
        container._ensure_container_artifacts(
            temporary, uploads=bool(compilation.ir["security"].get("upload_fields")))
        container._emit_wrapper(temporary, contract)
        if save_state:
            location._save_state(temporary, spec_rel, spec_source_path=spec_abs)
        artifacts = nomenclature.PROJECT_ARTIFACTS if save_state else tuple(
            name for name in nomenclature.PROJECT_ARTIFACTS if name != nomenclature.STATE_FILENAME)
        if not compilation.ir.get("sandbox_ai", {}).get("custom_functions"):
            artifacts = sans_sandbox(artifacts)
        publish_files(temporary, proj_abs, artifacts)

    print(f" -> Frontend contract     : {CONTRACT_FILENAME} + {PROMPT_FILENAME}")
    generated_direction = [name for name, written in direction.items() if written]
    if generated_direction:
        print(" -> Visual direction      : " + ", ".join(generated_direction))
    if save_state:
        print(f" -> Project state         : {nomenclature.STATE_FILENAME}")
    return contract

# ------------------------------------------------------------------- init --
def cmd_init(project_dir=None):
    # Rule-based guided dialogue, entirely deterministic (no AI, no network
    # call). The produced spec is revalidated by the real parser before being
    # written.
    from ..dialogue_engine import DialogueError, run_interactive_dialogue
    try:
        spec_text = run_interactive_dialogue()
    except (EOFError, KeyboardInterrupt) as err:
        print("Input interrupted: nothing was written; rerun `monl init`.",
              file=sys.stderr)
        raise SystemExit(130 if isinstance(err, KeyboardInterrupt) else 2) from None
    except DialogueError as err:
        # The engine keeps its question detail for the other callers.
        message = str(err).split(" : ", 1)[0]
        print(f"{message}: nothing was written; rerun `monl init`.", file=sys.stderr)
        raise SystemExit(2) from None
    app_match = re.match(r"app\s+(\w+)", spec_text)
    app_name = app_match.group(1) if app_match else "MonProjet"
    project_dir = os.path.abspath(project_dir or app_name)
    os.makedirs(project_dir, exist_ok=True)
    spec_path = os.path.join(project_dir, "spec.ml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_text)
    print(f"\n✅ Specification written: {spec_path}")
    compile_project(spec_path, project_dir)
    print("\nNext steps:")
    print(f"  1. Give {PROMPT_FILENAME} (in {project_dir}) to a frontend AI")
    print(f"     — it should write its output to {project_dir}/frontend/")
    print("  2. monl run", project_dir)
    return project_dir

def cmd_migrate(project_dir, name=None, down=False, list_only=False):
    """Explicitly applies a migration to the already compiled backend."""
    project_dir, _spec_path = location._locate_project(project_dir, "migrate")
    app_path = os.path.join(project_dir, "app.py")
    if not os.path.exists(app_path):
        print(f" ❌ Missing artifact: {app_path} — run 'monl update'.")
        raise SystemExit(1)
    current = os.getcwd()
    module = None
    try:
        os.chdir(project_dir)
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        module_name = f"_monl_migration_app_{id(project_dir)}"
        spec = importlib.util.spec_from_file_location(module_name, app_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load app.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        if list_only:
            conn = module._connect()
            try:
                module._prepare_database(conn)
                for migration in module._MIGRATIONS:
                    state = module._migration_is_applied(conn, migration)
                    irreversible = any(not op["reversible"] for op in migration["operations"])
                    suffix = " ; irreversible down (DROP)" if irreversible else " ; down available"
                    status = "✅ applied" if state else "⏳ pending"
                    print(f"{status}  {migration['name']}{suffix}")
            finally:
                conn.close()
            return
        if not name:
            print(" ❌ Specify --name NAME, or use --list.")
            raise SystemExit(1)
        module.apply_migration(name, "down" if down else "up")
    except SystemExit:
        raise
    except Exception as error:
        print(f" ❌ Migration failed: {error}")
        raise SystemExit(1) from error
    finally:
        os.chdir(current)
        if module is not None:
            sys.modules.pop(module.__name__, None)
