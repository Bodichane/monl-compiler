"""Couche de présentation du dialogue (bêta 3).

Deux garanties tenues ici :
  1. le rendu nu reste EXACTEMENT celui d'avant l'habillage — c'est ce qui
     rend les tests scriptés et les sorties redirigées insensibles à
     l'esthétique ;
  2. le rendu stylé dégrade proprement (aucune séquence ANSI ni caractère
     de dessin quand le terminal ne les gère pas).
"""
import sys

from monl.dialogue_engine import GuidedDialogue
from monl.tui import PlainDialogueUI, StyledDialogueUI, Terminal


class _TerminalNu(Terminal):
    """Terminal sans couleur ni Unicode, largeur fixe (rendu reproductible)."""

    def __init__(self, color=False, unicode=False, width=80):
        self.stream = sys.stdout
        self.color, self.unicode, self.width = color, unicode, width


def test_rendu_nu_conserve_les_chaines_historiques():
    ui = PlainDialogueUI()
    assert ui.menu("Type ?", ["A", "B"], allow_none=True) == "Type ?\n  [1] A  [2] B  [0] aucun\n> "
    assert ui.yes_no("Continuer ?") == "Continuer ? (o/n) > "
    assert ui.field("Nom (ex. Studio) > ") == "Nom (ex. Studio) > "
    assert ui.error("Répondre o ou n.") == "  ✗ Répondre o ou n."
    # Les éléments purement visuels n'existent pas en rendu nu.
    assert ui.banner() is None and ui.plan(["A"]) is None and ui.phase(0) is None


def test_moteur_utilise_le_rendu_nu_par_defaut():
    """Aucun habillage ne doit s'inviter dans un dialogue scripté."""
    vus = []
    dialogue = GuidedDialogue(ask=lambda p: (vus.append(p), "1")[1])
    assert isinstance(dialogue.ui, PlainDialogueUI)
    dialogue._ask_choice("Type ?", ["A", "B"])
    assert vus == ["Type ?\n  [1] A  [2] B\n> "]


def test_rendu_style_sans_couleur_ni_unicode_reste_du_texte_pur():
    ui = StyledDialogueUI(_TerminalNu())
    ui.plan(["Un", "Deux"])
    sorties = [ui.banner(), ui.phase(0), ui.menu("Type ?", ["A"], allow_none=True),
               ui.field("  Nom (ex. Studio) > "), ui.yes_no("Continuer ?"),
               ui.error("Invalide."), ui.note("Créé."),
               ui.recap("Titre", [("Clé", "valeur")])]
    # Les glyphes de dessin ont un équivalent ASCII ; le texte français, lui,
    # reste accentué — un terminal incapable d'encoder « é » ne pourrait de
    # toute façon afficher aucune question de ce dialogue.
    glyphes = "│❯○━✗→…"
    for sortie in sorties:
        assert "\033" not in sortie, f"séquence ANSI émise sans couleur : {sortie!r}"
        for glyphe in glyphes:
            assert glyphe not in sortie, f"glyphe {glyphe!r} non dégradé : {sortie!r}"


def test_rendu_style_colore_encadre_sans_casser_le_texte():
    ui = StyledDialogueUI(_TerminalNu(color=True, unicode=True))
    menu = ui.menu("Type ?", ["Alpha", "Bravo"], hints={"Alpha": "premier"})
    assert "\033[" in menu and "Alpha" in menu and "premier" in menu
    # L'invite termine la chaîne : l'utilisateur tape juste après.
    import re
    visible = re.sub(r"\033\[[0-9;]*m", "", menu).rstrip()
    assert visible.endswith("❯")


def test_explication_tronquee_a_la_largeur_du_terminal():
    """Une ligne qui repasse à la ligne casse l'alignement du menu."""
    ui = StyledDialogueUI(_TerminalNu(width=60))
    menu = ui.menu("Type ?", ["Court"], hints={"Court": "explication " * 20})
    assert all(len(ligne) <= 62 for ligne in menu.splitlines()), menu


def test_capacites_terminal_respectent_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert Terminal().color is False
