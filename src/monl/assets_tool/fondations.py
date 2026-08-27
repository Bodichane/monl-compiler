"""Ce que tout l'outil lit, et qui ne lit rien en retour."""

import hashlib
import re
import unicodedata

from ..errors import ToolError


class AssetsToolError(ToolError):
    pass

# Lettres que la décomposition Unicode NFKD ne sépare pas : sans cette table,
# « Sørlund » donne « srlund » et « Bæk » donne « bk » — un slug muet là où le
# nom était lisible. Le catalogue de SneakerLab porte déjà une maison nordique :
# le cas n'est pas théorique.
TRANSLITTERATIONS = {
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "þ": "th", "ð": "d",
    "đ": "d", "ł": "l", "ħ": "h", "ı": "i", "ŋ": "n", "ə": "e",
}

# Les mots qui ouvrent un bloc de premier niveau. Sert à placer un bloc
# 'assets' créé de toutes pièces : après l'en-tête du fichier (le nom de
# l'app et ses commentaires de tête), avant la première déclaration.
DEBUTS_DE_BLOC = ("entity", "relation", "actor", "rule", "workflow", "seed",
                  "landing", "ui", "capability", "custom", "migration",
                  "assets")

# Noms de fichiers de crédits reconnus — convention de projet, pas format monl.
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
