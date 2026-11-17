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
                        f"Structure: custom block '{custom['name']}' cannot accept "
                        "an Upload as input. Bytes pass only through the entity's "
                        "multipart route, never through the sandbox.")
        regles = {}
        for rule in self.rules:
            if rule.get("type") != "upload":
                continue
            reference = rule.get("reference", "")
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: the 'upload' rule must reference 'Entity.field', "
                    f"received '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'upload' rule targets entity '{entity}', "
                    "which does not exist.")
            declared = self.entities[entity].get(field)
            if declared is None:
                raise ASTValidationError(
                    f"Structure: the 'upload' rule targets field '{reference}', "
                    "which is not declared.")
            if declared != "Upload":
                raise ASTValidationError(
                    f"Structure: the 'upload' rule targets '{reference}' of type "
                    f"'{declared}'. Only the Upload type accepts a client upload; "
                    "Image remains a build-time asset.")
            if reference in regles:
                raise ASTValidationError(
                    f"Structure: multiple 'upload' rules declare '{reference}'.")
            maximum = rule.get("max_bytes")
            if not isinstance(maximum, int) or maximum <= 0:
                raise ASTValidationError(
                    f"Structure: the maximum size for '{reference}' must be a "
                    f"strictly positive integer (received {maximum!r}).")
            accepted = list(rule.get("accepted_types") or [])
            if not accepted:
                raise ASTValidationError(
                    f"Structure: the 'upload' rule for '{reference}' must declare "
                    "at least one permitted MIME type.")
            if len(set(accepted)) != len(accepted):
                raise ASTValidationError(
                    f"Structure: the 'upload' rule for '{reference}' repeats a MIME "
                    "type; each type must be declared only once.")
            inconnus = [mime for mime in accepted if mime not in self.UPLOAD_TYPES]
            if inconnus:
                raise ASTValidationError(
                    f"Structure: unauthorized MIME type(s) for '{reference}': "
                    f"{', '.join(inconnus)}. Recognized safe formats: "
                    f"{', '.join(sorted(self.UPLOAD_TYPES))}. Executable HTML and SVG "
                    "are rejected by design.")
            regles[reference] = {
                "entity": entity, "field": field, "max_bytes": maximum,
                "accepted_types": accepted,
            }

        for entity, fields in self.entities.items():
            for field, declared in fields.items():
                reference = f"{entity}.{field}"
                if declared == "Upload" and reference not in regles:
                    raise ASTValidationError(
                        f"Structure: '{reference}: Upload' has no upload rule. "
                        f"Declare 'rule {reference} upload max N types \"…\"': "
                        "the type alone would produce neither a limit nor a route.")

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
                    f"Structure: '{reference}' requires Read and Update workflows "
                    f"on '{entity}' to produce the read/upload routes; "
                    f"missing {', '.join(sorted(missing))}.")
            for action in ("Read", "Update"):
                if (entity, action) in self.public_actions or (
                        action == "Read" and (entity, "Read") in self.public_conditions):
                    raise ASTValidationError(
                        f"Security: file '{reference}' is private by default; "
                        f"'{entity}.{action}' cannot be public. Upload contents must "
                        "never be readable without the row's ACL.")
                if (entity, action) not in self.ownership_rules and (
                        entity, action) not in self.access_party_rules:
                    raise ASTValidationError(
                        f"Security: '{entity}.{action}' must use 'ownedBy' or "
                        "'accessibleBy' so an Upload file cannot be read merely by "
                        "knowing its path.")
        self.upload_fields = [
            regles[f"{entity}.{field}"]
            for entity, fields in self.entities.items()
            for field, declared in fields.items()
            if declared == "Upload"
        ]
