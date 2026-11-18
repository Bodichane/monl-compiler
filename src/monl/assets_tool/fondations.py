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
TRANSLITTERATIONS = {
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "þ": "th", "ð": "d",
    "đ": "d", "ł": "l", "ħ": "h", "ı": "i", "ŋ": "n", "ə": "e",
}

# The words that open a top-level block. Used to place an 'assets' block
# created from scratch: after the file's header (the app name and its leading
# comments), before the first declaration.
DEBUTS_DE_BLOC = ("entity", "relation", "actor", "rule", "workflow", "seed",
                  "landing", "ui", "capability", "custom", "migration",
                  "assets")

# Recognized credits file names — a project convention, not a monl format.
NOMS_DE_CREDITS = ("CREDITS.json", "CREDITS.md", "CREDITS.txt", "credits.json")

# ------------------------------------------------------------------ slug --
def sluggify(texte):
    """« Halo RS » → « halo-rs ». Un nom de fichier servi par un navigateur :
    minuscules, ASCII, tirets. Retourne "" si rien d'utilisable ne reste."""
    base = "".join(TRANSLITTERATIONS.get(c.lower(), c) for c in texte)
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")

def _sha256(chemin):
    with open(chemin, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
