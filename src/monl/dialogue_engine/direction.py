"""What the site must SHOW: visual register, images, texts, footer.

Point 72: the dialogue gathers a DIRECTION, it picks neither palette nor
typography. Brick 30 (point 146): the footer links are DECLARED here — a
brick without a producer does not exist."""

from .foundations import DESIGN_IMAGERY, DESIGN_REGISTERS, address_of_link


class DirectionMixin:
    """What the site must SHOW: visual register, images, texts, footer."""

    def _ask_design_intent(self):
        """Visual intent (point 53) — asked ONLY if the user passes a brief: with no
        home page to write, these answers would serve no one. Returns the
        sentence added to the brief.

        What the structure does not say: the same spec (entities, routes, roles)
        serves a contemplative portfolio as well as a hurried back office. The UI
        AI cannot decide, and without guidance it renders the lowest common
        denominator."""
        self._show(self.ui.section(
            "Visual direction — what the structure does not tell the AI "
            "that will design the interface."))
        action = self._ask_free_text(
            "What should visitors be able to do when they arrive? > ")
        registry = self._ask_choice("Which visual style?",
                                    [short for short, _ in DESIGN_REGISTERS])
        images = self._ask_choice("How prominent should images be?",
                                  [short for short, _ in DESIGN_IMAGERY])
        phrase_registry = dict(DESIGN_REGISTERS)[registry]
        phrase_images = dict(DESIGN_IMAGERY)[images]
        return (f"the visitor must be able to {action.rstrip('.')} ; "
                f"{phrase_registry} ; {phrase_images}")

    def _ask_image_topic(self):
        """Subject of the illustrations (point 59, rewritten). The compiler cannot
        deduce it: "Blog for cyber experts" is a free sentence, from which
        extracting a keyword would be interpretation — which the dialogue forbids
        itself.

        What the answer produces has CHANGED: no remote URL anymore, but a
        sentence of the brief that tells the interface AI what the visuals must
        evoke. The question therefore keeps an effect; it is the demo images
        delivered by a third party that have disappeared."""
        if not self._ask_yes_no(
                "Should the illustrations evoke a specific subject? "
                "(otherwise: no visual guidance)"):
            return None
        return self._ask_free_text(
            "  Illustration keyword, preferably in English "
            "(e.g. cybersecurity, pottery, architecture) > ")

    @staticmethod
    def _is_field_image(name):
        return any(k in name.lower() for k in ("image", "photo", "cover", "avatar",
                                              "picture", "visuel", "illustration"))

    #: What a footer OFTEN carries, in the order one thinks of it. The list is
    #: OFFERED, never imposed: each entry is skipped by leaving it empty,
    #: exactly like the sections of point 61.
    LINKS_PROPOSES = (
        {"label": "Email", "ask": "contact address"},
        {"label": "Phone", "ask": "phone number"},
        {"label": "Instagram", "ask": "account address"},
        {"label": "Facebook", "ask": "page address"},
        {"label": "LinkedIn", "ask": "page address"},
    )

    #: Completion lives at module level: the platform's web console shares it
    #: without instantiating a dialogue.
    _address_complete = staticmethod(address_of_link)

    def _ask_footer_links(self):
        """The footer links (brick 30).

        The brick had existed since point 144 and NOTHING produced it: neither
        this dialogue nor any of the ten templates declared a single link, so
        every site came out with a footer without a destination. A rule that
        produces nothing is exactly what point 85 forbids the compiler; the
        prohibition holds just as much for the dialogue that writes the spec.

        monl does NOT check that an address responds — it makes no network call
        (same boundary as point 83 for remote images). It checks that a browser
        will be able to open it, and that is all it promises."""
        links, seen = [], set()

        def keep(label, input_):
            address = self._address_complete(input_)
            if address is None:
                self._say(self.ui.error(
                    f"Unrecognized address: {input_!r}. Expected a web address "
                    "(example.com/studio), an email address, or a phone number — "
                    "skipping this link."))
                return
            if address != input_.strip():
                self._say(self.ui.note(f"saved: {address}"))
            if label.casefold() in seen:
                self._say(self.ui.error(
                    f"‘{label}’ is already used: a footer with duplicate labels "
                    "makes it unclear which link to follow — skipping this link."))
                return
            seen.add(label.casefold())
            links.append({"label": label, "url": address})

        self._show(self.ui.section(
            "Footer — how to contact and follow you. A footer with no "
            "destinations makes a site look abandoned. monl does not check "
            "whether an address responds; it checks that a browser can open it. "
            "Leave blank to skip."))
        for propose in self.LINKS_PROPOSES:
            input_ = self._ask_optional_free_text(
                f"  {propose['label']} — {propose['ask']} > ")
            if input_:
                keep(propose["label"], input_)
        while self._ask_yes_no("  Add another link (X, YouTube, TikTok, "
                               "press…) ?"):
            label = self._ask_free_text("  Its label (e.g. YouTube) > ")
            input_ = self._ask_optional_free_text("  Its address > ")
            if input_:
                keep(label, input_)
        return links

    def _ask_editorial_sections(self, defaults=()):
        """Static editorial content (point 55). An entity, a field, a route describe
        DATA: nothing in a spec can carry an "about". Without these sections, the
        AI literally has no material for anything other than a list and a form.

        POINT 61: when the chosen template carries sections expected for its
        category, we no longer ask whether they EXIST — we ask for their TEXT,
        section by section. Asking "do you want an about?" of someone building a
        portfolio is the same mistake as in point 60. An empty answer skips the
        section: the standard is offered, never imposed."""
        sections = []
        header_shown = False
        for spec in defaults:
            if not header_shown:
                header_shown = True
                self._show(self.ui.section(
                    "About content — these sections are expected on this type "
                    "of site. No data can provide them; only your text can. "
                    "Enter one paragraph at a time; leave blank to skip."))
            body = self._ask_paragraphs(
                f"  {spec['title']} — {spec['ask']} > ")
            if body:
                sections.append({"title": spec["title"], "body": body})
        if defaults:
            if not self._ask_yes_no("  Add another section?"):
                return sections
        elif not self._ask_yes_no(
                "Add about content (about, approach, services…)? No site data "
                "can provide this."):
            return sections
        while True:
            title = self._ask_free_text(
                f"  Section title {len(sections) + 1} "
                f"(e.g. About) > ")
            body = self._ask_paragraphs("  Its text > ")
            if body:
                sections.append({"title": title, "body": body})
            if not self._ask_yes_no("  Add another section?"):
                return sections
