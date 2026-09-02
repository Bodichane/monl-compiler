"""Ce que tout le paquet lit, et qui ne lit rien en retour."""

from ..errors import FrontendError

ALLOWED_EXTENSIONS = (".html", ".css", ".js", ".svg", ".json")

MAX_TOTAL_BYTES = 2_000_000

# Les deux briefs d'ÉVOLUTION (par opposition à FRONTEND_PROMPT.md, qui décrit
# une construction neuve). Nommés ici plutôt que chez leur producteur : c'est
# frontend_ai qui les consomme, et cli.py les importe — l'inverse ferait
# dépendre la couche IA de la couche commande.
UPDATE_PROMPT_FILENAME = "docs/FRONTEND_UPDATE_PROMPT.md"

RETOUCHE_PROMPT_FILENAME = "FRONTEND_RETOUCHE_PROMPT.md"

class FrontendAIError(FrontendError):
    pass

class _ChunkOutputLimitError(FrontendAIError):
    """Une reprise est impossible : le modèle coupe encore au plafond."""

class _ChunkGenerationError(FrontendAIError):
    """Les reprises locales d'un fichier sont épuisées.

    Cette erreur ne doit jamais déclencher la seconde génération complète :
    les fichiers précédents ont déjà été payés et le fichier fautif a déjà
    bénéficié de ses reprises ciblées.
    """
