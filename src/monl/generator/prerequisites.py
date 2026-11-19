"""What you must ALREADY have, and who escapes a condition.

`requiresOwn` (point 90) and its counterpart on deletion (point 96), plus
the two DECLARATIVE exemptions of `publicWhen` (point 116) — the supervisor
and the owner. `_condition_exemptions` is the single source shared by the
route and the runtime."""

from string import Template


class PrerequisitesMixin:
    """What you must ALREADY have, and who escapes a condition."""

    def _condition_exemptions(self, entity):
        """POINT 116: WHO escapes this entity's 'publicWhen' condition.

        Returns (declared supervisors, owner identity columns). SINGLE source of
        the two exemptions: the read route emits them, and `runtime.py` uses it to
        write the optional identity dependency ONLY if at least one exemption
        exists — otherwise a spec with neither supervisor nor owner would carry a
        function nothing calls. Two separate computations would eventually
        diverge, and that is the kind of gap that reopens an access check."""
        if (entity, "Read") not in self.public_conditions:
            return [], []
        supervisors = sorted(self.access_supervisors.get(Template(r"""${entity}.Read""").substitute(entity=entity), []))
        owner = sorted(self._identity_fk_columns().get(entity, set()))
        return supervisors, owner

    def _condition_identity_needed(self):
        """True if at least one conditional read carries an exemption."""
        return any(any(self._condition_exemptions(entity))
                   for entity, action in self.public_conditions
                   if action == "Read")

    def _profile_lookup(self, entity):
        """POINT 90: (table, column) where to look for the profile that
        'requiresOwn' requires, or None if the rule does not apply to this entity.

        The column is the one that the REQUIRED entity's Create route fills from
        the token — hence the one that carries an ACCOUNT identifier. It comes from
        `_identity_fk_columns`, the single source of that distinction since point
        88: finding it another way means rewriting half of the bug that point
        fixed."""
        required = self.required_profiles.get(entity)
        if not required:
            return None
        columns = self._identity_fk_columns().get(required, set())
        if not columns:
            return None
        return required.lower(), sorted(columns)[0]

    def _profile_dependents(self, entity):
        """POINT 96: entities that REQUIRE a profile of 'entity' to exist.

        Exact counterpart of `_profile_lookup`, at the other end of the life
        cycle. `requiresOwn` guarded CREATION and nothing else: on
        `projets/SneakerLab`, deleting one's customer profile left the order in
        the database — an order on the books with no recipient, exactly the state
        point 90 was written to prevent. The hole reopened from the other end.

        Returns [(table, account column)]: where to look for the records that
        would become orphans."""
        dependents = []
        for dependent, required in sorted(self.required_profiles.items()):
            if required != entity:
                continue
            columns = self._identity_fk_columns().get(dependent, set())
            if not columns:
                # Without an identity column, nothing links the dependent to an
                # account: we do not guess rather than refuse wrongly.
                continue
            dependents.append((dependent, dependent.lower(), sorted(columns)[0]))
        return dependents

    def _profile_account_column(self, entity):
        """Account column of the REQUIRED entity itself — to count the remaining
        profiles. `requiresOwn` asks for "at least one": deleting the second to
        last is therefore legitimate, only the LAST one is refused."""
        columns = self._identity_fk_columns().get(entity, set())
        return sorted(columns)[0] if columns else None
