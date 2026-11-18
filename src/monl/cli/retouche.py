"""Corriger sans reconstruire.

POINT 93 : il n'y a qu'UNE voie vers l'IA — `_lancer_ia`, partagée par
`frontend` et `retouche`. Recopier ces lignes ferait deux endroits où les
garde-fous peuvent diverger.
POINT 105 : `retouche` est le SEUL geste dont le premier argument n'est pas
le dossier ; l'inversion est donc l'erreur attendue, elle est DÉTECTÉE et
NOMMÉE — jamais corrigée d'office."""

import os
import sys

from ..frontend_ai import RETOUCHE_PROMPT_FILENAME
from . import emplacement, nomenclature


# --------------------------------------------------------------- retouche --
# POINT 93 : entre « le site est juste au regard du contrat » et « le site est
# raté », monl n'avait aucun geste. `monl frontend` RECONSTRUIT — on jette un
# site bon à 95 % pour un tirage non déterministe ; `monl update` ne parle que
# du delta de spec, et se tait quand la spec n'a pas bougé. Restait l'édition à
# la main, hors de la boucle de vérification.
#
# La retouche ne fait donc RIEN de neuf : elle réutilise la voie d'évolution du
# point 4 en changeant la seule chose qui manquait — l'origine du brief, une
# phrase humaine au lieu d'un diff. Tout le reste est commun, et doit le
# rester : empreinte des artefacts protégés, empreinte du frontend qui DOIT
# bouger (point 73), cohérence + smoke test, une correction au plus.
#
# CE QUE MONL NE PROMET PAS, et il faut le dire ici : que le résultat soit plus
# BEAU. Le smoke test prouve que la page tourne encore et respecte le contrat,
# jamais que le cadrage s'est amélioré. Même honnêteté qu'au point 83 — monl
# vérifie la complétude, pas le goût. D'où la sauvegarde systématique : la
# seule garantie qu'on peut offrir sur une question de goût, c'est de pouvoir
# revenir en arrière.
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
    """Copie frontend/ dans frontend.precedent/ avant une retouche.

    `monl import` sauvegarde depuis toujours (« rien n'est perdu ») ; la
    retouche en a plus besoin encore, puisqu'elle porte sur un site qui MARCHE
    et qu'aucune vérification automatique ne peut trancher une question de
    goût. C'est une COPIE et non un déplacement : l'IA doit trouver l'existant
    en place pour le faire évoluer."""
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
    """La voie vers l'IA, partagée par 'frontend' et 'retouche' (point 93).

    Elle était écrite en ligne dans le dispatch ; la recopier pour la retouche
    aurait fait DEUX chemins vers le modèle, donc deux endroits où les
    garde-fous peuvent diverger. CLAUDE.md l'interdit nommément : « ne jamais
    contourner le garde-fou d'empreinte en ajoutant une voie »."""
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
            # Le modèle par défaut n'existe QUE pour la voie Anthropic ;
            # ailleurs, openai_provider exige --model et le dit.
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
    """`monl retouche <dossier> "<ce qui cloche>"` — l'erreur attendue.

    POINT 105 : `retouche` est le SEUL geste dont le premier argument n'est pas
    le dossier ; `run`, `update`, `diff`, `compile` et `frontend` le prennent
    tous en tête. Écrire le dossier en premier est donc le réflexe, et monl
    répondait « ce dossier n'est pas un projet monl » en parlant de la PHRASE.

    Le diagnostic NOMME l'inversion, il ne la corrige pas : remettre les
    arguments en place à la place de l'auteur, ce serait deviner — et se
    tromper le jour où une demande ressemble à un chemin. Même arbitrage que
    partout ailleurs dans ce dépôt."""
    demande, dossier = demande or "", dossier or ""
    ressemble_a_un_chemin = " " not in demande and (
        os.sep in demande or os.path.isdir(demande))
    return ressemble_a_un_chemin and " " in dossier

def cmd_retouche(project_dir, demande, say=print):
    """Écrit la consigne et prépare le terrain. L'appel à l'IA est fait par
    l'appelant (main), qui porte déjà le choix du fournisseur — la retouche
    n'ouvre AUCUNE voie nouvelle vers le modèle."""
    if _arguments_inverses(demande, project_dir):
        say(" ❌ The two arguments appear to be reversed.")
        say(f"    ‘{demande}’ looks like a directory, and ‘{project_dir[:50]}"
            f"{'…' if len(project_dir) > 50 else ''}’ like a description of the issue.")
        say("    'retouche' expects the REQUEST first (it is the only command "
            "that works this way):")
        # La commande proposée doit MARCHER telle quelle : recopier un chemin
        # dont on sait déjà qu'il est faux ferait buter l'auteur une deuxième
        # fois, sur un autre message.
        cible = demande
        if not os.path.isdir(cible) and cible.startswith(os.sep) \
                and os.path.isdir(cible.lstrip(os.sep)):
            cible = cible.lstrip(os.sep)
        say(f'      monl retouche "{project_dir}" {cible}')
        sys.exit(1)
    project_dir = os.path.abspath(project_dir)
    souci = emplacement._erreur_de_chemin(project_dir)
    if souci:
        say(souci)
        sys.exit(1)
    if emplacement._load_state(project_dir) is None:
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
