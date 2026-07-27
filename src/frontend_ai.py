# ─────────────────────────────────────────────────────────────────────
# GÉNÉRATION DU FRONTEND PAR IA — pivot orchestrateur, point 4 : fermer
# complètement la boucle. 'monl frontend' envoie le brief
# (FRONTEND_PROMPT.md, ou FRONTEND_UPDATE_PROMPT.md + fichiers existants en
# mode --update) à une IA spécialisée, écrit les fichiers rendus dans
# frontend/, puis RE-VÉRIFIE automatiquement l'ensemble (cohérence statique
# + smoke test comportemental). En cas d'échec, les erreurs constatées sont
# renvoyées UNE FOIS au modèle pour correction : jamais de boucle infinie,
# jamais d'échec silencieux.
#
# Fournisseurs : 'claude' (API Anthropic, clé dans ANTHROPIC_API_KEY) en
# premier ; l'abstraction est une simple fonction provider(prompt) -> str,
# ce qui rend le module testable par exécution réelle avec un fournisseur
# factice (tests/test_frontend_ai.py) et extensible (GPT ou autre) sans
# toucher à la boucle d'orchestration.
#
# Garde-fous (le frontend rendu vient d'un modèle, il est traité comme une
# entrée non fiable — même philosophie que le garde-fou des blocs 'custom',
# point 4 du journal) :
#   - chemins strictement relatifs, confinés à frontend/ (ni '..' ni '/')
#   - extensions autorisées : .html .css .js .svg .json uniquement
#   - 'index.html' obligatoire, taille totale plafonnée
# ─────────────────────────────────────────────────────────────────────
import json
import os
import re

from frontend_contract import PROMPT_FILENAME

ALLOWED_EXTENSIONS = (".html", ".css", ".js", ".svg", ".json")
MAX_TOTAL_BYTES = 2_000_000
DEFAULT_MODEL = "claude-sonnet-4-6"

RESPONSE_FORMAT_INSTRUCTIONS = """
## Format de réponse EXIGÉ
Répondre UNIQUEMENT avec un objet JSON, sans préambule ni balises Markdown :
{"files": {"index.html": "<contenu complet>", "app.js": "<contenu complet>", ...}}
Chemins relatifs à frontend/ (pas de sous-dossier remontant, pas de chemin
absolu). Extensions autorisées : .html, .css, .js, .svg, .json.
'index.html' est obligatoire.
"""


class FrontendAIError(Exception):
    pass


