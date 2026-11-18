"""L'audit `[SECURITY_AUDIT]` — ce qui AVERTIT sans refuser.

À garder distinct des refus : un avertissement qui bloquerait immobiliserait
des projets sains, et un refus qui n'avertirait que ferait passer une faille
pour un détail de style."""




class AuditMixin:
    """L'audit `[SECURITY_AUDIT]` — ce qui AVERTIT sans refuser."""

    def _audit_security_rules(self):
        """Moteur d'analyse statique traquant les vulnérabilités complexes."""
        reports = []
        restricted_fields = {}

        for rule in self.rules:
            if rule["type"] == "restrictedTo":
                restricted_fields[rule["reference"]] = rule["value"]

        custom_callers = {}
        for wf in self.workflows:
            actor = wf["actor"]
            for action in wf["actions"]:
                target = action["target"]
                if action["type"] == "Delete" and actor != "Admin":
                    reports.append(f"⚠️  [CRITICAL_WARNING] Workflow '{wf['name']}' allows actor '{actor}' to delete entity '{target}'. Ensure this action is highly secured at the infrastructure level.")

                if action["type"] == "Execute":
                    if target not in custom_callers:
                        custom_callers[target] = set()
                    custom_callers[target].add(actor)

        reports.extend(self._audit_blocs_custom(restricted_fields, custom_callers))

        if not reports:
            print("🛡️  Audit: No vulnerabilities or excessive privileges detected in the specification.")
        else:
            print(f"🛑 Audit: {len(reports)} security concern(s) identified:")
            for r in reports:
                print(f"   {r}")

        return reports

    def _audit_blocs_custom(self, restricted_fields, custom_callers):
        """Un bloc `custom` lancé par un acteur qui n'a pas droit à une donnée
        `restrictedTo` qu'il lit. Extrait de `_audit_security_rules` (plafond
        de complexité) ; rapports et ordre inchangés."""
        reports = []
        for c_name, c_bloc in self.custom_logic.items():
            calling_actors = custom_callers.get(c_name, set())
            for inp in c_bloc.get("input", []):
                ref = inp.get("reference")
                if ref is None or ref not in restricted_fields:
                    continue
                allowed_actor = restricted_fields[ref]
                for caller in calling_actors:
                    if caller != allowed_actor:
                        reports.append(f"🔒 [SECURITY_AUDIT] AI logic block '{c_name}' (run by '{caller}') uses sensitive data '{ref}', restricted to actor '{allowed_actor}'.")
        return reports

    def _audit_self_registration(self):
        """Rapporte le périmètre d'inscription libre déclaré par la spec."""
        reports = []
        provisioned = [a for a in self.actors if a not in self.self_register_actors]
        if self.self_register_actors:
            print(f"🔓 Open registration: [{', '.join(self.self_register_actors)}]"
                  + (f" — provisioned offline: [{', '.join(provisioned)}]."
                     if provisioned else " (all roles)."))
        elif self.actors:
            print("🔒 No 'selfRegister' actor: '/register' will reject all registrations "
                  "(accounts must be created via 'python3 manage.py adduser').")
        if not self.self_register_actors:
            reports.append(
                "[SECURITY_NOTE] No actor is marked 'selfRegister': "
                "'POST /register' will reject all registrations and accounts "
                "must be created offline (python3 manage.py adduser). "
                f"To open registration for a role: 'actor {self.actors[0]} selfRegister'."
                if self.actors else
                "[SECURITY_NOTE] No actor declared."
            )
        else:
            reports.append(
                "[SECURITY_NOTE] Open registration for "
                f"[{', '.join(self.self_register_actors)}]"
                + (f"; roles provisioned offline: [{', '.join(provisioned)}]."
                   if provisioned else " (all declared roles).")
            )
        return reports
