# ─────────────────────────────────────────────────────────────────────
# PRÉSENTATION TERMINAL DU DIALOGUE GUIDÉ
#
# Le dialogue est le premier contact avec monl : il doit ressembler à un
# instrument de précision, pas à un assistant bavard. D'où le parti pris
# de ce module — un plan d'entretien visible dès la première seconde
# (l'utilisateur sait combien d'étapes il reste, et laquelle est en
# cours), des menus alignés, une seule couleur d'accent, aucune animation.
#
# Trois contraintes de conception :
#   1. AUCUNE dépendance (rich, colorama…) — le projet est hors-ligne et
#      son socle doit le rester ; tout passe par des séquences ANSI.
#   2. DÉGRADATION SILENCIEUSE : hors terminal (sortie redirigée, CI,
#      tests scriptés), NO_COLOR, TERM=dumb ou encodage non-UTF-8, on
#      retombe sur du texte nu — jamais de caractères parasites dans un
#      fichier de log.
#   3. Le MOTEUR ne connaît pas ce module : il appelle une interface
#      (PlainDialogueUI) dont la version nue reproduit exactement les
#      chaînes historiques. Les tests scriptés sont donc insensibles à
#      tout ce qui suit.
# ─────────────────────────────────────────────────────────────────────
import os
import shutil
import sys


# --------------------------------------------------------------- capacités --
def _supports_color(stream):
    if os.environ.get("NO_COLOR") or os.environ.get("MONL_NO_COLOR"):
        return False
    if os.environ.get("TERM", "") in ("dumb", ""):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        # Terminal Windows moderne uniquement : on tente d'activer le mode
        # séquences virtuelles, et on renonce proprement si indisponible.
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
        except Exception:
            return False
    return True


def _supports_unicode(stream):
    encoding = getattr(stream, "encoding", None) or ""
    try:
        "─┃❯✓✗·".encode(encoding or "ascii")
        return True
    except (LookupError, UnicodeEncodeError):
        return False


