"""Les fournisseurs d'IA, et le seul endroit qui appelle le réseau."""

import json
import os
import re
import time
from datetime import datetime, timezone

from . import fondations

DEFAULT_MODEL = "claude-sonnet-4-6"

DEFAULT_MAX_OUTPUT_TOKENS = 16_000

# Un fichier peut encore contenir plusieurs milliers de lignes de CSS/JS et
# un modèle de raisonnement consomme une partie du plafond avant son JSON.
# Le découpage limite la taille totale de la réponse ; il ne faut pas limiter
# chaque pièce au plafond qui a cassé la réponse monolithique.
DEFAULT_CHUNK_MAX_OUTPUT_TOKENS = 8_000

# Une réponse JSON tronquée ne doit pas faire perdre les morceaux précédents.
# Deux reprises suffisent à corriger une coupe sans transformer un appel en
# boucle ouverte ; la hausse du plafond est explicite et reste bornée.
CHUNK_MAX_RETRIES = 2

# Le facteur DOIT amener la dernière reprise sur la borne ci-dessous, sinon
# celle-ci ne contraint jamais rien — une constante qui ne produit rien est
# ce que le point 85 interdit. À 1,5, l'échelle montait 8 000 → 12 000 →
# 18 000 et les 32 000 déclarés n'étaient jamais atteints ; à 2,0 elle monte
# 8 000 → 16 000 → 32 000. Un test tient cet accord entre les trois nombres.
CHUNK_RETRY_OUTPUT_TOKEN_FACTOR = 2.0

CHUNK_RETRY_MAX_OUTPUT_TOKENS = 32_000

RESPONSE_FORMAT_INSTRUCTIONS = """
## Format de réponse EXIGÉ
Répondre UNIQUEMENT avec un objet JSON, sans préambule ni balises Markdown :
{"files": {"index.html": "<contenu complet>", "app.js": "<contenu complet>", ...}}
Chemins relatifs à frontend/ (pas de sous-dossier remontant, pas de chemin
absolu). Extensions autorisées : .html, .css, .js, .svg, .json.
'index.html' est obligatoire.
Les images matricielles du manifeste sont déjà écrites dans le dossier
d'assets ; elles ne sont pas des fichiers texte à rendre dans cette réponse.
"""

