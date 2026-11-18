"""The `GuidedDialogue` class, recomposed from mixins.

A new question is added in its family's mixin — input, direction,
journey, commerce, accounts — never here. This file carries only the
dialogue's state."""

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
    """The guided dialogue, without AI and without network."""

    def __init__(self, ask, say=None, max_retries=3, ui=None, express=False,
                 choose_experience=False, express_links=()):
        """Rule-based guided dialogue, entirely deterministic: no AI, no network
        call. Each answer is validated with strict input (numbers, y/n,
        identifiers) and asked again as long as it is invalid. The produced
        specification is then revalidated by the real parser before being
        written."""
        self._ask_fn = ask
        self._say = say or (lambda *_: None)
        self.max_retries = max_retries
        self.express = express
        self.choose_experience = choose_experience
        # Express mode asks NO finishing question — that is its reason to
        # exist. Its footer links therefore come through the caller (the web
        # console), never through one more question.
        self.express_links = tuple(express_links or ())
        # ADDED (beta 3): presentation layer. By default, plain rendering —
        # strings strictly identical to the historical ones, so scripted tests
        # and any redirected output are insensitive to the styling. Interactive
        # input (run_interactive_dialogue) injects the styled rendering. The
        # engine itself only knows this interface.
        from ..tui import PlainDialogueUI
        self.ui = ui or PlainDialogueUI()
        # What the engine KNOWS about the current question (point 171): its
        # kind, its options, their help texts. Written by `_ask` before each
        # call, never read back by the engine — a presentation layer that does
        # not render terminal text needs it, the dialogue does not.
        self.derniere_question = None
