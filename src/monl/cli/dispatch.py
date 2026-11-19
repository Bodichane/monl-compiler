"""Subcommand dispatch."""

import argparse
import os
import sys

from .. import __version__
from ..errors import MonlError
from ..parser.version import LANGUAGE_VERSION
from . import consommation, construction, contenu_editorial, delta, lancement, retouche


# ----------------------------------------------------------- construction --
def build_parser():
    """Build the public parser, the source of truth of the ``monl`` CLI."""
    parser = argparse.ArgumentParser(
        prog="monl",
        description="monl — orchestration platform: guided dialogue → "
                    "DSL → backend + frontend contract → UI AI → run/update.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (language {LANGUAGE_VERSION})")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Guided dialogue (default when no subcommand is given).")
    p_init.add_argument("--dir", default=None, help="Project directory (default: ./NomApp)")

    p_compile = sub.add_parser("compile", help="Compile an existing .ml spec.")
    p_compile.add_argument("spec")
    p_compile.add_argument("--output", default=None,
                           help="Project directory (default: spec directory).")

    p_run = sub.add_parser("run", help="Check consistency, then launch the application.")
    p_run.add_argument("dir", nargs="?", default=".")
    p_run.add_argument("--check", action="store_true", help="Check without launching.")
    p_run.add_argument("--skip-smoke", action="store_true",
                       help="Skip the behavioral smoke test (not recommended).")
    p_run.add_argument("--port", type=int, default=8000)

    p_update = sub.add_parser("update", help="Recompile after the spec changes.")
    p_update.add_argument("dir", nargs="?", default=".")

    p_diff = sub.add_parser(
        "diff",
        help="Show the contract delta WITHOUT recompiling or writing anything.")
    p_diff.add_argument("dir", nargs="?", default=".")

    p_usage = sub.add_parser(
        "usage", help="Measure the project's AI usage and declared cost.")
    p_usage.add_argument("dir", nargs="?", default=".",
                         help="Project directory (first argument; default: .).")
    p_usage.add_argument(
        "--prices", default=None, metavar="JSON_FILE",
        help="JSON table provider → model → prices per million tokens; "
             "takes precedence over MONL_USAGE_PRICES. Format: "
             "{currency, prices: {provider: {model: "
             "{input_per_million_tokens, output_per_million_tokens}}}}.")
    p_usage.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Emit the JSON report for quotas and billing.")

    p_migrate = sub.add_parser(
        "migrate", help="Apply or roll back a named schema migration.")
    p_migrate.add_argument("dir", nargs="?", default=".")
    p_migrate.add_argument("--name", default=None, metavar="NAME",
                           help="Name declared by a 'migration' block.")
    p_migrate.add_argument("--down", action="store_true",
                           help="Roll back the migration when the operation is reversible.")
    p_migrate.add_argument("--list", action="store_true",
                           help="Show migration status without applying any.")

    p_front = sub.add_parser(
        "frontend", help="Generate the frontend with a specialized AI, with "
                         "automatic re-checks (consistency + smoke test).")
    p_front.add_argument("dir", nargs="?", default=".")
    from ..frontend_ai import CLI_AGENTS, GENERIC_PROVIDER, OPENAI_COMPATIBLE
    from ..image_ai import IMAGE_PROVIDERS
    _voies = sorted({"claude", GENERIC_PROVIDER} | set(OPENAI_COMPATIBLE) | set(CLI_AGENTS))
    p_front.add_argument("--provider", default="claude", choices=_voies,
                         help="API key: 'claude' (ANTHROPIC_API_KEY); "
                              + ", ".join(f"'{n}' ({v})" for n, (_u, v) in
                                          sorted(OPENAI_COMPATIBLE.items()))
                              + f" ; '{GENERIC_PROVIDER}' for any other "
                                "endpoint using the OpenAI dialect (MONL_AI_BASE_URL + "
                                "MONL_AI_API_KEY). Except for 'claude', '--model' is required. "
                                "Command-line agents, no key required: "
                              + ", ".join(f"'{n}'" for n in sorted(CLI_AGENTS))
                              + " — the agent works in the project directory.")
    p_front.add_argument("--model", default=None, help="Provider model.")
    p_front.add_argument(
        "--model-for", dest="model_for", action="append", default=None,
        metavar="TARGET=MODEL",
        help="Repeatable routing for staged generation (e.g. "
             "styles.css=yandexgpt-lite). Exact targets: index.html, styles.css, "
             "app.js, and planned SVGs. A monolithic or agent path makes "
             "one call and will report that this routing was not applied.")
    p_front.add_argument("--agent-command", default=None,
                         help="Command template for an agent not in the "
                              "list, with {instruction} substituted — for example "
                         "\"mon-agent --auto {instruction}\". Takes precedence over "
                              "--provider and can also override a preset.")
    p_front.add_argument("--max-turns", type=int, default=None,
                         help="Agent turn budget ('claude-code' "
                              "only). Default: 120.")
    p_front.add_argument("--update", action="store_true",
                         help="Update the existing frontend using "
                              "docs/FRONTEND_UPDATE_PROMPT.md instead of starting from scratch.")
    p_front.add_argument(
        "--generate-images", action="store_true",
        help="Explicitly generate planned raster images in the "
             "assets directory (default: no images).")
    p_front.add_argument(
        "--image-provider", choices=sorted(IMAGE_PROVIDERS), default="yandexart",
        help="Image provider used with --generate-images (default: yandexart).")

    # POINT 93: fix a defect SEEN on the site, without rebuilding it. The
    # options are strictly those of 'frontend' — it is the same path to the AI,
    # with the same safeguards; only the origin of the brief changes.
    p_ret = sub.add_parser(
        "retouche", help="Fix an observed issue on the site (layout, "
                         "framing, readability) without rebuilding the frontend.")
    p_ret.add_argument("demande", help="Describe the issue in one sentence — name "
                                       "the screen and element: \"images in the "
                                       "Trends section are poorly framed\".")
    p_ret.add_argument("dir", nargs="?", default=".")
    p_ret.add_argument("--provider", default="claude", choices=_voies,
                       help="Same options as 'monl frontend'.")
    p_ret.add_argument("--model", default=None, help="Provider model.")
    p_ret.add_argument("--agent-command", default=None,
                       help="Command template for an agent not in the list, "
                            "with {instruction} substituted.")
    p_ret.add_argument("--max-turns", type=int, default=None,
                       help="Agent turn budget. Default: 120.")
    p_ret.add_argument("--prompt-only", "--consigne-seule", dest="consigne_seule",
                       action="store_true",
                       help="Write FRONTEND_RETOUCHE_PROMPT.md and stop — "
                            "to give it to an AI yourself, then run 'monl import'.")

    # BRICK 13, LAYER 2 (point 84): drop a human's file and DECLARE it, in one
    # command. The tool writes, the compiler proves: the resulting spec is
    # revalidated before being written, so layer 2 cannot produce what layer 1
    # refuses.
    p_assets = sub.add_parser(
        "assets", help="Install user-provided files (photos, "
                       "logo, favicon) and declare them in the spec.")
    sub_assets = p_assets.add_subparsers(dest="assets_command")

    p_add = sub_assets.add_parser(
        "add", help="Copy a file to the assets directory and declare it in the spec.")
    p_add.add_argument("fichier", help="The file to install (photo, logo...).")
    p_add.add_argument("--for", dest="pour", default=None, metavar="VALUE",
                       help="Target seed record, identified by one of its values "
                            "— for example --for \"Halo RS\".")
    p_add.add_argument("--logo", action="store_true",
                       help="Declare this file as the project logo (assets.logo).")
    p_add.add_argument("--favicon", action="store_true",
                       help="Declare this file as the favicon (assets.favicon).")
    p_add.add_argument("--entity", default=None,
                       help="Resolve ambiguity when the --for value exists "
                            "in multiple entities.")
    p_add.add_argument("--field", default=None,
                       help="Target 'Image' field, if the entity has several.")
    p_add.add_argument("--as", dest="nom", default=None, metavar="FILENAME",
                       help="Destination filename (default: the --for slug "
                            "plus the original extension).")
    p_add.add_argument("--force", action="store_true",
                       help="Overwrite a same-name file with different contents.")
    p_add.add_argument("--dir", default=".", help="Project directory (default: .).")

    p_alist = sub_assets.add_parser(
        "list", help="Show what the spec declares, what is present, and what is untracked.")
    p_alist.add_argument("dir", nargs="?", default=".")

    p_content = sub.add_parser(
        "content", help="Export or re-import demonstration records as CSV.")
    sub_content = p_content.add_subparsers(dest="content_command")
    p_cexport = sub_content.add_parser(
        "export", help="Create content/<Entity>.csv from seed blocks.")
    p_cexport.add_argument("dir", nargs="?", default=".")
    p_cimport = sub_content.add_parser(
        "import", help="Replace seed blocks from CSV files.")
    p_cimport.add_argument("dir", nargs="?", default=".")

    p_import = sub.add_parser(
        "import", help="Install a frontend obtained WITHOUT an API key (brief pasted "
                       "into claude.ai, downloaded result), then re-check it.")
    p_import.add_argument("source", help="A .zip file, index.html, directory, or "
                                         "JSON {'files': ...} downloaded from Claude.")
    p_import.add_argument("dir", nargs="?", default=".", help="Project directory.")

    return parser


