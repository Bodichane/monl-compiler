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
import time
from datetime import datetime, timezone

from .design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    GENERATED_MARKER,
    activate_asset_manifest,
)
from .errors import FrontendError
from .frontend_contract import PROMPT_FILENAME

ALLOWED_EXTENSIONS = (".html", ".css", ".js", ".svg", ".json")
MAX_TOTAL_BYTES = 2_000_000
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_OUTPUT_TOKENS = 16_000
# Un fichier peut encore contenir plusieurs milliers de lignes de CSS/JS et
# un modèle de raisonnement consomme une partie du plafond avant son JSON.
# Le découpage limite la taille totale de la réponse ; il ne faut pas limiter
# chaque pièce au plafond qui a cassé la réponse monolithique.
DEFAULT_CHUNK_MAX_OUTPUT_TOKENS = 16_000

# Les deux briefs d'ÉVOLUTION (par opposition à FRONTEND_PROMPT.md, qui décrit
# une construction neuve). Nommés ici plutôt que chez leur producteur : c'est
# frontend_ai qui les consomme, et cli.py les importe — l'inverse ferait
# dépendre la couche IA de la couche commande.
UPDATE_PROMPT_FILENAME = "FRONTEND_UPDATE_PROMPT.md"
RETOUCHE_PROMPT_FILENAME = "FRONTEND_RETOUCHE_PROMPT.md"

RESPONSE_FORMAT_INSTRUCTIONS = """
## Format de réponse EXIGÉ
Répondre UNIQUEMENT avec un objet JSON, sans préambule ni balises Markdown :
{"files": {"index.html": "<contenu complet>", "app.js": "<contenu complet>", ...}}
Chemins relatifs à frontend/ (pas de sous-dossier remontant, pas de chemin
absolu). Extensions autorisées : .html, .css, .js, .svg, .json.
'index.html' est obligatoire.
"""


class FrontendAIError(FrontendError):
    pass


def _requests_module():
    """Charge le client HTTP uniquement pour l'extra ``.[ai]``."""
    try:
        import requests
    except ImportError as exc:
        raise FrontendAIError(
            "Le fournisseur frontend par API nécessite l'extra optionnel : "
            "pip install 'monl-compiler[ai]'."
        ) from exc
    return requests


def _max_output_tokens():
    """Plafond API réglable, distinct du budget de tours des agents CLI."""
    raw = (os.environ.get("MONL_AI_MAX_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise FrontendAIError("MONL_AI_MAX_TOKENS doit être un entier positif.") from exc
    if value <= 0:
        raise FrontendAIError("MONL_AI_MAX_TOKENS doit être un entier positif.")
    return value


def _chunk_max_output_tokens():
    """Plafond par fichier pour les modèles dont la réponse complète est
    trop longue pour tenir dans un seul JSON (notamment DeepSeek via Yandex)."""
    raw = (os.environ.get("MONL_AI_CHUNK_MAX_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_CHUNK_MAX_OUTPUT_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise FrontendAIError(
            "MONL_AI_CHUNK_MAX_TOKENS doit être un entier positif.") from exc
    if value <= 0:
        raise FrontendAIError("MONL_AI_CHUNK_MAX_TOKENS doit être un entier positif.")
    return value


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
        requests = _requests_module()
        started = time.monotonic()
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": _max_output_tokens(),
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=300)
        if resp.status_code != 200:
            raise FrontendAIError(f"API Anthropic : {resp.status_code} — {resp.text[:300]}")
        payload = resp.json()
        blocks = payload.get("content", [])
        usage = payload.get("usage") or {}
        call.last_usage = {
            "duration_seconds": round(time.monotonic() - started, 3),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": ((usage.get("input_tokens") or 0)
                             + (usage.get("output_tokens") or 0)),
        }
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    call.provider_name = "claude"
    call.model = model
    call.last_usage = None
    return call


# ─────────────────────────────────────────────────────────────────────
# POINT 69 : « n'importe quelle clé API ». Deux dialectes couvrent le
# marché — Anthropic Messages (ci-dessus) et OpenAI Chat Completions, que
# parlent Groq, OpenAI, OpenRouter, DeepSeek, Mistral, xAI, Together et
# tout serveur local (Ollama, llama.cpp, vLLM). Plutôt qu'un fournisseur
# par marque — code dupliqué, liste toujours en retard d'un acteur — un
# seul fournisseur paramétré, et une table de préréglages qui n'épargne
# que la frappe de l'URL et du nom de variable.
#
# AUCUN modèle par défaut n'est codé pour ces fournisseurs, à dessein :
# les catalogues changent tous les mois, et un identifiant périmé en dur
# transforme une erreur claire ('--model manquant') en 404 obscur six mois
# plus tard. '--model' est donc exigé hors voie Anthropic.
# ─────────────────────────────────────────────────────────────────────
OPENAI_COMPATIBLE = {
    # nom            base_url                         variable d'environnement portant la clé
    "groq":       ("https://api.groq.com/openai/v1",  "GROQ_API_KEY"),
    "openai":     ("https://api.openai.com/v1",       "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",    "OPENROUTER_API_KEY"),
    "deepseek":   ("https://api.deepseek.com",        "DEEPSEEK_API_KEY"),
    "mistral":    ("https://api.mistral.ai/v1",       "MISTRAL_API_KEY"),
    "together":   ("https://api.together.xyz/v1",     "TOGETHER_API_KEY"),
    "xai":        ("https://api.x.ai/v1",             "XAI_API_KEY"),
    "yandex":     ("https://ai.api.cloud.yandex.net/v1", "YANDEX_API_KEY"),
    # Serveur local : pas de clé, mais l'en-tête Bearer reste accepté.
    "ollama":     ("http://localhost:11434/v1",       "OLLAMA_API_KEY"),
}

# Échappatoire totale, pour un point de terminaison que la table ignore :
# --provider openai-compatible + MONL_AI_BASE_URL (+ MONL_AI_API_KEY).
GENERIC_PROVIDER = "openai-compatible"

_FRONTEND_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
    "required": ["files"],
    "additionalProperties": False,
}


