"""The columns and indexes the schema must carry.

The migration stays ADDITIVE (point 32): it catches up a column, never its
content. A unique index rather than a column constraint, because SQLite
cannot add `UNIQUE` to an existing column."""




class SqlColumnsMixin:
    """The columns and indexes the schema must carry."""

    def _unique_fields(self, entity):
        """The fields of this entity declared 'unique' (point 85)."""
        return sorted(field for field, constraints
                      in self.field_constraints.get(entity, {}).items()
                      if constraints.get("unique"))

    def _once_per_rules_for(self, entity):
        return [rule for rule in self.once_per_rules
                if rule["trigger_entity"] == entity]

    def _compute_once_per_indexes(self):
        """Multi-column unique indexes coming from `oncePer` rules."""
        indexes = []
        placements = self._compute_fk_placements()
        for rule in self.once_per_rules:
            entity = rule["trigger_entity"]
            columns = []
            for parent in rule["parents"]:
                placement = next(
                    (p for p in placements.get(entity, [])
                     if p["owner_entity"] == parent), None)
                if not placement:
                    raise ValueError(
                        f"Generation: no foreign key of '{entity}' points to "
                        f"'{parent}', although 'oncePer' requires it.")
                # POINT 116: a composite index on a column the Create route
                # NEVER writes refuses nothing — SQLite treats two NULLs as
                # distinct, so the rule passes compilation, creates its index,
                # and lets someone vote ten times. It happened on
                # `exemples/03_reseau_social.ml`: the column targeted by an
                # `increments` is left out of the INSERT when it is the FIRST
                # incoming relation, and `oncePer Member, Post` no longer bit.
                # Refuse rather than produce a rule with no effect — exactly
                # what point 85 closed for `unique`.
                written = set(self._client_fk_columns(entity))
                written |= set(self._identity_fk_columns().get(entity, set()))
                # The counter branch of the Create route writes these columns
                # outside the client FKs. The refusal therefore stays active
                # for a column that is truly never written, without rejecting a
                # real server write.
                written |= set(self._counter_fk_columns(entity))
                if placement["fk_column"] not in written:
                    raise ValueError(
                        f"Generation: 'oncePer' on '{entity}' points to '{parent}', "
                        f"but the column '{placement['fk_column']}' is never "
                        f"written at creation — uniqueness would refuse nothing. "
                        f"Declare the relation to the actor BEFORE the one targeted "
                        f"by an 'increments'/'decrements', so the parent column "
                        f"stays supplied by the client.")
                columns.append(placement["fk_column"])
            index_name = "idx_once_per_{}_{}".format(
                entity.lower(), "_".join(c.lower() for c in columns))
            indexes.append((entity.lower(), columns, index_name))
        return indexes

    def _compute_unique_indexes(self):
        """POINT 85: [(table, column, index_name)] for each 'rule Entity.field
        unique'.

        Single source of the index name, so that creation at startup and any later
        check designate the same object. The name carries the table and the
        column: two entities may have a field with the same name.

        POINT 102: a 'numbered' field joins without having to declare 'unique'. A
        duplicate order number is not a number — requiring it in the spec would
        make the guarantee depend on a line one can forget to write. Since the
        index name derives from the table and the column, declaring both produces
        a single index."""
        vises = {
            (entity, field)
            for entity, fields in self.field_constraints.items()
            for field, constraints in fields.items()
            if constraints.get("unique")
        }
        vises |= {(entity, rule["field"])
                  for entity, rules in self.numbered_fields_by_entity.items()
                  for rule in rules}
        return [
            (entity.lower(), field, f"idx_unique_{entity.lower()}_{field.lower()}")
            for entity, field in sorted(vises)
        ]

    def _compute_lookup_indexes(self):
        """Lookup indexes for foreign keys and filters.

        Foreign keys come from `_compute_fk_placements`, the same source
        `sql_schema.py` uses to emit the columns and the `FOREIGN KEY`
        constraints. Filterable fields come from the IR prepared by `core.py`; no
        second list of relations or filters must be able to diverge from what the
        routes accept. The columns of `accessibleBy` and `publicWhen` rules are
        added from their own IR structures: they are route filters too, even
        though they are neither foreign keys nor `filter` fields.

        A column already covered by `_compute_unique_indexes` needs no second
        index. The tuples are deduplicated then sorted so the generated runtime
        stays deterministic, even if a column is both a foreign key and
        filterable."""
        unique_columns = {
            (table, column)
            for table, column, _index in self._compute_unique_indexes()
        }
        lookup_columns = set()
        for entity, placements in self._compute_fk_placements().items():
            table = entity.lower()
            for placement in placements:
                column = placement["fk_column"]
                if (table, column) not in unique_columns:
                    lookup_columns.add((table, column))
        for entity, fields in self.filterable_fields_by_entity.items():
            table = entity.lower()
            for column in fields:
                if (table, column) not in unique_columns:
                    lookup_columns.add((table, column))
        for reference, columns in self.access_parties.items():
            table = reference.split(".", 1)[0].lower()
            for column in columns:
                if (table, column) not in unique_columns:
                    lookup_columns.add((table, column))
        for (entity, _action), condition in self.public_conditions.items():
            table = entity.lower()
            column = condition["field"]
            if (table, column) not in unique_columns:
                lookup_columns.add((table, column))
        return [
            (table, column, f"idx_lookup_{table}_{column.lower()}")
            for table, column in sorted(lookup_columns)
        ]

    def _compute_numbered_columns(self):
        """POINT 102: [(table, column)] for each 'rule Entity.field numbered'.

        Same use as `_compute_timestamp_columns` and the same honesty: records
        older than the rule have NO number, and none is invented for them —
        numbering them at startup would claim an arrival order the server never
        observed."""
        return [
            (entity.lower(), rule["field"])
            for entity, rules in sorted(self.numbered_fields_by_entity.items())
            for rule in rules
        ]

    def _compute_timestamp_columns(self):
        """POINT 89: [(table, column)] for each 'rule Entity.field timestamp'.

        Used only for the startup report: counting the records older than the
        rule, which will never have a date."""
        return [
            (entity.lower(), field)
            for entity, fields in sorted(self.timestamp_fields_by_entity.items())
            for field in sorted(fields)
        ]

    def _compute_postpayment_enumerated_columns(self):
        """POINT 191: post-payment statuses whose old NULLs are named.

        The source of the values stays ``enumerated_fields``, identical to the one
        for the Pydantic ``Literal`` and the initial value at creation."""
        return [
            (entity.lower(), field)
            for entity, config in sorted(
                self.postpayment_writable_by_entity.items())
            for field in sorted(config.get("fields", []))
            if self.enumerated_fields.get(entity, {}).get(field)
        ]

    def _compute_expected_columns(self):
        """ADDED (long-term roadmap, migrations without data loss): returns
        {table_name: [(column, sql_type), ...]} for every business table, in the
        exact order of _generate_sql (declared attributes then incoming foreign
        keys). The id is not included: it is always created by the initial CREATE
        TABLE and never added afterwards. Used by init_db() to detect, at startup,
        the columns present in the spec but missing from an already created
        database, and to add them with ALTER TABLE ADD COLUMN — a purely additive
        operation that neither touches nor deletes any existing data."""
        fk_placements = self._compute_fk_placements()
        expected = {}
        for ent_name, attrs in self.entities.items():
            table = ent_name.lower()
            columns = []
            for attr_name, attr_type in attrs.items():
                columns.append((attr_name, self._map_type_to_sql(attr_type)))
            if ent_name in self.payable_by_entity:
                # The DEFAULT matters here as much as in the CREATE TABLE: on
                # an existing database, SQLite applies it to the rows already
                # present. Without it, adding `payable` to a spec in production
                # would leave the old records at NULL and the new ones at
                # 'en_attente' — two ways of saying the same thing, which every
                # read would then have to reconcile.
                columns.append(("payment_status", "VARCHAR(32) DEFAULT 'en_attente'"))
                columns.append(("payment_ref", "VARCHAR(255)"))
            for placement in fk_placements.get(ent_name, []):
                columns.append((placement["fk_column"], "INTEGER"))
            expected[table] = columns
        return expected

    def _compute_migrations(self):
        """Prepares the validated migrations for the generated app.

        The DSL types are kept for the messages and their SQL types are added here
        so the runtime has no mapping table independent of the generator."""
        prepared = []
        for migration in self.migrations:
            operations = []
            for operation in migration["operations"]:
                item = dict(operation)
                if item["kind"] == "alter":
                    item["from_sql_type"] = self._map_type_to_sql(item["from_type"])
                    item["to_sql_type"] = self._map_type_to_sql(item["to_type"])
                operations.append(item)
            prepared.append({"name": migration["name"], "operations": operations})
        return prepared

    def _map_type_to_sql(self, type_str):
        mapping = {
            "String": "VARCHAR(255)", "Text": "TEXT", "Integer": "INTEGER",
            # Float is a binary number, not a currency: DOUBLE PRECISION is the
            # type shared by SQLite/PostgreSQL. Money stays fixed-scale NUMERIC
            # below, because its values go to Stripe and a binary float is not
            # a money type.
            "Float": "DOUBLE PRECISION", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID",
            "Money": "NUMERIC(10, 2)",
            # Brick 13 (point 83): 'Image' stores a PATH relative to the
            # project, not the binary. Same column as a String, then — the
            # difference is elsewhere: the validator checks that the file
            # exists, and the contract declares it as media without having to
            # guess from the name.
            "Image": "VARCHAR(255)",
            # Brick B1: an opaque reference to runtime storage, never the
            # bytes. Unlike Image, no existence is checked at compile time.
            "Upload": "VARCHAR(255)",
        }
        return mapping.get(type_str, "TEXT")