def _subparser(parser, command):
    """Find a subparser to display its contextual help."""
    return next(
        action.choices[command]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )


# ------------------------------------------------------------------- main --
def _dispatch(argv=None):
    parser = build_parser()

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
        _commande_assets(parser, args)
    elif args.command == "content":
        _commande_content(parser, args)
    elif args.command == "frontend":
        retouche._lancer_ia(args, update_mode=args.update)
    elif args.command == "retouche":
        _commande_retouche(args)
    elif args.command == "import":
        _commande_import(args)


# The four functions below are extracted from `_dispatch` (complexity
# ceiling): same calls, same messages, same exit codes. They still reach
# the commands through their MODULE objects, so tests that monkeypatch
# them keep working.
def _commande_assets(parser, args):
    """`monl assets add|list`."""
    if args.assets_command == "add":
        if args.logo and args.favicon:
            print(" ❌ --logo and --favicon declare two different "
                  "things; set them in separate commands.")
            sys.exit(1)
        cible = "logo" if args.logo else ("favicon" if args.favicon else None)
        contenu_editorial.cmd_assets_add(args.dir, args.fichier, pour=args.pour, cible=cible,
                       entity=args.entity, field=args.field, nom=args.nom,
                       force=args.force)
    elif args.assets_command == "list":
        contenu_editorial.cmd_assets_list(args.dir)
    else:
        _subparser(parser, "assets").print_help()
        sys.exit(1)


def _commande_content(parser, args):
    """`monl content export|import`."""
    if args.content_command == "export":
        contenu_editorial.cmd_content_export(args.dir)
    elif args.content_command == "import":
        contenu_editorial.cmd_content_import(args.dir)
    else:
        _subparser(parser, "content").print_help()
        sys.exit(1)


def _commande_retouche(args):
    """`monl retouche`."""
    retouche.cmd_retouche(args.dir, args.demande)
    if args.consigne_seule:
        print("  → Give this file to an AI, then install the result "
              "with 'monl import'.")
    else:
        retouche._lancer_ia(args, retouche_mode=True)


def _commande_import(args):
    """`monl import`."""
    from ..frontend_ai import FrontendAIError, import_and_verify
    try:
        ok, _errors = import_and_verify(args.dir, args.source)
    except FrontendAIError as e:
        print(f" ❌ {e}")
        sys.exit(1)
    if not ok:
        sys.exit(1)


def main(argv=None):
    """CLI entry point: translates MONL errors into an exit code."""
    try:
        return _dispatch(argv)
    except MonlError as err:
        print(f" ❌ {err}")
        raise SystemExit(1) from err
