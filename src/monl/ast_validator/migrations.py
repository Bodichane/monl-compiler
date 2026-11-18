"""Declared migrations, and what they are allowed to do.

The point 32 rule, held ever since: a migration is ADDITIVE. It catches up
a column, never its content (points 89 and 99)."""

from .socle import ASTValidationError


class MigrationsMixin:
    """Declared migrations, and what they are allowed to do."""

    def _operation_de_migration(self, name, reference, entity, field, operation, known_types):
        """A `rename`, `alter` or `drop` operation, validated and normalized.
        Extracted from `_valider_migrations` (complexity ceiling); refusals,
        messages and the operation's shape unchanged."""
        kind = operation["kind"]
        if kind == "rename":
            new_field = operation["new_name"]
            if field == new_field:
                raise ASTValidationError(
                    f"Structure: migration '{name}' renames "
                    f"'{reference}' to itself.")
            if field in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: source column '{reference}' still exists "
                    "in the target spec; remove it before renaming it.")
            if new_field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: rename '{reference}' to "
                    f"'{entity}.{new_field}' cannot find the target column "
                    "in the current spec.")
            return {
                "kind": kind, "entity": entity, "table": entity.lower(),
                "old": field, "new": new_field, "reversible": True,
            }
        if kind == "alter":
            old_type = operation["from_type"]
            new_type = operation["to_type"]
            if old_type not in known_types or new_type not in known_types:
                raise ASTValidationError(
                    f"Structure: migration '{name}' has unknown types "
                    f"({old_type} -> {new_type}).")
            if old_type == new_type:
                raise ASTValidationError(
                    f"Structure: migration '{name}' does not change the type "
                    f"of '{reference}'.")
            actual_type = self.entities[entity].get(field)
            if actual_type != new_type:
                raise ASTValidationError(
                    f"Structure: target spec for '{name}' declares '{reference}' "
                    f"as {actual_type}, but the operation specifies {new_type}.")
            return {
                "kind": kind, "entity": entity, "table": entity.lower(),
                "field": field, "from_type": old_type, "to_type": new_type,
                "reversible": True,
            }
        if field in self.entities[entity]:
            raise ASTValidationError(
                f"Structure: dropped column '{reference}' still exists "
                "in the target spec; remove it before the explicit DROP.")
        return {
            "kind": kind, "entity": entity, "table": entity.lower(),
            "old": field, "reversible": False,
        }

    def _valider_migrations(self):
        """Validates the schema operations that are not additive.

        A migration describes the spec's target state, so its old column may
        legitimately no longer appear in ``self.entities``. The old form is
        nevertheless kept in the operation so the runtime can check the
        precondition when the operator runs it, rather than guessing a rename
        from two similar names."""
        self.migrations = []
        names = set()
        seen_operations = set()
        known_types = {
            "String", "Text", "Integer", "Float", "Boolean", "Date",
            "DateTime", "Email", "UUID", "Money", "Image", "Upload",
        }
        for migration in self.migrations_raw:
            name = migration["name"]
            if name in names:
                raise ASTValidationError(
                    f"Structure: migration '{name}' is declared more than once.")
            names.add(name)
            operations = []
            if not migration.get("operations"):
                raise ASTValidationError(
                    f"Structure: migration '{name}' contains no operations.")
            for index, operation in enumerate(migration["operations"], start=1):
                reference = operation["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure: operation {index} of migration '{name}' must "
                        f"reference 'Entity.field'; received '{reference}'.")
                entity, field = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure: migration '{name}' targets entity '{entity}', "
                        "which does not exist in the current spec.")
                kind = operation["kind"]
                key = (kind, entity, field, operation.get("new_name"),
                       operation.get("from_type"), operation.get("to_type"))
                if key in seen_operations:
                    raise ASTValidationError(
                        f"Structure: operation {index} of migration '{name}' "
                        "is declared more than once.")
                seen_operations.add(key)
                operations.append(self._operation_de_migration(
                    name, reference, entity, field, operation, known_types))
            self.migrations.append({"name": name, "operations": operations})
