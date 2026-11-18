"""Access control: WHO has the right, and on WHICH rows.

POINT 109: the access-control model lives here and nowhere else —
`ownedBy` (direct and transitive), `accessibleBy`, the supervisor, and
anonymous visibility. It is the DECISION side of security; the EMISSION
side is `generator/sql.py` (point 108)."""

from .socle import ASTValidationError


class AccesMixin:
    """Access control: WHO has the right, and on WHICH rows."""

    def _valider_controle_dacces(self):
        """The core of access control — a security boundary (point 109).

        Gathers, in a dedicated pipeline pass, EVERYTHING that decides WHO may
        touch WHAT: the 'ownedBy' rules (direct ownership), the resolution of the
        transitive chain up to an actor (bricks 11 and 24), the 'accessibleBy'
        rules (multi-party access) and the supervisor role (brick 23). Fills
        self.ownership_rules, self.transitive_ownership and
        self.access_supervisors, then read by the generator through
        _transitive_chain / _owner_lookup_sql.

        Uses only self.* and forms a self-contained pipeline boundary."""
        # ADDED (post-v6, roadmap): 'ownedBy' rules restrict an action to the
        # sole record belonging to the current actor. They require a 'hasMany'
        # relation between the declared "owner" entity and the target entity,
        # to provide the foreign key column that stores the owner
        # (automatically generated as <source>_id).
        self.ownership_rules = {}
        for rule in self.rules:
            if rule["type"] == "ownedBy":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule must reference 'Entity.Action', got '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                owner_entity = rule["value"]

                if entity not in self.entities:
                    raise ASTValidationError(f"Structure: the 'ownedBy' rule targets entity '{entity}', which does not exist.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure: invalid action '{act_type}' in the 'ownedBy' rule on '{entity}'.")
                # FIX (beta 3): 'Create' was accepted while the generator did
                # nothing with it — a security rule accepted then silently
                # ignored is worse than its absence, because the spec's author
                # believes the protection is in place. At creation, the owner
                # is the caller by construction: the rule has nothing to
                # restrict.
                if act_type == "Create":
                    raise ASTValidationError(
                        f"Structure: 'ownedBy' is not meaningful on '{entity}.Create' — "
                        "on creation, the owner is the caller by definition. "
                        "Use 'ownedBy' on Read, Update, or Delete.")

                # FIX (roadmap): checking the required relation is now
                # generalized to the 3 types (hasMany, hasOne, belongsTo),
                # consistent with _compute_fk_placements() in generator.py —
                # before, only 'hasMany' was recognized here, whereas
                # 'belongsTo'/'hasOne' also provide a valid ownership column
                # according to their own placement convention.
                has_matching_relation = any(
                    (rel["type"] in ("hasMany", "hasOne") and rel["source"] == owner_entity and rel["target"] == entity)
                    or (rel["type"] == "belongsTo" and rel["target"] == owner_entity and rel["source"] == entity)
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule on '{entity}.{act_type}' references owner "
                        f"'{owner_entity}', but no compatible relationship ('{owner_entity} hasMany {entity}', "
                        f"'{owner_entity} hasOne {entity}', or '{entity} belongsTo {owner_entity}') is declared."
                    )

                # The named owner is either an ACTOR (direct ownership, the
                # historical brick) or an ENTITY (TRANSITIVE ownership, brick
                # 11 / point 81) -- this second case is resolved after this
                # loop, which needs to know ALL the 'ownedBy' rules to climb
                # the chain up to an account.
                self.ownership_rules[(entity, act_type)] = owner_entity

        # ADDED (roadmap, capability ecosystem -- brick 11, point 81):
        # TRANSITIVE ownership. "This order line belongs to whoever owns its
        # order": the named owner is an ENTITY, not an actor, and the chain
        # climbs to an account through that intermediate's 'ownedBy' rule.
        #
        # Why this resolution lives AFTER the loop: it needs the intermediate's
        # 'ownedBy' rules, which may be declared further down in the spec than
        # the one referring to it. Same reason as the point 79 cross-check.
        #
        # What point 80 had found, and which stays refused here: naming an
        # entity that climbs to NO account compiled silently and produced
        # inconsistent code — a foreign key announced toward the accounts
        # table, the caller's identifier written instead of the requested
        # attachment, a read filter comparing a record id with an account id.
        # Checked at runtime: an order line attached itself to the buyer's
        # account, never to the named order. The chain must therefore lead
        # somewhere, otherwise refusal.
        self.transitive_ownership = {}
        proprietaires_par_entite = {}
        for (ent, _act), owner in self.ownership_rules.items():
            proprietaires_par_entite.setdefault(ent, set()).add(owner)

        for (entity, act_type), owner_entity in sorted(self.ownership_rules.items()):
            if owner_entity in self.actors:
                continue

            # ADDED (brick 24, point 107): the chain used to climb ONE
            # intermediate only ('{entity} -> via -> actor'). It now climbs the
            # full depth, link by link, up to an ACTOR. Each link must be owned
            # by ONE SINGLE owner (otherwise ambiguity: which path to check?)
            # and the walk must neither loop nor end in a void.
            maillon = owner_entity
            vus = set()
            chaine = []
            while maillon not in self.actors:
                if maillon in vus:
                    raise ASTValidationError(
                        f"Structure: the ownership chain for '{entity}' loops at '{maillon}' "
                        f"('{entity}' -> {' -> '.join(chaine)} ...) -- the server cannot resolve it. "
                        f"Break the cycle."
                    )
                vus.add(maillon)
                chaine.append(maillon)
                parents = proprietaires_par_entite.get(maillon, set())
                if not parents:
                    raise ASTValidationError(
                        f"Structure: the 'ownedBy' rule on '{entity}.{act_type}' designates "
                        f"'{owner_entity}' as owner, but the chain '{entity}' -> "
                        f"{' -> '.join(chaine)} does not lead to ANY actor -- the server cannot "
                        f"verify WHO owns a '{entity}'. Add a rule "
                        f"'<last link>.Read ownedBy <Actor>', or attach '{entity}' "
                        f"directly to an actor."
                    )
                if len(parents) > 1:
                    raise ASTValidationError(
                        f"Structure: the ownership chain for '{entity}' is ambiguous at "
                        f"'{maillon}': it is owned by multiple different entities "
                        f"({', '.join(sorted(parents))}) -- the server cannot determine which one "
                        f"to check. Designate only one on '{maillon}'."
                    )
                maillon = next(iter(parents))
            acteur = maillon
            # Mixing direct and transitive ownership on the SAME entity would
            # make its foreign key both filled from the token (for one rule)
            # and supplied by the client (for the other): two contradictory
            # treatments on a single column.
            autres = proprietaires_par_entite.get(entity, set()) - {owner_entity}
            if autres:
                raise ASTValidationError(
                    f"Structure: '{entity}' is owned through '{owner_entity}' (transitive "
                    f"ownership) but also designates '{', '.join(sorted(autres))}' as owner "
                    f"-- its ownership foreign key would be supplied by the client and "
                    f"derived from the token. Designate only one owner for '{entity}'."
                )
            self.transitive_ownership[entity] = {"chain": chaine, "actor": acteur}

        # ADDED (roadmap, capability ecosystem -- "two-party access" brick):
        # 'accessibleBy' rules restrict an action to the records where one of
        # the listed columns contains the caller's identifier. Canonical use
        # case: private messaging (sender through the auto-filled relation
        # column, recipient through a declared Integer field). Each column must
        # be either a declared Integer field of the entity, or the foreign key
        # column derived from an incoming relation (e.g. 'user_id').
        self.access_party_rules = {}
        for rule in self.rules:
            if rule["type"] != "accessibleBy":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule must reference 'Entity.Action', got '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            columns = rule["value"]

            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'accessibleBy' rule targets entity '{entity}', which does not exist.")
            if act_type not in ("Read", "Update", "Delete"):
                raise ASTValidationError(
                    f"Structure: invalid action '{act_type}' in the 'accessibleBy' rule on '{entity}' "
                    f"(only Read/Update/Delete apply to an existing record whose parties can be checked)."
                )
            if len(set(columns)) < 2:
                raise ASTValidationError(
                    f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' must list at least two "
                    f"distinct columns — with only one party, use 'ownedBy'."
                )

            # Foreign key columns an incoming relation provides to this entity
            # (same convention as _compute_fk_placements in generator.py:
            # '<source>_id').
            relation_fk_columns = set()
            for rel in self.relations:
                if rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity:
                    relation_fk_columns.add(f"{rel['source'].lower()}_id")
                elif rel["type"] == "belongsTo" and rel["source"] == entity:
                    relation_fk_columns.add(f"{rel['target'].lower()}_id")

            for col in columns:
                declared_type = self.entities[entity].get(col)
                if col in relation_fk_columns:
                    continue
                if declared_type is None:
                    raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' references column "
                        f"'{col}', which is neither a declared field of '{entity}' nor an incoming relationship column "
                        f"({', '.join(sorted(relation_fk_columns)) or 'no incoming relationship'})."
                    )
                if declared_type != "Integer":
                    raise ASTValidationError(
                        f"Structure: the 'accessibleBy' rule on '{entity}.{act_type}' requires '{col}' to be "
                        f"of type Integer (user identifier), got '{declared_type}'."
                    )

            if (entity, act_type) in self.ownership_rules:
                raise ASTValidationError(
                    f"Conflict: '{entity}.{act_type}' has both 'ownedBy' and 'accessibleBy' — "
                    f"choose one ('accessibleBy' generalizes 'ownedBy' to multiple parties)."
                )

            self.access_party_rules[(entity, act_type)] = list(columns)

            # ADDED (brick 23, point 106): a SUPERVISOR role can pierce this
            # column check. Syntax: a 'sharedBy' rule carrying the SAME
            # reference — 'rule Message.Delete sharedBy Moderator' placed next
            # to 'rule Message.Delete accessibleBy member_id, recipient_id'.
            # The role so named sees/deletes/ updates every record; the parties
            # stay confined to their own. It is, for 'accessibleBy', the exact
            # counterpart of the supervisor already acquired for 'ownedBy' at
            # point 88 ('rule X.Update sharedBy Proprietaire, Patron'). The
            # named roles must be declared actors.
            superviseurs = self._superviseurs_declares(entity, act_type)
            if superviseurs:
                self.access_supervisors[(entity, act_type)] = superviseurs

    def _superviseurs_declares(self, entity, act_type):
        """The roles named by a 'sharedBy' carrying the exact reference.

        SINGLE source of the supervisor, shared by 'accessibleBy' (brick 23, point
        106) and by 'publicWhen' (point 116). Two parallel resolutions would
        eventually diverge on role validation — and it is precisely that
        validation that prevents a typo from silently disabling supervision (same
        lesson as point 112)."""
        ref = f"{entity}.{act_type}"
        superviseurs = []
        for r in self.rules:
            if r["type"] == "sharedBy" and r["reference"] == ref:
                for role in r["value"]:
                    if role not in self.actors:
                        raise ASTValidationError(
                            f"Structure: supervisor role '{role}' in the 'sharedBy' rule "
                            f"on '{ref}' is not a declared actor."
                        )
                    if role not in superviseurs:
                        superviseurs.append(role)
        return superviseurs

    def _valider_regle_public(self):
        """The 'public' rule — an action that no longer requires authentication
        (point 111). Uses only self.rules, self.entities, self.public_actions."""
        # ADDED (roadmap, portfolio use case): validation of 'public' rules —
        # an action so marked no longer requires authentication on the
        # generated route (e.g. reading a portfolio without an account, sending
        # a contact message without an account).
        for rule in self.rules:
            if rule["type"] == "public":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure: the 'public' rule must reference 'Entity.Action', got '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure: the 'public' rule targets entity '{entity}', which does not exist.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure: invalid action '{act_type}' in the 'public' rule on '{entity}'.")
                self.public_actions.add((entity, act_type))
            elif rule["type"] == "publicWhen":
                reference = rule["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' must reference 'Entity.Read', got '{reference}'."
                    )
                entity, act_type = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' targets entity '{entity}', which does not exist."
                    )
                if act_type != "Read":
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' only applies to 'Read' (got '{reference}')."
                    )
                field = rule.get("field")
                if field not in self.entities[entity]:
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' targets field '{field}', which does not exist on '{entity}'."
                    )
                if self.entities[entity][field] not in ("String", "Text", "Email", "UUID"):
                    raise ASTValidationError(
                        f"Structure: 'publicWhen' requires a text field, got '{entity}.{field}' "
                        f"of type '{self.entities[entity][field]}'."
                    )
                if (entity, act_type) in self.public_actions:
                    raise ASTValidationError(
                        f"Structure: '{reference}' is both 'public' and 'publicWhen' — "
                        "only one visibility policy is allowed."
                    )
                if (entity, act_type) in self.public_conditions:
                    raise ASTValidationError(
                        f"Structure: multiple 'publicWhen' rules on '{reference}' — "
                        "the condition would be ambiguous."
                    )
                self.public_actions.add((entity, act_type))
                self.public_conditions[(entity, act_type)] = {
                    "field": field, "value": rule.get("value", "")
                }
                # POINT 116: a 'sharedBy' on the SAME reference names the roles
                # that pierce the condition — same keyword and same meaning as
                # the accessibleBy supervisor (brick 23). Without it, hiding
                # content ALSO took it away from the moderator who had just
                # hidden it: they could neither reread it nor undo the action.
                superviseurs = self._superviseurs_declares(entity, act_type)
                if superviseurs:
                    self.access_supervisors[(entity, act_type)] = superviseurs
