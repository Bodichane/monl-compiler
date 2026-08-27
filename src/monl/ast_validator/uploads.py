"""Les fichiers que le CLIENT téléverse.

À ne pas confondre avec `assets.py`, qui porte les fichiers fournis par
l'HUMAIN à la compilation (brique 13). Ici c'est un tiers qui écrit, d'où
une liste fermée de formats : ni HTML ni SVG, qui seraient interprétés
comme du code depuis l'origine de l'application."""

from .socle import ASTValidationError


class UploadsMixin:
    """Les fichiers que le CLIENT téléverse."""

    # Formats dont le détecteur d'octets et le service de lecture ont une
    # politique sûre. HTML et SVG ne sont pas acceptés : ils pourraient être
    # interprétés comme du code depuis l'origine de l'application.
    UPLOAD_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf",
    }

    def _valider_champs_uploades(self):
        """Valide la déclaration complète d'un dépôt client.

        ``Image`` reste un chemin d'asset contrôlé à la compilation. Un
        ``Upload`` n'est accepté que s'il est relié à une règle complète, à
        une route d'écriture et de lecture, et à une ACL privée par
        enregistrement.
        """
        for custom in self.custom_logic.values():
            for input_ in custom.get("input", []):
                reference = input_.get("reference")
                input_type = input_.get("type")
                referenced_type = None
                if reference and "." in reference:
                    ref_entity, ref_field = reference.split(".", 1)
                    referenced_type = self.entities.get(ref_entity, {}).get(ref_field)
                if input_type == "Upload" or referenced_type == "Upload":
                    raise ASTValidationError(
                        f"Structure : le bloc custom '{custom['name']}' ne peut pas "
                        "prendre un Upload en entrée. Les octets passent uniquement "
                        "par la route multipart de l'entité, jamais par la sandbox.")
        regles = {}
        for rule in self.rules:
            if rule.get("type") != "upload":
                continue
            reference = rule.get("reference", "")
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' doit référencer 'Entite.champ', "
                    f"reçu '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible l'entité '{entity}', "
                    "qui n'existe pas.")
            declared = self.entities[entity].get(field)
            if declared is None:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible le champ '{reference}', "
                    "qui n'est pas déclaré.")
            if declared != "Upload":
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible '{reference}' de type "
                    f"'{declared}'. Seul le type Upload accepte un dépôt client ; "
                    "Image reste un asset fourni à la compilation.")
            if reference in regles:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'upload' déclarent '{reference}'.")
            maximum = rule.get("max_bytes")
            if not isinstance(maximum, int) or maximum <= 0:
                raise ASTValidationError(
                    f"Structure : la taille maximale de '{reference}' doit être un "
                    f"entier strictement positif (reçu {maximum!r}).")
            accepted = list(rule.get("accepted_types") or [])
            if not accepted:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' de '{reference}' doit déclarer "
                    "au moins un type MIME autorisé.")
            if len(set(accepted)) != len(accepted):
                raise ASTValidationError(
                    f"Structure : la règle 'upload' de '{reference}' répète un type "
                    "MIME ; chaque type doit être déclaré une seule fois.")
            inconnus = [mime for mime in accepted if mime not in self.UPLOAD_TYPES]
            if inconnus:
                raise ASTValidationError(
                    f"Structure : type(s) MIME non autorisé(s) pour '{reference}' : "
                    f"{', '.join(inconnus)}. Formats sûrs reconnus : "
                    f"{', '.join(sorted(self.UPLOAD_TYPES))}. HTML et SVG exécutables "
                    "sont refusés par conception.")
            regles[reference] = {
                "entity": entity, "field": field, "max_bytes": maximum,
                "accepted_types": accepted,
            }

        for entity, fields in self.entities.items():
            for field, declared in fields.items():
                reference = f"{entity}.{field}"
                if declared == "Upload" and reference not in regles:
                    raise ASTValidationError(
                        f"Structure : '{reference}: Upload' n'a aucune règle de dépôt. "
                        f"Déclarer 'rule {reference} upload max N types \"…\"' : "
                        "le type seul ne produirait ni limite ni route.")

        for reference, rule in regles.items():
            entity = rule["entity"]
            has_actions = {
                action["type"]
                for workflow in self.workflows
                for action in workflow["actions"]
                if action["type"] in ("Read", "Update")
                and action["target"].split(".", 1)[0] == entity
            }
            missing = {"Read", "Update"} - has_actions
            if missing:
                raise ASTValidationError(
                    f"Structure : '{reference}' nécessite des workflows Read et Update "
                    f"sur '{entity}' pour produire les routes de lecture/dépôt ; "
                    f"il manque {', '.join(sorted(missing))}.")
            for action in ("Read", "Update"):
                if (entity, action) in self.public_actions or (
                        action == "Read" and (entity, "Read") in self.public_conditions):
                    raise ASTValidationError(
                        f"Sécurité : le fichier '{reference}' est privé par défaut ; "
                        f"'{entity}.{action}' ne peut pas être public. Le contenu d'un "
                        "Upload ne doit jamais être lisible sans l'ACL de la ligne.")
                if (entity, action) not in self.ownership_rules and (
                        entity, action) not in self.access_party_rules:
                    raise ASTValidationError(
                        f"Sécurité : '{entity}.{action}' doit porter 'ownedBy' ou "
                        "'accessibleBy' pour qu'un fichier Upload ne soit pas lisible "
                        "par simple connaissance de son chemin.")
        self.upload_fields = [
            regles[f"{entity}.{field}"]
            for entity, fields in self.entities.items()
            for field, declared in fields.items()
            if declared == "Upload"
        ]
