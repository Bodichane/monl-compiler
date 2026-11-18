"""Les migrations déclarées, et ce qu'elles ont le droit de faire.

La règle du point 32, tenue depuis : une migration est ADDITIVE. Elle
rattrape une colonne, jamais son contenu (points 89 et 99)."""

from .socle import ASTValidationError


class MigrationsMixin:
    """Les migrations déclarées, et ce qu'elles ont le droit de faire."""

    def _operation_de_migration(self, name, reference, entity, field, operation, known_types):
        """Une opération `rename`, `alter` ou `drop`, validée et normalisée.
        Extraite de `_valider_migrations` (plafond de complexité) ; refus,
        messages et forme de l'opération inchangés."""
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
        """Valide les opérations de schéma qui ne sont pas additives.

        Une migration décrit l'état cible de la spec, donc son ancienne
        colonne peut légitimement ne plus figurer dans ``self.entities``.
        L'ancienne forme est néanmoins conservée dans l'opération afin que le
        runtime puisse vérifier la précondition au moment où l'opérateur la
        lance, plutôt que de deviner un renommage depuis deux noms proches.
        """
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
