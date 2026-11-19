"""The `Create` route's transaction body.

What the server writes in place of the client (derived amounts, totals,
timestamps, numbers), the counters moved in the same transaction, and the
409 that names which integrity rule spoke. Split from routes_creation.py
(file ceiling); the route itself is rendered there."""


class CreationTransactionRoutesMixin:
    """The `Create` route's transaction body."""

    def _values_server_create(self, base_target, derives_here):
        """Expressions the server writes instead of `data.<field>`, and the
        numbering lines that belong inside the transaction."""
        computed = {r.field: f"_calcul_{r.field}" for r in derives_here}
        computed.update(dict.fromkeys(self.event_counters_by_entity.get(base_target, ()), "0"))
        # ADDED (brick 12, point 82): an order is born without lines, so its
        # total is born at 0 — never NULL, which no frontend knows how to
        # display, and never from `data` (the field is no longer there). The
        # sum will follow the lines, write by write.
        for name_sum in self._aggregated_field_names(base_target):
            computed[name_sum] = "0"
        # ADDED (brick 16, point 89): the creation moment. Written here, only
        # once, and removed from the Update route's SET — a creation date that
        # moves is not a creation date.
        for name_date in self.timestamp_fields_by_entity.get(base_target, []):
            computed[name_date] = "_horodatage()"
        # BRICK 25 (point 113): a field reserved to the `apres-paiement` route
        # is absent from the generic input schema. At creation it is therefore
        # born empty, exactly like a tracking value that does not exist yet.
        # Letting it fall through to the `data.<field>` fallback gave an
        # AttributeError and a 500 on EVERY creation of the entity — discovered
        # on CodexShop's real checkout, where fulfillmentStatus and
        # trackingNumber are legitimately unknown before payment.
        postpayment_here = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        for name_postpayment in postpayment_here:
            # POINT 191: the order of the `oneOf` is the life cycle (point 96).
            # A status reserved to post-payment is therefore born in its first
            # state; data without a closed list (tracking number, etc.) stays
            # legitimately unknown. `enumerated_fields` is the single source
            # already consumed by the Pydantic `Literal`s, and `repr()`
            # protects the generated literal as everywhere else.
            computed[name_postpayment] = self._value_initial_postpayment(
                base_target, name_postpayment)
        # BRICK 22 (point 102): the readable number. The counter is read AND
        # incremented in the database; these lines therefore go INTO the `try`
        # below, not here — outside the transaction, a refused insertion would
        # leave the counter advanced and the next number would skip. Never
        # `MAX(...) + 1` on the business table: it would give back a deleted
        # record's number, and would go wrong as soon as two creations cross.
        lines_numbering = []
        for rule in self.numbered_fields_by_entity.get(base_target, []):
            var = f"_numero_{rule['field']}"
            lines_numbering.append(
                f"        {var} = _attribuer_numero(cursor, "
                f"{base_target!r}, {rule['field']!r}, "
                f"{rule['format']!r}, {rule['periode']!r})")
            computed[rule["field"]] = var
        return computed, lines_numbering

    def _effects_counters_create(self, base_target):
        """increments/decrements, with the floored stock check."""
        api_lines = []
        reputation_rules_here = self.reputation_rules_by_trigger.get(base_target, [])
        for rule in reputation_rules_here:
            target_table = rule.target_entity.lower()
            target_field = rule.target_field
            sql_op = "-" if rule.direction == "decrements" else "+"
            # FIX (point 86): the targeted column is the one that points to the
            # DECREMENTED entity, not the "owner" relation. As long as a
            # triggering entity had only ONE incoming relation (Report ->
            # Member, Like -> Post), the two coincided and nobody saw the
            # difference. OrderLine has two — Order and Product — and the code
            # decremented the stock of the product carrying the ORDER's id. The
            # compiler had already known this defect ("a foreign key mechanism
            # that decremented the wrong record"): it came back through the
            # door of the second relation.
            fk_vers_target = rule.target_fk
            fk_value_expr = f"data.{fk_vers_target}"
            # BRICK 14 (point 86): the quantity is either a constant or a field
            # of the request body ('by quantity').
            quantity = (f"data.{rule.amount_field}" if rule.amount_field
                        else str(rule.amount))
            # THE heart of the brick. A count that can go below its floor is a
            # stock that LIES: the shop would show -3 pairs available, and
            # would have charged for the eight it did not have. The safeguard
            # is not a hard-coded "stock" exception — it comes from the point
            # 85 'min' DECLARATION on the targeted field. A reputation without
            # 'min' keeps going below zero, as is its right.
            bound = rule.minimum
            if bound is not None and rule.direction == "decrements":
                # ONE single statement: the condition and the write are
                # evaluated together, so two simultaneous orders cannot read
                # the same stock and count it down twice.
                api_lines.append(
                    f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = "
                    f'"{target_field}" - ? WHERE id = ? AND "{target_field}" - ? >= ?\', '
                    f"({quantity}, {fk_value_expr}, {quantity}, {bound}))")
                # Neither rollback nor close HERE: we are in the creation's
                # `try`, whose `except Exception` handles it before re-raising.
                # Doing them twice gave 500 — the second close operated on an
                # already closed connection (checked against a real server: the
                # stock refusal answered 500 instead of 409).
                api_lines += [
                    "        if cursor.rowcount == 0:",
                    "            raise HTTPException(status_code=409, detail=(",
                    f"                '{rule.target_entity}.{target_field} insufficient: "
                    f"the requested quantity exceeds what remains available.'))",
                ]
            else:
                api_lines.append(
                    f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = \"{target_field}\" {sql_op} ? "
                    f"WHERE id = ?', ({quantity}, {fk_value_expr}))"
                )
        return api_lines

    def _conflicts_integrity_create(self, base_target):
        """The integrity `except`: once_per, unique, foreign key, then a raise."""
        api_lines = []
        # POINT 85: until now this 409 could only come from a foreign key, and
        # its message said so. 'unique' adds a second cause — the same HTTP
        # code, but not the same explanation: answering "invalid reference" to
        # a duplicate would send the caller looking for a problem they do not
        # have.
        #
        # POINT 116: 'oncePer' added a THIRD cause to the same 409, and its
        # sentence took precedence over the one for 'unique' — a plain field
        # duplicate, on another target and another account, got the answer "you
        # have already done it for this target" (checked against a real
        # server). It is exactly the defect point 85 had closed, reopened by
        # the next brick. The two causes are therefore distinguished by the
        # COLUMNS SQLite names in its error, instead of assuming which of the
        # two rules spoke.
        uniques_here = self._unique_fields(base_target)
        once_here = [index for index in self._compute_once_per_indexes()
                    if index[0] == base_target.lower()]
        # A1: classification goes through SQLSTATE on the PostgreSQL side and
        # through the historical message on the SQLite side. THREE named
        # branches, then an UNCONDITIONAL `raise` — without it, an integrity
        # violation of a fourth kind (NOT NULL, CHECK, a unique index the spec
        # does not declare) leaves the `except` without raising anything: the
        # route carries on to the `return {'status': 'success'}` AFTER a
        # rollback, and announces as written what has just been undone.
        # Measured: a duplicate `numbered` reference gave 500
        # (UnboundLocalError on `row_id`) instead of a 409, and the case where
        # `row_id` is already bound would have given a false success. An
        # `except` that does not end in a `raise` is an `except` that lies.
        once_names = tuple(index[2] for index in once_here)
        once_signatures = tuple(
            f"{table}.{col}" for table, columns, _index in once_here for col in columns)
        api_lines.append("    except _DATABASE_INTEGRITY_ERRORS as _err:")
        api_lines.append("        conn.rollback(); conn.close()")
        api_lines.append(
            f"        _integrity_kind = _database_integrity_kind(_err, {once_names!r}, "
            f"{once_signatures!r})")
        if once_here:
            api_lines.append("        if _integrity_kind == 'once_per':")
            api_lines.append("            raise HTTPException(status_code=409, detail=(")
            api_lines.append(
                "                'This action has already been performed on this "
                "target by this account.'))")
        # The `unique` branch is emitted EVEN without a declared `unique`
        # field: brick 22 (`numbered`) sets a unique index without it being
        # declared, and point 85 sets one per `unique`. Emitting it only for
        # the second left the first without an answer.
        api_lines.append("        if _integrity_kind == 'unique':")
        api_lines.append("            raise HTTPException(status_code=409, detail=(")
        if uniques_here:
            api_lines.append(
                f"                'Value already in use: {', '.join(uniques_here)} "
                f"must be unique.'))")
        else:
            api_lines.append(
                "                'Value already in use: this record "
                "already exists.'))")
        api_lines.append("        if _integrity_kind == 'foreign_key':")
        api_lines.append("            raise HTTPException(status_code=409, detail=(")
        api_lines.append("                'Invalid reference: a linked identifier supplied matches no '")
        api_lines.append("                'existing record.'))")
        api_lines.append("        raise HTTPException(status_code=409, detail=(")
        api_lines.append("            'Database integrity conflict: the write was cancelled, '")
        api_lines.append("            'nothing was saved.'))")
        return api_lines
