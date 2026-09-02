"""Public compilation-console template.

The page layout and its browser behavior are kept separate so this module only
assembles the public HTML artifact.
"""

from __future__ import annotations

from .console_script import SCRIPT
from .console_template import BODY, EXTRA_CSS, TERMINAL
from .theme import page

CONSOLE_HTML = page(
    # La console portait mot pour mot le titre de l'ACCUEIL. Toutes les autres
    # pages se nomment (« MCP — … », « Votre compte — … ») : avec plusieurs
    # onglets ouverts, celui de la console était indiscernable de la page
    # d'accueil, et un signet ne disait pas où il menait.
    title="Console — MONL",
    description="Décrivez vos règles métier. Monl compile un backend autonome, "
                "son schéma SQL et son contrat frontend.",
    body=BODY,
    active="console",
    scripts=SCRIPT,
    extra_css=EXTRA_CSS,
)

__all__ = ["BODY", "CONSOLE_HTML", "EXTRA_CSS", "SCRIPT", "TERMINAL"]
