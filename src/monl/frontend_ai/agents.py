"""Les agents en ligne de commande, et les deux garde-fous d'empreinte."""

import hashlib
import os
import shlex
import shutil
import subprocess
import time
import uuid

from ..design_system import activate_asset_manifest
from ..frontend_contract import PROMPT_FILENAME
from . import fondations, fournisseurs, images, redaction

# ─────────────────────────────────────────────────────────────────────
# CLAUDE CODE — le travail fait DIRECTEMENT dans le dossier cible
# (point 43 du journal). Claude Code s'authentifie par l'abonnement
# ('claude login'), pas par une clé API — c'est la voie agentique du flux
# sans clé : au lieu de copier/coller (point 42), l'agent lit le brief sur
# place, écrit dans frontend/, et monl re-vérifie derrière.
#
# Deux usages :
#   - interactif : 'cd MonProjet && claude' — le CLAUDE.md généré dans le
#     dossier du projet (voir write_project_claude_md) cadre la session
#     (rôle, fichiers interdits, commande de vérification) ;
#   - headless : 'monl frontend --provider claude-code' invoque
#     'claude -p' avec des permissions restreintes, puis la MÊME
#     re-vérification et la MÊME correction unique que la voie API.
#
# Garde-fou SPÉCIFIQUE à cette voie : contrairement à l'API (qui rend du
# texte que monl écrit lui-même), Claude Code écrit directement sur le
# disque. Les artefacts protégés (spec, backend, contrat, état) sont donc
# empreints AVANT l'exécution et re-vérifiés APRÈS — toute modification
# est une erreur bloquante, même si le frontend rendu est correct.
# ─────────────────────────────────────────────────────────────────────

# POINT 134 : CETTE LISTE EST UN INVARIANT *PENDANT* LE PASSAGE DE L'AGENT,
# PAS UNE DÉCLARATION DE PROPRIÉTÉ. L'empreinte est prise juste avant de
# lancer l'agent et comparée juste après : l'auteur reste donc parfaitement
# libre d'adapter son Dockerfile entre deux exécutions. C'est cette confusion
# qui avait laissé dehors des fichiers EXÉCUTABLES au prétexte qu'ils sont
# éditables.
#
# `manage.py` est le trou grave (revue Codex, vérifiée ligne à ligne) : il
# CRÉE les comptes administrateurs — c'est la frontière que `selfRegister`
# tient côté API. Il était scellé dans monl.json mais absent d'ici, et le
# contrôle de cohérence qui l'aurait vu n'est même pas atteint quand l'agent
# ne touche pas à frontend/ : `generate_with_cli_agent` retourne un SUCCÈS
# avant lui. Un agent réécrivant manage.py sans rien changer d'autre n'était
# donc vu par personne, et le code injecté s'exécutait à la première création
# de compte privilégié.
#
# `Dockerfile` et `.dockerignore` suivent le même raisonnement : ils décrivent
# ce qui s'exécute au déploiement, y compris des `RUN`.
#
# `serve.py` (point 133) n'y était pas parce qu'il n'existait qu'après
# 'monl run'. Émis dès la compilation, il est là quand l'IA passe, et c'est
# LUI qui décide quels dossiers sont servis.
#
# La liste reste une ÉNUMÉRATION, et c'est sa faiblesse : chaque artefact
# nouveau doit y être ajouté à la main, et trois l'ont été après coup. La
# renverser — « rien hors de frontend/ ne bouge » — est la bonne forme, et
# demande de parcourir le projet entier ; à faire, pas à improviser ici.
PROTECTED_ARTEFACTS = ("spec.ml", "app.py", "schema.sql", "sandbox_ai.py",
                       "manage.py", "serve.py", "Dockerfile", ".dockerignore",
                       "frontend_contract.json", "FRONTEND_PROMPT.md",
                       "DESIGN_SYSTEM.md", "DESIGN_SPEC.md",
                       "ASSET_MANIFEST.json", "monl.json", ".jwt_secret")

