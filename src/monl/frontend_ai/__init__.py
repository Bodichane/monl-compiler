# ─────────────────────────────────────────────────────────────────────
# GÉNÉRATION DU FRONTEND PAR IA — pivot orchestrateur, point 4 : fermer
# complètement la boucle. 'monl frontend' envoie le brief
# (docs/FRONTEND_PROMPT.md, ou docs/FRONTEND_UPDATE_PROMPT.md + fichiers existants en
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
#
# Ce module est un PAQUET depuis le point 153 : un fichier par
# préoccupation. La surface publique n'a pas bougé.

from ..design_system import activate_asset_manifest
from ..frontend_contract import PROMPT_FILENAME
from .agents import (
    CLAUDE_CODE_INSTRUCTION,
    CLI_AGENTS,
    DEFAULT_MAX_TURNS,
    PROTECTED_ARTEFACTS,
    RETOUCHE_INSTRUCTION,
    _fingerprint_frontend,
    _fingerprint_protected,
    build_agent_argv,
    generate_with_claude_code,
    generate_with_cli_agent,
    run_claude_code,
    run_cli_agent,
)
from .controles_design import (
    _design_completeness_errors,
    _editorial_content_errors,
    _generated_asset_reuse_errors,
)
from .controles_fichiers import (
    _declared_link_errors,
    _frontend_behavioral_quality_errors,
    _frontend_local_reference_errors,
)
from .etages import (
    CHUNKED_FRONTEND_FILES,
    _budget,
    _build_chunk_prompt,
    _chunk_context,
    _generate_chunked_files,
    _parse_model_routing,
    _planned_generated_asset_paths,
    _provider_for_chunk,
    _raise_chunk_output_limit,
    _validate_model_routing,
)
from .fondations import (
    ALLOWED_EXTENSIONS,
    MAX_TOTAL_BYTES,
    RETOUCHE_PROMPT_FILENAME,
    UPDATE_PROMPT_FILENAME,
    FrontendAIError,
)
from .fournisseurs import (
    CHUNK_MAX_RETRIES,
    CHUNK_RETRY_MAX_OUTPUT_TOKENS,
    CHUNK_RETRY_OUTPUT_TOKEN_FACTOR,
    DEFAULT_CHUNK_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    GENERIC_PROVIDER,
    OPENAI_COMPATIBLE,
    PROVIDERS,
    RESPONSE_FORMAT_INSTRUCTIONS,
    USAGE_FILENAME,
    _chunk_max_output_tokens,
    _max_output_tokens,
    _openai_preset,
    _record_provider_usage,
    claude_provider,
    openai_provider,
)
from .images import _generate_planned_images, _image_prompt
from .orchestration import generate_and_verify, import_and_verify, load_frontend_source
from .redaction import ampleur_du_contrat, brief_evolution, build_generation_prompt
from .reponse import (
    _fichier_depuis_un_bloc,
    _json_payload,
    _project_guidance,
    _read_existing_frontend,
    _restaurer_frontend,
    _validate_files,
    _write_files,
    parse_files_payload,
    parse_single_file_payload,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "CHUNKED_FRONTEND_FILES",
    "CHUNK_MAX_RETRIES",
    "CHUNK_RETRY_MAX_OUTPUT_TOKENS",
    "CHUNK_RETRY_OUTPUT_TOKEN_FACTOR",
    "CLAUDE_CODE_INSTRUCTION",
    "CLI_AGENTS",
    "DEFAULT_CHUNK_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_MODEL",
    "GENERIC_PROVIDER",
    "MAX_TOTAL_BYTES",
    "OPENAI_COMPATIBLE",
    "PROMPT_FILENAME",
    "PROTECTED_ARTEFACTS",
    "PROVIDERS",
    "RESPONSE_FORMAT_INSTRUCTIONS",
    "RETOUCHE_INSTRUCTION",
    "RETOUCHE_PROMPT_FILENAME",
    "UPDATE_PROMPT_FILENAME",
    "USAGE_FILENAME",
    "FrontendAIError",
    "_budget",
    "_build_chunk_prompt",
    "_chunk_context",
    "_chunk_max_output_tokens",
    "_declared_link_errors",
    "_design_completeness_errors",
    "_editorial_content_errors",
    "_fichier_depuis_un_bloc",
    "_fingerprint_frontend",
    "_fingerprint_protected",
    "_frontend_behavioral_quality_errors",
    "_frontend_local_reference_errors",
    "_generate_chunked_files",
    "_generate_planned_images",
    "_generated_asset_reuse_errors",
    "_image_prompt",
    "_json_payload",
    "_max_output_tokens",
    "_openai_preset",
    "_parse_model_routing",
    "_planned_generated_asset_paths",
    "_project_guidance",
    "_provider_for_chunk",
    "_raise_chunk_output_limit",
    "_read_existing_frontend",
    "_record_provider_usage",
    "_restaurer_frontend",
    "_validate_files",
    "_validate_model_routing",
    "_write_files",
    "activate_asset_manifest",
    "ampleur_du_contrat",
    "brief_evolution",
    "build_agent_argv",
    "build_generation_prompt",
    "claude_provider",
    "generate_and_verify",
    "generate_with_claude_code",
    "generate_with_cli_agent",
    "import_and_verify",
    "load_frontend_source",
    "openai_provider",
    "parse_files_payload",
    "parse_single_file_payload",
    "run_claude_code",
    "run_cli_agent",
]
