"""Le dialogue guidé : de la question posée à la spec écrite.

La surface publique n'a pas bougé en devenant un paquet."""


from .core import GuidedDialogue
from .fondations import DialogueError, adresse_de_lien


def run_interactive_dialogue():
    """Point d'entrée réel (stdin/stdout) utilisé par cli.py.

    C'est le seul endroit où le rendu stylé est injecté : partout ailleurs
    (tests, sortie redirigée), le moteur reste en rendu nu.
    """
    from ..tui import PlainDialogueUI, StyledDialogueUI, Terminal
    terminal = Terminal()
    # Hors terminal interactif (sortie redirigée, CI), rendu nu : un journal
    # ne doit contenir ni séquence ANSI ni caractère de dessin.
    ui = StyledDialogueUI(terminal) if terminal.color else PlainDialogueUI()
    dialogue = GuidedDialogue(ask=input, say=print, ui=ui,
                              choose_experience=True)
    return dialogue.run()

__all__ = [
    "DialogueError",
    "GuidedDialogue",
    "adresse_de_lien",
    "run_interactive_dialogue",
]