def openai_provider(model=None, base_url=None, key_env="MONL_AI_API_KEY",
                    key_required=True, auth_scheme="Bearer", extra_headers=None,
                    provider_name=None, extra_body=None):
    """Fournisseur au dialecte OpenAI (POST {base_url}/chat/completions).

    Même contrat que claude_provider : rend une fonction prompt -> texte.
    La clé vient de l'environnement, JAMAIS d'un argument de ligne de
    commande — elle finirait dans l'historique du shell (règle posée pour
    la voie Anthropic, elle vaut pour toutes)."""
    if not base_url:
        raise FrontendAIError(
            "base_url manquante — préciser MONL_AI_BASE_URL pour "
            f"'--provider {GENERIC_PROVIDER}', ou choisir un fournisseur "
            "de la table : " + ", ".join(sorted(OPENAI_COMPATIBLE)))
    if not model:
        raise FrontendAIError(
            "modèle manquant — préciser '--model <identifiant>'. monl ne code "
            "aucun modèle par défaut hors voie Anthropic : les catalogues "
            "changent, et un identifiant périmé en dur donnerait un 404 "
            "obscur au lieu de ce message.")
    api_key = os.environ.get(key_env)
    if not api_key and key_required:
        raise FrontendAIError(
            f"{key_env} absent de l'environnement — exporter la clé avant "
            "'monl frontend' (jamais en argument : le shell l'archiverait).")

    def call(prompt):
        requests = _requests_module()
        started = time.monotonic()
        try:
            resp = requests.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"{auth_scheme} {api_key or 'sans-cle'}",
                         "content-type": "application/json",
                         **(extra_headers or {})},
                json={"model": model,
                      "max_tokens": (getattr(call, "max_output_tokens", None)
                                     or _max_output_tokens()),
                      "messages": [{"role": "user", "content": prompt}],
                      **(extra_body or {})},
                timeout=300)
        except requests.RequestException as exc:
            raise FrontendAIError(
                f"API {base_url} inaccessible ou trop lente : {exc}. "
                "Réessayer, ou réduire MONL_AI_MAX_TOKENS.") from exc
        if resp.status_code != 200:
            raise FrontendAIError(f"API {base_url} : {resp.status_code} — {resp.text[:300]}")
        payload = resp.json()
        choices = payload.get("choices", [])
        if not choices:
            raise FrontendAIError(f"API {base_url} : réponse sans 'choices' — {resp.text[:300]}")
        usage = payload.get("usage") or {}
        call.last_usage = {
            "duration_seconds": round(time.monotonic() - started, 3),
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return choices[0].get("message", {}).get("content") or ""
    call.provider_name = provider_name or "openai-compatible"
    call.model = model
    call.last_usage = None
    call.max_output_tokens = None
    return call


def _openai_preset(name):
    """Construit le fournisseur d'un préréglage de OPENAI_COMPATIBLE."""
    base_url, key_env = OPENAI_COMPATIBLE[name]

    def build(model=None):
        if name == "yandex":
            if not os.environ.get(key_env):
                raise FrontendAIError(
                    f"{key_env} absent de l'environnement — exporter la clé "
                    "avant 'monl frontend' (jamais en argument : le shell "
                    "l'archiverait).")
            folder = os.environ.get("YANDEX_FOLDER_ID")
            if not folder:
                raise FrontendAIError(
                    "YANDEX_FOLDER_ID absent de l'environnement — c'est "
                    "l'identifiant du dossier Yandex Cloud qui porte le modèle.")
            reasoning_effort = (os.environ.get(
                "MONL_YANDEX_REASONING_EFFORT", "low").strip() or "low")
            provider = openai_provider(
                model=model, base_url=base_url, key_env=key_env,
                auth_scheme="Api-Key", extra_headers={"OpenAI-Project": folder},
                provider_name=name, extra_body={
                    "temperature": 0.3,
                    # Certains modèles AI Studio comptent leur raisonnement
                    # interne dans le plafond de complétion. Ici le résultat
                    # est un fichier, pas une question à résoudre : réserver
                    # ce budget au HTML/CSS/JS évite un JSON tronqué.
                    "reasoning_effort": reasoning_effort,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "frontend_files",
                            "description": "Fichiers statiques du frontend.",
                            "schema": _FRONTEND_FILES_SCHEMA,
                            "strict": True,
                        },
                    },
                })
            # DeepSeek peut produire un frontend riche, mais pas trois gros
            # fichiers dans une seule réponse JSON. Le mode séquentiel est
            # activé au niveau du fournisseur, sans changer le contrat des
            # autres APIs compatibles OpenAI.
            provider.chunked_generation = True
            provider.max_output_tokens = _chunk_max_output_tokens()
            return provider
        return openai_provider(model=model, base_url=base_url, key_env=key_env,
                               key_required=(name != "ollama"), provider_name=name)
    return build


