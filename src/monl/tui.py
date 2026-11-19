# ─────────────────────────────────────────────────────────────────────
# TERMINAL PRESENTATION OF THE GUIDED DIALOGUE
#
# The dialogue is the first contact with monl: it must look like a precision
# instrument, not a chatty assistant. Hence this module's stance — an interview
# plan visible from the first second (the user knows how many steps remain, and
# which one is in progress), aligned menus, a single accent color, no
# animation.
#
# Three design constraints:
#   1. NO dependency (rich, colorama…) — the project is offline and its
#      foundation must stay so; everything goes through ANSI sequences.
#   2. SILENT DEGRADATION: outside a terminal (redirected output, CI,
#      scripted tests), NO_COLOR, TERM=dumb or a non-UTF-8 encoding, we
#      fall back on plain text — never stray characters in a log file.
#   3. The ENGINE does not know this module: it calls an interface
#      (PlainDialogueUI) whose plain version reproduces exactly the
#      historical strings. Scripted tests are therefore insensitive to
#      everything that follows.
# ─────────────────────────────────────────────────────────────────────
import os
import shutil
import sys


# ------------------------------------------------------------- capabilities --
def _supports_color(stream):
    if os.environ.get("NO_COLOR") or os.environ.get("MONL_NO_COLOR"):
        return False
    if os.environ.get("TERM", "") in ("dumb", ""):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        # Modern Windows terminal only: we try to enable virtual terminal
        # sequence mode, and give up cleanly if it is unavailable.
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
    """Capabilities of the current terminal, resolved only once."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.color = _supports_color(self.stream)
        self.unicode = _supports_unicode(self.stream)
        self.width = max(58, min(shutil.get_terminal_size((80, 24)).columns, 96))

    # Palette: a single accent, two grays, an error red. 256-color codes
    # (widely supported) rather than the 16-color palette, whose rendering
    # varies too much from one theme to another to be controlled.
    ACCENT = "38;5;36"      # deep blue-green: the single accent
    MUTED = "38;5;245"      # mid gray: hints, units, captions
    FAINT = "38;5;240"      # dark gray: rules, rail
    ALERT = "38;5;167"      # brick red: input errors
    LIGHT = "38;5;252"      # light gray: values

    def paint(self, text, *codes):
        if not self.color or not codes:
            return text
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    def glyph(self, rich, plain):
        return rich if self.unicode else plain


# ------------------------------------------------------- interface neutre --
class PlainDialogueUI:
    """Plain rendering — strings strictly identical to the engine's historical
    ones.

    It is the dialogue engine's default behavior: scripted tests and any
    redirected output go through here, so no aesthetic change can alter what
    the dialogue produces."""

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
        none_hint = "  [0] none" if allow_none else ""
        return f"{prompt}\n  {menu}{none_hint}\n> "

    def field(self, prompt):
        return prompt

    def yes_no(self, prompt):
        return f"{prompt} (y/n) > "

    def error(self, message):
        return f"  ✗ {message}"

    def note(self, message):
        return f"  → {message}"

    def recap(self, title, rows):
        lines = [f"\n{title}"]
        lines += [f"  {key} : {valeur}" for key, valeur in rows]
        return "\n".join(lines)


# --------------------------------------------------------- styled rendering --
class StyledDialogueUI(PlainDialogueUI):
    """Terminal rendering of the dialogue: interview plan, rail, aligned menus."""

    def __init__(self, terminal=None):
        self.t = terminal or Terminal()
        self._phases = []
        self._current = -1

    # -- structural elements ------------------------------------------------
    def banner(self):
        t = self.t
        title = t.paint("monl", t.ACCENT, "1")
        dash, arrow, point = t.glyph("—", "-"), t.glyph("→", "->"), t.glyph("·", "|")
        sous = t.paint(f"intent compiler {dash} .ml spec {arrow} "
                       "deterministic backend", t.MUTED)
        guarantee = t.paint(f"rules-based dialogue {point} no AI {point} "
                           "offline", t.FAINT)
        # The rule follows the title line rather than the window: a 90-column
        # line above three words crushes the rest of the screen.
        filet = t.glyph("─", "-") * 58
        return f"\n{title}  {sous}\n{guarantee}\n{t.paint(filet, t.FAINT)}"

    def plan(self, phases):
        """Displays the complete flow BEFORE the first question.

        It is this screen's central move: an interview whose end one cannot see
        is endured. By showing the steps and marking the current one, a queue of
        questions becomes a journey one can place oneself in."""
        self._phases, self._current = list(phases), -1
        t = self.t
        lines = [t.paint("Dialogue outline", t.MUTED)]
        for i, phase in enumerate(self._phases, 1):
            puce = t.glyph("○", "o")
            lines.append(f"  {t.paint(puce, t.FAINT)} {t.paint(f'{i}.', t.FAINT)} "
                          f"{t.paint(phase, t.MUTED)}")
        return "\n" + "\n".join(lines)

    def phase(self, index):
        """Header of the current step: rank, title, progress."""
        if not self._phases or not 0 <= index < len(self._phases):
            return None
        self._current = index
        t = self.t
        total = len(self._phases)
        rang = t.paint(f"{index + 1:02d}", t.ACCENT, "1")
        on = t.paint(f"/{total:02d}", t.FAINT)
        title = t.paint(self._phases[index].upper(), "1")

        full, empty = t.glyph("━", "="), t.glyph("─", "-")
        width = 18
        crossed = round(width * (index + 1) / total)
        gauge = (t.paint(full * crossed, t.ACCENT)
                 + t.paint(empty * (width - crossed), t.FAINT))
        return f"\n{rang}{on}  {title}  {gauge}"

    def section(self, text):
        return "\n" + self.t.paint(text.strip(), self.t.MUTED)

    # -- questions -------------------------------------------------------
    def _rail(self):
        return self.t.paint(self.t.glyph("│", "|"), self.t.FAINT)

    def menu(self, prompt, options, allow_none=False, hints=None):
        """Numbered menu, labels and descriptions in aligned columns.

        Descriptions are truncated to the terminal's real width: a line that
        wraps breaks the alignment, and a misaligned menu reads twice as slowly."""
        t = self.t
        hints = hints or {}
        width_num = len(str(len(options)))
        # Bounded label column: a single very long entry must not squeeze the
        # explanation column of all the others.
        width_lib = min(max((len(o) for o in options), default=0), 32)
        reste = t.width - width_num - width_lib - 8

        lines = [f"\n{t.paint(prompt, '1')}"]
        for i, option in enumerate(options, 1):
            number = t.paint(f"{i:>{width_num}}", t.ACCENT)
            line = f"  {self._rail()} {number}  {t.paint(option, t.LIGHT)}"
            if hints:  # padding OUTSIDE the color sequence
                line += " " * max(0, width_lib - len(option))
            aide = hints.get(option)
            if aide and reste > 12:
                if len(aide) > reste:
                    aide = aide[:reste - 1].rstrip() + t.glyph("…", "...")
                line += "  " + t.paint(aide, t.MUTED)
            lines.append(line)
        if allow_none:
            zero = t.paint(f"{0:>{width_num}}", t.FAINT)
            lines.append(f"  {self._rail()} {zero}  {t.paint('none', t.MUTED)}")
        lines.append(self._invite())
        return "\n".join(lines)

    def field(self, prompt):
        """Turns "Application name (e.g. StudioNova) >" into a titled question + a
        grayed hint + a prompt on its own line."""
        t = self.t
        text = prompt.rstrip()
        indented = text.startswith("  ")
        text = text.strip()
        if text.endswith(">"):
            text = text[:-1].rstrip()

        aide = None
        for opening, closing in (("(", ")"), ("[", "]")):
            if text.endswith(closing) and opening in text:
                coupe = text.rindex(opening)
                aide, text = text[coupe + 1:-1], text[:coupe].rstrip()
                break

        marge = "    " if indented else "  "
        line = f"\n{marge}{t.paint(text, '1')}"
        if aide:
            line += f"\n{marge}{t.paint(aide, t.MUTED)}"
        return line + self._invite(marge)

    def yes_no(self, prompt):
        t = self.t
        text = prompt.strip()
        indented = prompt.startswith("  ")
        marge = "    " if indented else "  "
        return (f"\n{marge}{t.paint(text, '1')}  "
                f"{t.paint('y / n', t.MUTED)}{self._invite(marge)}")

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
        """Summary before compilation: what the spec will contain.

        The last moment when the user can notice a gap between what they believe
        they declared and what will be written — the spec stays the source of
        truth, so it might as well be given to read before compiling it."""
        t = self.t
        filet = t.glyph("─", "-") * min(t.width, 62)
        width_key = max((len(str(c)) for c, _ in rows), default=0)
        lines = [f"\n{t.paint(filet, t.FAINT)}",
                  t.paint(title.upper(), "1")]
        for key, valeur in rows:
            lines.append(f"  {t.paint(str(key).ljust(width_key), t.MUTED)}  "
                          f"{t.paint(str(valeur), t.LIGHT)}")
        lines.append(t.paint(filet, t.FAINT))
        return "\n".join(lines)
