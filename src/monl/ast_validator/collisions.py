"""Ce qui se dispute une même route, et la restriction par champ.

`restrictedTo` (point 2, dont l'existence des références est vérifiée depuis
le point 112), les règles de message, et la matrice de collision entre deux
acteurs qui visent la même action."""

from .socle import ASTValidationError


class CollisionsMixin:
    """Ce qui se dispute une même route, et la restriction par champ."""

    def _valider_regle_restrictedTo(self):
        """Valide la règle 'restrictedTo' (point 112). Contrairement à
        'public'/'ownedBy'/'requiresOwn', rien ne vérifiait qu'un champ ou un
        acteur référencé par 'restrictedTo' existe réellement. Une faute de
        frappe sur le nom du champ ou de l'acteur désactivait silencieusement
        la restriction : _audit_security_rules ne trouverait jamais de
        correspondance, sans qu'aucun avertissement n'apparaisse -- exactement
        le genre de défaut que ownedBy/requiresOwn refusent déjà à la
        compilation."""
        for rule in self.rules:
            if rule["type"] != "restrictedTo":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'restrictedTo' rule must reference "
                    f"'Entity.field'; received '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'restrictedTo' rule targets entity "
                    f"'{entity}', which does not exist."
                )
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: the 'restrictedTo' rule targets field "
                    f"'{entity}.{field}', which is not a declared attribute -- "
                    f"a typo would silently disable the restriction."
                )
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure: the 'restrictedTo' rule on "
                    f"'{entity}.{field}' restricts access to actor '{actor}', "
                    f"which is not a declared actor."
                )

    def _valider_regles_message(self):
        """Valide les notifications e-mail déclenchées par une création.

        B2 choisit délibérément une seule transition : Create. La cible
        est le compte authentifié qui vient de créer la ligne, donc son
        identifiant canonique en base. Aucun champ métier libre nommé
        email ne participe à cette décision.
        """
        self.message_rules = []
        references = set()
        for rule in self.rules:
            if rule["type"] != "sends":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: the 'sends' rule must reference "
                    f"'Entity.Create'; received '{reference}'.")
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: 'sends' targets entity '{entity}', which does not exist.")
            if action != "Create":
                raise ASTValidationError(
                    f"Structure: 'sends' only applies to 'Entity.Create' "
                    f"(received '{reference}'). The oneOf transition is deliberately "
                    "outside this feature.")
            if reference in references:
                raise ASTValidationError(
                    f"Structure: multiple 'sends' rules target '{reference}' -- "
                    "a creation must trigger only one message.")
            references.add(reference)
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{reference}' is public, but 'sends' must "
                    "know the recipient account. A public creation provides "
                    "no identity to send a message to.")
            if not any(
                    action_["type"] == "Create" and action_["target"] == entity
                    for workflow in self.workflows
                    for action_ in workflow["actions"]):
                raise ASTValidationError(
                    f"Structure: '{reference}' has 'sends', but no Create {entity} "
                    "route is declared -- the message would never be sent.")
            if not self.auth_identifier or "email" not in self.auth_identifier:
                raise ASTValidationError(
                    f"Structure: '{reference}' wants to send an email, but the spec "
                    "does not declare 'capability auth' with 'identifier: email'. "
                    "Without this account identity, monl has no address to send to; "
                    "a free-text field named 'email' is not an account address.")

            subject = rule.get("subject", "")
            body = rule.get("body", "")
            if not subject.strip():
                raise ASTValidationError(
                    f"Structure: the subject of message '{reference}' cannot be empty.")
            if not body.strip():
                raise ASTValidationError(
                    f"Structure: the body of message '{reference}' cannot be empty.")
            if "\r" in subject or "\n" in subject:
                raise ASTValidationError(
                    f"Structure: the subject of '{reference}' contains a line break. "
                    "Rejected to prevent SMTP header injection (Bcc, Cc, etc.).")
            if "\r" in body or "\n" in body:
                raise ASTValidationError(
                    f"Structure: the body of '{reference}' contains a raw line break. "
                    "Use the '¶' separator between paragraphs.")
            self.message_rules.append({
                "trigger_entity": entity,
                "trigger_action": action,
                "subject": subject,
                "body": body,
            })

    def _valider_workflows_et_collisions(self):
        """Valide les workflows et détecte les collisions d'autorité."""
        access_matrix = {}
        shared_permissions = {
            rule["reference"]: set(rule["value"])
            for rule in self.rules if rule["type"] == "sharedBy"
        }
        for workflow in self.workflows:
            actor = workflow["actor"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure: actor '{actor}' in workflow '{workflow['name']}' is not declared."
                )
            for action in workflow["actions"]:
                target = action["target"]
                action_type = action["type"]
                if action_type == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(
                            f"Architecture: Execute action calls '{target}', but this custom block is not defined."
                        )
                    continue
                entity = target.split(".")[0] if "." in target else target
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure: action targets entity '{entity}', which does not exist."
                    )
                if (entity, action_type) in self.public_actions:
                    continue
                access_matrix.setdefault(entity, {}).setdefault(action_type, set()).add(actor)

        for entity, actions in access_matrix.items():
            for action_type, authorized_actors in actions.items():
                if len(authorized_actors) <= 1 or action_type not in ("Create", "Update", "Delete"):
                    continue
                key = f"{entity}.{action_type}"
                allowed_shared = shared_permissions.get(key)
                if allowed_shared and authorized_actors.issubset(allowed_shared):
                    print(f"🤝 [SHARED_PRIVILEGE] Action '{action_type}' on '{entity}' is explicitly "
                          f"shared among [{', '.join(sorted(authorized_actors))}] via a 'sharedBy' rule.")
                    continue
                if (entity, action_type) in self.ownership_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_OWNERSHIP] Action '{action_type}' on '{entity}' is shared "
                          f"among [{', '.join(sorted(authorized_actors))}], but protected at the record level "
                          f"by the 'ownedBy' rule (owner: "
                          f"{self.ownership_rules[(entity, action_type)]}).")
                    continue
                if (entity, action_type) in self.access_party_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_ACCESS] Action '{action_type}' on '{entity}' is shared "
                          f"among [{', '.join(sorted(authorized_actors))}], but protected at the record level "
                          f"by the 'accessibleBy' rule (parties: {self.access_party_rules[(entity, action_type)]}).")
                    continue
                actors = ", ".join(sorted(authorized_actors))
                suggestion = f"'rule {entity}.{action_type} sharedBy {actors}'"
                extra = ""
                if allowed_shared:
                    uncovered = authorized_actors - allowed_shared
                    extra = (f" A 'sharedBy' rule already exists for '{key}' but does not cover: "
                             f"[{', '.join(sorted(uncovered))}].")
                raise ASTValidationError(
                    f"🔒 [CRITICAL_COLLISION] Authority conflict on entity '{entity}': "
                    f"actors [{actors}] are all allowed to perform action '{action_type}'. "
                    f"Separate these privileges, or explicitly declare sharing with: {suggestion}.{extra}"
                )