def _generic_openai(model=None):
    """--provider openai-compatible : tout est dans l'environnement."""
    return openai_provider(model=model,
                           base_url=os.environ.get("MONL_AI_BASE_URL"),
                           key_env="MONL_AI_API_KEY",
                           key_required=bool(os.environ.get("MONL_AI_BASE_URL")))


PROVIDERS = {"claude": claude_provider, GENERIC_PROVIDER: _generic_openai}
PROVIDERS.update({name: _openai_preset(name) for name in OPENAI_COMPATIBLE})

USAGE_FILENAME = ".monl_ai_usage.jsonl"


def _record_provider_usage(project_dir, provider, operation, attempt, stage=None):
    """Conserve les compteurs de coût, jamais le prompt, la réponse ou la clé."""
    usage = getattr(provider, "last_usage", None)
    if usage is None:
        return
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": getattr(provider, "provider_name", "custom"),
        "model": getattr(provider, "model", None),
        "operation": operation,
        "attempt": attempt,
        **usage,
    }
    if stage is not None:
        event["stage"] = stage
    path = os.path.join(project_dir, USAGE_FILENAME)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


# ------------------------------------------------------- parsing + gardes --
def _validate_files(files, require_index=True):
    """Valide une map de fichiers sans imposer son format de transport."""
    if not isinstance(files, dict) or not files:
        raise FrontendAIError("réponse du modèle sans clé 'files' exploitable")
    if require_index and "index.html" not in files:
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


def _json_payload(raw_text):
    """Décode une réponse JSON, avec tolérance aux clôtures Markdown."""
    text = raw_text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise FrontendAIError(f"réponse du modèle illisible (JSON attendu) : {e}") from e


def parse_files_payload(raw_text):
    """Extrait {chemin: contenu} de la réponse du modèle, avec les mêmes
    garde-fous que pour toute entrée non fiable."""
    payload = _json_payload(raw_text)
    return _validate_files(payload.get("files"), require_index=True)


