"""L'aiguillage des sous-commandes."""

import argparse
import os
import sys

from ..errors import MonlError
from . import consommation, construction, contenu_editorial, delta, lancement, retouche


# ------------------------------------------------------------------- main --
def _dispatch(argv=None):
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

    p_diff = sub.add_parser(
        "diff",
        help="Voir le delta du contrat SANS rien recompiler ni écrire.")
    p_diff.add_argument("dir", nargs="?", default=".")

    p_usage = sub.add_parser(
        "usage", help="Mesurer la consommation IA et le coût déclaré du projet.")
    p_usage.add_argument("dir", nargs="?", default=".",
                         help="Dossier du projet (premier argument; défaut : .).")
    p_usage.add_argument(
        "--prices", default=None, metavar="FICHIER_JSON",
        help="Table JSON fournisseur → modèle → tarifs par million de jetons; "
             "prioritaire sur MONL_USAGE_PRICES. Format: "
             "{currency, prices: {fournisseur: {modèle: "
             "{input_per_million_tokens, output_per_million_tokens}}}}.")
    p_usage.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Émettre le rapport JSON, pour quota et facturation.")

    p_migrate = sub.add_parser(
        "migrate", help="Appliquer ou défaire une migration de schéma nommée.")
    p_migrate.add_argument("dir", nargs="?", default=".")
    p_migrate.add_argument("--name", default=None, metavar="NOM",
                           help="Nom déclaré par un bloc 'migration'.")
    p_migrate.add_argument("--down", action="store_true",
                           help="Défaire la migration quand l'opération est réversible.")
    p_migrate.add_argument("--list", action="store_true",
                           help="Afficher l'état des migrations sans en appliquer.")

    p_front = sub.add_parser(
        "frontend", help="Générer le frontend par une IA spécialisée, avec "
                         "re-vérification automatique (cohérence + smoke test).")
    p_front.add_argument("dir", nargs="?", default=".")
    from ..frontend_ai import CLI_AGENTS, GENERIC_PROVIDER, OPENAI_COMPATIBLE
    from ..image_ai import IMAGE_PROVIDERS
    _voies = sorted({"claude", GENERIC_PROVIDER} | set(OPENAI_COMPATIBLE) | set(CLI_AGENTS))
    p_front.add_argument("--provider", default="claude", choices=_voies,
                         help="Clé API : 'claude' (ANTHROPIC_API_KEY) ; "
                              + ", ".join(f"'{n}' ({v})" for n, (_u, v) in
                                          sorted(OPENAI_COMPATIBLE.items()))
                              + f" ; '{GENERIC_PROVIDER}' pour tout autre point de "
                                "terminaison au dialecte OpenAI (MONL_AI_BASE_URL + "
                                "MONL_AI_API_KEY). Hors 'claude', '--model' est exigé. "
                                "Agent en ligne de commande, sans clé : "
                              + ", ".join(f"'{n}'" for n in sorted(CLI_AGENTS))
                              + " — l'agent travaille dans le dossier du projet.")
    p_front.add_argument("--model", default=None, help="Modèle du fournisseur.")
    p_front.add_argument(
        "--model-for", dest="model_for", action="append", default=None,
        metavar="CIBLE=MODELE",
        help="Routage répétable de la génération découpée (ex. "
             "styles.css=yandexgpt-lite). Cibles exactes : index.html, styles.css, "
             "app.js et SVG planifiés. Une voie monolithique ou agent ne comporte "
             "qu'un appel et signalera que ce routage n'est pas appliqué.")
    p_front.add_argument("--agent-command", default=None,
                         help="Gabarit de commande pour un agent absent de la "
                              "liste, {instruction} étant substitué — par exemple "
                              "\"mon-agent --auto {instruction}\". L'emporte sur "
                              "--provider et permet aussi de corriger un préréglage.")
    p_front.add_argument("--max-turns", type=int, default=None,
                         help="Budget de tours de l'agent ('claude-code' "
                              "uniquement). Défaut : 120.")
    p_front.add_argument("--update", action="store_true",
                         help="Faire évoluer le frontend existant à partir de "
                              "FRONTEND_UPDATE_PROMPT.md au lieu de repartir de zéro.")
    p_front.add_argument(
        "--generate-images", action="store_true",
        help="Générer explicitement les images matricielles planifiées dans le "
             "dossier d'assets (défaut : aucune image).")
    p_front.add_argument(
        "--image-provider", choices=sorted(IMAGE_PROVIDERS), default="yandexart",
        help="Fournisseur d'images utilisé avec --generate-images (défaut : yandexart).")

    # POINT 93 : corriger un défaut CONSTATÉ sur le site, sans le reconstruire.
    # Les options sont rigoureusement celles de 'frontend' — c'est la même voie
    # vers l'IA, avec les mêmes garde-fous ; seule l'origine du brief change.
    p_ret = sub.add_parser(
        "retouche", help="Corriger un défaut constaté sur le site (mise en page, "
                         "cadrage, lisibilité) sans reconstruire le frontend.")
    p_ret.add_argument("demande", help="Ce qui cloche, en une phrase — nommer "
                                       "l'écran et l'élément : \"les images de la "
                                       "section Tendances sont mal cadrées\".")
    p_ret.add_argument("dir", nargs="?", default=".")
    p_ret.add_argument("--provider", default="claude", choices=_voies,
                       help="Mêmes voies que 'monl frontend'.")
    p_ret.add_argument("--model", default=None, help="Modèle du fournisseur.")
    p_ret.add_argument("--agent-command", default=None,
                       help="Gabarit de commande pour un agent absent de la liste, "
                            "{instruction} étant substitué.")
    p_ret.add_argument("--max-turns", type=int, default=None,
                       help="Budget de tours de l'agent. Défaut : 120.")
    p_ret.add_argument("--consigne-seule", action="store_true",
                       help="Écrire FRONTEND_RETOUCHE_PROMPT.md et s'arrêter là — "
                            "pour le donner soi-même à une IA, puis 'monl import'.")

    # BRIQUE 13, COUCHE 2 (point 84) : poser un fichier de l'humain et le
    # DÉCLARER, en une commande. L'outil écrit, le compilateur prouve : la spec
    # obtenue est revalidée avant d'être écrite, donc la couche 2 ne peut pas
    # produire ce que la couche 1 refuse.
    p_assets = sub.add_parser(
        "assets", help="Installer les fichiers fournis par l'humain (photos, "
                       "logo, favicon) et les déclarer dans la spec.")
    sub_assets = p_assets.add_subparsers(dest="assets_command")

    p_add = sub_assets.add_parser(
        "add", help="Copier un fichier dans le dossier d'assets et l'écrire dans la spec.")
    p_add.add_argument("fichier", help="Le fichier à installer (photo, logo…).")
    p_add.add_argument("--for", dest="pour", default=None, metavar="VALEUR",
                       help="Fiche de seed visée, désignée par une de ses valeurs "
                            "— par exemple --for \"Halo RS\".")
    p_add.add_argument("--logo", action="store_true",
                       help="Déclarer ce fichier comme logo du projet (assets.logo).")
    p_add.add_argument("--favicon", action="store_true",
                       help="Déclarer ce fichier comme favicon (assets.favicon).")
    p_add.add_argument("--entity", default=None,
                       help="Lever une ambiguïté quand la valeur de --for existe "
                            "dans plusieurs entités.")
    p_add.add_argument("--field", default=None,
                       help="Champ 'Image' visé, si l'entité en a plusieurs.")
    p_add.add_argument("--as", dest="nom", default=None, metavar="NOM",
                       help="Nom du fichier de destination (défaut : le slug de --for "
                            "plus l'extension d'origine).")
    p_add.add_argument("--force", action="store_true",
                       help="Écraser un fichier de même nom au contenu différent.")
    p_add.add_argument("--dir", default=".", help="Dossier du projet (défaut : .).")

    p_alist = sub_assets.add_parser(
        "list", help="Ce que la spec déclare, ce qui est présent, ce qui traîne.")
    p_alist.add_argument("dir", nargs="?", default=".")

    p_content = sub.add_parser(
        "content", help="Exporter ou réimporter les fiches de démonstration en CSV.")
    sub_content = p_content.add_subparsers(dest="content_command")
    p_cexport = sub_content.add_parser(
        "export", help="Créer content/<Entite>.csv depuis les blocs seed.")
    p_cexport.add_argument("dir", nargs="?", default=".")
    p_cimport = sub_content.add_parser(
        "import", help="Remplacer les blocs seed depuis les fichiers CSV.")
    p_cimport.add_argument("dir", nargs="?", default=".")

    p_import = sub.add_parser(
        "import", help="Installer un frontend obtenu SANS clé API (brief collé "
                       "dans claude.ai, résultat téléchargé) puis re-vérifier.")
    p_import.add_argument("source", help="Fichier .zip, index.html, dossier, ou "
                                         "JSON {'files': ...} téléchargé depuis Claude.")
    p_import.add_argument("dir", nargs="?", default=".", help="Dossier du projet.")

    args = parser.parse_args(argv)

    if args.command in (None, "init"):
        construction.cmd_init(getattr(args, "dir", None))
    elif args.command == "compile":
        project_dir = args.output or os.path.dirname(os.path.abspath(args.spec))
        construction.compile_project(args.spec, project_dir)
    elif args.command == "run":
        lancement.cmd_run(args.dir, check_only=args.check, port=args.port, skip_smoke=args.skip_smoke)
    elif args.command == "update":
        delta.cmd_update(args.dir)
    elif args.command == "diff":
        delta.cmd_diff(args.dir)
    elif args.command == "usage":
        consommation.cmd_usage(args.dir, prices_path=args.prices, json_output=args.json_output)
    elif args.command == "migrate":
        construction.cmd_migrate(args.dir, name=args.name, down=args.down, list_only=args.list)
    elif args.command == "assets":
        if args.assets_command == "add":
            if args.logo and args.favicon:
                print(" ❌ --logo et --favicon désignent deux déclarations "
                      "différentes : les poser en deux commandes.")
                sys.exit(1)
            cible = "logo" if args.logo else ("favicon" if args.favicon else None)
            contenu_editorial.cmd_assets_add(args.dir, args.fichier, pour=args.pour, cible=cible,
                           entity=args.entity, field=args.field, nom=args.nom,
                           force=args.force)
        elif args.assets_command == "list":
            contenu_editorial.cmd_assets_list(args.dir)
        else:
            p_assets.print_help()
            sys.exit(1)
    elif args.command == "content":
        if args.content_command == "export":
            contenu_editorial.cmd_content_export(args.dir)
        elif args.content_command == "import":
            contenu_editorial.cmd_content_import(args.dir)
        else:
            p_content.print_help()
            sys.exit(1)
    elif args.command == "frontend":
        retouche._lancer_ia(args, update_mode=args.update)
    elif args.command == "retouche":
        retouche.cmd_retouche(args.dir, args.demande)
        if args.consigne_seule:
            print("  → Donner ce fichier à une IA, puis installer le résultat "
                  "avec 'monl import'.")
        else:
            retouche._lancer_ia(args, retouche_mode=True)
    elif args.command == "import":
        from ..frontend_ai import FrontendAIError, import_and_verify
        try:
            ok, _errors = import_and_verify(args.dir, args.source)
        except FrontendAIError as e:
            print(f" ❌ {e}")
            sys.exit(1)
        if not ok:
            sys.exit(1)

def main(argv=None):
    """Point d'entrée CLI : traduit les erreurs MONL en code de sortie."""
    try:
        return _dispatch(argv)
    except MonlError as err:
        print(f" ❌ {err}")
        raise SystemExit(1) from err
