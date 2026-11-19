"""The AI providers, and the only place that calls the network."""

import json
import os
import re
import time
from datetime import datetime, timezone

from . import foundations

DEFAULT_MODEL = "claude-sonnet-4-6"

DEFAULT_MAX_OUTPUT_TOKENS = 16_000

# A file can still contain several thousand lines of CSS/JS, and a reasoning
# model uses part of the ceiling before its JSON. Splitting limits the total
# size of the response; each piece must not be limited to the ceiling that
# broke the monolithic response.
DEFAULT_CHUNK_MAX_OUTPUT_TOKENS = 8_000

# A truncated JSON response must not lose the previous pieces. Two retries are
# enough to fix a cut without turning a call into an open loop; raising the
# ceiling is explicit and stays bounded.
CHUNK_MAX_RETRIES = 2

# The factor MUST bring the last retry onto the bound below, otherwise the
# bound never constrains anything — a constant that produces nothing is what
# point 85 forbids. At 1.5, the ladder went 8,000 → 12,000 → 18,000 and the
# declared 32,000 was never reached; at 2.0 it goes 8,000 → 16,000 → 32,000. A
# test holds this agreement between the three numbers.
CHUNK_RETRY_OUTPUT_TOKEN_FACTOR = 2.0

CHUNK_RETRY_MAX_OUTPUT_TOKENS = 32_000

RESPONSE_FORMAT_INSTRUCTIONS = """
## REQUIRED response format
Answer ONLY with a JSON object, with no preamble and no Markdown fences:
{"files": {"index.html": "<complete content>", "app.js": "<complete content>", ...}}
Paths relative to frontend/ (no parent-directory climb, no absolute path).
Allowed extensions: .html, .css, .js, .svg, .json.
'index.html' is required.
The manifest's raster images are already written in the assets folder;
they are not text files to return in this response.
"""

def _requests_module():
    """Loads the HTTP client only for the ``.[ai]`` extra."""
    try:
        import requests
    except ImportError as exc:
        raise foundations.FrontendAIError(
            "The API frontend provider requires the optional extra: "
            "pip install 'monl-compiler[ai]'."
        ) from exc
    return requests