def parse_single_file_payload(raw_text, expected_path):
    """Décode la réponse d'une étape de génération séquentielle.

    Le transport reste ``{"files": {…}}`` pour conserver le même contrat
    JSON côté fournisseur, mais une étape ne peut rendre qu'un seul fichier.
    """
    payload = _json_payload(raw_text)
    files = _validate_files(payload.get("files"), require_index=False)
    if set(files) != {expected_path}:
        rendus = ", ".join(sorted(files))
        raise FrontendAIError(
            f"l'étape devait rendre uniquement {expected_path}, reçu : {rendus}")
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


def _project_guidance(project_dir):
    """Ajoute les artefacts de direction préparés par l'auteur au brief IA."""
    blocks = []
    for name in (DESIGN_SYSTEM_FILENAME, DESIGN_SPEC_FILENAME,
                 ASSET_MANIFEST_FILENAME):
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                blocks.append(f"\n\n## {name} — source de vérité\n{fh.read()}")
    return "".join(blocks)


def _design_completeness_errors(project_dir):
    """Contrôles de complétude visuelle propres aux projets qui les déclarent.

    Le contrat Monl vérifie l'API et le fonctionnement. Ce contrôle séparé
    vérifie qu'un projet doté d'un design spec a aussi livré ses assets et ses
    sections obligatoires ; les projets historiques sans manifeste restent
    compatibles.
    """
    manifest_path = os.path.join(project_dir, "ASSET_MANIFEST.json")
    if not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            raw = fh.read()
            if raw.startswith(GENERATED_MARKER):
                raw = "\n".join(raw.splitlines()[1:])
            manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"ASSET_MANIFEST.json illisible : {exc}"]

    # Le compilateur peut préparer le plan avant que le frontend n'existe.
    # Tant que l'orchestrateur n'a pas reçu une construction/importation, ce
    # plan informe l'IA mais ne bloque pas un projet qui possède déjà une
    # interface historique. La transition vers ``active`` est faite après
    # l'écriture du frontend, hors du périmètre de l'agent.
    if manifest.get("generated_by") == "monl" and manifest.get("status") == "planned":
        return []

    errors = []
    frontend_dir = os.path.join(project_dir, "frontend")
    asset_paths = []
    for group in ("products", "editorial"):
        values = manifest.get(group, {})
        if not isinstance(values, dict):
            errors.append(f"ASSET_MANIFEST.json : section '{group}' invalide")
            continue
        asset_paths.extend(values.values())
    for rel in asset_paths:
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            errors.append(f"asset refusé dans le manifeste : {rel}")
            continue
        if not os.path.isfile(os.path.join(frontend_dir, rel)):
            errors.append(f"asset manquant : frontend/{rel}")

    for filename, markers in (manifest.get("required_markers") or {}).items():
        path = os.path.join(frontend_dir, filename)
        if not os.path.isfile(path):
            errors.append(f"fichier visuel obligatoire absent : frontend/{filename}")
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        for marker in markers:
            if marker not in content:
                errors.append(f"section visuelle obligatoire absente : {marker}")
    return errors


# ------------------------------------------------------------ orchestration --
def brief_evolution(update_mode, retouche_mode):
    """Nom du brief d'ÉVOLUTION à donner à l'IA, ou None pour une construction
    neuve (point 93).

    Les deux modes d'évolution ne diffèrent QUE par l'origine du brief : un
    delta de spec pour `monl update`, une phrase humaine pour `monl retouche`.
    Tout le reste — joindre les fichiers actuels, rappeler le contrat,
    re-vérifier, empreindre — leur est commun, et le rester est le but : une
    seconde voie vers l'IA qui aurait ses propres garde-fous serait une voie
    par laquelle les contourner."""
    if retouche_mode:
        return RETOUCHE_PROMPT_FILENAME
    if update_mode:
        return UPDATE_PROMPT_FILENAME
    return None


def build_generation_prompt(project_dir, update_mode, retouche_mode=False):
    with open(os.path.join(project_dir, PROMPT_FILENAME), encoding="utf-8") as fh:
        base_prompt = fh.read() + _project_guidance(project_dir)
    brief = brief_evolution(update_mode, retouche_mode)
    if brief is None:
        return base_prompt + RESPONSE_FORMAT_INSTRUCTIONS

    brief_path = os.path.join(project_dir, brief)
    if not os.path.exists(brief_path):
        origine = ("'monl retouche' n'a pas écrit sa consigne"
                   if retouche_mode else "lancer d'abord 'monl update'")
        raise FrontendAIError(f"{brief} est absent — {origine}.")
    with open(brief_path, encoding="utf-8") as fh:
        delta = fh.read()
    existing = _read_existing_frontend(project_dir)
    files_block = "\n\n".join(
        f"### frontend/{p}\n```\n{c}\n```" for p, c in sorted(existing.items()))
    return (f"{delta}\n\n## Fichiers actuels du frontend (à faire évoluer, "
            f"pas à réécrire de zéro)\n{files_block}\n\n## Rappel du contrat "
            f"d'origine\n{base_prompt}{RESPONSE_FORMAT_INSTRUCTIONS}")


