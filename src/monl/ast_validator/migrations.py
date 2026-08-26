"""Les migrations déclarées, et ce qu'elles ont le droit de faire.

La règle du point 32, tenue depuis : une migration est ADDITIVE. Elle
rattrape une colonne, jamais son contenu (points 89 et 99)."""

from .socle import ASTValidationError


class MigrationsMixin:
    """Les migrations déclarées, et ce qu'elles ont le droit de faire."""

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
                    f"Structure : la migration '{name}' est déclarée plusieurs fois.")
            names.add(name)
            operations = []
            if not migration.get("operations"):
                raise ASTValidationError(
                    f"Structure : la migration '{name}' ne contient aucune opération.")
            for index, operation in enumerate(migration["operations"], start=1):
                reference = operation["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure : l'opération {index} de la migration '{name}' doit "
                        f"référencer 'Entite.champ', reçu '{reference}'.")
                entity, field = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : la migration '{name}' cible l'entité '{entity}', "
                        "qui n'existe pas dans la spec courante.")
                kind = operation["kind"]
                key = (kind, entity, field, operation.get("new_name"),
                       operation.get("from_type"), operation.get("to_type"))
                if key in seen_operations:
                    raise ASTValidationError(
                        f"Structure : l'opération {index} de la migration '{name}' "
                        "est déclarée en double.")
                seen_operations.add(key)
                if kind == "rename":
                    new_field = operation["new_name"]
                    if field == new_field:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' renomme "
                            f"'{reference}' vers lui-même.")
                    if field in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : la colonne source '{reference}' existe encore "
                            "dans la spec cible ; retirez-la avant de la renommer.")
                    if new_field not in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : le renommage '{reference}' vers "
                            f"'{entity}.{new_field}' ne trouve pas la colonne cible "
                            "dans la spec courante.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "old": field, "new": new_field, "reversible": True,
                    })
                elif kind == "alter":
                    old_type = operation["from_type"]
                    new_type = operation["to_type"]
                    if old_type not in known_types or new_type not in known_types:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' porte des types "
                            f"inconnus ({old_type} -> {new_type}).")
                    if old_type == new_type:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' ne change pas le type "
                            f"de '{reference}'.")
                    actual_type = self.entities[entity].get(field)
                    if actual_type != new_type:
                        raise ASTValidationError(
                            f"Structure : la cible de '{name}' déclare '{reference}' "
                            f"en {actual_type}, mais l'opération annonce {new_type}.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "field": field, "from_type": old_type, "to_type": new_type,
                        "reversible": True,
                    })
                else:
                    if field in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : la colonne retirée '{reference}' existe encore "
                            "dans la spec cible ; retirez-la avant le DROP explicite.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "old": field, "reversible": False,
                    })
            self.migrations.append({"name": name, "operations": operations})