def _max_output_tokens():
    """Configurable API ceiling, distinct from the CLI agents' turn budget."""
    raw = (os.environ.get("MONL_AI_MAX_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise foundations.FrontendAIError("MONL_AI_MAX_TOKENS must be a positive integer.") from exc
    if value <= 0:
        raise foundations.FrontendAIError("MONL_AI_MAX_TOKENS must be a positive integer.")
    return value

def _chunk_max_output_tokens():
    """Per-file ceiling for models whose complete response is too long to fit in
    a single JSON (notably DeepSeek through Yandex)."""
    raw = (os.environ.get("MONL_AI_CHUNK_MAX_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_CHUNK_MAX_OUTPUT_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise foundations.FrontendAIError(
            "MONL_AI_CHUNK_MAX_TOKENS must be a positive integer.") from exc
    if value <= 0:
        raise foundations.FrontendAIError("MONL_AI_CHUNK_MAX_TOKENS must be a positive integer.")
    return value

# ------------------------------------------------------------- providers --
def claude_provider(model=DEFAULT_MODEL):
    """Anthropic API provider. The key comes from ANTHROPIC_API_KEY — never from
    a project file, never as a command line argument (it would end up in the
    shell history)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise foundations.FrontendAIError(
            "ANTHROPIC_API_KEY missing from the environment — export the key "
            "before 'monl frontend --provider claude'.")

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
            raise foundations.FrontendAIError(f"API Anthropic : {resp.status_code} — {resp.text[:300]}")
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
# POINT 69: "any API key". Two dialects cover the market — Anthropic Messages
# (above) and OpenAI Chat Completions, spoken by Groq, OpenAI, OpenRouter,
# DeepSeek, Mistral, xAI, Together and any local server (Ollama, llama.cpp,
# vLLM). Rather than one provider per brand — duplicated code, a list always
# one player behind — a single parameterized provider, and a table of presets
# that only saves typing the URL and the variable name.
#
# NO default model is coded for these providers, on purpose: catalogs change
# every month, and a stale hard-coded identifier turns a clear error ('--model
# missing') into an obscure 404 six months later. '--model' is therefore
# required outside the Anthropic path.
# ─────────────────────────────────────────────────────────────────────
OPENAI_COMPATIBLE = {
    # name           base_url                         environment variable holding the key
    "groq":       ("https://api.groq.com/openai/v1",  "GROQ_API_KEY"),
    "openai":     ("https://api.openai.com/v1",       "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",    "OPENROUTER_API_KEY"),
    "deepseek":   ("https://api.deepseek.com",        "DEEPSEEK_API_KEY"),
    "mistral":    ("https://api.mistral.ai/v1",       "MISTRAL_API_KEY"),
    "together":   ("https://api.together.xyz/v1",     "TOGETHER_API_KEY"),
    "xai":        ("https://api.x.ai/v1",             "XAI_API_KEY"),
    "yandex":     ("https://ai.api.cloud.yandex.net/v1", "YANDEX_API_KEY"),
    # Local server: no key, but the Bearer header is still accepted.
    "ollama":     ("http://localhost:11434/v1",       "OLLAMA_API_KEY"),
}

_YANDEX_REASONING_EFFORTS = ("low", "medium", "high")

# Full escape hatch, for an endpoint the table does not know: --provider
# openai-compatible + MONL_AI_BASE_URL (+ MONL_AI_API_KEY).
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
    """Provider using the OpenAI dialect (POST {base_url}/chat/completions).

    Same contract as claude_provider: returns a prompt -> text function. The
    key comes from the environment, NEVER from a command line argument — it
    would end up in the shell history (a rule set for the Anthropic path, it
    holds for all)."""
    if not base_url:
        raise foundations.FrontendAIError(
            "base_url missing — set MONL_AI_BASE_URL for "
            f"'--provider {GENERIC_PROVIDER}', or choose a provider "
            "from the table: " + ", ".join(sorted(OPENAI_COMPATIBLE)))
    if not model:
        raise foundations.FrontendAIError(
            "model missing — set '--model <identifier>'. monl hard-codes "
            "no default model outside the Anthropic path: catalogs change, "
            "and a stale hard-coded identifier would give an obscure 404 "
            "instead of this message.")
    api_key = os.environ.get(key_env)
    if not api_key and key_required:
        raise foundations.FrontendAIError(
            f"{key_env} missing from the environment — export the key before "
            "'monl frontend' (never as an argument: the shell would record it).")

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
            raise foundations.FrontendAIError(
                f"API {base_url} unreachable or too slow: {exc}. "
                "Try again, or lower MONL_AI_MAX_TOKENS.") from exc
        if resp.status_code != 200:
            raise foundations.FrontendAIError(f"API {base_url}: {resp.status_code} — {resp.text[:300]}")
        payload = resp.json()
        choices = payload.get("choices", [])
        if not choices:
            raise foundations.FrontendAIError(f"API {base_url}: response without 'choices' — {resp.text[:300]}")
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
    """Builds the provider of an OPENAI_COMPATIBLE preset."""
    base_url, key_env = OPENAI_COMPATIBLE[name]

    def build(model=None):
        if name == "yandex":
            if not os.environ.get(key_env):
                raise foundations.FrontendAIError(
                    f"{key_env} missing from the environment — export the key "
                    "before 'monl frontend' (never as an argument: the shell "
                    "would record it).")
            folder = os.environ.get("YANDEX_FOLDER_ID")
            if not folder:
                raise foundations.FrontendAIError(
                    "YANDEX_FOLDER_ID missing from the environment — it is the "
                    "identifier of the Yandex Cloud folder that holds the model.")
            model_uri = model
            if model and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", model):
                model_uri = f"gpt://{folder}/{model}"
            # DeepSeek V4 Flash can reason, but internal reasoning uses the
            # same ceiling as the files JSON. For structured output, Monl's
            # verification is the reasoning: sending nothing by default makes
            # the build reliable and leaves an explicit override for the cases
            # that need it.
            raw_reasoning_effort = os.environ.get("MONL_YANDEX_REASONING_EFFORT")
            reasoning_effort = ((raw_reasoning_effort or "").strip()
                                if raw_reasoning_effort is not None else None)
            if reasoning_effort == "":
                # Compatibility: "none" stays an explicit alias to omit the
                # field, even though Yandex itself does not accept it.
                reasoning_effort = "none"
            if reasoning_effort not in (*_YANDEX_REASONING_EFFORTS, "none", None):
                allowed = ", ".join(_YANDEX_REASONING_EFFORTS)
                raise foundations.FrontendAIError(
                    "MONL_YANDEX_REASONING_EFFORT invalid: "
                    f"{reasoning_effort!r}. Allowed values: {allowed} "
                    "(or 'none' to omit the field).")
            extra_body = {
                "temperature": 0.3,
                # Some AI Studio models count their internal reasoning in the
                # completion ceiling. Here the result is a file, not a question
                # to solve: reserving that budget for the HTML/CSS/JS avoids a
                # truncated JSON.
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "frontend_files",
                        "description": "Static frontend files.",
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
            # Yandex expects the full URI on the wire, but the readable model
            # identifier is the key of the telemetry and its groupings.
            provider.model = model
            # DeepSeek can produce a rich frontend, but not three large files
            # in a single JSON response. Sequential mode is enabled at the
            # provider level, without changing the contract of the other
            # OpenAI-compatible APIs.
            provider.chunked_generation = True
            provider.max_output_tokens = _chunk_max_output_tokens()
            return provider
        return openai_provider(model=model, base_url=base_url, key_env=key_env,
                               key_required=(name != "ollama"), provider_name=name)
    return build

def _generic_openai(model=None):
    """--provider openai-compatible: everything is in the environment."""
    return openai_provider(model=model,
                           base_url=os.environ.get("MONL_AI_BASE_URL"),
                           key_env="MONL_AI_API_KEY",
                           key_required=bool(os.environ.get("MONL_AI_BASE_URL")))

PROVIDERS = {"claude": claude_provider, GENERIC_PROVIDER: _generic_openai}

PROVIDERS.update({name: _openai_preset(name) for name in OPENAI_COMPATIBLE})

USAGE_FILENAME = ".monl_ai_usage.jsonl"

def _record_provider_usage(project_dir, provider, operation, attempt, *,
                           run_id, stage=None, retry=None, usage=None):
    """Keeps the cost counters, never the prompt, the response or the key.

    ``run_id`` is MANDATORY: without it, two successive runs give
    indistinguishable events and "what this site cost" stops being
    computable — the defect this column closes. A fallback that made one up
    per event would be worse than nothing: the report would show as many runs
    as calls, and it would look right."""
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
