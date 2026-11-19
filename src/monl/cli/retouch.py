"""Fix without rebuilding.

POINT 93: there is only ONE path to the AI — `_lancer_ia`, shared by
`frontend` and `retouche`. Copying these lines would make two places where
the safeguards can diverge.

POINT 105: `retouche` is the ONLY command whose first argument is not the
folder; the inversion is therefore the expected error, it is DETECTED and
NAMED — never corrected automatically."""

import os
import sys

from ..frontend_ai import RETOUCHE_PROMPT_FILENAME
from . import location, nomenclature


# --------------------------------------------------------------- retouche --
# POINT 93: between "the site is right with respect to the contract" and "the
# site is a failure", monl had no command. `monl frontend` REBUILDS — throwing
# away a 95% good site for a non-deterministic draw; `monl update` only talks
# about the spec delta, and stays silent when the spec has not moved. What
# remained was editing by hand, outside the verification loop.
#
# The touch-up therefore does NOTHING new: it reuses the evolution path of
# point 4, changing the only thing that was missing — the origin of the brief,
# a human sentence instead of a diff. Everything else is shared, and must stay
# so: fingerprint of the protected artifacts, fingerprint of the frontend that
# MUST move (point 73), consistency + smoke test, at most one correction.
#
# WHAT MONL DOES NOT PROMISE, and it must be said here: that the result is more
# BEAUTIFUL. The smoke test proves that the page still runs and honors the
# contract, never that the framing improved. Same honesty as point 83 — monl
# checks completeness, not taste. Hence the systematic backup: the only
# guarantee one can offer on a matter of taste is being able to go back.
def _write_retouche_brief(project_dir, demande):
    body = f"""# Requested touch-up (instruction written by 'monl retouche')

The site works and follows the contract. A defect was OBSERVED on it, by a
human who looked at it:

> {demande.strip()}

## What to do

Fix that defect in the existing frontend (`frontend/`), and only that one.
Do not redo the overall layout, do not rewrite what works: a touch-up is
judged by what it leaves intact as much as by what it changes.

If the request is ambiguous, choose the NARROWEST interpretation — the one
that touches the fewest things. A touch-up that is too broad can no longer be
told apart from a rebuild, and that is exactly what this command avoids.

If the defect CANNOT be fixed in `frontend/` — because it comes from what the
spec says, or does not say — do not work around it with a display trick:
report it in the response and leave the frontend as it is. A text cut up
blindly because the contract does not structure it is a guessed structure,
which will be lost again at the next build.

## Unchanged rules

The complete contract is still `frontend_contract.json`, and the rules of
`FRONTEND_PROMPT.md` all remain in force — same routes, same API origin, same
self-containment (no CDN). Do not modify any other project file.

A reminder about iconography, because "no CDN" is easily read as "no icons
possible": no icon library is reachable, but SVG written INLINE in the HTML
and `.svg` files placed in `frontend/` work and are served. It is an
available MEANS, not an instruction: nothing requires using any.

After the change, `monl run` will revalidate everything (static consistency
+ behavioral smoke test) before any start.
"""
    path = os.path.join(project_dir, RETOUCHE_PROMPT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path

def sauvegarder_frontend(project_dir, say=print):
    """Copies frontend/ into frontend.precedent/ before a touch-up.

    `monl import` has always backed up ("nothing is lost"); the touch-up needs
    it even more, since it works on a site that WORKS and no automatic check
    can settle a matter of taste. It is a COPY and not a move: the AI must
    find the existing site in place to evolve it."""
    import shutil
    source = os.path.join(project_dir, "frontend")
    if not os.path.isdir(source):
        return None
    backup = source + ".precedent"
    shutil.rmtree(backup, ignore_errors=True)
    shutil.copytree(source, backup)
    say(" -> Current frontend copied to frontend.precedent/ (you can restore it later).")
    return backup

def _lancer_ia(args, update_mode=False, retouche_mode=False):
    """The path to the AI, shared by 'frontend' and 'retouche' (point 93).

    It was written inline in the dispatch; copying it for the touch-up would
    have made TWO paths to the model, hence two places where the safeguards
    can diverge. CLAUDE.md forbids it by name: "never bypass the fingerprint
    safeguard by adding a path"."""
    from ..frontend_ai import (
        CLI_AGENTS,
        DEFAULT_MAX_TURNS,
        DEFAULT_MODEL,
        PROVIDERS,
        FrontendAIError,
        _parse_model_routing,
        _validate_model_routing,
        generate_and_verify,
        generate_with_cli_agent,
    )
    try:
        image_provider = None
        if getattr(args, "generate_images", False):
            from ..image_ai import IMAGE_PROVIDERS, ImageProviderError
            try:
                image_provider = IMAGE_PROVIDERS[args.image_provider]()
            except ImageProviderError as exc:
                raise FrontendAIError(str(exc)) from exc
        model_routes = _parse_model_routing(getattr(args, "model_for", None))
        _validate_model_routing(args.dir, model_routes)
        if args.agent_command or args.provider in CLI_AGENTS:
            if model_routes:
                declared = ", ".join(
                    f"{target}={model}" for target, model in sorted(model_routes.items()))
                print(" -> Per-stage routing not applied: the agent workflow does not "
                      f"use split calls (declared mappings: {declared}).")
            ok, _errors = generate_with_cli_agent(
                args.dir, update_mode=update_mode, retouche_mode=retouche_mode,
                max_turns=args.max_turns or DEFAULT_MAX_TURNS,
                agent=args.provider, agent_command=args.agent_command,
                generate_images=getattr(args, "generate_images", False),
                image_provider=image_provider)
        else:
            # The default model exists ONLY for the Anthropic path; elsewhere,
            # openai_provider requires --model and says so.
            defaut = DEFAULT_MODEL if args.provider == "claude" else None
            def provider_factory(model):
                return PROVIDERS[args.provider](model=model)

            provider = provider_factory(args.model or defaut)
            ok, _errors = generate_and_verify(args.dir, provider,
                                              update_mode=update_mode,
                                              retouche_mode=retouche_mode,
                                              model_routes=model_routes,
                                              provider_factory=provider_factory,
                                              generate_images=getattr(
                                                  args, "generate_images", False),
                                              image_provider=image_provider)
    except FrontendAIError as e:
        print(f" ❌ {e}")
        sys.exit(1)
    if not ok:
        sys.exit(1)

def _arguments_inverses(demande, dossier):
    """`monl retouche <folder> "<what looks wrong>"` — the expected error.

    POINT 105: `retouche` is the ONLY command whose first argument is not the
    folder; `run`, `update`, `diff`, `compile` and `frontend` all take it
    first. Writing the folder first is therefore the reflex, and monl answered
    "this folder is not a monl project" while talking about the SENTENCE.

    The diagnosis NAMES the inversion, it does not correct it: putting the
    arguments back in place for the author would be guessing — and getting it
    wrong the day a request looks like a path. Same trade-off as everywhere
    else in this repository."""
    demande, dossier = demande or "", dossier or ""
    ressemble_a_un_chemin = " " not in demande and (
        os.sep in demande or os.path.isdir(demande))
    return ressemble_a_un_chemin and " " in dossier

def cmd_retouche(project_dir, demande, say=print):
    """Writes the instruction and prepares the ground. The AI call is made by
    the caller (main), which already carries the provider choice — the
    touch-up opens NO new path to the model."""
    if _arguments_inverses(demande, project_dir):
        say(" ❌ The two arguments appear to be reversed.")
        say(f"    ‘{demande}’ looks like a directory, and ‘{project_dir[:50]}"
            f"{'…' if len(project_dir) > 50 else ''}’ like a description of the issue.")
        say("    'retouche' expects the REQUEST first (it is the only command "
            "that works this way):")
        # The suggested command must WORK as is: copying a path already known
        # to be wrong would make the author stumble a second time, on another
        # message.
        cible = demande
        if not os.path.isdir(cible) and cible.startswith(os.sep) \
                and os.path.isdir(cible.lstrip(os.sep)):
            cible = cible.lstrip(os.sep)
        say(f'      monl retouche "{project_dir}" {cible}')
        sys.exit(1)
    project_dir = os.path.abspath(project_dir)
    souci = location._erreur_de_chemin(project_dir)
    if souci:
        say(souci)
        sys.exit(1)
    if location._load_state(project_dir) is None:
        say(f" ❌ {nomenclature.STATE_FILENAME} not found — this directory is not a monl project.")
        sys.exit(1)
    if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
        say(" ❌ No frontend to touch up (frontend/index.html is missing) — "
            "build one first with 'monl frontend' or 'monl import'.")
        sys.exit(1)
    if not demande or not demande.strip():
        say(" ❌ The request is empty — describe the issue, naming the screen "
            "and the element.")
        sys.exit(1)
    sauvegarder_frontend(project_dir, say=say)
    chemin = _write_retouche_brief(project_dir, demande)
    say(f" -> Instructions written: {os.path.basename(chemin)}")
    return chemin
