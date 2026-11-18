"""Write the spec, and have the real parser REVALIDATE it.

The tool writes, the compiler proves: the produced spec is reread by the
real parser before being written to disk."""

from . import emission_parts
from .fondations import DialogueError


class EmissionMixin:
    """Write the spec, and have the real parser REVALIDATE it."""

    def _recap(self, app_name, entities, actors, self_register, public_read, owned,
               payable=None):
        """A last look at what is about to be written, before compilation."""
        lignes = [
            ("Application", app_name),
            ("Entities", ", ".join(entities) or "none"),
            ("Roles", ", ".join(actors) or "none"),
            ("Online registration", self_register or "closed (manage.py)"),
            ("Readable without an account", ", ".join(public_read) or "none"),
        ]
        prives = [e for e in owned if e not in public_read]
        if prives:
            lignes.append(("Owner-only reading", ", ".join(prives)))
        if owned:
            lignes.append(("Creator ownership",
                           ", ".join(f"{e} ({a})" for e, a in owned.items())))
        if payable:
            lignes.append((
                "Amount charged",
                f"{payable['entity']}.{payable['field']} — calculated by the server "
                f"({payable['source_entity']}.{payable['source_field']} × "
                f"{payable['factor']}), Stripe key required"))
        self._show(self.ui.recap("What the spec will declare", lignes))

    # ---------- deterministic emission of the spec ----------
    def _emit_spec(self, app_name, description, entities, relations, actors,
                   managers, readers, public_read, public_create,
                   owned, want_seed, want_landing, design_intent=None,
                   sections=(), links=(),
                   image_topic=None,
                   self_register=None, extra_rules=(), extra_workflows=(),
                   custom_seeds=None,
                   payable=None, account_identifier=None):
        lines = emission_parts.spec_header(app_name, description, image_topic)
        emission_parts.emit_structure(lines, entities, relations, actors, self_register)
        emission_parts.emit_capability(lines, account_identifier)

        extra_rules = list(extra_rules)
        extra_rules.extend(emission_parts.derived_list_rules(entities, extra_rules))
        if payable:
            entity = payable["entity"]
            timestamped = any(
                field == self.CHAMP_DATE
                for field, _type in entities.get(entity, ()))
            if timestamped:
                sort_rule = f"rule {entity}.Read sort {self.CHAMP_DATE}"
                # The payable timestamp is emitted by `emit_payable`, not in
                # `extra_rules`; its sort must nevertheless follow the same
                # derivation without copying the timestamp rule itself.
                if sort_rule not in extra_rules:
                    extra_rules.append(sort_rule)
        calculated = emission_parts.calculated_server_fields(self, payable)
        emission_parts.emit_base_rules(
            lines, entities, extra_rules, public_read, public_create, owned,
            managers, calculated,
        )
        emission_parts.emit_payable(self, lines, payable)
        emission_parts.emit_extra_rules(lines, extra_rules, payable)

        emission_parts.emit_workflows(lines, entities, managers, extra_workflows,
                                      actors, readers)

        emission_parts.emit_seeds(self, lines, entities, public_read, want_seed,
                                  custom_seeds, image_topic)

        emission_parts.emit_landing(lines, description, design_intent, image_topic,
                                    want_landing, sections, links)
        return "\n".join(lines)

    @staticmethod
    def _literal(value):
        """Seed value -> DSL literal (the grammar accepts only STRING_LITERAL and
        SIGNED_NUMBER)."""
        if isinstance(value, bool):
            raise DialogueError("a seed cannot contain a boolean (grammar)")
        if isinstance(value, (int, float)):
            return str(value)
        return '"' + str(value).replace('"', "'") + '"'

    @staticmethod
    def _seed_value(field_name, ftype, n, image_topic=None):
        low = field_name.lower()
        if ftype in ("Integer",):
            return str(n * 10)
        if ftype in ("Float", "Money"):
            return f"{n * 10}.5"
        if ftype == "Email":
            return f'"demo{n}@exemple.fr"'
        if any(k in low for k in ("image", "photo", "url", "cover", "avatar")):
            # EMPTY, never a remote URL: a demo that fetches its images from a
            # third party contradicts the autonomy monl promises, and does not
            # open offline. The real photo goes through `monl assets add`
            # (brick 13). See `_img` in app_templates.py.
            return '""'
        if ftype == "Text":
            return f'"Demo content number {n}, generated by the guided dialogue."'
        return f'"Example {n}"'
