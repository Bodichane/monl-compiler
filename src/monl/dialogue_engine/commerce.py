"""The commerce chain, set up in one question (point 86).

The dialogue produces the WHOLE chain — cart, transitive ownership,
`derivedFrom`, `sumOf`, `min`, count, `payable`. Any change to the order
of questions after `_ask_self_register` must have
`tests/test_app_templates.py` checked: three templates ask the `payable`
question, and the scripted answers shift otherwise."""

class CommerceMixin:
    """The commerce chain, set up in one question (point 86)."""

    FIELD_QUANTITY = "quantite"

    # BRICK B1: a single menu carries the three choices an Upload requires.
    # There is no implicit ceiling or type: the user picks a profile whose
    # label shows the field, the exact limit and the allowed MIME types.
    UPLOAD_PROFILES = (
        ("Photo", "photo", 5 * 1024 * 1024, ("image/png", "image/jpeg")),
        ("Document PDF", "document", 10 * 1024 * 1024, ("application/pdf",)),
    )

    # POINT 86: a cart line's subtotal. Named here rather than hard-coded in
    # the emitter — two places would eventually diverge.
    FIELD_SOUS_TOTAL = "sousTotal"

    # POINT 89: the arrival date of what is charged. NO question offers it, on
    # purpose: it is written by the server, so it cannot be wrong, and an order
    # without a date is not an order — the only useful answer would be "yes".
    # The dialogue likewise already emits the total, the stock floor and the
    # count without having them decided one by one.
    FIELD_DATE = "creeLe"

    @classmethod
    def _upload_profiles_for(cls, fields):
        """Profiles this entity can receive without a field collision."""
        types = dict(fields)
        existing = [name for name, type_ in fields if type_ == "Upload"]
        if len(existing) > 1:
            return []
        result = []
        for label, default_field, maximum, accepted_types in cls.UPLOAD_PROFILES:
            field = existing[0] if existing else default_field
            if not existing and field in types:
                continue
            result.append((label, field, maximum, accepted_types))
        return result

    def _ask_uploads(self, entities, public_read, owned):
        """Declares the uploads a dialogue can produce safely.

        An Upload must have a private Read and Update route, and a per-row ACL.
        The dialogue produces these routes and the `ownedBy` ACL for an owned,
        non-public entity; all others are therefore excluded before asking the
        question. A chosen profile writes the field and the complete rule in a
        single pass."""
        public = set(public_read)
        rules = []
        for entity, fields in entities.items():
            if entity not in owned or entity in public:
                continue
            profiles = self._upload_profiles_for(fields)
            if not profiles:
                continue
            labels = [
                f"{label} — field {field}, {maximum} bytes, "
                f"types {', '.join(accepted_types)}"
                for label, field, maximum, accepted_types in profiles
            ]
            # The question SAYS what it produces. Without that, one picks
            # "Photo" for an ad believing buyers will see it — yet the rule
            # written is `ownedBy`, and they get a 403 (measured). monl cannot
            # serve an uploaded file publicly, and keeping quiet about it would
            # build a catalog without images.
            choice = self._ask_choice(
                f"Which file upload for {entity}? "
                "(the file will only be readable by its owner)",
                labels, allow_none=True)
            if choice is None:
                continue
            profile = profiles[labels.index(choice)]
            _label, field, maximum, accepted_types = profile
            if not any(name == field for name, _type in fields):
                fields.append((field, "Upload"))
            mime_list = ", ".join(f'"{mime}"' for mime in accepted_types)
            rules.append(
                f"rule {entity}.{field} upload max {maximum} types {mime_list}")
        return rules

    def _ask_payable(self, entities, owned, relations, managers, readers):
        """What amount does this application charge? (points 75 and 79)

        The `payable` brick (point 74) was unreachable from the only path most
        users take: the spec had to be written by hand. A capability the dialogue
        cannot express does not exist for them.

        **What point 79 changed.** The question started from a `Money` field on an
        owned entity. That was too little: a record's creator becomes its owner,
        hence the payer — and if the amount is an ordinary field, the payer sets
        what they pay themselves. The compiler now refuses it. The dialogue can
        therefore no longer ask the question on the mere presence of a `Money`: it
        needs something to have the server CALCULATE the amount.

        Concretely, a catalog is needed: ANOTHER entity carrying a price, which
        the charged entity can reference. The dialogue then builds the complete
        structure — a quantity, the relation to the catalog, and the two rules —
        instead of leaving the author to assemble it from memory.

        **What this requirement revealed.** Of the three catalog templates that
        carried a `Money` on an owned entity, two had no catalog to reference —
        and for a good reason: in "Classified ads" the seller creates their ad, so
        they own it, so they are the payer; they would pay themselves. In
        "Personal expense tracking", the ledger is personal. The question should
        never have been asked of them. A compiler refusal fixed a dialogue
        question.

        Returns None, or a dictionary describing the derivation. Mutates
        `entities` and `relations` to add what the brick requires."""
        candidates = self._candidates_payables(entities, owned)
        if not candidates:
            return None
        if not self._ask_yes_no(
                "Does this application accept online payments?"):
            return None
        choice = self._choose_the_amount(candidates)
        entity, amount, source, price = choice
        result = {"entity": entity, "field": amount,
                    "source_entity": source, "source_field": price,
                    "factor": self.FIELD_QUANTITY}
        # POINT 89: the timestamp, added at the END — the emitter's "first
        # required field" rule would otherwise apply to a field the client
        # cannot send, and compilation would fail (point 85 cross-check).
        if not any(c == self.FIELD_DATE for c, _t in entities[entity]):
            entities[entity].append((self.FIELD_DATE, "DateTime"))

        # POINT 86: the dialogue could produce an order with ONE item — the
        # point 77 shape — while the compiler has been able to make a cart
        # since point 82. A capability the dialogue does not express does not
        # exist for anyone who does not write the spec by hand: exactly the
        # argument that gave birth to this question at point 75, still valid
        # four bricks later.
        self._build_the_cart(entity, amount, source, result,
                                   entities, owned, relations, managers, readers)

        self._ask_the_stock(source, price, entities, result)

        self._show(self.ui.note(
            f"Amount charged: {entity}.{amount} — CALCULATED by the server, "
            "never sent by the browser. Without this calculation, the buyer "
            "would set their own price."))
        return result

    def _candidates_payables(self, entities, owned):
        """(entity, amount, catalog, price) pairs the server can calculate."""
        candidates = []
        for ent in entities:
            if ent not in owned:
                continue
            amounts = [c for c, t in entities[ent] if t == "Money"]
            if not amounts:
                continue
            # A catalog: another entity carrying a price. It is what lets the
            # server calculate, hence not trust the client.
            for source in entities:
                # Neither the entity itself nor its OWNER: the owner's foreign
                # key comes from the token, not the client, so no row could be
                # designated there. The validator refuses it; the dialogue must
                # not offer what the compiler rejects.
                if source == ent or source == owned.get(ent) or source in owned:
                    continue
                price = [c for c, t in entities[source]
                        if t in ("Money", "Float", "Integer")]
                if price:
                    candidates.append((ent, amounts[0], source, price[0]))
        return candidates

    def _choose_the_amount(self, candidates):
        """The only candidate, or the one the author picks."""
        if len(candidates) == 1:
            return candidates[0]
        labels = [f"{e}.{m} (calculated from {s}.{p})"
                    for e, m, s, p in candidates]
        return candidates[labels.index(
            self._ask_choice("Which amount should be charged?", labels))]

    def _build_the_cart(self, entity, amount, source, result,
                              entities, owned, relations, managers, readers):
        """Multi-item cart (lines, transitive ownership) or single-item shape."""
        cart = self._ask_yes_no(
            f"Can a {entity} contain MULTIPLE different items?")
        if cart:
            line = self._name_of_line(entity, entities)
            # The quantity FIRST: the emitter's "first required field" rule
            # makes it mandatory, which the calculation needs.
            entities[line] = [(self.FIELD_QUANTITY, "Integer"),
                               (self.FIELD_SOUS_TOTAL, "Money")]
            for rel in ((entity, "hasMany", line), (source, "hasMany", line)):
                if rel not in relations:
                    relations.append(rel)
            managers[line] = list(managers.get(entity, []))
            readers[line] = set(readers.get(entity, set()))
            # TRANSITIVE ownership (point 81): the line belongs to whoever owns
            # its order. The emitter writes 'ownedBy <entity>' from this
            # dictionary — no special syntax to invent here.
            owned[line] = entity
            result["line_entity"] = line
            self._show(self.ui.note(
                f"Cart: each {line} holds an item and its quantity; "
                f"{entity}.{amount} is the TOTAL, recalculated by the server "
                f"whenever a line is added, updated, or deleted."))
        else:
            # Single-item shape: the quantity lives on the charged entity.
            if not any(c == self.FIELD_QUANTITY for c, _t in entities[entity]):
                entities[entity].append((self.FIELD_QUANTITY, "Integer"))
            if not any(r[0] == source and r[2] == entity for r in relations):
                relations.append((source, "hasMany", entity))

    def _ask_the_stock(self, source, price, entities, result):
        """Offers the stock countdown, never guessing the field."""
        # POINT 86: the stock count, made reachable here. The field is not
        # GUESSED among the catalog's integers — guessing wrong would silently
        # count down something other than what one thinks.
        stocks = [c for c, t in entities[source] if t == "Integer" and c != price]
        if stocks and self._ask_yes_no(
                f"Should stock in {source} be decremented with each purchase?"):
            result["stock_field"] = (stocks[0] if len(stocks) == 1 else
                                       self._ask_choice("Which field holds the stock?",
                                                        stocks))
