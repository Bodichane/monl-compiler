"""Poser une question, et n'accepter qu'une réponse valide.

Saisie STRICTE et entièrement déterministe : aucune IA, aucun appel
réseau. Le rendu n'est pas ici — le moteur ne connaît `tui` que par
l'interface `PlainDialogueUI`."""

from .fondations import IDENT_RE, PARAGRAPH_SEP, DialogueError


class QuestionsMixin:
    """Poser une question, et n'accepter qu'une réponse valide."""

    def _show(self, rendu):
        """N'affiche que ce que la couche de présentation a produit."""
        if rendu:
            self._say(rendu)

    # ---------- primitives de question (chacune valide et redemande) ----------
    def _ask(self, prompt, validate, error_msg, kind="free_text", options=None):
        for _ in range(self.max_retries):
            answer = self._ask_fn(prompt).strip()
            ok, value = validate(answer)
            if ok:
                return value
            self._say(self.ui.error(error_msg))
        raise DialogueError(f"Réponse invalide après {self.max_retries} tentatives : {prompt!r}")

    def _ask_identifier(self, prompt, forbidden=()):
        prompt = self.ui.field(prompt)

        def validate(a):
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Identifiant attendu (lettres/chiffres, commence par une lettre, sans doublon).",
                         kind="identifier")

    def _ask_optional_identifier(self, prompt, forbidden=()):
        """Comme _ask_identifier mais une réponse vide signifie 'terminé'."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Identifiant attendu (ou vide pour terminer), sans doublon.",
                         kind="identifier")

    def _ask_choice(self, prompt, options, allow_none=False, hints=None):
        full = self.ui.menu(prompt, options, allow_none=allow_none, hints=hints)

        def validate(a):
            if allow_none and a == "0":
                return True, None
            if a.isdigit() and 1 <= int(a) <= len(options):
                return True, options[int(a) - 1]
            return False, None
        return self._ask(full, validate, "Choisir un numéro du menu.",
                         kind="choice", options=list(options) + (["aucun"] if allow_none else []))

    def _ask_yes_no(self, prompt):
        def validate(a):
            low = a.lower()
            if low in ("o", "oui", "y", "yes"):
                return True, True
            if low in ("n", "non", "no"):
                return True, False
            return False, None
        return self._ask(self.ui.yes_no(prompt), validate, "Répondre o ou n.", kind="yes_no")

    def _ask_free_text(self, prompt):
        prompt = self.ui.field(prompt)

        def validate(a):
            # Les guillemets doubles casseraient le STRING_LITERAL émis.
            if a and '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate, "Texte non vide, sans guillemets doubles.",
                         kind="free_text")

    def _ask_optional_free_text(self, prompt):
        """Comme _ask_free_text, mais une réponse vide vaut « passer »."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Texte sans guillemets doubles (ou vide pour passer).",
                         kind="free_text")

    def _ask_paragraphs(self, prompt):
        """Un texte éditorial en PLUSIEURS paragraphes (point 64).

        Une saisie d'une seule ligne était un piège silencieux : un « à
        propos » collé depuis un traitement de texte arrivait aplati, ses
        paragraphes recollés sans même une espace (« …8 ans.Mon travail… »),
        et l'IA d'interface recevait un mur de texte sans césure possible.
        Le retour à la ligne reste interdit — il casserait le
        STRING_LITERAL émis — donc on demande les paragraphes l'un après
        l'autre, et on les joint par un séparateur que le contrat retraduit
        en vrais sauts de paragraphe.

        Rend None si le premier paragraphe est vide (rubrique passée)."""
        premier = self._ask_optional_free_text(prompt)
        if not premier:
            return None
        paragraphes = [premier]
        while True:
            suite = self._ask_optional_free_text(
                "    … paragraphe suivant (vide pour terminer) > ")
            if not suite:
                return PARAGRAPH_SEP.join(paragraphes)
            paragraphes.append(suite)
