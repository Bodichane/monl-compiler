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
                    f"Structure : la règle 'restrictedTo' doit référencer "
                    f"'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' cible l'entité "
                    f"'{entity}' qui n'existe pas."
                )
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' cible le champ "
                    f"'{entity}.{field}', qui n'est pas un attribut déclaré -- "
                    f"une faute de frappe désactiverait silencieusement la "
                    f"restriction."
                )
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' sur "
                    f"'{entity}.{field}' restreint à l'acteur '{actor}', qui "
                    f"n'est pas un acteur déclaré."
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
                    f"Structure : la règle 'sends' doit référencer "
                    f"'Entite.Create', reçu '{reference}'.")
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'sends' cible l'entité '{entity}' qui n'existe pas.")
            if action != "Create":
                raise ASTValidationError(
                    f"Structure : 'sends' ne vaut que sur 'Entite.Create' "
                    f"(reçu '{reference}'). La transition oneOf est volontairement "
                    "hors de cette brique.")
            if reference in references:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'sends' sur '{reference}' -- "
                    "une création ne doit déclencher qu'un seul message.")
            references.add(reference)
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{reference}' est public, mais 'sends' doit "
                    "connaître le compte destinataire. Une création publique "
                    "n'offre aucune identité à laquelle écrire.")
            if not any(
                    action_["type"] == "Create" and action_["target"] == entity
                    for workflow in self.workflows
                    for action_ in workflow["actions"]):
                raise ASTValidationError(
                    f"Structure : '{reference}' porte 'sends', mais aucune route "
                    f"Create {entity} n'est déclarée -- l'envoi ne se déclencherait jamais.")
            if not self.auth_identifier or "email" not in self.auth_identifier:
                raise ASTValidationError(
                    f"Structure : '{reference}' veut envoyer un courriel, mais la spec "
                    "ne déclare pas 'capability auth' avec 'identifier: email'. "
                    "Sans cette identité de compte, monl n'a aucune adresse où écrire ; "
                    "un champ texte libre nommé 'email' ne vaut pas une adresse de compte.")

            subject = rule.get("subject", "")
            body = rule.get("body", "")
            if not subject.strip():
                raise ASTValidationError(
                    f"Structure : le sujet du message '{reference}' ne peut pas être vide.")
            if not body.strip():
                raise ASTValidationError(
                    f"Structure : le corps du message '{reference}' ne peut pas être vide.")
            if "\r" in subject or "\n" in subject:
                raise ASTValidationError(
                    f"Structure : le sujet de '{reference}' contient un saut de ligne. "
                    "Refusé pour empêcher une injection d'en-têtes SMTP (Bcc, Cc, etc.).")
            if "\r" in body or "\n" in body:
                raise ASTValidationError(
                    f"Structure : le corps de '{reference}' contient un saut de ligne brut. "
                    "Utiliser le séparateur '¶' entre les paragraphes.")
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
                    f"Structure : L'acteur '{actor}' dans le workflow '{workflow['name']}' n'est pas déclaré."
                )
            for action in workflow["actions"]:
                target = action["target"]
                action_type = action["type"]
                if action_type == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(
                            f"Architecture : L'action Execute appelle '{target}', mais ce bloc custom n'est pas défini."
                        )
                    continue
                entity = target.split(".")[0] if "." in target else target
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : L'action cible l'entité '{entity}' qui n'existe pas."
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
                    print(f"🤝 [SHARED_PRIVILEGE] L'action '{action_type}' sur '{entity}' est explicitement "
                          f"partagée entre [{', '.join(sorted(authorized_actors))}] via une règle 'sharedBy'.")
                    continue
                if (entity, action_type) in self.ownership_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_OWNERSHIP] L'action '{action_type}' sur '{entity}' est partagée "
                          f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                          f"enregistrement par la règle 'ownedBy' (propriétaire : "
                          f"{self.ownership_rules[(entity, action_type)]}).")
                    continue
                if (entity, action_type) in self.access_party_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_ACCESS] L'action '{action_type}' sur '{entity}' est partagée "
                          f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                          f"enregistrement par la règle 'accessibleBy' "
                          f"(parties : {self.access_party_rules[(entity, action_type)]}).")
                    continue
                actors = ", ".join(sorted(authorized_actors))
                suggestion = f"'rule {entity}.{action_type} sharedBy {actors}'"
                extra = ""
                if allowed_shared:
                    uncovered = authorized_actors - allowed_shared
                    extra = (f" Une règle 'sharedBy' existe déjà pour '{key}' mais ne couvre pas : "
                             f"[{', '.join(sorted(uncovered))}].")
                raise ASTValidationError(
                    f"🔒 [CRITICAL_COLLISION] Conflit d'autorité sur l'entité '{entity}' : "
                    f"les acteurs [{actors}] ont tous le droit d'exécuter l'action '{action_type}'. "
                    f"Séparez ces privilèges, ou déclarez explicitement le partage avec : {suggestion}.{extra}"
                )