# POINT 62 : budget de tours de l'agent. 40 était un chiffre posé avant que le
# brief ne porte l'intention visuelle (point 53), les rubriques éditoriales
# (points 55 et 61) et les attentes d'archétype (point 60) : un frontend réel
# se construit fichier par fichier, chacun coûtant un tour, et le budget
# s'épuisait AVANT que index.html n'existe. Relevé à 120, et rendu réglable
# depuis la ligne de commande — un site à trois rubriques ne coûte pas ce que
# coûte un catalogue.
DEFAULT_MAX_TURNS = 120

CLAUDE_CODE_INSTRUCTION = (
    "Lis {brief} et construis le frontend demandé, en écrivant UNIQUEMENT "
    "dans le dossier frontend/ (point d'entrée frontend/index.html, "
    "autonome : aucun CDN). Ne modifie AUCUN autre fichier du projet — "
    "ni la spec .ml, ni app.py, ni le contrat. Le CLAUDE.md du dossier "
    "détaille le contexte."
)

# POINT 93 : une retouche n'est pas une construction. L'instruction générique
# (« construis le frontend demandé ») invitait à repartir de zéro, ce qui est
# exactement ce qu'on veut éviter — le site est bon à 95 %, et une
# reconstruction est un tirage dont on peut perdre ce qu'on aimait.
RETOUCHE_INSTRUCTION = (
    "Lis {brief} : il décrit un défaut CONSTATÉ sur le site en marche. Corrige "
    "ce défaut-là dans le frontend EXISTANT (dossier frontend/), et lui seul — "
    "ne réécris pas ce qui fonctionne déjà, ne refais pas la mise en page "
    "générale. Ne modifie AUCUN autre fichier du projet : ni la spec .ml, ni "
    "app.py, ni le contrat. Le CLAUDE.md du dossier détaille le contexte."
)

# ─────────────────────────────────────────────────────────────────────
# POINT 69 (suite) : « et aussi codex et autre ». La voie agentique ne
# dépendait de Claude Code que par sa ligne de commande — le garde-fou
# d'empreinte, la re-vérification et la correction unique sont communs à
# tout agent qui écrit sur le disque. La table ci-dessous n'est donc que
# la partie variable : quel binaire, quels arguments.
#
# HONNÊTETÉ SUR LA VÉRIFICATION : seul 'claude' est éprouvé contre le vrai
# binaire (tests avec agent factice + usage réel). Les lignes 'codex' et
# 'gemini' suivent l'invocation non interactive publiée par ces outils,
# mais AUCUN des deux n'était installé sur la machine de développement :
# elles sont données comme préréglages, pas comme garanties. C'est
# précisément pourquoi '--agent-command' existe — un gabarit libre permet
# de câbler n'importe quel agent (ou de corriger un préréglage devenu
# faux) sans attendre une version de monl.
# ─────────────────────────────────────────────────────────────────────
CLI_AGENTS = {
    "claude-code": {
        "binary": "claude",
        "args": lambda instruction, max_turns: [
            "-p", instruction, "--permission-mode", "acceptEdits",
            "--max-turns", str(max_turns)],
        "auth": "Claude Code : 'claude login' (abonnement, aucune clé)",
    },
    "codex": {
        "binary": "codex",
        "args": lambda instruction, max_turns: [
            "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
            instruction],
        "auth": "Codex CLI : 'codex login' (abonnement ChatGPT) ou OPENAI_API_KEY",
    },
    "gemini": {
        "binary": "gemini",
        "args": lambda instruction, max_turns: ["--yolo", "-p", instruction],
        "auth": "Gemini CLI : 'gemini' (compte Google) ou GEMINI_API_KEY",
    },
}

def build_agent_argv(agent, instruction, max_turns, agent_command=None):
    """Rend la ligne de commande complète d'un agent.

    'agent_command' est un gabarit libre où {instruction} est substitué —
    par exemple 'mon-agent --auto {instruction}'. Il l'emporte sur la
    table, ce qui permet aussi de corriger un préréglage sur place."""
    if agent_command:
        parts = shlex.split(agent_command)
        if not parts:
            raise fondations.FrontendAIError("--agent-command est vide.")
        if not any("{instruction}" in p for p in parts):
            raise fondations.FrontendAIError(
                "--agent-command doit contenir {instruction} — sans lui, "
                "l'agent serait lancé sans savoir quoi faire.")
        argv = [p.replace("{instruction}", instruction) for p in parts]
        return argv[0], argv[1:]
    if agent not in CLI_AGENTS:
        raise fondations.FrontendAIError(
            f"agent inconnu : {agent} — connus : {', '.join(sorted(CLI_AGENTS))} "
            "(ou --agent-command pour tout autre).")
    entry = CLI_AGENTS[agent]
    return entry["binary"], entry["args"](instruction, max_turns)

