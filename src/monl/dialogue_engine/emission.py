"""Écrire la spec, et la faire REVALIDER par le vrai parseur.

L'outil écrit, le compilateur prouve : la spec produite est relue par le
vrai parseur avant d'être écrite sur le disque."""

from . import emission_parts
from .fondations import DialogueError


class EmissionMixin:
    """Écrire la spec, et la faire REVALIDER par le vrai parseur."""

    def _recap(self, app_name, entities, actors, self_register, public_read, owned,
               payable=None):
        """Dernier regard sur ce qui va être écrit, avant compilation."""
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

    # ---------- émission déterministe de la spec ----------
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
                # Le timestamp de payable est émis par `emit_payable`, pas
                # dans `extra_rules`; son tri doit néanmoins suivre la même
                # dérivation sans recopier la règle timestamp elle-même.
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
        """Valeur de seed -> littéral DSL (la grammaire n'accepte que
        STRING_LITERAL et SIGNED_NUMBER)."""
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
            # VIDE, jamais une URL distante : une démonstration qui va chercher
            # ses images chez un tiers contredit l'autonomie que monl promet, et
            # ne s'ouvre pas hors ligne. La vraie photo passe par
            # `monl assets add` (brique 13). Voir `_img` dans app_templates.py.
            return '""'
        if ftype == "Text":
            return f'"Demo content number {n}, generated by the guided dialogue."'
        return f'"Example {n}"'