CHUNKED_FRONTEND_FILES = ("index.html", "styles.css", "app.js")


def _chunk_context(files):
    """Rend uniquement les fichiers utiles aux étapes suivantes."""
    morceaux = []
    for path in CHUNKED_FRONTEND_FILES:
        if path in files:
            morceaux.append(f"### frontend/{path}\n```\n{files[path]}\n```")
    return "\n\n".join(morceaux) or "(aucun fichier généré pour le moment)"


def _build_chunk_prompt(base_prompt, target, files):
    """Demande une seule pièce complète du frontend.

    Le brief complet reste présent : le modèle conserve le contrat API et la
    direction produit. Le contexte des fichiers précédents garantit toutefois
    que le CSS et le JS s'accordent sur les mêmes classes et identifiants.
    """
    instructions = {
        "index.html": (
            "Produis maintenant uniquement frontend/index.html. Construis la "
            "structure complète de l'application et de son parcours principal, "
            "ses états vides/chargement/erreur, ses zones de formulaire, de "
            "contenu et de compte selon le contrat, puis charge styles.css et "
            "app.js avec des chemins locaux. Reste très compact : vise environ "
            "900 tokens, avec une structure complète mais peu de texte. "
            "Aucune section décorative longue. Limite dure : termine le JSON "
            "avant 7 000 caractères."
        ),
        "styles.css": (
            "Produis maintenant uniquement frontend/styles.css. Donne un "
            "style complet, dense, responsive et accessible à la structure "
            "index.html ; ne remplace pas le CSS par une librairie externe. "
            "Reste très compact : vise environ 1 200 tokens et réutilise les "
            "sélecteurs plutôt que de dupliquer les règles. Limite dure : "
            "termine le JSON avant 9 000 caractères."
        ),
        "app.js": (
            "Produis maintenant uniquement frontend/app.js. Implémente les "
            "interactions et les appels aux routes autorisées du contrat, "
            "avec états de chargement, erreur, formulaires et authentification "
            "adaptés au type d'application ; n'invente aucune route. Reste "
            "très compact : vise environ 900 tokens et factorise le code. "
            "Limite dure : termine le JSON avant 7 000 caractères."
        ),
    }
    return (
        f"{base_prompt}\n\n"
        "## Génération séquentielle — une seule pièce à la fois\n"
        f"{instructions[target]}\n"
        f"Le fichier cible est exactement : {target}\n"
        "Réponds UNIQUEMENT avec un objet JSON de cette forme, sans Markdown :\n"
        f'{{"files": {{"{target}": "contenu complet du fichier"}}}}\n'
        "Ne rends aucun autre fichier, ne tronque pas le contenu et ne mets "
        "jamais de commentaire hors JSON.\n\n"
        "## Fichiers déjà générés — à respecter\n"
        f"{_chunk_context(files)}"
    )


def _generate_chunked_files(project_dir, provider, base_prompt, operation,
                            attempt, say):
    """Génère puis valide chaque fichier d'un frontend DeepSeek/Yandex."""
    files = _read_existing_frontend(project_dir)
    for target in CHUNKED_FRONTEND_FILES:
        say(f" -> Génération de frontend/{target}…")
        raw = provider(_build_chunk_prompt(base_prompt, target, files))
        _record_provider_usage(project_dir, provider, operation, attempt,
                               stage=target)
        files.update(parse_single_file_payload(raw, target))
    return files


