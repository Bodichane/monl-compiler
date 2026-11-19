"""The path without a template: the user describes their entities."""

from .fondations import RELATION_TYPES


class LibreMixin:
    """The path without a template: the user describes their entities."""

    def _run_free(self):
        """The historical free dialogue — unchanged, behind "start from scratch"."""
        self._show(self.ui.plan(["Project identity", "Data", "Public access",
                                 "Actors", "Write permissions", "Relations",
                                 "Finishing touches"]))
        self._show(self.ui.phase(0))
        app_name = self._ask_identifier("Application name (e.g. StudioNova) > ")
        description = self._ask_free_text("Describe the project in one sentence (used on the homepage) > ")

        # Entities and fields
        entities = self._demander_les_entites()
        entity_names = list(entities.keys())

        # Public storefront (reading without an account) and public creation
        # (contact)
        self._show(self.ui.phase(2))
        public_read, public_create = self._demander_lacces_public(entity_names)

        # Acteurs
        actors = self._demander_les_acteurs()

        # Write management: a single actor by default (no collision possible,
        # strict rule no. 1 respected BY CONSTRUCTION), or an EXPLICIT sharing
        # between several actors — in which case the dialogue emits the
        # matching 'sharedBy' rules, exactly the legitimate path the compiler
        # provides (point 1 of the journal).
        managers = self._demander_les_gestionnaires(entity_names, actors)

        # Per-record ownership (ownedBy): only a record's creator can
        # update/delete it. Requires an "owner" entity named like the actor +
        # the relation that provides the foreign key column (canonical pattern:
        # exemples/03, point 5 of the journal). Not offered when management is
        # shared (v1).
        owned = self._demander_la_propriete(entities, entity_names, managers)

        # Additional readers (reads create no collision)
        readers = self._demander_les_lecteurs(entity_names, actors, managers)

        # Relations
        relations = self._demander_les_relations(entity_names)

        self._show(self.ui.phase(6))
        self_register = self._ask_self_register(actors, managers, owned)
        account_identifier = self._ask_account_identifier(self_register)
        upload_rules = self._ask_uploads(entities, public_read, owned)
        payable = self._ask_payable(entities, owned, relations, managers, readers)
        want_seed = self._ask_yes_no("Pre-fill the site with demo data?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Send your description to the frontend AI as the homepage brief?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = self._ask_editorial_sections() if want_landing else []
        links = self._ask_footer_links() if want_landing else []

        # Owning entities + ownership relations (helper shared with the
        # "template" path; deduplicated if already declared by hand).
        readers = {e: readers.get(e, set()) for e in entities}
        managers = {e: managers.get(e, [actors[0]]) for e in entities}
        self._ensure_ownership_structure(entities, managers, readers, owned, relations)

        self._recap(app_name, entities, actors, self_register, public_read, owned,
                    payable=payable)
        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read,
                               [public_create] if public_create else [],
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               links=links,
                               image_topic=image_topic,
                               self_register=self_register,
                               account_identifier=account_identifier,
                               payable=payable,
                               extra_rules=upload_rules)

        # Final guarantee: the emitted spec MUST compile. It is revalidated
        # through the real pipeline — if it does not, it is an engine bug, not
        # the user's, and we fail loudly rather than return a broken file.
        return self._revalider_la_spec(spec)

    def _demander_les_entites(self):
        """Entities and their fields, until a blank name."""
        entities = {}   # name -> [(field, type)]
        self._show(self.ui.phase(1))
        self._show(self.ui.section(
            "Let's define the data (entities). Example: Project, Message, Article…"))
        while True:
            prompt = ("Name of the first entity > " if not entities
                      else "Name of another entity (leave blank to finish) > ")
            name = (self._ask_identifier(prompt, forbidden=entities.keys()) if not entities
                    else self._ask_optional_identifier(prompt, forbidden=entities.keys()))
            if name is None:
                break
            fields = self._champs_sur_mesure(name)
            entities[name] = fields
        return entities

    def _demander_lacces_public(self, entity_names):
        """Public storefront and public creation (contact form)."""
        public_read = []
        for ent in entity_names:
            if self._ask_yes_no(f"Should entity {ent} be READABLE without an account (public showcase)?"):
                public_read.append(ent)
        public_create = self._ask_choice(
            "Can an entity be CREATED without an account (e.g. a contact form)?",
            entity_names, allow_none=True)
        return public_read, public_create

    def _demander_les_acteurs(self):
        """The actors, until a blank name."""
        actors = []
        self._show(self.ui.phase(3))
        self._show(self.ui.section("Who uses the application? (e.g. Admin, Visitor, Member…)"))
        while True:
            prompt = ("Name of the first actor > " if not actors
                      else "Another actor (leave blank to finish) > ")
            a = (self._ask_identifier(prompt, forbidden=actors) if not actors
                 else self._ask_optional_identifier(prompt, forbidden=actors))
            if a is None:
                break
            actors.append(a)
        return actors

    def _demander_les_gestionnaires(self, entity_names, actors):
        """Who writes each entity: one actor, or an explicit share."""
        managers = {}  # ent -> [actors] (only 1, or 2+ if shared)
        for ent in entity_names:
            if len(actors) == 1:
                managers[ent] = [actors[0]]
                continue
            pick = self._ask_choice(
                f"Who manages {ent} for writing (create/update/delete)?",
                actors + ["(multiple actors share management)"])
            if pick != "(multiple actors share management)":
                managers[ent] = [pick]
                continue
            shared = [a for a in actors
                      if self._ask_yes_no(f"  Does {a} help manage {ent}?")]
            if len(shared) < 2:
                self._say(self.ui.error("Sharing requires at least two actors — "
                                        "management assigned to the first actor."))
                shared = [shared[0] if shared else actors[0]]
            managers[ent] = shared
        return managers

    def _demander_la_propriete(self, entities, entity_names, managers):
        """Per-record ownership, creating the owner entity if needed."""
        owned = {}  # ent -> owning entity
        for ent in entity_names:
            if len(managers[ent]) != 1:
                continue
            actor = managers[ent][0]
            if not self._ask_yes_no(
                    f"Should every {ent} record belong to its creator "
                    f"(only they can update/delete it)?"):
                continue
            owned[ent] = actor
            if actor not in entities:
                entities[actor] = [("displayName", "String")]
                entity_names.append(actor)
                managers[actor] = [actor]
                self._show(self.ui.note(
                    f"Owner entity '{actor}' created automatically "
                    f"(displayName: String), linked by '{actor} hasMany {ent}'."))
        return owned

    def _demander_les_lecteurs(self, entity_names, actors, managers):
        """Additional signed-in readers per entity."""
        readers = {ent: set() for ent in entity_names}
        for ent in entity_names:
            for act in actors:
                if act in managers[ent]:
                    continue
                if self._ask_yes_no(f"Can {act} READ {ent} (once signed in)?"):
                    readers[ent].add(act)
        return readers

    def _demander_les_relations(self, entity_names):
        """Relations between entities, until '(finish)'."""
        relations = []
        if len(entity_names) >= 2 and self._ask_yes_no("\nAre any entities related to each other?"):
            while True:
                src = self._ask_choice("Source entity for the relation?", entity_names + ["(finish)"])
                if src == "(finish)":
                    break
                rtype = self._ask_choice(
                    f"Relation type from {src}? (hasMany: {src} contains multiple targets)",
                    RELATION_TYPES)
                targets = [e for e in entity_names if e != src]
                tgt = self._ask_choice("Target entity?", targets)
                relations.append((src, rtype, tgt))
                if not self._ask_yes_no("Add another relation?"):
                    break
        return relations

    @staticmethod
    def _ensure_ownership_structure(entities, managers, readers, owned, relations):
        """Every ownedBy rule requires an owning entity named like the actor + the
        relation that provides the foreign key (point 5, the exemples/03
        pattern). Created here if missing — shared between the "template" path
        and the free path."""
        for ent, owner in list(owned.items()):
            if owner not in entities:
                entities[owner] = [("displayName", "String")]
                managers[owner] = [owner]
                readers[owner] = set()
            if (owner, "hasMany", ent) not in relations:
                relations.append((owner, "hasMany", ent))

    @staticmethod
    def _nom_de_ligne(entite, entities):
        """A free entity name for the cart line. A silent collision would overwrite
        one of the user's entities."""
        base = f"Ligne{entite}"
        nom, n = base, 2
        while nom in entities:
            nom, n = f"{base}{n}", n + 1
        return nom
