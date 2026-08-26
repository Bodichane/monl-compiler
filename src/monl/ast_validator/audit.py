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
                    reports.append(f"⚠️  [CRITICAL_WARNING] Le workflow '{wf['name']}' permet à l'acteur '{actor}' de supprimer l'entité '{target}'. Assurez-vous que cette action est hautement sécurisée au niveau infra.")

                if action["type"] == "Execute":
                    if target not in custom_callers:
                        custom_callers[target] = set()
                    custom_callers[target].add(actor)

        for c_name, c_bloc in self.custom_logic.items():
            inputs = c_bloc.get("input", [])
            calling_actors = custom_callers.get(c_name, set())

            for inp in inputs:
                if "reference" in inp:
                    ref = inp["reference"]
                    if ref in restricted_fields:
                        allowed_actor = restricted_fields[ref]
                        for caller in calling_actors:
                            if caller != allowed_actor:
                                reports.append(f"🔒 [SECURITY_AUDIT] Le bloc de logique IA '{c_name}' (exécuté par '{caller}') utilise la donnée sensible '{ref}' restreinte à l'acteur '{allowed_actor}'.")

        if not reports:
            print("🛡️  Audit : Aucune vulnérabilité ou privilège excessif détecté dans la spécification.")
        else:
            print(f"🛑 Audit : {len(reports)} point(s) de vigilance sécurité identifié(s) :")
            for r in reports:
                print(f"   {r}")

        return reports

    def _audit_self_registration(self):
        """Rapporte le périmètre d'inscription libre déclaré par la spec."""
        reports = []
        provisioned = [a for a in self.actors if a not in self.self_register_actors]
        if self.self_register_actors:
            print(f"🔓 Inscription libre : [{', '.join(self.self_register_actors)}]"
                  + (f" — provisionnés hors ligne : [{', '.join(provisioned)}]."
                     if provisioned else " (tous les rôles)."))
        elif self.actors:
            print("🔒 Aucun acteur 'selfRegister' : '/register' refusera toute inscription "
                  "(comptes à créer via 'python3 manage.py adduser').")
        if not self.self_register_actors:
            reports.append(
                "[SECURITY_NOTE] Aucun acteur n'est marqué 'selfRegister' : "
                "'POST /register' refusera toutes les inscriptions et les comptes "
                "devront être créés hors ligne (python3 manage.py adduser). "
                f"Pour ouvrir l'inscription d'un rôle : 'actor {self.actors[0]} selfRegister'."
                if self.actors else
                "[SECURITY_NOTE] Aucun acteur déclaré."
            )
        else:
            reports.append(
                "[SECURITY_NOTE] Inscription libre ouverte à "
                f"[{', '.join(self.self_register_actors)}]"
                + (f" ; rôles provisionnés hors ligne : [{', '.join(provisioned)}]."
                   if provisioned else " (tous les rôles déclarés).")
            )
        return reports
