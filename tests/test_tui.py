"""Presentation layer of the dialogue (beta 3).

Two guarantees held here:
  1. plain rendering stays EXACTLY what it was before styling — that is
     what makes scripted tests and redirected output insensitive to
     aesthetics;
  2. styled rendering degrades cleanly (no ANSI sequence nor drawing
     character when the terminal does not support them).
"""
import sys

from monl.dialogue_engine import GuidedDialogue
from monl.tui import PlainDialogueUI, StyledDialogueUI, Terminal


class _TerminalNu(Terminal):
    """Terminal without color or Unicode, fixed width (reproducible rendering)."""

    def __init__(self, color=False, unicode=False, width=80):
        self.stream = sys.stdout
        self.color, self.unicode, self.width = color, unicode, width


def test_plain_rendering_keeps_the_historical_strings():
    ui = PlainDialogueUI()
    assert ui.menu("Type ?", ["A", "B"], allow_none=True) == "Type ?\n  [1] A  [2] B  [0] none\n> "
    assert ui.yes_no("Continue?") == "Continue? (y/n) > "
    assert ui.field("Nom (ex. Studio) > ") == "Nom (ex. Studio) > "
    assert ui.error("Answer y or n.") == "  ✗ Answer y or n."
    # Purely visual elements do not exist in plain rendering.
    assert ui.banner() is None and ui.plan(["A"]) is None and ui.phase(0) is None


def test_engine_uses_plain_rendering_by_default():
    """No styling must slip into a scripted dialogue."""
    vus = []
    dialogue = GuidedDialogue(ask=lambda p: (vus.append(p), "1")[1])
    assert isinstance(dialogue.ui, PlainDialogueUI)
    dialogue._ask_choice("Type ?", ["A", "B"])
    assert vus == ["Type ?\n  [1] A  [2] B\n> "]


def test_styled_rendering_without_color_or_unicode_stays_plain_text():
    ui = StyledDialogueUI(_TerminalNu())
    ui.plan(["Un", "Deux"])
    sorties = [ui.banner(), ui.phase(0), ui.menu("Type ?", ["A"], allow_none=True),
               ui.field("  Name (e.g. Studio) > "), ui.yes_no("Continue?"),
               ui.error("Invalid."), ui.note("Created."),
               ui.recap("Titre", [("Clé", "valeur")])]
    # Drawing glyphs have an ASCII equivalent; the text itself is not
    # transliterated — a terminal unable to encode non-ASCII letters could not
    # show the user's own accented input either.
    glyphes = "│❯○━✗→…"
    for sortie in sorties:
        assert "\033" not in sortie, f"séquence ANSI émise sans couleur : {sortie!r}"
        for glyphe in glyphes:
            assert glyphe not in sortie, f"glyphe {glyphe!r} non dégradé : {sortie!r}"


def test_styled_rendering_colors_and_frames_without_breaking_text():
    ui = StyledDialogueUI(_TerminalNu(color=True, unicode=True))
    menu = ui.menu("Type ?", ["Alpha", "Bravo"], hints={"Alpha": "premier"})
    assert "\033[" in menu and "Alpha" in menu and "premier" in menu
    # The prompt ends the string: the user types right after it.
    import re
    visible = re.sub(r"\033\[[0-9;]*m", "", menu).rstrip()
    assert visible.endswith("❯")


def test_explanation_truncated_to_terminal_width():
    """A line that wraps breaks the menu's alignment."""
    ui = StyledDialogueUI(_TerminalNu(width=60))
    menu = ui.menu("Type ?", ["Court"], hints={"Court": "explication " * 20})
    assert all(len(ligne) <= 62 for ligne in menu.splitlines()), menu


def test_capacites_terminal_respectent_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert Terminal().color is False
