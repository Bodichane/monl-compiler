"""Ask a question, and accept only a valid answer.

STRICT and entirely deterministic input: no AI, no network call. Rendering
is not here — the engine knows `tui` only through the `PlainDialogueUI`
interface."""

from .fondations import IDENT_RE, PARAGRAPH_SEP, DialogueError


class QuestionsMixin:
    """Ask a question, and accept only a valid answer."""

    def _show(self, rendu):
        """Displays only what the presentation layer produced."""
        if rendu:
            self._say(rendu)

    # ---------- question primitives (each one validates and asks again) ----------
    def _ask(self, prompt, validate, error_msg, kind="free_text", options=None,
             hints=None, title=None):
        # POINT 171: `kind` and `options` had always been received and NEVER
        # used — point 85 in another form. The web console therefore only
        # received the TERMINAL text and stuck it in a <pre>: eleven templates
        # in a "[1] … [2] …" mush. They are recorded here, as close to the call
        # as possible, so that any presentation layer can render something
        # other than a string.
        #
        # The state is overwritten at each question and is NEVER read by the
        # engine: it cannot change a dialogue decision, which stays entirely
        # deterministic.
        self.derniere_question = {
            "kind": kind,
            # The title ALONE, as the engine received it. Rebuilding it by
            # splitting the terminal text would force the presentation layer to
            # know its formatting — and, in a non-raw Python template, to write
            # a `\n` that becomes a real line break in the middle of a
            # JavaScript string (point 163).
            "title": title,
            "options": [dict(o) for o in options] if options else None,
            "hints": dict(hints) if hints else None,
        }
        for _ in range(self.max_retries):
            answer = self._ask_fn(prompt).strip()
            ok, value = validate(answer)
            if ok:
                return value
            self._say(self.ui.error(error_msg))
        raise DialogueError(f"Invalid response after {self.max_retries} attempts: {prompt!r}")

    def _ask_identifier(self, prompt, forbidden=()):
        prompt = self.ui.field(prompt)

        def validate(a):
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Expected identifier (letters/digits, starts with a letter, no duplicates).",
                         kind="identifier")

    def _ask_optional_identifier(self, prompt, forbidden=()):
        """Like _ask_identifier but an empty answer means 'done'."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Expected identifier (or leave blank to finish), no duplicates.",
                         kind="identifier")

    def _ask_choice(self, prompt, options, allow_none=False, hints=None):
        full = self.ui.menu(prompt, options, allow_none=allow_none, hints=hints)

        def validate(a):
            if allow_none and a == "0":
                return True, None
            if a.isdigit() and 1 <= int(a) <= len(options):
                return True, options[int(a) - 1]
            return False, None
        # Each option carries the VALUE to answer, not only its label: "none"
        # is answered with 0 and not with its rank. Letting a presentation
        # layer rediscover this rule would mean two implementations of the same
        # rule — they always diverge (point 146).
        choix = [{"label": libelle, "value": str(rang)}
                 for rang, libelle in enumerate(options, start=1)]
        if allow_none:
            choix.append({"label": "none", "value": "0"})
        return self._ask(full, validate, "Choose a menu number.",
                         kind="choice", options=choix, hints=hints,
                         title=prompt)

    def _ask_yes_no(self, prompt):
        def validate(a):
            low = a.lower()
            if low in ("o", "oui", "y", "yes"):
                return True, True
            if low in ("n", "non", "no"):
                return True, False
            return False, None
        return self._ask(self.ui.yes_no(prompt), validate, "Answer y or n.", kind="yes_no")

    def _ask_free_text(self, prompt):
        prompt = self.ui.field(prompt)

        def validate(a):
            # Double quotes would break the emitted STRING_LITERAL.
            if a and '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate, "Text must not be empty or contain double quotes.",
                         kind="free_text")

    def _ask_optional_free_text(self, prompt):
        """Like _ask_free_text, but an empty answer means "skip"."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Text must not contain double quotes (or leave blank to skip).",
                         kind="free_text")

    def _ask_paragraphs(self, prompt):
        """An editorial text in SEVERAL paragraphs (point 64).

        Single-line input was a silent trap: an "about" pasted from a word
        processor arrived flattened, its paragraphs glued back together without
        even a space ("…8 years.My work…"), and the interface AI received a wall
        of text with no possible break. The line break stays forbidden — it would
        break the emitted STRING_LITERAL — so the paragraphs are asked one after
        the other, and joined with a separator the contract translates back into
        real paragraph breaks.

        Returns None if the first paragraph is empty (section skipped)."""
        premier = self._ask_optional_free_text(prompt)
        if not premier:
            return None
        paragraphes = [premier]
        while True:
            suite = self._ask_optional_free_text(
                "    … next paragraph (leave blank to finish) > ")
            if not suite:
                return PARAGRAPH_SEP.join(paragraphes)
            paragraphes.append(suite)