def _fingerprint_protected(project_dir):
    prints = {}
    for name in PROTECTED_ARTEFACTS:
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                prints[name] = hashlib.sha256(fh.read()).hexdigest()
    return prints

def _fingerprint_frontend(project_dir):
    """Empreinte de TOUT le contenu de frontend/ (POINT 73).

    Le garde-fou d'empreinte ne surveillait que les artefacts PROTÉGÉS —
    ce qu'un agent ne doit pas toucher. Personne ne mesurait ce qu'il était
    censé produire : `frontend/index.html` existait déjà, la cohérence
    passait, le smoke test aussi, et monl annonçait « Frontend construit »
    alors que l'agent n'avait pas écrit une ligne. Un contrôle qui ne peut
    pas distinguer « construit » de « laissé intact » ne contrôle rien.
    """
    prints = {}
    racine = os.path.join(project_dir, "frontend")
    for dossier, _sous, fichiers in os.walk(racine):
        for nom in fichiers:
            chemin = os.path.join(dossier, nom)
            with open(chemin, "rb") as fh:
                prints[os.path.relpath(chemin, racine)] = hashlib.sha256(fh.read()).hexdigest()
    return prints

def run_cli_agent(project_dir, instruction, max_turns=DEFAULT_MAX_TURNS,
                  command=None, agent="claude-code", agent_command=None):
    """Invoque l'agent dans le dossier du projet. 'command' est injectable
    pour les tests (exécutable factice) — même approche que le fournisseur
    factice de la voie API : l'orchestration s'exécute pour de vrai, seul
    l'agent est simulé.

    POINT 62 : l'épuisement du budget de tours n'est PAS une erreur
    d'exécution. L'agent a pu écrire un frontend complet au tour 39 et
    dépasser au 40e ; le traiter comme un échec dur jetait un travail que la
    vérification aurait peut-être accepté, et privait la boucle de sa passe
    de correction. Rendu comme un avertissement, la suite tranche sur pièces."""
    wanted, args = build_agent_argv(agent, instruction, max_turns, agent_command)
    binary = command or shutil.which(wanted)
    if not binary:
        auth = CLI_AGENTS.get(agent, {}).get("auth", "")
        raise fondations.FrontendAIError(
            f"l'exécutable '{wanted}' est introuvable — l'installer puis "
            "s'authentifier" + (f" ({auth})" if auth else "")
            + ". Sans agent en ligne de commande, deux voies restent : "
              "'monl frontend --provider <api>' avec une clé, ou 'monl import' "
              "après un copier/coller dans n'importe quel chat.")
    proc = subprocess.run(
        [binary] + args,
        cwd=project_dir, capture_output=True, text=True, timeout=1800)
    sortie = (proc.stderr or proc.stdout) or ""
    if proc.returncode != 0:
        if "max turns" in sortie.lower():
            return sortie          # budget épuisé : la vérification tranchera
        raise fondations.FrontendAIError(f"l'agent '{agent}' a terminé en erreur : "
                              + sortie[-400:])
    return proc.stdout

def run_claude_code(project_dir, instruction, max_turns=DEFAULT_MAX_TURNS,
                    command=None):
    """Alias conservé pour compatibilité.

    Utiliser ``run_cli_agent(..., agent="claude-code")`` dans le nouveau code.
    Voir ``docs/DEPRECATIONS.md`` pour la politique de retrait.
    """
    return run_cli_agent(project_dir, instruction, max_turns=max_turns,
                         command=command, agent="claude-code")