def _requests_module():
    """Charge le client HTTP uniquement pour l'extra ``.[ai]``."""
    try:
        import requests
    except ImportError as exc:
        raise fondations.FrontendAIError(
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
        raise fondations.FrontendAIError("MONL_AI_MAX_TOKENS doit être un entier positif.") from exc
    if value <= 0:
        raise fondations.FrontendAIError("MONL_AI_MAX_TOKENS doit être un entier positif.")
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
        raise fondations.FrontendAIError(
            "MONL_AI_CHUNK_MAX_TOKENS doit être un entier positif.") from exc
    if value <= 0:
        raise fondations.FrontendAIError("MONL_AI_CHUNK_MAX_TOKENS doit être un entier positif.")
    return value

# ------------------------------------------------------------- providers --
def claude_provider(model=DEFAULT_MODEL):
    """Fournisseur API Anthropic. La clé vient de ANTHROPIC_API_KEY —
    jamais d'un fichier du projet, jamais en argument de ligne de commande
    (elle finirait dans l'historique shell)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise fondations.FrontendAIError(
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
            raise fondations.FrontendAIError(f"API Anthropic : {resp.status_code} — {resp.text[:300]}")
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

_YANDEX_REASONING_EFFORTS = ("low", "medium", "high")

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
        raise fondations.FrontendAIError(
            "base_url manquante — préciser MONL_AI_BASE_URL pour "
            f"'--provider {GENERIC_PROVIDER}', ou choisir un fournisseur "
            "de la table : " + ", ".join(sorted(OPENAI_COMPATIBLE)))
    if not model:
        raise fondations.FrontendAIError(
            "modèle manquant — préciser '--model <identifiant>'. monl ne code "
            "aucun modèle par défaut hors voie Anthropic : les catalogues "
            "changent, et un identifiant périmé en dur donnerait un 404 "
            "obscur au lieu de ce message.")
    api_key = os.environ.get(key_env)
    if not api_key and key_required:
        raise fondations.FrontendAIError(
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
            raise fondations.FrontendAIError(
                f"API {base_url} inaccessible ou trop lente : {exc}. "
                "Réessayer, ou réduire MONL_AI_MAX_TOKENS.") from exc
        if resp.status_code != 200:
            raise fondations.FrontendAIError(f"API {base_url} : {resp.status_code} — {resp.text[:300]}")
        payload = resp.json()
        choices = payload.get("choices", [])
        if not choices:
            raise fondations.FrontendAIError(f"API {base_url} : réponse sans 'choices' — {resp.text[:300]}")
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
                raise fondations.FrontendAIError(
                    f"{key_env} absent de l'environnement — exporter la clé "
                    "avant 'monl frontend' (jamais en argument : le shell "
                    "l'archiverait).")
            folder = os.environ.get("YANDEX_FOLDER_ID")
            if not folder:
                raise fondations.FrontendAIError(
                    "YANDEX_FOLDER_ID absent de l'environnement — c'est "
                    "l'identifiant du dossier Yandex Cloud qui porte le modèle.")
            model_uri = model
            if model and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", model):
                model_uri = f"gpt://{folder}/{model}"
            # DeepSeek V4 Flash sait raisonner, mais le raisonnement interne
            # consomme le même plafond que le JSON de fichiers. Pour une
            # sortie structurée, la vérification Monl est le raisonnement :
            # ne rien envoyer par défaut rend la construction fiable et
            # laisse une surcharge explicite pour les cas qui en ont besoin.
            raw_reasoning_effort = os.environ.get("MONL_YANDEX_REASONING_EFFORT")
            reasoning_effort = ((raw_reasoning_effort or "").strip()
                                if raw_reasoning_effort is not None else None)
            if reasoning_effort == "":
                # Compatibilité : « none » reste un alias explicite pour
                # omettre le champ, même si Yandex ne l'accepte pas lui-même.
                reasoning_effort = "none"
            if reasoning_effort not in (*_YANDEX_REASONING_EFFORTS, "none", None):
                allowed = ", ".join(_YANDEX_REASONING_EFFORTS)
                raise fondations.FrontendAIError(
                    "MONL_YANDEX_REASONING_EFFORT invalide : "
                    f"{reasoning_effort!r}. Valeurs permises : {allowed} "
                    "(ou 'none' pour omettre le champ).")
            extra_body = {
                "temperature": 0.3,
                # Certains modèles AI Studio comptent leur raisonnement
                # interne dans le plafond de complétion. Ici le résultat
                # est un fichier, pas une question à résoudre : réserver
                # ce budget au HTML/CSS/JS évite un JSON tronqué.
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "frontend_files",
                        "description": "Fichiers statiques du frontend.",
                        "schema": _FRONTEND_FILES_SCHEMA,
                        "strict": True,
                    },
                },
            }
            if reasoning_effort in _YANDEX_REASONING_EFFORTS:
                extra_body["reasoning_effort"] = reasoning_effort
            provider = openai_provider(
                model=model_uri, base_url=base_url, key_env=key_env,
                auth_scheme="Api-Key", extra_headers={"OpenAI-Project": folder},
                provider_name=name, extra_body=extra_body)
            # Yandex attend l'URI complète sur le fil, mais l'identifiant de
            # modèle lisible est la clé de la télémétrie et de ses regroupements.
            provider.model = model
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

def _record_provider_usage(project_dir, provider, operation, attempt, *,
                           run_id, stage=None, retry=None, usage=None):
    """Conserve les compteurs de coût, jamais le prompt, la réponse ou la clé.

    ``run_id`` est OBLIGATOIRE : sans lui, deux exécutions successives donnent
    des événements indiscernables et « ce que ce site a coûté » cesse d'être
    calculable — le défaut que cette colonne vient fermer. Un repli qui en
    fabriquerait un par événement serait pire que l'absence : le rapport
    montrerait autant d'exécutions que d'appels, et il aurait l'air juste.
    """
    usage = usage if usage is not None else getattr(provider, "last_usage", None)
    usage = usage or {}
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "provider": getattr(provider, "provider_name", "custom"),
        "model": getattr(provider, "model", None),
        "operation": operation,
        "attempt": attempt,
        "duration_seconds": usage.get("duration_seconds"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    if stage is not None:
        event["stage"] = stage
    if retry is not None:
        event["retry"] = retry
    path = os.path.join(project_dir, USAGE_FILENAME)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
