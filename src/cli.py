# ─────────────────────────────────────────────────────────────────────
# CLI ORCHESTRATEUR — pivot "monl orchestrateur" (brique 3).
#
# monl ne cherche plus à tout générer : il coordonne. Le CLI matérialise
# le cycle de vie complet d'un projet :
#
#   monl                  → dialogue guidé (sans IA) → spec.ml → backend
#                              + contrat frontend (à donner à une IA UI)
#   monl compile spec.ml  → recompilation directe d'une spec existante
#   monl run [DIR]        → vérifie la COHÉRENCE (spec/artefacts/contrat/
#                              frontend) puis lance l'application
#   monl update [DIR]     → recompile après évolution de la spec, régénère
#                              le contrat, et rapporte le DELTA (routes et
#                              champs ajoutés/retirés) à transmettre à l'IA
#                              frontend — la base de données est préservée
#                              (migrations additives au démarrage, point 32).
#
# L'état du projet vit dans monl.json (dossier du projet) : chemin de la
# spec, empreinte SHA-256 de la spec compilée et du contrat. C'est ce qui
# permet à 'run' de détecter une spec modifiée mais non recompilée, et à
# 'update' de mesurer le delta.
# ─────────────────────────────────────────────────────────────────────
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ast_validator import MonlAST
from frontend_contract import (
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    contract_sha256,
    generate_frontend_contract,
)
from generator import MonlSecureGenerator
from parser import parse_monl_file

