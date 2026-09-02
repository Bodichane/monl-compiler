"""Le contrat frontend : ce que monl PROMET à l'IA d'interface.

Un module par section du contrat. La surface publique n'a pas bougé en
devenant un paquet. RÈGLE INTERNE (point 153) : une référence entre
modules passe par l'objet MODULE (`fondations.paragraphes(...)`), jamais
par un nom lié — sans quoi un `monkeypatch` visant le paquet ne mordrait
plus sur l'appel réel."""

from .assemblage import build_contract
from .emission import contract_sha256, generate_frontend_contract
from .fondations import (
    AGENTS_FILENAME,
    CONTRACT_FILENAME,
    CONTRACT_VERSION,
    PROMPT_FILENAME,
    README_FILENAME,
    paragraphes,
)
from .projet import PROJECT_CLAUDE_MD_MARKER

__all__ = [
    "AGENTS_FILENAME",
    "CONTRACT_FILENAME",
    "CONTRACT_VERSION",
    "PROJECT_CLAUDE_MD_MARKER",
    "PROMPT_FILENAME",
    "README_FILENAME",
    "build_contract",
    "contract_sha256",
    "generate_frontend_contract",
    "paragraphes",
]
