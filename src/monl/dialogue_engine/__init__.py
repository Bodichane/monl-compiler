"""The guided dialogue: from the question asked to the spec written.

The public surface did not move when it became a package."""


from .core import GuidedDialogue
from .foundations import DialogueError, adresse_de_lien


def run_interactive_dialogue():
    """Real entry point (stdin/stdout) used by cli.py.

    It is the only place where styled rendering is injected: everywhere else
    (tests, redirected output), the engine stays in plain rendering."""
    from ..tui import PlainDialogueUI, StyledDialogueUI, Terminal
    terminal = Terminal()
    # Outside an interactive terminal (redirected output, CI), plain rendering:
    # a log must contain neither ANSI sequences nor box-drawing characters.
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
