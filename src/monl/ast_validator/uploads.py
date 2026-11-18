"""The files the CLIENT uploads.

Not to be confused with `assets.py`, which carries the files supplied by
the HUMAN at compile time (brick 13). Here a third party writes, hence a
closed list of formats: neither HTML nor SVG, which would be interpreted
as code from the application's origin."""

from .socle import ASTValidationError


class UploadsMixin:
    """The files the CLIENT uploads."""

    # Formats for which the byte detector and the read service have a safe
    # policy. HTML and SVG are not accepted: they could be interpreted as code
    # from the application's origin.
    UPLOAD_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf",
    }

    def _valider_champs_uploades(self):
        """Validates the complete declaration of a client upload.

        ``Image`` stays an asset path checked at compile time. An ``Upload`` is
        accepted only if it is tied to a complete rule, to a write and a read
        route, and to a private per-record ACL."""
        self._refuser_upload_en_entree_custom()
        regles = {}
        for rule in self.rules:
            if rule.get("type") != "upload":
                continue
            reference, declaration = self._exiger_regle_upload(rule, regles)
            regles[reference] = declaration
        self._exiger_une_regle_par_upload(regles)
        self._exiger_acl_des_uploads(regles)
        self.upload_fields = [
            regles[f"{entity}.{field}"]
            for entity, fields in self.entities.items()
            for field, declared in fields.items()
            if declared == "Upload"
        ]

    def _refuser_upload_en_entree_custom(self):
        """Bytes never enter the sandbox: no custom block takes an Upload."""
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

    def _exiger_regle_upload(self, rule, regles):
        """One 'upload' rule, checked: returns (reference, declaration)."""
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
        return reference, {
            "entity": entity, "field": field, "max_bytes": maximum,
            "accepted_types": accepted,
        }

    def _exiger_une_regle_par_upload(self, regles):
        """Every Upload field carries its rule: the type alone produces nothing."""
        for entity, fields in self.entities.items():
            for field, declared in fields.items():
                reference = f"{entity}.{field}"
                if declared == "Upload" and reference not in regles:
                    raise ASTValidationError(
                        f"Structure: '{reference}: Upload' has no upload rule. "
                        f"Declare 'rule {reference} upload max N types \"…\"': "
                        "the type alone would produce neither a limit nor a route.")

    def _exiger_acl_des_uploads(self, regles):
        """Read and Update exist, are never public, and carry a per-row ACL."""
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
