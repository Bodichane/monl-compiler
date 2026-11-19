"""What the whole tool reads, and which reads nothing back."""

import hashlib
import re
import unicodedata

from ..errors import ToolError


class AssetsToolError(ToolError):
    pass

# Letters that Unicode NFKD decomposition does not split: without this table,
# "Sørlund" gives "srlund" and "Bæk" gives "bk" — a mute slug where the name
# was readable. SneakerLab's catalog already carries a Nordic brand: the case
# is not theoretical.
TRANSLITERATIONS = {
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "þ": "th", "ð": "d",
    "đ": "d", "ł": "l", "ħ": "h", "ı": "i", "ŋ": "n", "ə": "e",
}

# The words that open a top-level block. Used to place an 'assets' block
# created from scratch: after the file's header (the app name and its leading
# comments), before the first declaration.
STARTS_OF_BLOCK = ("entity", "relation", "actor", "rule", "workflow", "seed",
                  "landing", "ui", "capability", "custom", "migration",
                  "assets")

# Recognized credits file names — a project convention, not a monl format.
NAMES_OF_CREDITS = ("CREDITS.json", "CREDITS.md", "CREDITS.txt", "credits.json")

# ------------------------------------------------------------------ slug --
def slugify(text):
    """"Halo RS" → "halo-rs". A file name served by a browser: lowercase,
    ASCII, hyphens. Returns "" if nothing usable remains."""
    base = "".join(TRANSLITERATIONS.get(c.lower(), c) for c in text)
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")

def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
