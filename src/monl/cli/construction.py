"""Compiler, initialiser, migrer."""

import importlib.util
import os
import re
import sys

from ..artifacts import copy_preserved_files, publish_files, sans_sandbox, staging_directory
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
from . import conteneur, emplacement, nomenclature


# ---------------------------------------------------------------- compile --
def compile_project(spec_path, project_dir, base_dir=None, save_state=True):
    """Pipeline complet : spec → backend + contrat frontend + état.
    Réutilise compile_monl (main.py) pour le backend et son résultat validé,
    puis ajoute la couche contrat sans reparsing ni second audit.

    POINT 103 : `base_dir` et `save_state` existent pour `monl diff`, qui
    compile dans un dossier JETABLE. Les assets déclarés vivent, eux, dans le
    vrai projet — les chercher dans le dossier temporaire ferait échouer la
    compilation pour une raison qui n'existe pas. Hors `diff`, le projet de
    référence est par défaut le dossier de la spec, pas le dossier de sortie :
    c'est ce qui permet à `monl compile spec.ml --output build/` de fonctionner
    avec des assets voisins de la spec. Un dry-run, lui, n'a pas à déposer
    d'état."""
    from ..main import compile_monl
    reference_dir = base_dir or os.path.dirname(os.path.abspath(spec_path))
    spec_abs = os.path.abspath(spec_path)
    proj_abs = os.path.abspath(project_dir)
    spec_rel = (os.path.relpath(spec_abs, proj_abs)
                if spec_abs.startswith(proj_abs + os.sep) else spec_abs)
    with staging_directory(proj_abs) as temporary:
        # Le secret, CLAUDE.md et les deux artefacts de conteneur ne sont
        # jamais régénérés depuis zéro dans le staging : ils survivent à la
        # compilation et restent protégés contre un remplacement accidentel.
        copy_preserved_files(
            proj_abs, temporary,
            (".jwt_secret", "CLAUDE.md", DESIGN_SYSTEM_FILENAME,
             DESIGN_SPEC_FILENAME, ASSET_MANIFEST_FILENAME, *nomenclature.CONTAINER_ARTEFACTS),
        )
        compilation = compile_monl(
            spec_path, output_dir=temporary, base_dir=reference_dir)
        contract = generate_frontend_contract(
            compilation.ir, compilation.plans, temporary)
        direction = ensure_design_artifacts(proj_abs, temporary, contract)
        conteneur._ensure_container_artifacts(
            temporary, uploads=bool(compilation.ir["security"].get("upload_fields")))
        conteneur._emettre_wrapper(temporary, contract)
        if save_state:
            emplacement._save_state(temporary, spec_rel, spec_source_path=spec_abs)
        artefacts = nomenclature.PROJECT_ARTEFACTS if save_state else tuple(
            name for name in nomenclature.PROJECT_ARTEFACTS if name != nomenclature.STATE_FILENAME)
        if not compilation.ir.get("sandbox_ai", {}).get("custom_functions"):
            artefacts = sans_sandbox(artefacts)
        publish_files(temporary, proj_abs, artefacts)

    print(f" -> Contrat frontend      : {CONTRACT_FILENAME} + {PROMPT_FILENAME}")
    generated_direction = [name for name, written in direction.items() if written]
    if generated_direction:
        print(" -> Direction visuelle    : " + ", ".join(generated_direction))
    if save_state:
        print(f" -> État du projet        : {nomenclature.STATE_FILENAME}")
    return contract

# ------------------------------------------------------------------- init --
def cmd_init(project_dir=None):
    # Dialogue guidé à règles, entièrement déterministe (aucune IA, aucun
    # appel réseau). La spec produite est revalidée par le vrai parseur avant
    # d'être écrite.
    from ..dialogue_engine import run_interactive_dialogue
    spec_text = run_interactive_dialogue()
    app_match = re.match(r"app\s+(\w+)", spec_text)
    app_name = app_match.group(1) if app_match else "MonProjet"
    project_dir = os.path.abspath(project_dir or app_name)
    os.makedirs(project_dir, exist_ok=True)
    spec_path = os.path.join(project_dir, "spec.ml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_text)
    print(f"\n✅ Spécification écrite : {spec_path}")
    compile_project(spec_path, project_dir)
    print("\nProchaines étapes :")
    print(f"  1. Donner {PROMPT_FILENAME} (dans {project_dir}) à une IA frontend")
    print(f"     — elle doit écrire son résultat dans {project_dir}/frontend/")
    print("  2. monl run", project_dir)
    return project_dir

def cmd_migrate(project_dir, name=None, down=False, list_only=False):
    """Applique explicitement une migration du backend déjà compilé."""
    project_dir, _spec_path = emplacement._situer_projet(project_dir, "migrer")
    app_path = os.path.join(project_dir, "app.py")
    if not os.path.exists(app_path):
        print(f" ❌ Artefact manquant : {app_path} — lancer 'monl update'.")
        raise SystemExit(1)
    courant = os.getcwd()
    module = None
    try:
        os.chdir(project_dir)
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        module_name = f"_monl_migration_app_{id(project_dir)}"
        spec = importlib.util.spec_from_file_location(module_name, app_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("impossible de charger app.py")
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
                    suffix = " ; down irréversible (DROP)" if irreversible else " ; down disponible"
                    status = "✅ appliquée" if state else "⏳ en attente"
                    print(f"{status}  {migration['name']}{suffix}")
            finally:
                conn.close()
            return
        if not name:
            print(" ❌ Indiquer --name NOM, ou utiliser --list.")
            raise SystemExit(1)
        module.apply_migration(name, "down" if down else "up")
    except SystemExit:
        raise
    except Exception as error:
        print(f" ❌ Migration échouée : {error}")
        raise SystemExit(1) from error
    finally:
        os.chdir(courant)
        if module is not None:
            sys.modules.pop(module.__name__, None)
