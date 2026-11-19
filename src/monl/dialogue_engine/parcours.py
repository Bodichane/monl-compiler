"""The guided path: the template catalog, and express mode."""

from .fondations import DESIGN_IMAGERY, DESIGN_REGISTERS, FIELD_TYPES


class ParcoursMixin:
    """The guided path: the template catalog, and express mode."""

    # ---------- dialogue flow ----------
    def run(self):
        """Leads the complete conversation and returns the text of the .ml spec.
        REWORK (point 45): the dialogue opens on the catalog of the 10 types of
        applications web developers build most — choosing a template prefills
        everything and asks only the follow-up questions specific to the template.
        "Start from scratch" keeps the free dialogue."""
        from ..app_templates import FREE_MODE_LABEL, TEMPLATES
        self._show(self.ui.banner())
        # ADDED (beta 3): the label and its explanation are now two distinct
        # columns of the menu, instead of a single "name — help" string that
        # overflowed on narrow terminals. The return value stays the full
        # string: the rest of the engine is unchanged.
        labels = [f"{t['name']} — {t['hint']}" for t in TEMPLATES] + [FREE_MODE_LABEL]
        courts = {label: TEMPLATES[i]["name"] for i, label in enumerate(labels[:-1])}
        courts[FREE_MODE_LABEL] = FREE_MODE_LABEL.split(" (")[0]
        aides = {t["name"]: f'{t["hint"]} — {self._ligne_de_compte(t)}'
                 for t in TEMPLATES}
        aides[courts[FREE_MODE_LABEL]] = "describe my entities freely, without a template"

        self._show(self.ui.plan(["Application type", "Project identity",
                                 "Template options", "Finishing touches"]))
        self._show(self.ui.phase(0))
        choisi_court = self._ask_choice("What type of application are you building?",
                                        [courts[label] for label in labels], hints=aides)
        picked = labels[[courts[label] for label in labels].index(choisi_court)]
        if picked == FREE_MODE_LABEL:
            return self._run_free()
        template = TEMPLATES[labels.index(picked)]
        if self.choose_experience:
            experience = self._ask_choice(
                "Which experience would you like?",
                ["Quick creation with AI", "Detailed customization"],
                hints={
                    "Quick creation with AI":
                        "recommended — Monl prepares the structure, content, and visual direction",
                    "Detailed customization":
                        "all questions about structure, content, and presentation",
                })
            self.express = experience.startswith("Quick creation")
        return self._run_from_template(template)

    @staticmethod
    def _express_intent(template):
        """A safe and precise enough direction for express mode.

        It never changes the functional contract: it only allows the frontend AI
        to do its editorial and visual job from the template."""
        name = template["name"]
        if name in {"Portfolio / showcase site", "Blog"}:
            register, imagery = DESIGN_REGISTERS[1][1], DESIGN_IMAGERY[0][1]
        elif name in {"Task management", "Inventory / stock management",
                      "Personal expense tracking"}:
            register, imagery = DESIGN_REGISTERS[2][1], DESIGN_IMAGERY[1][1]
        elif name in {"Online shop", "Community ranking"}:
            register, imagery = DESIGN_REGISTERS[3][1], DESIGN_IMAGERY[0][1]
        else:
            register, imagery = DESIGN_REGISTERS[1][1], DESIGN_IMAGERY[0][1]
        return (
            "use the main flow expected for this category right away ; "
            f"{register} ; {imagery} ; express mode: the frontend AI "
            "writes the missing presentation texts, builds a page dense with "
            "useful blocks and produces consistent local SVG illustrations, "
            "without inventing any data, route or feature"
        )

    @staticmethod
    def _ligne_de_compte(template):
        """Will visitors have an account? DERIVED, never written by hand.

        The question "website or application?" does not exist in the dialogue,
        and that is deliberate: everything monl produces has a server and a
        database. What varies is whether someone registers — and one does not
        pick from a list without knowing what it implies.

        The answer comes from `_default_self_register`, the very one the dialogue
        uses as a default: the displayed line therefore cannot diverge from what
        will really be built. Writing a table by hand would make it stop keeping
        up with the first template added — point 146.

        This function's meaning is NARROW and the sentence respects it: it says
        which role would be offered at open registration, NOT whether the site is
        readable without an account. "Inventory" has no public role and yet is
        not a storefront."""
        managers = {n: [m["manager"]] for n, m in template["entities"].items()}
        owned = {n: m["manager"] for n, m in template["entities"].items()
                 if m["owned"]}
        role = ParcoursMixin._default_self_register(
            template["actors"], managers, owned)
        return (f"self-registration: {role}" if role
                else "accounts created by the administrator")

    @staticmethod
    def _default_self_register(actors, managers, owned):
        """Cautious choice of the public role, the deterministic counterpart of the
        question."""
        privilegies = {
            actor
            for entity, entity_managers in managers.items()
            for actor in entity_managers
            if owned.get(entity) != actor and entity != actor
        }
        return next((actor for actor in actors if actor not in privilegies), None)

    @staticmethod
    def _express_image_topic(template):
        """Public keyword per category, without disclosing the free brief.

        The URLs are loaded from a third party by the browser. Injecting the
        description into them could pass on a client, a place or an idea that is
        still confidential."""
        return {
            "Portfolio / showcase site": "creative-studio",
            "Blog": "editorial",
            "Online shop": "products",
            "Task management": "workspace",
            "Forum / social network": "community",
            "Classified ads": "marketplace",
            "Appointment booking": "wellness-service",
            "Inventory / stock management": "warehouse",
            "Personal expense tracking": "finance-desk",
            "Community ranking": "competition",
        }.get(template["name"], "abstract")

    def _run_from_template(self, template):
        """"Template" path: specific follow-up questions, then the shared
        finishing touches. The template is deep-copied — the catalog is never
        mutated between two runs (determinism)."""
        import copy

        from ..app_templates import apply_effects
        template = copy.deepcopy(template)

        self._show(self.ui.phase(1))
        app_name = self._ask_identifier("Application name (e.g. StudioNova) > ")
        description = self._ask_free_text(
            "Describe the project in one sentence (used as the frontend brief) > ")

        if self.express:
            return self._parcours_express(template, app_name, description)

        self._show(self.ui.phase(2))
        for followup in template["followups"]:
            if self._ask_yes_no(followup["ask"]):
                apply_effects(template, followup["effects"])

        # Conversion from the template to the emitter's format
        (entities, actors, managers, readers, public_read, public_create,
         owned, relations) = self._depuis_le_modele(template)

        # Escape hatch: one custom entity on top of the template.
        self._entites_sur_mesure(entities, actors, managers, readers, public_read)

        self._ensure_ownership_structure(entities, managers, readers, owned, relations)

        self._show(self.ui.phase(3))
        self_register = self._ask_self_register(actors, managers, owned)
        account_identifier = self._ask_account_identifier(self_register)
        upload_rules = self._ask_uploads(entities, public_read, owned)
        payable = (self._ask_payable(entities, owned, relations, managers, readers)
                   if template.get("accept_payments", True) else None)
        want_seed = bool(template["seeds"]) and self._ask_yes_no(
            "Pre-fill the site with the template's demo data?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Send your description to the frontend AI as the homepage brief?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = (self._ask_editorial_sections(template.get("sections", []))
                    if want_landing else [])
        links = self._ask_footer_links() if want_landing else []
        self._recap(app_name, entities, actors, self_register, public_read, owned,
                    payable=payable)

        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read, public_create,
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               links=links,
                               image_topic=image_topic,
                               self_register=self_register,
                               account_identifier=account_identifier,
                               extra_rules=template["extra_rules"] + upload_rules,
                               extra_workflows=template.get("extra_workflows", ()),
                               custom_seeds=template["seeds"],
                               payable=payable)
        return self._revalider_la_spec(spec)

    def _parcours_express(self, template, app_name, description):
        """Express mode: the template as is, no question asked."""
        (entities, actors, managers, readers, public_read, public_create,
         owned, relations) = self._depuis_le_modele(template)
        self._ensure_ownership_structure(
            entities, managers, readers, owned, relations)
        self_register = self._default_self_register(actors, managers, owned)
        self._recap(app_name, entities, actors, self_register, public_read, owned)
        spec = self._emit_spec(
            app_name, description, entities, relations, actors, managers,
            readers, public_read, public_create, owned,
            want_seed=bool(template["seeds"]), want_landing=True,
            design_intent=self._express_intent(template), sections=(),
            links=self.express_links,
            image_topic=self._express_image_topic(template),
            self_register=self_register,
            extra_rules=template["extra_rules"], custom_seeds=template["seeds"])
        return self._revalider_la_spec(spec)

    @staticmethod
    def _depuis_le_modele(template):
        """The template converted to the emitter's format."""
        entities = {name: list(meta["fields"]) for name, meta in template["entities"].items()}
        actors = list(template["actors"])
        managers = {name: [meta["manager"]] for name, meta in template["entities"].items()}
        readers = {name: set(meta["readers"]) for name, meta in template["entities"].items()}
        public_read = [n for n, m in template["entities"].items() if m["public_read"]]
        public_create = [n for n, m in template["entities"].items() if m["public_create"]]
        owned = {n: m["manager"] for n, m in template["entities"].items() if m["owned"]}
        relations = list(template["relations"])
        return (entities, actors, managers, readers, public_read, public_create,
                owned, relations)

    def _entites_sur_mesure(self, entities, actors, managers, readers, public_read):
        """Custom entities added on top of the template, one at a time."""
        while self._ask_yes_no("Add a custom entity in addition to the template?"):
            name = self._ask_identifier("  Entity name > ", forbidden=entities.keys())
            fields = self._champs_sur_mesure(name)
            entities[name] = fields
            managers[name] = [actors[0] if len(actors) == 1
                              else self._ask_choice(f"  Who manages {name} for writing?", actors)]
            readers[name] = set()
            if self._ask_yes_no(f"  Should {name} be readable without an account?"):
                public_read.append(name)

    def _champs_sur_mesure(self, name):
        """The fields of a custom entity: at least one, blank to finish."""
        fields = []
        while True:
            taken = [f for f, _ in fields]
            fprompt = (f"  First field for {name} > " if not fields
                       else f"  Another field for {name} (leave blank to finish) > ")
            fname = (self._ask_identifier(fprompt, forbidden=taken) if not fields
                     else self._ask_optional_identifier(fprompt, forbidden=taken))
            if fname is None:
                break
            ftype = self._ask_choice(f"  Type of {name}.{fname}?", FIELD_TYPES)
            fields.append((fname, ftype))
        return fields

    @staticmethod
    def _revalider_la_spec(spec):
        """The produced spec goes through the real parser and validator."""
        from ..ast_validator import MonlAST
        from ..parser import parse_monl_string
        MonlAST(parse_monl_string(spec)).validate_and_audit()
        return spec