class Terminal:
    """Capacités du terminal courant, résolues une seule fois."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.color = _supports_color(self.stream)
        self.unicode = _supports_unicode(self.stream)
        self.width = max(58, min(shutil.get_terminal_size((80, 24)).columns, 96))

    # Palette : un seul accent, deux gris, un rouge d'erreur. Codes 256
    # couleurs (largement supportés) plutôt que la palette 16, dont le
    # rendu varie trop d'un thème à l'autre pour être maîtrisé.
    ACCENT = "38;5;36"      # vert-bleu profond : l'accent unique
    MUTED = "38;5;245"      # gris moyen : hints, unités, légendes
    FAINT = "38;5;240"      # gris sombre : filets, rail
    ALERT = "38;5;167"      # rouge brique : erreurs de saisie
    LIGHT = "38;5;252"      # gris clair : valeurs

    def paint(self, text, *codes):
        if not self.color or not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    def glyph(self, rich, plain):
        return rich if self.unicode else plain


# ------------------------------------------------------- interface neutre --
class PlainDialogueUI:
    """Rendu nu — chaînes strictement identiques à l'historique du moteur.

    C'est le comportement par défaut du moteur de dialogue : les tests
    scriptés et toute sortie redirigée passent par ici, donc aucune
    évolution esthétique ne peut modifier ce que produit le dialogue.
    """

    def plan(self, phases):
        return None

    def phase(self, index):
        return None

    def banner(self):
        return None

    def section(self, text):
        return f"\n{text}"

    def menu(self, prompt, options, allow_none=False, hints=None):
        menu = "  ".join(f"[{i + 1}] {opt}" for i, opt in enumerate(options))
        none_hint = "  [0] aucun" if allow_none else ""
        return f"{prompt}\n  {menu}{none_hint}\n> "

    def field(self, prompt):
        return prompt

    def yes_no(self, prompt):
        return f"{prompt} (o/n) > "

    def error(self, message):
        return f"  ✗ {message}"

    def note(self, message):
        return f"  → {message}"

    def recap(self, title, rows):
        lignes = [f"\n{title}"]
        lignes += [f"  {cle} : {valeur}" for cle, valeur in rows]
        return "\n".join(lignes)


# ------------------------------------------------------------ rendu stylé --
class StyledDialogueUI(PlainDialogueUI):
    """Rendu terminal du dialogue : plan d'entretien, rail, menus alignés."""

    def __init__(self, terminal=None):
        self.t = terminal or Terminal()
        self._phases = []
        self._current = -1

    # -- éléments de structure ------------------------------------------
    def banner(self):
        t = self.t
        titre = t.paint("monl", t.ACCENT, "1")
        tiret, fleche, point = t.glyph("—", "-"), t.glyph("→", "->"), t.glyph("·", "|")
        sous = t.paint(f"compilateur d'intention {tiret} spec .ml {fleche} "
                       "backend déterministe", t.MUTED)
        garantie = t.paint(f"entretien guidé par règles {point} sans IA {point} "
                           "hors-ligne", t.FAINT)
        # Le filet épouse la ligne de titre plutôt que la fenêtre : un trait
        # de 90 colonnes au-dessus de trois mots écrase le reste de l'écran.
        filet = t.glyph("─", "-") * 58
        return f"\n{titre}  {sous}\n{garantie}\n{t.paint(filet, t.FAINT)}"

    def plan(self, phases):
        """Affiche le déroulé complet AVANT la première question.

        C'est le geste central de cet écran : un entretien dont on ne voit
        pas la fin est subi. En montrant les étapes et en marquant celle en
        cours, on transforme une file de questions en parcours situé.
        """
        self._phases, self._current = list(phases), -1
        t = self.t
        lignes = [t.paint("Déroulé de l'entretien", t.MUTED)]
        for i, phase in enumerate(self._phases, 1):
            puce = t.glyph("○", "o")
            lignes.append(f"  {t.paint(puce, t.FAINT)} {t.paint(f'{i}.', t.FAINT)} "
                          f"{t.paint(phase, t.MUTED)}")
        return "\n" + "\n".join(lignes)

    def phase(self, index):
        """En-tête de l'étape en cours : rang, intitulé, avancement."""
        if not self._phases or not 0 <= index < len(self._phases):
            return None
        self._current = index
        t = self.t
        total = len(self._phases)
        rang = t.paint(f"{index + 1:02d}", t.ACCENT, "1")
        sur = t.paint(f"/{total:02d}", t.FAINT)
        titre = t.paint(self._phases[index].upper(), "1")

        plein, vide = t.glyph("━", "="), t.glyph("─", "-")
        largeur = 18
        franchi = round(largeur * (index + 1) / total)
        jauge = (t.paint(plein * franchi, t.ACCENT)
                 + t.paint(vide * (largeur - franchi), t.FAINT))
        return f"\n{rang}{sur}  {titre}  {jauge}"

    def section(self, text):
        return "\n" + self.t.paint(text.strip(), self.t.MUTED)

    # -- questions -------------------------------------------------------
    def _rail(self):
        return self.t.paint(self.t.glyph("│", "|"), self.t.FAINT)

    def menu(self, prompt, options, allow_none=False, hints=None):
        """Menu numéroté, libellés et descriptions en colonnes alignées.

        Les descriptions sont tronquées à la largeur réelle du terminal :
        une ligne qui repasse à la ligne casse l'alignement, et un menu
        désaligné se lit deux fois plus lentement.
        """
        t = self.t
        hints = hints or {}
        largeur_num = len(str(len(options)))
        # Colonne de libellés bornée : une seule entrée très longue ne doit
        # pas comprimer la colonne d'explications de toutes les autres.
        largeur_lib = min(max((len(o) for o in options), default=0), 32)
        reste = t.width - largeur_num - largeur_lib - 8

        lignes = [f"\n{t.paint(prompt, '1')}"]
        for i, option in enumerate(options, 1):
            numero = t.paint(f"{i:>{largeur_num}}", t.ACCENT)
            ligne = f"  {self._rail()} {numero}  {t.paint(option, t.LIGHT)}"
            if hints:  # remplissage HORS séquence de couleur
                ligne += " " * max(0, largeur_lib - len(option))
            aide = hints.get(option)
            if aide and reste > 12:
                if len(aide) > reste:
                    aide = aide[:reste - 1].rstrip() + t.glyph("…", "...")
                ligne += "  " + t.paint(aide, t.MUTED)
            lignes.append(ligne)
        if allow_none:
            zero = t.paint(f"{0:>{largeur_num}}", t.FAINT)
            lignes.append(f"  {self._rail()} {zero}  {t.paint('aucune', t.MUTED)}")
        lignes.append(self._invite())
        return "\n".join(lignes)

    def field(self, prompt):
        """Transforme « Nom de l'application (ex. StudioNova) > » en une
        question titrée + une aide grisée + une invite sur sa propre ligne."""
        t = self.t
        texte = prompt.rstrip()
        indente = texte.startswith("  ")
        texte = texte.strip()
        if texte.endswith(">"):
            texte = texte[:-1].rstrip()

        aide = None
        for ouvrant, fermant in (("(", ")"), ("[", "]")):
            if texte.endswith(fermant) and ouvrant in texte:
                coupe = texte.rindex(ouvrant)
                aide, texte = texte[coupe + 1:-1], texte[:coupe].rstrip()
                break

        marge = "    " if indente else "  "
        ligne = f"\n{marge}{t.paint(texte, '1')}"
        if aide:
            ligne += f"\n{marge}{t.paint(aide, t.MUTED)}"
        return ligne + self._invite(marge)

    def yes_no(self, prompt):
        t = self.t
        texte = prompt.strip()
        indente = prompt.startswith("  ")
        marge = "    " if indente else "  "
        return (f"\n{marge}{t.paint(texte, '1')}  "
                f"{t.paint('o / n', t.MUTED)}{self._invite(marge)}")

    def _invite(self, marge="  "):
        return f"\n{marge}{self.t.paint(self.t.glyph('❯', '>'), self.t.ACCENT)} "

    # -- retours ---------------------------------------------------------
    def error(self, message):
        t = self.t
        return f"  {t.paint(t.glyph('✗', 'x'), t.ALERT)} {t.paint(message, t.ALERT)}"

    def note(self, message):
        t = self.t
        return f"  {t.paint(t.glyph('→', '->'), t.ACCENT)} {t.paint(message, t.MUTED)}"

    def recap(self, title, rows):
        """Récapitulatif avant compilation : ce que la spec va contenir.

        Dernier moment où l'utilisateur peut constater un écart entre ce
        qu'il croit avoir déclaré et ce qui sera écrit — la spec reste la
        source de vérité, autant la donner à lire avant de la compiler.
        """
        t = self.t
        filet = t.glyph("─", "-") * min(t.width, 62)
        largeur_cle = max((len(str(c)) for c, _ in rows), default=0)
        lignes = [f"\n{t.paint(filet, t.FAINT)}",
                  t.paint(title.upper(), "1")]
        for cle, valeur in rows:
            lignes.append(f"  {t.paint(str(cle).ljust(largeur_cle), t.MUTED)}  "
                          f"{t.paint(str(valeur), t.LIGHT)}")
        lignes.append(t.paint(filet, t.FAINT))
        return "\n".join(lignes)