STATE_FILENAME = "monl.json"


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_state(project_dir):
    path = os.path.join(project_dir, STATE_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# Ce que la spec produit et que personne ne doit retoucher à la main
# (manage.py et sandbox_ai.py compris : ils portent des droits).
SCELLE_ARTEFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py")


def _save_state(project_dir, spec_relpath):
    state = {
        "spec": spec_relpath,
        "spec_sha256": _sha256_file(os.path.join(project_dir, spec_relpath)),
        "contract_sha256": contract_sha256(project_dir),
        # POINT 64 : empreinte du backend généré. « app.py reste scellé » était
        # une promesse que RIEN ne mesurait : la cohérence ne vérifiait que
        # l'existence de ces fichiers, et une retouche à la main passait sans
        # bruit — alors que 'monl run' annonce « spec ↔ backend ↔ contrat ↔
        # frontend » vérifiés. Découvert en écrivant le premier test du
        # parcours de commandes, pas en relisant le code.
        "backend_sha256": {
            nom: _sha256_file(os.path.join(project_dir, nom))
            for nom in SCELLE_ARTEFACTS
            if os.path.exists(os.path.join(project_dir, nom))
        },
    }
    with open(os.path.join(project_dir, STATE_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return state


# ---------------------------------------------------------------- compile --
def compile_project(spec_path, project_dir):
    """Pipeline complet : spec → backend + contrat frontend + état.
    Réutilise compile_monl (main.py) pour le backend — même pipeline,
    mêmes échappatoires IA non bloquantes — puis ajoute la couche contrat."""
    from main import compile_monl
    compile_monl(spec_path, output_dir=project_dir)

    raw = parse_monl_file(spec_path)
    normalized = MonlAST(raw).validate_and_audit()
    generator = MonlSecureGenerator(normalized, output_dir=project_dir)
    contract = generate_frontend_contract(normalized, generator, project_dir)

    spec_abs = os.path.abspath(spec_path)
    proj_abs = os.path.abspath(project_dir)
    spec_rel = (os.path.relpath(spec_abs, proj_abs)
                if spec_abs.startswith(proj_abs + os.sep) else spec_abs)
    _save_state(proj_abs, spec_rel)
    print(f" -> Contrat frontend      : {CONTRACT_FILENAME} + {PROMPT_FILENAME}")
    print(f" -> État du projet        : {STATE_FILENAME}")
    return contract


# ------------------------------------------------------------------- init --
def cmd_init(project_dir=None):
    # Dialogue guidé à règles, entièrement déterministe (aucune IA, aucun
    # appel réseau). La spec produite est revalidée par le vrai parseur avant
    # d'être écrite.
    from dialogue_engine import run_interactive_dialogue
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


# ------------------------------------------------------------ cohérence ----
def check_coherence(project_dir):
    """Vérifie que spec, backend, contrat et frontend forment un ensemble
    cohérent. Retourne (ok, erreurs, avertissements)."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)

    state = _load_state(project_dir)
    if state is None:
        errors.append(f"{STATE_FILENAME} introuvable — ce dossier n'est pas un projet "
                      "monl compilé (lancer 'monl' ou 'monl compile').")
        return False, errors, warnings

    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    if not os.path.exists(spec_path):
        errors.append(f"Spec introuvable : {spec_path}")
        return False, errors, warnings

    if _sha256_file(spec_path) != state["spec_sha256"]:
        errors.append("La spec a été modifiée depuis la dernière compilation — "
                      "lancer 'monl update' pour resynchroniser backend et contrat.")

    for artefact in ("app.py", "schema.sql", CONTRACT_FILENAME):
        if not os.path.exists(os.path.join(project_dir, artefact)):
            errors.append(f"Artefact manquant : {artefact}")
    if errors:
        return False, errors, warnings

    # Le backend est scellé (point 64) : il se régénère depuis la spec, il ne
    # se retouche pas. Un état antérieur à cette empreinte n'est pas une
    # erreur — il est simplement muet, et le dire vaut mieux que laisser
    # croire à une vérification qui n'a pas eu lieu.
    empreintes = state.get("backend_sha256")
    if not empreintes:
        warnings.append("État antérieur au scellé du backend : recompiler "
                        "('monl update') pour que app.py et schema.sql soient "
                        "réellement vérifiés.")
    else:
        for nom, attendu in sorted(empreintes.items()):
            chemin = os.path.join(project_dir, nom)
            if os.path.exists(chemin) and _sha256_file(chemin) != attendu:
                errors.append(
                    f"{nom} a été modifié à la main — le backend est généré "
                    "depuis la spec. Modifier la spec puis 'monl update' ; "
                    "toute retouche directe sera écrasée.")
        if errors:
            return False, errors, warnings

    if contract_sha256(project_dir) != state["contract_sha256"]:
        errors.append(f"{CONTRACT_FILENAME} a été modifié à la main — le contrat est "
                      "dérivé de la spec, il ne se modifie que via 'monl update'.")
        return False, errors, warnings

    # Frontend (optionnel) : vérification best-effort que les chemins d'API
    # référencés existent dans le contrat. On ne bloque pas (un chemin peut
    # être construit dynamiquement) : on AVERTIT, nominalement.
    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        if not os.path.exists(os.path.join(frontend_dir, "index.html")):
            errors.append("frontend/ existe mais frontend/index.html est absent "
                          "(point d'entrée exigé par le contrat).")
            return False, errors, warnings
        with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
            contract = json.load(fh)
        known_prefixes = {r["path"].split("/")[1] for r in contract["routes"]}
        known_prefixes |= {"register", "login", "logout", "docs", "app", "site", "workflow"}
        referenced = set()
        for root, _dirs, files in os.walk(frontend_dir):
            for name in files:
                if not name.endswith((".html", ".js")):
                    continue
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                    # Le littéral ENTIER est examiné, pas seulement son début
                    # (point 57) : `'/edit">Modifier</a>'` est la fin d'une
                    # route de navigation `#/article/<id>/edit` coupée par une
                    # concaténation — du balisage, jamais une URL d'API. Toute
                    # application monopage en produisait, et l'avertissement
                    # criait au loup à chaque fois. Un chemin qui contient de
                    # l'espace ou un chevron n'est pas un chemin.
                    for match in re.finditer(r"""(['"`])(/[^'"`\n]*)\1""", fh.read()):
                        chemin = match.group(2)
                        if any(c in chemin for c in "<> "):
                            continue
                        segment = re.match(r"/([a-z_]+)(?:[/?#]|$)", chemin)
                        if segment:
                            referenced.add(segment.group(1))
        unknown = sorted(referenced - known_prefixes)
        if unknown:
            warnings.append("Le frontend référence des chemins absents du contrat : "
                            + ", ".join(f"/{u}" for u in unknown))
    else:
        warnings.append("Aucun dossier frontend/ — l'app sera servie avec ses seules "
                        "pages générées (landing, /app, /docs).")

    return True, errors, warnings


SERVE_WRAPPER = '''"""Wrapper généré par 'monl run' — ne pas éditer.
Monte le frontend produit par l'IA (frontend/) sur /site, sans modifier
app.py (le backend reste un artefact scellé du compilateur)."""
from fastapi.staticfiles import StaticFiles
from app import app

app.mount("/site", StaticFiles(directory="frontend", html=True), name="site")
'''


def cmd_run(project_dir, check_only=False, port=8000, skip_smoke=False):
    ok, errors, warnings = check_coherence(project_dir)
    for w in warnings:
        print(f" ⚠️  {w}")
    if not ok:
        for e in errors:
            print(f" ❌ {e}")
        sys.exit(1)
    print(" ✅ Cohérence statique vérifiée (spec ↔ backend ↔ contrat ↔ frontend).")

    # Point 1 du pivot : la cohérence statique ne garantit pas que ça
    # FONCTIONNE. Smoke test comportemental sur serveur éphémère (base
    # neuve, données réelles intouchées) : routes du contrat éprouvées en
    # HTTP réel, frontend exécuté dans jsdom si Node est disponible.
    if not skip_smoke:
        from smoke_test import run_smoke_test
        print(" -> Smoke test comportemental (serveur éphémère, base neuve)…")
        smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir)
        for w in smoke_warnings:
            print(f" ⚠️  {w}")
        if not smoke_ok:
            for e in smoke_errors:
                print(f" ❌ {e}")
            print(" ❌ Smoke test échoué — l'application ne sera pas lancée "
                  "(contourner en connaissance de cause : --skip-smoke).")
            sys.exit(1)
        print(" ✅ Smoke test réussi : l'API répond conformément au contrat"
              + (" et le frontend s'exécute sans erreur." if os.path.isdir(
                  os.path.join(os.path.abspath(project_dir), "frontend")) else "."))
    if check_only:
        return

    project_dir = os.path.abspath(project_dir)
    has_frontend = os.path.isdir(os.path.join(project_dir, "frontend"))
    module = "app:app"
    if has_frontend:
        with open(os.path.join(project_dir, "serve.py"), "w", encoding="utf-8") as fh:
            fh.write(SERVE_WRAPPER)
        module = "serve:app"
        print(f" -> Frontend monté sur http://127.0.0.1:{port}/site")
    print(f" -> Lancement : uvicorn {module} (port {port})")
    subprocess.run([sys.executable, "-m", "uvicorn", module,
                    "--host", "127.0.0.1", "--port", str(port)], cwd=project_dir)


# ----------------------------------------------------------------- update --
UPDATE_PROMPT_FILENAME = "FRONTEND_UPDATE_PROMPT.md"


def _write_update_brief(project_dir, added_routes, removed_routes,
                        added_fields, removed_fields):
    """Point 3 du pivot : le delta n'est pas qu'informatif, il devient une
    CONSIGNE prête à donner à l'IA frontend — la boucle se ferme sans que
    l'humain ait à reformuler le changement."""
    def bullet(items, verb):
        return "\n".join(f"- {verb} `{i}`" for i in sorted(items))
    sections = []
    if added_routes:
        sections.append("## Nouvelles routes à exploiter\n"
                        + bullet(added_routes, "brancher"))
    if removed_routes:
        sections.append("## Routes SUPPRIMÉES — retirer tout appel\n"
                        + bullet(removed_routes, "ne plus appeler"))
    if added_fields:
        sections.append("## Nouveaux champs à afficher/saisir\n"
                        + bullet(added_fields, "intégrer"))
    if removed_fields:
        sections.append("## Champs SUPPRIMÉS — retirer des vues et formulaires\n"
                        + bullet(removed_fields, "retirer"))
    body = f"""# Mise à jour du frontend (delta généré par 'monl update')

Le backend a évolué. Modifiez le frontend existant dans `frontend/` pour
refléter UNIQUEMENT les changements ci-dessous — ne réécrivez pas ce qui
fonctionne déjà. Le contrat complet à jour est dans `frontend_contract.json`
(les règles de `FRONTEND_PROMPT.md` restent en vigueur).

{chr(10).join(sections)}

Après modification, `monl run` revalidera l'ensemble (cohérence statique
+ smoke test comportemental) avant tout lancement.

Si vous lisez ceci dans une conversation (sans clé API) : rendez le
frontend mis à jour en ZIP téléchargeable ou en `index.html` autonome —
l'utilisateur l'installera avec `monl import <fichier> <projet>`.
"""
    path = os.path.join(project_dir, UPDATE_PROMPT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def _contract_signature(contract):
    routes = {f"{r['method']} {r['path']}" for r in contract["routes"]}
    fields = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
              for f in spec["fields"]}
    return routes, fields


def cmd_update(project_dir):
    project_dir = os.path.abspath(project_dir)
    state = _load_state(project_dir)
    if state is None:
        print(f" ❌ {STATE_FILENAME} introuvable — rien à mettre à jour ici.")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])

    old_routes, old_fields = set(), set()
    contract_path = os.path.join(project_dir, CONTRACT_FILENAME)
    if os.path.exists(contract_path):
        with open(contract_path, encoding="utf-8") as fh:
            old_routes, old_fields = _contract_signature(json.load(fh))

    new_contract = compile_project(spec_path, project_dir)
    new_routes, new_fields = _contract_signature(new_contract)

    added_routes, removed_routes = new_routes - old_routes, old_routes - new_routes
    added_fields, removed_fields = new_fields - old_fields, old_fields - new_fields
    changes = any((added_routes, removed_routes, added_fields, removed_fields))

    print("\n─── Delta du contrat frontend ───")
    for item in sorted(added_routes):
        print(f"  + route ajoutée : {item}")
    for item in sorted(removed_routes):
        print(f"  - route retirée : {item}")
    for item in sorted(added_fields):
        print(f"  + champ ajouté : {item}")
    for item in sorted(removed_fields):
        print(f"  - champ retiré : {item}")
    if not changes:
        print("  (aucun changement d'interface — le frontend existant reste valide)")
    else:
        brief_path = _write_update_brief(project_dir, added_routes, removed_routes,
                                         added_fields, removed_fields)
        print(f"  → Consigne prête pour l'IA frontend : {os.path.basename(brief_path)}")
    print("──────────────────────────────────────────────────────────────────")
    print("La base de données existante est préservée : les nouvelles colonnes "
          "sont ajoutées par migration additive au démarrage (docs/MIGRATIONS.md).")


# ------------------------------------------------------------------- main --
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="monl",
        description="monl — plateforme d'orchestration : dialogue guidé → "
                    "DSL → backend + contrat frontend → IA UI → run/update.")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Dialogue guidé (défaut sans sous-commande).")
    p_init.add_argument("--dir", default=None, help="Dossier du projet (défaut : ./NomApp)")

    p_compile = sub.add_parser("compile", help="Compiler une spec .ml existante.")
    p_compile.add_argument("spec")
    p_compile.add_argument("--output", default=None,
                           help="Dossier du projet (défaut : dossier de la spec).")

    p_run = sub.add_parser("run", help="Vérifier la cohérence puis lancer l'application.")
    p_run.add_argument("dir", nargs="?", default=".")
    p_run.add_argument("--check", action="store_true", help="Vérifier sans lancer.")
    p_run.add_argument("--skip-smoke", action="store_true",
                       help="Sauter le smoke test comportemental (déconseillé).")
    p_run.add_argument("--port", type=int, default=8000)

    p_update = sub.add_parser("update", help="Recompiler après évolution de la spec.")
    p_update.add_argument("dir", nargs="?", default=".")

    p_front = sub.add_parser(
        "frontend", help="Générer le frontend par une IA spécialisée, avec "
                         "re-vérification automatique (cohérence + smoke test).")
    p_front.add_argument("dir", nargs="?", default=".")
    p_front.add_argument("--provider", default="claude",
                         choices=["claude", "claude-code"],
                         help="'claude' : API Anthropic (clé dans ANTHROPIC_API_KEY). "
                              "'claude-code' : l'agent Claude Code travaille directement "
                              "dans le dossier (authentification par abonnement, "
                              "'claude login' — aucune clé requise).")
    p_front.add_argument("--model", default=None, help="Modèle du fournisseur.")
    p_front.add_argument("--max-turns", type=int, default=None,
                         help="Budget de tours de l'agent ('claude-code' "
                              "uniquement). Défaut : 120.")
    p_front.add_argument("--update", action="store_true",
                         help="Faire évoluer le frontend existant à partir de "
                              "FRONTEND_UPDATE_PROMPT.md au lieu de repartir de zéro.")

    p_import = sub.add_parser(
        "import", help="Installer un frontend obtenu SANS clé API (brief collé "
                       "dans claude.ai, résultat téléchargé) puis re-vérifier.")
    p_import.add_argument("source", help="Fichier .zip, index.html, dossier, ou "
                                         "JSON {'files': ...} téléchargé depuis Claude.")
    p_import.add_argument("dir", nargs="?", default=".", help="Dossier du projet.")

    args = parser.parse_args(argv)

    if args.command in (None, "init"):
        cmd_init(getattr(args, "dir", None))
    elif args.command == "compile":
        project_dir = args.output or os.path.dirname(os.path.abspath(args.spec))
        compile_project(args.spec, project_dir)
    elif args.command == "run":
        cmd_run(args.dir, check_only=args.check, port=args.port, skip_smoke=args.skip_smoke)
    elif args.command == "update":
        cmd_update(args.dir)
    elif args.command == "frontend":
        from frontend_ai import (
            DEFAULT_MAX_TURNS,
            DEFAULT_MODEL,
            PROVIDERS,
            FrontendAIError,
            generate_and_verify,
            generate_with_claude_code,
        )
        try:
            if args.provider == "claude-code":
                ok, _errors = generate_with_claude_code(
                    args.dir, update_mode=args.update,
                    max_turns=args.max_turns or DEFAULT_MAX_TURNS)
            else:
                provider = PROVIDERS[args.provider](model=args.model or DEFAULT_MODEL)
                ok, _errors = generate_and_verify(args.dir, provider, update_mode=args.update)
        except FrontendAIError as e:
            print(f" ❌ {e}")
            sys.exit(1)
        if not ok:
            sys.exit(1)
    elif args.command == "import":
        from frontend_ai import FrontendAIError, import_and_verify
        try:
            ok, _errors = import_and_verify(args.dir, args.source)
        except FrontendAIError as e:
            print(f" ❌ {e}")
            sys.exit(1)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
