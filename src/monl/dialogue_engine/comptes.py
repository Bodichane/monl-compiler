"""Who registers, and with which form of identifier.

POINT 138: the identifier question was asked by NOBODY — every project
born from the dialogue accepted `'!!!'` as an account identifier. A brick
that constrains an INPUT must be wired into the dialogue, otherwise it
only protects hand-written specs."""

from .fondations import PHONE_PREFIX_RE


class ComptesMixin:
    """Who registers, and with which form of identifier."""

    def _ask_self_register(self, actors, managers, owned):
        """Which role can create its account from the site?

        A security question, therefore asked — never guessed. The order of the
        options carries the recommendation: first the roles that manage no data
        in writing (a visitor, a customer), because opening registration to a
        managing role amounts to letting anyone grant themselves write
        permissions."""
        if not actors:
            return None
        # A role is "privileged" if it writes to SHARED data. Writing only to
        # its own records (ownedBy rule) or to its own profile (an entity named
        # like the actor) is not: that is precisely what a customer or a member
        # does. Without this distinction, a template where each role manages
        # something would offer the administrator first — exactly the
        # privilege-escalation flaw fixed elsewhere.
        privilegies = set()
        for entite, gestionnaires in managers.items():
            for acteur in gestionnaires:
                if owned.get(entite) == acteur or entite == acteur:
                    continue
                privilegies.add(acteur)
        consommateurs = [a for a in actors if a not in privilegies]
        ordonnes = consommateurs + [a for a in actors if a in privilegies]
        aides = {a: ("recommended — writes only to their own data"
                     if a in consommateurs else
                     "manages shared data: enable with care")
                 for a in ordonnes}
        choisi = self._ask_choice(
            "Which role can create an account on the site?",
            ordonnes, allow_none=True, hints=aides)
        if choisi is None:
            self._show(self.ui.note(
                "No online registration: accounts will be created on the "
                "server with 'python3 manage.py adduser'."))
        return choisi

    def _ask_account_identifier(self, self_register):
        """What do accounts log in with? (brick 1, point 95)

        The brick had existed since point 95 and the dialogue never offered it: no
        spec coming from a template declared an identifier, and `username` stayed
        free text. Seen on `projets/AtelierNaya`, a beauty workshop in Cotonou:
        `'!!!'` and even two spaces created an account, and the workshop received
        bookings it could not honor for lack of a way to reach anyone. Same
        family as point 90 — an order without a recipient cannot be shipped.

        The question is asked ONLY if someone registers online: without
        registration, accounts are born in `manage.py`, where the form check is
        deliberately absent (service roles without an address).

        The ORDER of the options carries the recommendation, as in
        `_ask_self_register`. The phone comes first: in the targeted market, it is
        the real callback channel, well ahead of email.

        Choosing nothing leaves the spec WITHOUT a `capability auth` block — not
        an empty block. `None` is not `[]` (point 95): that is what guarantees
        that a spec written before this question compiles identically."""
        if not self_register:
            return None
        choix = self._ask_choice(
            "How will users sign in?",
            ["Phone number", "Email address", "Phone or email, user's choice"],
            allow_none=True,
            hints={
                "Phone number": "recommended if you call your customers back",
                "Email address": "if you communicate in writing",
                "Phone or email, user's choice": "each person signs up as they prefer",
            })
        if choix is None:
            self._show(self.ui.note(
                "Unrestricted identifier: any text can be used for an account, "
                "and you will have no way to contact the person again."))
            return None
        formes = {"Phone number": ["phone"],
                  "Email address": ["email"],
                  "Phone or email, user's choice": ["email", "phone"]}[choix]

        prefixe = None
        if "phone" in formes:
            # POINT 95: without a calling code, "97…" and "+22997…" are TWO
            # accounts for one person. monl makes people DECLARE what it cannot
            # guess — it does not know the application's country.
            def valide(a):
                if a == "":
                    return True, None
                if PHONE_PREFIX_RE.match(a):
                    return True, a
                return False, None
            prefixe = self._ask(
                self.ui.field("Country calling code for phone numbers "
                              "(e.g. +229 for Benin, leave blank for none) > "),
                valide, "A calling code starts with + followed by 1 to 4 digits.",
                kind="free_text")
            if prefixe is None:
                self._show(self.ui.note(
                    "Without a calling code, '97…' and '+22997…' will be "
                    "different accounts for the same person."))
        configuration = {"formes": formes, "prefixe": prefixe}
        if formes == ["email"]:
            configuration.update(self._ask_email_verification())
        return configuration

    def _ask_email_verification(self):
        """The brick's producer: only an email registration."""
        if not self._ask_yes_no("Require email address confirmation before sign-in?"):
            return {}
        duree = self._ask_positive_seconds("Confirmation link validity, in seconds")
        maximum = self._ask_positive_seconds("Maximum resends in the window")
        fenetre = self._ask_positive_seconds("Resend window, in seconds")
        return {"verify_email": duree, "verify_resend": (maximum, fenetre)}

    def _ask_positive_seconds(self, titre):
        def valide(value):
            if value.isdecimal() and int(value) > 0:
                return True, int(value)
            return False, None
        return self._ask(self.ui.field(titre + " > "), valide,
                         "Enter a strictly positive integer.", kind="free_text")
