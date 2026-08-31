"""La classe `GuidedDialogue`, recomposée par mixins.

Une question nouvelle s'ajoute dans le mixin de sa famille — saisie,
direction, parcours, commerce, comptes — jamais ici. Ce fichier ne
porte que l'état du dialogue."""

from .commerce import CommerceMixin
from .comptes import ComptesMixin
from .direction import DirectionMixin
from .emission import EmissionMixin
from .libre import LibreMixin
from .parcours import ParcoursMixin
from .questions import QuestionsMixin


class GuidedDialogue(
    QuestionsMixin,
    DirectionMixin,
    ParcoursMixin,
    LibreMixin,
    CommerceMixin,
    ComptesMixin,
    EmissionMixin,
):
    """Le dialogue guidé, sans IA et sans réseau."""

    def __init__(self, ask, say=None, max_retries=3, ui=None, express=False,
                 choose_experience=False, express_links=()):
        """Dialogue guidé à règles, entièrement déterministe : aucune IA,
        aucun appel réseau. Chaque réponse est validée en saisie stricte
        (numéros, o/n, identifiants) et redemandée tant qu'elle est invalide.
        La spécification produite est ensuite revalidée par le vrai parseur
        avant d'être écrite."""
        self._ask_fn = ask
        self._say = say or (lambda *_: None)
        self.max_retries = max_retries
        self.express = express
        self.choose_experience = choose_experience
        # Le mode express ne pose AUCUNE question de finition — c'est sa
        # raison d'être. Ses liens de pied de page arrivent donc par
        # l'appelant (la console web), jamais par une question de plus.
        self.express_links = tuple(express_links or ())
        # AJOUT (bêta 3) : couche de présentation. Par défaut, rendu nu —
        # chaînes strictement identiques à l'historique, donc les tests
        # scriptés et toute sortie redirigée sont insensibles à l'habillage.
        # L'entrée interactive (run_interactive_dialogue) injecte le rendu
        # stylé. Le moteur, lui, ne connaît que cette interface.
        from ..tui import PlainDialogueUI
        self.ui = ui or PlainDialogueUI()
        # Ce que le moteur SAIT de la question en cours (point 171) : sa
        # nature, ses options, leurs aides. Écrit par `_ask` avant chaque
        # appel, jamais relu par le moteur — une couche de présentation qui
        # ne rend pas du texte de terminal en a besoin, le dialogue non.
        self.derniere_question = None