# ------------------------------------------------------------- providers --
def claude_provider(model=DEFAULT_MODEL):
    """Fournisseur API Anthropic. La clé vient de ANTHROPIC_API_KEY —
    jamais d'un fichier du projet, jamais en argument de ligne de commande
    (elle finirait dans l'historique shell)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise FrontendAIError(
            "ANTHROPIC_API_KEY absent de l'environnement — exporter la clé "
            "avant 'monl frontend --provider claude'.")

    def call(prompt):
        import requests
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 16000,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=300)
        if resp.status_code != 200:
            raise FrontendAIError(f"API Anthropic : {resp.status_code} — {resp.text[:300]}")
        blocks = resp.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return call


PROVIDERS = {"claude": claude_provider}


# ------------------------------------------------------- parsing + gardes --
def parse_files_payload(raw_text):
    """Extrait {chemin: contenu} de la réponse du modèle, avec les mêmes
    garde-fous que pour toute entrée non fiable."""
    text = raw_text.strip()
    # Tolérance aux clôtures Markdown malgré la consigne (les modèles en
    # remettent parfois) — on retire une éventuelle paire de balises.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise FrontendAIError(f"réponse du modèle illisible (JSON attendu) : {e}") from e
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise FrontendAIError("réponse du modèle sans clé 'files' exploitable")
    if "index.html" not in files:
        raise FrontendAIError("'index.html' absent de la réponse (obligatoire)")

    total = 0
    for path, content in files.items():
        norm = path.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            raise FrontendAIError(f"chemin refusé (doit rester dans frontend/) : {path}")
        if not norm.endswith(ALLOWED_EXTENSIONS):
            raise FrontendAIError(f"extension refusée : {path}")
        if not isinstance(content, str):
            raise FrontendAIError(f"contenu non textuel pour : {path}")
        total += len(content.encode("utf-8"))
    if total > MAX_TOTAL_BYTES:
        raise FrontendAIError(f"réponse trop volumineuse ({total} octets)")
    return files


def _write_files(project_dir, files):
    frontend_dir = os.path.join(project_dir, "frontend")
    os.makedirs(frontend_dir, exist_ok=True)
    for path, content in files.items():
        dest = os.path.join(frontend_dir, path.replace("\\", "/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
    return frontend_dir


def _read_existing_frontend(project_dir):
    frontend_dir = os.path.join(project_dir, "frontend")
    snapshot = {}
    if not os.path.isdir(frontend_dir):
        return snapshot
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, frontend_dir)
            if name.endswith(ALLOWED_EXTENSIONS):
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    snapshot[rel] = fh.read()
    return snapshot


# ------------------------------------------------------------ orchestration --
def build_generation_prompt(project_dir, update_mode):
    with open(os.path.join(project_dir, PROMPT_FILENAME), encoding="utf-8") as fh:
        base_prompt = fh.read()
    if not update_mode:
        return base_prompt + RESPONSE_FORMAT_INSTRUCTIONS

    update_path = os.path.join(project_dir, "FRONTEND_UPDATE_PROMPT.md")
    if not os.path.exists(update_path):
        raise FrontendAIError("--update demandé mais FRONTEND_UPDATE_PROMPT.md est "
                              "absent — lancer d'abord 'monl update'.")
    with open(update_path, encoding="utf-8") as fh:
        delta = fh.read()
    existing = _read_existing_frontend(project_dir)
    files_block = "\n\n".join(
        f"### frontend/{p}\n```\n{c}\n```" for p, c in sorted(existing.items()))
    return (f"{delta}\n\n## Fichiers actuels du frontend (à faire évoluer, "
            f"pas à réécrire de zéro)\n{files_block}\n\n## Rappel du contrat "
            f"d'origine\n{base_prompt}{RESPONSE_FORMAT_INSTRUCTIONS}")


def generate_and_verify(project_dir, provider, update_mode=False, say=print):
    """La boucle complète du point 4 : générer → écrire → RE-VÉRIFIER
    (cohérence + smoke test) → si échec, renvoyer les erreurs au modèle une
    seule fois → re-vérifier. Retourne (ok, erreurs)."""
    from cli import check_coherence
    from smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    prompt = build_generation_prompt(project_dir, update_mode)

    last_errors = []
    for attempt in (1, 2):
        if attempt == 2:
            say(" -> Correction automatique : erreurs renvoyées au modèle (1 seule fois)…")
            prompt = (prompt + "\n\n## ÉCHEC DE LA VÉRIFICATION — À CORRIGER\n"
                      "Votre précédente réponse a échoué à la vérification monl :\n"
                      + "\n".join(f"- {e}" for e in last_errors)
                      + "\nRendre une version corrigée, même format de réponse.")
        say(f" -> Génération du frontend par l'IA (tentative {attempt}/2)…")
        files = parse_files_payload(provider(prompt))
        _write_files(project_dir, files)
        say(f" -> {len(files)} fichier(s) écrits dans frontend/ "
            f"({', '.join(sorted(files))})")

        say(" -> Re-vérification automatique (cohérence + smoke test)…")
        ok, errors, warnings = check_coherence(project_dir)
        if ok:
            smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
            errors, warnings = smoke_errors, warnings + smoke_warnings
            ok = smoke_ok
        for w in warnings:
            say(f" ⚠️  {w}")
        if ok:
            say(" ✅ Frontend généré et vérifié : l'ensemble est cohérent et fonctionne.")
            return True, []
        last_errors = errors
        for e in errors:
            say(f" ❌ {e}")

    say(" ❌ Le frontend généré échoue encore après correction — les fichiers "
        "sont conservés dans frontend/ pour inspection, mais 'monl run' "
        "refusera de lancer tant que le smoke test échoue.")
    return False, last_errors


# ─────────────────────────────────────────────────────────────────────
# IMPORT MANUEL — la voie SANS clé API (point 42 du journal). Le cas le
# plus courant : l'utilisateur a un abonnement Claude (claude.ai) mais pas
# de clé. Le flux devient :
#   1. copier FRONTEND_PROMPT.md dans la conversation Claude
#   2. télécharger ce que Claude produit (zip, index.html, ou dossier)
#   3. 'monl import <téléchargement> [projet]' — installation dans
#      frontend/ avec les MÊMES garde-fous que la voie API (extensions en
#      liste blanche, confinement, index.html obligatoire, taille
#      plafonnée), puis la MÊME re-vérification (cohérence + smoke test).
# Pas d'auto-correction ici : l'humain est déjà dans la boucle — en cas
# d'échec, les erreurs sont affichées, prêtes à être recollées dans la
# conversation Claude pour obtenir un correctif, puis réimporter.
# ─────────────────────────────────────────────────────────────────────
import shutil
import tempfile
import zipfile


def _collect_from_directory(root):
    """Ramène un dossier au format {chemin relatif: contenu}, filtré par la
    liste blanche d'extensions. Racine intelligente : si index.html vit dans
    un sous-dossier (zip Claude du type 'mon-app/index.html'), c'est CE
    sous-dossier qui devient la racine — le moins profond gagne."""
    index_candidates = []
    for dirpath, _dirs, names in os.walk(root):
        if "index.html" in names:
            index_candidates.append(dirpath)
    if not index_candidates:
        raise FrontendAIError("aucun 'index.html' trouvé dans la source — "
                              "c'est le point d'entrée exigé par le contrat.")
    base = min(index_candidates, key=lambda p: len(os.path.relpath(p, root).split(os.sep)))

    files, skipped = {}, []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            if not rel.endswith(ALLOWED_EXTENSIONS):
                skipped.append(rel)
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                files[rel] = fh.read()
    return files, skipped


def load_frontend_source(source):
    """Accepte les formes sous lesquelles un frontend revient d'une
    conversation Claude : un .zip téléchargé, un index.html seul, un dossier
    déjà décompressé, ou le JSON {"files": ...} (même format que l'API).
    Retourne ({chemin: contenu}, [fichiers ignorés])."""
    source = os.path.abspath(source)
    if not os.path.exists(source):
        raise FrontendAIError(f"source introuvable : {source}")

    if os.path.isdir(source):
        return _collect_from_directory(source)

    low = source.lower()
    if low.endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="monl_import_")
        try:
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    norm = info.filename.replace("\\", "/")
                    # Protection zip-slip : rien ne sort du dossier d'extraction.
                    if norm.startswith("/") or ".." in norm.split("/"):
                        raise FrontendAIError(f"archive refusée : chemin suspect '{info.filename}'")
                zf.extractall(tmp)
            return _collect_from_directory(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if low.endswith((".html", ".htm")):
        with open(source, encoding="utf-8", errors="replace") as fh:
            return {"index.html": fh.read()}, []

    if low.endswith((".json", ".txt")):
        with open(source, encoding="utf-8", errors="replace") as fh:
            return parse_files_payload(fh.read()), []

    raise FrontendAIError(f"format non reconnu : {os.path.basename(source)} "
                          "(attendu : .zip, .html, dossier, ou JSON {'files': ...})")


def import_and_verify(project_dir, source, say=print):
    """'monl import' : installer la source dans frontend/ puis re-vérifier
    exactement comme la voie API. Retourne (ok, erreurs)."""
    from cli import check_coherence
    from smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    files, skipped = load_frontend_source(source)

    # Mêmes garde-fous que la réponse d'un modèle : la source vient d'une
    # conversation, elle est traitée comme une entrée non fiable.
    total = sum(len(c.encode("utf-8")) for c in files.values())
    if total > MAX_TOTAL_BYTES:
        raise FrontendAIError(f"source trop volumineuse ({total} octets)")
    if "index.html" not in files:
        raise FrontendAIError("'index.html' absent après filtrage — point d'entrée obligatoire.")

    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        backup = frontend_dir + ".precedent"
        shutil.rmtree(backup, ignore_errors=True)
        os.rename(frontend_dir, backup)
        say(" -> Frontend existant conservé dans frontend.precedent/ (rien n'est perdu).")
    _write_files(project_dir, files)
    say(f" -> {len(files)} fichier(s) installés dans frontend/ ({', '.join(sorted(files))})")
    for rel in skipped:
        say(f" ⚠️  ignoré (extension hors liste blanche .html/.css/.js/.svg/.json) : {rel}")

    say(" -> Re-vérification automatique (cohérence + smoke test)…")
    ok, errors, warnings = check_coherence(project_dir)
    if ok:
        smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
        errors, warnings = smoke_errors, warnings + smoke_warnings
        ok = smoke_ok
    for w in warnings:
        say(f" ⚠️  {w}")
    if ok:
        say(" ✅ Frontend importé et vérifié : 'monl run' est prêt.")
        return True, []
    for e in errors:
        say(f" ❌ {e}")
    say(" ❌ Vérification échouée. Recollez les erreurs ci-dessus dans votre "
        "conversation Claude, demandez un correctif, puis réimportez "
        "(les fichiers restent dans frontend/ pour inspection).")
    return False, errors


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
import hashlib
import subprocess

PROTECTED_ARTEFACTS = ("spec.ml", "app.py", "schema.sql", "sandbox_ai.py",
                       "frontend_contract.json", "FRONTEND_PROMPT.md",
                       "monl.json", ".jwt_secret")

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


def _fingerprint_protected(project_dir):
    prints = {}
    for name in PROTECTED_ARTEFACTS:
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                prints[name] = hashlib.sha256(fh.read()).hexdigest()
    return prints


def run_claude_code(project_dir, instruction, max_turns=DEFAULT_MAX_TURNS,
                    command=None):
    """Invoque 'claude -p' dans le dossier du projet. 'command' est
    injectable pour les tests (exécutable factice) — même approche que le
    fournisseur factice de la voie API : l'orchestration s'exécute pour de
    vrai, seul l'agent est simulé.

    POINT 62 : l'épuisement du budget de tours n'est PAS une erreur
    d'exécution. L'agent a pu écrire un frontend complet au tour 39 et
    dépasser au 40e ; le traiter comme un échec dur jetait un travail que la
    vérification aurait peut-être accepté, et privait la boucle de sa passe
    de correction. Rendu comme un avertissement, la suite tranche sur pièces."""
    binary = command or shutil.which("claude")
    if not binary:
        raise FrontendAIError(
            "l'exécutable 'claude' (Claude Code) est introuvable — installer "
            "Claude Code puis s'authentifier avec l'abonnement : voir "
            "https://docs.claude.com/en/docs/claude-code/overview")
    proc = subprocess.run(
        [binary, "-p", instruction,
         "--permission-mode", "acceptEdits",
         "--max-turns", str(max_turns)],
        cwd=project_dir, capture_output=True, text=True, timeout=1800)
    sortie = (proc.stderr or proc.stdout) or ""
    if proc.returncode != 0:
        if "max turns" in sortie.lower():
            return sortie          # budget épuisé : la vérification tranchera
        raise FrontendAIError("Claude Code a terminé en erreur : "
                              + sortie[-400:])
    return proc.stdout


def generate_with_claude_code(project_dir, update_mode=False, say=print,
                              command=None, max_turns=DEFAULT_MAX_TURNS):
    """La boucle du point 4, version Claude Code : exécuter l'agent dans le
    dossier cible → vérifier les artefacts protégés → re-vérifier (cohérence
    + smoke test) → une correction au plus. Retourne (ok, erreurs)."""
    from cli import check_coherence
    from smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    brief = "FRONTEND_UPDATE_PROMPT.md" if update_mode else "FRONTEND_PROMPT.md"
    if not os.path.exists(os.path.join(project_dir, brief)):
        raise FrontendAIError(f"{brief} absent du projet — lancer d'abord "
                              + ("'monl update'." if update_mode else "'monl compile'."))
    instruction = CLAUDE_CODE_INSTRUCTION.format(brief=brief)

    last_errors = []
    for attempt in (1, 2):
        if attempt == 2:
            say(" -> Correction automatique : erreurs renvoyées à Claude Code (1 seule fois)…")
            instruction = (CLAUDE_CODE_INSTRUCTION.format(brief=brief)
                           + " Ta précédente tentative a échoué à la vérification "
                             "monl, corrige le frontend en conséquence : "
                           + " ; ".join(last_errors))
        say(f" -> Claude Code travaille dans {project_dir} (tentative {attempt}/2)…")
        before = _fingerprint_protected(project_dir)
        run_claude_code(project_dir, instruction, max_turns=max_turns, command=command)

        # Garde-fou : rien d'autre que frontend/ ne doit avoir bougé.
        after = _fingerprint_protected(project_dir)
        touched = sorted(set(before) ^ set(after)
                         | {n for n in before if n in after and before[n] != after[n]})
        if touched:
            say(" ❌ Claude Code a modifié des artefacts protégés : "
                + ", ".join(touched))
            say("    Restaurer depuis votre gestion de versions, puis relancer — "
                "le frontend est le SEUL périmètre autorisé.")
            return False, [f"artefact protégé modifié : {n}" for n in touched]

        if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
            last_errors = ["frontend/index.html absent après l'exécution — le "
                           "point d'entrée exigé par le contrat n'a pas été produit"]
            say(f" ❌ {last_errors[0]}")
            continue

        say(" -> Re-vérification automatique (cohérence + smoke test)…")
        ok, errors, warnings = check_coherence(project_dir)
        if ok:
            smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
            errors, warnings = smoke_errors, warnings + smoke_warnings
            ok = smoke_ok
        for w in warnings:
            say(f" ⚠️  {w}")
        if ok:
            say(" ✅ Frontend construit par Claude Code et vérifié : 'monl run' est prêt.")
            return True, []
        last_errors = errors
        for e in errors:
            say(f" ❌ {e}")

    say(" ❌ Échec après correction — les fichiers restent dans frontend/ pour "
        "inspection ; 'monl run' refusera de lancer tant que le smoke test échoue.")
    return False, last_errors
