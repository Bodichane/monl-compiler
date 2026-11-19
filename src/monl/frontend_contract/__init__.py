"""The frontend contract: what monl PROMISES the interface AI.

One module per section of the contract. The public surface did not move
when it became a package. INTERNAL RULE (point 153): a reference between
modules goes through the MODULE object (`fondations.paragraphes(...)`),
never through a bound name — otherwise a `monkeypatch` targeting the
package would no longer bite on the real call."""

from .assembly import build_contract
from .emission import contract_sha256, generate_frontend_contract
from .foundations import (
    AGENTS_FILENAME,
    CONTRACT_FILENAME,
    CONTRACT_VERSION,
    PROMPT_FILENAME,
    README_FILENAME,
    paragraphes,
)
from .project import PROJECT_CLAUDE_MD_MARKER

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