def generate_with_cli_agent(project_dir, update_mode=False, say=print,
                            command=None, max_turns=DEFAULT_MAX_TURNS,
                            agent="claude-code", agent_command=None,
                            retouche_mode=False, generate_images=False,
                            image_provider=None):
    """La boucle du point 4, version agent en ligne de commande : exécuter
    l'agent dans le dossier cible → vérifier les artefacts protégés →
    re-vérifier (cohérence + smoke test) → une correction au plus.
    Retourne (ok, erreurs).

    POINT 69 : le corps est rigoureusement celui écrit pour Claude Code. Un
    agent tiers ne relâche AUCUN garde-fou — c'est le sens de la
    généralisation : ce qui protège le projet ne dépend pas de qui écrit."""
    from ..cli import check_coherence
    from ..smoke_test import run_smoke_test

    nom = agent_command.split()[0] if agent_command else agent
    project_dir = os.path.abspath(project_dir)
    run_id = uuid.uuid4().hex
    operation = ("retouche" if retouche_mode else
                 ("update" if update_mode else "construction"))
    image_failures = []
    if generate_images:
        if image_provider is None:
            raise fondations.FrontendAIError(
                "--generate-images exige un fournisseur d'images injectable.")
        _generated, image_failures = images._generate_planned_images(
            project_dir, image_provider, operation, 1, run_id, say=say)
    brief = redaction.brief_evolution(update_mode, retouche_mode) or PROMPT_FILENAME
    if not os.path.exists(os.path.join(project_dir, brief)):
        origine = ("'monl retouche' n'a pas écrit sa consigne" if retouche_mode
                   else "lancer d'abord 'monl update'" if update_mode
                   else "lancer d'abord 'monl compile'")
        raise fondations.FrontendAIError(f"{brief} absent du projet — {origine}.")
    gabarit = RETOUCHE_INSTRUCTION if retouche_mode else CLAUDE_CODE_INSTRUCTION
    instruction = gabarit.format(brief=brief)

    last_errors = []
    for attempt in (1, 2):
        if attempt == 2:
            say(f" -> Correction automatique : erreurs renvoyées à {nom} (1 seule fois)…")
            instruction = (gabarit.format(brief=brief)
                           + " Ta précédente tentative a échoué à la vérification "
                             "monl, corrige le frontend en conséquence : "
                           + " ; ".join(last_errors))
        say(f" -> {nom} travaille dans {project_dir} (tentative {attempt}/2)…")
        before = _fingerprint_protected(project_dir)
        front_avant = _fingerprint_frontend(project_dir)
        started = time.monotonic()
        # POINT 97 : la réponse de l'agent est CONSERVÉE. Elle était jetée, et
        # c'est précisément ce qu'il faut lire quand rien n'a bougé : un agent
        # qui décline explique pourquoi — la consigne de retouche lui demande
        # même de le faire — et monl affichait à la place une hypothèse fausse
        # (« reformuler en nommant l'écran »), sur une demande qui les nommait.
        reponse_agent = run_cli_agent(
            project_dir, instruction, max_turns=max_turns,
            command=command, agent=agent, agent_command=agent_command)
        agent_usage = type("AgentUsage", (), {
            "provider_name": "agent",
            "model": agent if agent in CLI_AGENTS else "custom",
        })()
        fournisseurs._record_provider_usage(
            project_dir, agent_usage, operation=("retouche" if retouche_mode else
                                                ("update" if update_mode else "construction")),
            attempt=attempt, run_id=run_id,
            usage={"duration_seconds": round(time.monotonic() - started, 3),
                   "input_tokens": None, "output_tokens": None, "total_tokens": None})

        # Garde-fou : rien d'autre que frontend/ ne doit avoir bougé.
        after = _fingerprint_protected(project_dir)
        touched = sorted(set(before) ^ set(after)
                         | {n for n in before if n in after and before[n] != after[n]})
        if touched:
            say(f" ❌ {nom} a modifié des artefacts protégés : "
                + ", ".join(touched))
            say("    Restaurer depuis votre gestion de versions, puis relancer — "
                "le frontend est le SEUL périmètre autorisé.")
            return False, [f"artefact protégé modifié : {n}" for n in touched]

        if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
            last_errors = ["frontend/index.html absent après l'exécution — le "
                           "point d'entrée exigé par le contrat n'a pas été produit"]
            say(f" ❌ {last_errors[0]}")
            continue

        # POINT 73 : l'agent n'a rien écrit. Un frontend valide préexistant
        # franchit sinon TOUS les contrôles suivants — index.html est là, la
        # cohérence tient, le smoke test passe — et monl annonce une
        # construction qui n'a pas eu lieu. On le dit, plutôt que de féliciter
        # l'agent pour le travail de son prédécesseur.
        if _fingerprint_frontend(project_dir) == front_avant:
            # POINT 93 : sur une RETOUCHE, ne rien changer n'est pas un état
            # neutre — c'est la demande non traitée. L'humain a signalé un
            # défaut qu'il VOIT ; répondre « tout va bien » serait le contraire
            # d'un rapport honnête, et le point 73 dit déjà qu'on ne félicite
            # pas un agent pour le travail de son prédécesseur.
            if retouche_mode:
                say(f" ❌ {nom} n'a modifié AUCUN fichier de frontend/ — la "
                    "retouche demandée n'a pas été faite.")
                explication = (reponse_agent or "").strip()
                if explication:
                    # LE point : deviner à la place de l'agent, c'est ce qui
                    # rendait le message faux. Il a une raison, elle est là.
                    say("    Ce que l'agent répond :")
                    for ligne in explication.splitlines()[-12:]:
                        if ligne.strip():
                            say(f"      {ligne.rstrip()}")
                    say("    Si la demande touche au CONTENU (une rubrique à "
                        "retirer, un texte à structurer),")
                    say("    elle se règle dans la spec puis 'monl update' — "
                        "pas par une retouche d'affichage.")
                else:
                    say("    Reformuler la demande en nommant l'écran et l'élément "
                        "(« les images de la section Tendances sont mal cadrées »)")
                    say("    donne à l'IA de quoi la situer.")
                return False, ["aucune modification du frontend : retouche non appliquée"]
            say(f" ⚠️  {nom} n'a modifié AUCUN fichier de frontend/.")
            say("    Un frontend valide existait déjà : l'agent a jugé qu'il")
            say("    répondait au contrat et n'a rien réécrit. Rien n'est cassé,")
            say("    mais rien n'a été construit non plus.")
            say("    Pour forcer une réécriture, videz frontend/ d'abord ")
            say("    (sauvegardez-le), ou utilisez 'monl frontend --update' pour")
            say("    demander une ÉVOLUTION de l'existant.")
            return True, []

        # La transition est opérée par l'orchestrateur, après le contrôle de
        # périmètre de l'agent : modifier le manifeste ne peut donc pas servir
        # à masquer une écriture hors de frontend/.
        activate_asset_manifest(project_dir)
        say(" -> Re-vérification automatique (cohérence + smoke test)…")
        ok, errors, warnings = check_coherence(project_dir)
        if ok:
            smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
            errors, warnings = smoke_errors, warnings + smoke_warnings
            ok = smoke_ok
        # Même règle que dans la voie API : check_coherence() est l'unique
        # collecte des erreurs de complétude pour cette vérification.
        for w in warnings:
            say(f" ⚠️  {w}")
        if image_failures:
            for error in errors:
                say(f" ❌ {error}")
            say(" ❌ Livraison refusée : le manifeste reste l'autorité pour les "
                "images planifiées ; relancez après disponibilité du fournisseur.")
            return False, errors
        if ok:
            say(f" ✅ Frontend construit par {nom} et vérifié : 'monl run' est prêt.")
            return True, []
        last_errors = errors
        for e in errors:
            say(f" ❌ {e}")

    say(" ❌ Échec après correction — les fichiers restent dans frontend/ pour "
        "inspection ; 'monl run' refusera de lancer tant que le smoke test échoue.")
    return False, last_errors

def generate_with_claude_code(project_dir, update_mode=False, say=print,
                              command=None, max_turns=DEFAULT_MAX_TURNS):
    """Nom d'origine (point 43), conservé : la voie Claude Code est un cas
    particulier de generate_with_cli_agent."""
    return generate_with_cli_agent(project_dir, update_mode=update_mode, say=say,
                                   command=command, max_turns=max_turns,
                                   agent="claude-code")
