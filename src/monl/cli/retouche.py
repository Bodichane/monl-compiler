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
    body = f"""# Retouche demandée (consigne écrite par 'monl retouche')

Le site fonctionne et respecte le contrat. Un défaut a été CONSTATÉ dessus,
par un humain qui l'a regardé :

> {demande.strip()}

## Ce qu'il faut faire

Corriger ce défaut-là dans le frontend existant (`frontend/`), et lui seul.
Ne pas refaire la mise en page générale, ne pas réécrire ce qui fonctionne :
une retouche se juge à ce qu'elle laisse intact autant qu'à ce qu'elle change.

Si la demande est ambiguë, choisir l'interprétation la plus ÉTROITE — celle
qui touche le moins de choses. Une retouche trop large ne se distingue plus
d'une reconstruction, et c'est précisément ce que cette commande évite.

Si le défaut ne peut PAS se corriger dans `frontend/` — parce qu'il vient de
ce que la spec dit, ou ne dit pas — ne pas le contourner par une astuce
d'affichage : le signaler dans la réponse et laisser le frontend en l'état.
Un texte qu'on découpe à l'aveugle parce que le contrat ne le structure pas
est une structure devinée, qui se reperdra à la prochaine construction.

## Règles inchangées

Le contrat complet reste `frontend_contract.json`, et les règles de
`FRONTEND_PROMPT.md` restent toutes en vigueur — mêmes routes, même origine
d'API, même autonomie (aucun CDN). Ne modifier aucun autre fichier du projet.

Rappel sur l'iconographie, parce que « aucun CDN » se lit facilement comme
« pas d'icônes possibles » : aucune librairie d'icônes n'est atteignable, mais
le SVG écrit EN LIGNE dans le HTML et les fichiers `.svg` déposés dans
`frontend/` fonctionnent et sont servis. C'est un MOYEN disponible, pas une
consigne : rien n'oblige à en mettre.

Après modification, `monl run` revalidera l'ensemble (cohérence statique
+ smoke test comportemental) avant tout lancement.
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
    say(" -> Frontend actuel copié dans frontend.precedent/ (retour en arrière possible).")
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
                print(" -> Routage par étage non appliqué : la voie agent ne comporte "
                      f"pas d'appels découpés (correspondances déclarées : {declared}).")
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
        say(" ❌ Les deux arguments semblent inversés.")
        say(f"    « {demande} » ressemble à un dossier, et « {project_dir[:50]}"
            f"{'…' if len(project_dir) > 50 else ''} » à ce qui cloche.")
        say("    'retouche' attend la DEMANDE d'abord (c'est le seul geste dans "
            "ce sens) :")
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
        say(f" ❌ {nomenclature.STATE_FILENAME} introuvable — ce dossier n'est pas un projet monl.")
        sys.exit(1)
    if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
        say(" ❌ Aucun frontend à retoucher (frontend/index.html absent) — "
            "construire d'abord avec 'monl frontend' ou 'monl import'.")
        sys.exit(1)
    if not demande or not demande.strip():
        say(" ❌ La demande est vide — décrire ce qui cloche, en nommant l'écran "
            "et l'élément.")
        sys.exit(1)
    sauvegarder_frontend(project_dir, say=say)
    chemin = _write_retouche_brief(project_dir, demande)
    say(f" -> Consigne écrite : {os.path.basename(chemin)}")
    return chemin