def generate_and_verify(project_dir, provider, update_mode=False, say=print,
                        retouche_mode=False):
    """La boucle complète du point 4 : générer → écrire → RE-VÉRIFIER
    (cohérence + smoke test) → si échec, renvoyer les erreurs au modèle une
    seule fois → re-vérifier. Retourne (ok, erreurs)."""
    from .cli import check_coherence
    from .smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    prompt = build_generation_prompt(project_dir, update_mode, retouche_mode)

    last_errors = []
    for attempt in (1, 2):
        if attempt == 2:
            say(" -> Correction automatique : erreurs renvoyées au modèle (1 seule fois)…")
            prompt = (prompt + "\n\n## ÉCHEC DE LA VÉRIFICATION — À CORRIGER\n"
                      "Votre précédente réponse a échoué à la vérification monl :\n"
                      + "\n".join(f"- {e}" for e in last_errors)
                      + "\nRendre une version corrigée, même format de réponse.")
        say(f" -> Génération du frontend par l'IA (tentative {attempt}/2)…")
        operation = ("retouche" if retouche_mode else
                     ("update" if update_mode else "construction"))
        if getattr(provider, "chunked_generation", False):
            files = _generate_chunked_files(
                project_dir, provider, prompt, operation, attempt, say)
        else:
            raw = provider(prompt)
            _record_provider_usage(project_dir, provider, operation, attempt)
            files = parse_files_payload(raw)
        _write_files(project_dir, files)
        # Un manifeste généré par Monl est seulement un plan tant que le
        # frontend n'existe pas. Après la réponse de l'IA, il devient une
        # obligation vérifiable : les assets et marqueurs attendus entrent
        # ainsi dans la correction automatique avec les erreurs d'API.
        activate_asset_manifest(project_dir)
        say(f" -> {len(files)} fichier(s) écrits dans frontend/ "
            f"({', '.join(sorted(files))})")

        say(" -> Re-vérification automatique (cohérence + smoke test)…")
        ok, errors, warnings = check_coherence(project_dir)
        if ok:
            smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
            errors, warnings = smoke_errors, warnings + smoke_warnings
            ok = smoke_ok
        design_errors = _design_completeness_errors(project_dir)
        if design_errors:
            errors = errors + design_errors
            ok = False
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
    from .cli import check_coherence
    from .smoke_test import run_smoke_test

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
    activate_asset_manifest(project_dir)
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
import shlex
import subprocess

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
            raise FrontendAIError("--agent-command est vide.")
        if not any("{instruction}" in p for p in parts):
            raise FrontendAIError(
                "--agent-command doit contenir {instruction} — sans lui, "
                "l'agent serait lancé sans savoir quoi faire.")
        argv = [p.replace("{instruction}", instruction) for p in parts]
        return argv[0], argv[1:]
    if agent not in CLI_AGENTS:
        raise FrontendAIError(
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
        raise FrontendAIError(
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
        raise FrontendAIError(f"l'agent '{agent}' a terminé en erreur : "
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
                            retouche_mode=False):
    """La boucle du point 4, version agent en ligne de commande : exécuter
    l'agent dans le dossier cible → vérifier les artefacts protégés →
    re-vérifier (cohérence + smoke test) → une correction au plus.
    Retourne (ok, erreurs).

    POINT 69 : le corps est rigoureusement celui écrit pour Claude Code. Un
    agent tiers ne relâche AUCUN garde-fou — c'est le sens de la
    généralisation : ce qui protège le projet ne dépend pas de qui écrit."""
    from .cli import check_coherence
    from .smoke_test import run_smoke_test

    nom = agent_command.split()[0] if agent_command else agent
    project_dir = os.path.abspath(project_dir)
    brief = brief_evolution(update_mode, retouche_mode) or PROMPT_FILENAME
    if not os.path.exists(os.path.join(project_dir, brief)):
        origine = ("'monl retouche' n'a pas écrit sa consigne" if retouche_mode
                   else "lancer d'abord 'monl update'" if update_mode
                   else "lancer d'abord 'monl compile'")
        raise FrontendAIError(f"{brief} absent du projet — {origine}.")
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
        # POINT 97 : la réponse de l'agent est CONSERVÉE. Elle était jetée, et
        # c'est précisément ce qu'il faut lire quand rien n'a bougé : un agent
        # qui décline explique pourquoi — la consigne de retouche lui demande
        # même de le faire — et monl affichait à la place une hypothèse fausse
        # (« reformuler en nommant l'écran »), sur une demande qui les nommait.
        reponse_agent = run_cli_agent(
            project_dir, instruction, max_turns=max_turns,
            command=command, agent=agent, agent_command=agent_command)

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
        for w in warnings:
            say(f" ⚠️  {w}")
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
