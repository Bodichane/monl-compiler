"""Public compilation-console template.

The page layout and its browser behavior are kept separate so this module only
assembles the public HTML artifact.
"""

from __future__ import annotations

from .console_script import SCRIPT
from .console_template import BODY, EXTRA_CSS, TERMINAL
from .theme import page

CONSOLE_HTML = page(
    # The console carried the HOME page's title word for word. Every other page
    # names itself ("MCP — …", "Your account — …"): with several tabs open, the
    # console's was indistinguishable from the home page, and a bookmark did
    # not say where it led.
    title="Console — MONL",
    description="Describe your business rules. Monl compiles a standalone backend, "
                "its SQL schema and its frontend contract.",
    body=BODY,
    active="console",
    scripts=SCRIPT,
    extra_css=EXTRA_CSS,
)

__all__ = ["BODY", "CONSOLE_HTML", "EXTRA_CSS", "SCRIPT", "TERMINAL"]
