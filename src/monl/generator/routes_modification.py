"""The `Update` route.

The amount is RECOMPUTED here from the STORED foreign key, never the one
in the request body — the point 78 lesson: computing from `data.<fk>` let
someone be billed €89 for a €189 item."""

from . import sql


class ModificationRoutesMixin:
    """The `Update` route."""

    def _generate_update_route_lines(self, plan, context, act_type):
        """Renders the ``Update`` route family."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        update_deps, ownership_check_lines = self._control_access_update(context)
        update_deps_suffix = f", {update_deps}" if update_deps else ""
        api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def update_{base_target.lower()}(id: int, data: {base_target}Schema{update_deps_suffix}):")
        api_lines.append(context["security_check"])
        api_lines.extend(ownership_check_lines)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        api_lines += self._locks_of_payment_update(base_target)
        derives_upd = self.derived_by_entity.get(base_target, ())
        api_lines += self._recomputes_derives_update(base_target, derives_upd)
        postpayment_upd, written = self._fields_written_update(base_target)
        # POINT 85: the writes are gathered BEFORE being emitted, so they can
        # be wrapped in a try when the entity carries a 'unique'. SQLite raises
        # at `execute`, not at `commit` — a guard around the commit alone gave
        # 500 (checked against a real server, not inferred).
        states, lines_write = self._releases_update(base_target, postpayment_upd)
        api_lines += states
        lines_write += self._counts_update(base_target)
        lines_write += self._write_update(
            base_target, written, {r.field for r in derives_upd})
        lines_write += self._recomputes_aggregated_update(base_target)
        api_lines += self._wrap_writes(base_target, lines_write)
        api_lines.append("    return {'status': 'success', 'id': id}")
        api_lines.append("")

        return api_lines

    def _control_access_update(self, context):
        """Dependencies and party/owner checks of the Update route."""
        base_target = context["base_target"]
        access = context["access"]
        is_public = context["is_public"]
        # ADDED (post-v6, roadmap): if an 'ownedBy' rule targets this action,
        # an extra check verifies that the current actor really owns the
        # record, on top of the usual role check.
        owner_entity = access.owner_entity
        # 'ownedBy' assumes a caller identity (current_actor) — incompatible
        # with a 'public' route, which has none. If both are declared on the
        # same action, 'public' wins: the route stays open, without an
        # ownership check (see docs/design_decisions.md).
        apply_ownership = owner_entity and not is_public
        # ADDED (roadmap, "two-party access" brick): same principle as
        # 'ownedBy' but the caller must be ONE of the listed party columns.
        # Unlike 'ownedBy', the check applies to every actor of the route,
        # except a SUPERVISOR role declared through sharedBy on the same
        # reference (brick 23, point 106) — that one pierces the check and
        # updates every record.
        update_parties = access.party_fields
        apply_update_parties = bool(update_parties) and not is_public
        update_supers = access.supervisors
        apply_update_super = bool(update_supers) and apply_update_parties
        update_deps = context["dependency_injection"]
        ownership_check_lines = []
        if apply_update_parties:
            update_deps += ", current_user_id: int = Depends(get_current_user_id)" if update_deps else "current_user_id: int = Depends(get_current_user_id)"
            cols_literal = ", ".join(f'\"{c}\"' for c in update_parties)
            ownership_check_lines = [
                "    _p_conn = _connect(); _p_cur = _p_conn.cursor()",
                f"    _p_cur.execute('SELECT {cols_literal} FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                "    _p_row = _p_cur.fetchone(); _p_conn.close()",
                "    if not _p_row: raise HTTPException(status_code=404, detail='Record not found')",
            ]
            if apply_update_super:
                _superset = ", ".join(f'"{s}"' for s in update_supers)
                ownership_check_lines.append(f"    if current_actor not in {{{_superset}}}:")
                ownership_check_lines.append("        if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Access control: only the resource's parties can perform this action\")")
            else:
                ownership_check_lines.append("    if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Access control: only the resource's parties can perform this action\")")
        elif apply_ownership:
            check_actor, owner_select = self._owner_lookup_sql(base_target, owner_entity)
            update_deps += ", current_user_id: int = Depends(get_current_user_id)" if update_deps else "current_user_id: int = Depends(get_current_user_id)"
            # FIX (roadmap, ownedBy + sharedBy combination): if this route is
            # shared by several actors (e.g. an 'Agent' who handles every
            # ticket, besides the owning 'Customer'), the ownership check must
            # apply only to the actor explicitly designated as owner by the
            # 'ownedBy' rule — not to the other actors that share the route
            # through their own role. Without this condition, a legitimately
            # privileged actor (Agent) would be wrongly blocked, since they
            # never "own" the resource in the hasMany/belongsTo sense.
            ownership_check_lines = [
                f"    if current_actor == \"{check_actor}\":",
                "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                f"        _owner_cur.execute({owner_select.text!r}, {sql.params_tuple(owner_select)})",
                "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                "        if not _owner_row: raise HTTPException(status_code=404, detail='Record not found')",
                "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                "detail=\"Access control: only the resource's owner can perform this action\")",
            ]
        return update_deps, ownership_check_lines

    def _locks_of_payment_update(self, base_target):
        """The payment lock of the record and of its settled parents."""
        api_lines = []
        # BRICK 18 (point 91): a charged record is FROZEN. The guard is placed
        # before any read and any calculation.
        if self._payment_lock_field(base_target):
            api_lines += self._payment_lock_lines(
                base_target.lower(), "id", base_target)
        # …and a line of a settled order is just as frozen: it is through it
        # that the total climbed to €594 after an €89 payment. The parent is
        # reread FROM THE DATABASE from the STORED foreign key, never
        # `data.<fk>` — this route does not write foreign keys, so the request
        # body can designate a different order than the one the line belongs to
        # (point 78 lesson).
        for lock in self._payment_locked_parents(base_target):
            link = f"_verrou_{lock['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{lock['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {link} = cursor.fetchone()",
                f"    if {link} and {link}[0] is not None:",
            ]
            api_lines += self._payment_lock_lines(
                lock["table"], f"{link}[0]", lock["entity"],
                indent="        ", var="_parent_regle")
        return api_lines

    def _recomputes_derives_update(self, base_target, derives_upd):
        """Recomputes each derivedFrom amount from the STORED linked row."""
        # ADDED (brick 10, point 77): a 'derivedFrom' field is RECOMPUTED here.
        # Leaving it as is would merely move the flaw: create at quantity 1
        # then update to quantity 5 without recomputing would give five items
        # for the price of one.
        api_lines = []
        for rule in derives_upd:
            fk_col = rule.source_fk
            field = rule.field
            api_lines += [
                # The linked row is the STORED one, reread from the database —
                # never the one the request body declares. Both directions were
                # tried against a real server: this route does not write
                # foreign key columns, so the FK in the database is the only
                # truth about "which item". Computing from `data.<fk>` let a
                # client lower the amount by declaring a cheap item it did not
                # point to (€189 billed as €89, checked).
                f"    cursor.execute('SELECT \"{fk_col}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    _lien_{field} = cursor.fetchone()",
                f"    if not _lien_{field}:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Record not found')",
                f"    cursor.execute('SELECT \"{rule.source_field}\" FROM "
                f'"{rule.source_entity.lower()}" WHERE id = ?\', '
                f"(_lien_{field}[0],))",
                f"    _src_{field} = cursor.fetchone()",
                f"    if not _src_{field}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{rule.source_entity} not found: unable to recalculate "
                f"{field}.'))",
                f"    if data.{rule.factor} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'The quantity must be strictly positive.'))",
                f"    _calcul_{field} = round(float(_src_{field}[0] or 0) "
                f"* int(data.{rule.factor}), 2)",
            ]
        return api_lines

    def _fields_written_update(self, base_target):
        """The fields the client may rewrite, and the post-payment ones."""
        fields = list(self.entities[base_target].keys())
        # FIX (point 78): a 'generated' field is NOT in the Pydantic schema,
        # yet this route read `data.<field>` for ALL attributes -- hence 500
        # (AttributeError) on every entity combining 'generated' and 'Update'.
        # Latent until now: no example combined them. A field filled by the
        # server has no business being rewritten from the request body;
        # excluding it also preserves its value (the pseudonym must not
        # change).
        generated_upd = self.generated_fields_by_entity.get(base_target, [])
        generated_upd = self.generated_fields_by_entity.get(base_target, [])
        # ADDED (brick 12, point 82): a 'sumOf' field is not in `data` and has
        # no place in the SET — rewriting it from the request would hand back
        # to the client the total just taken away from them, and reading
        # `data.<field>` would give 500 (the point 78 defect, on another
        # brick).
        sums_upd = set(self._aggregated_field_names(base_target))
        # ADDED (brick 16, point 89): the creation moment is written at
        # creation, period. Excluding it from the SET is what makes it
        # trustworthy; leaving it there would also have given 500
        # (`data.<field>` absent from the schema), the point 78 defect.
        timestamped_upd = set(self.timestamp_fields_by_entity.get(base_target, []))
        # BRICK 22 (point 102): an order number that changes is no longer a
        # reference — the client wrote it down, and so did the seller.
        timestamped_upd |= {n["field"] for n
                          in self.numbered_fields_by_entity.get(base_target, [])}
        # Same exclusion on the generic Update: these fields do not exist in
        # its Pydantic schema and are written only through the route dedicated
        # to the supervisor.
        postpayment_upd = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        written = [f for f in fields
                  if f not in generated_upd and f not in sums_upd
                  and (base_target, f) not in self.event_counters
                  and f not in timestamped_upd
                  and f not in postpayment_upd
                  and self.entities[base_target][f] != "Upload"]
        return postpayment_upd, written

    def _releases_update(self, base_target, postpayment_upd):
        """State reads before the write, and the release on transition."""
        api_lines, lines_write = [], []
        # BRICK 20 (point 98): reaching a value UNDOES an effect. Cancelling an
        # order set it to "cancelled" and kept its lines: the stock stayed
        # consumed. Restoration had existed since point 92, but only on
        # DELETION — which erases the history, and a merchant wants both.
        #
        # THE point of the brick: give back ONLY ONCE. The state is read BEFORE
        # the write, and release happens only on the TRANSITION — two
        # successive PUTs to "cancelled" would otherwise give the stock back
        # twice, and the shop would invent pairs for itself. Only a real server
        # shows this.
        for rule in self.release_rules_by_entity.get(base_target, []):
            child = rule["releases"]
            fk_child = self._fk_child_released(base_target, child)
            if not fk_child:
                continue
            # The field may have been removed from THIS route by
            # `writableAfterPayment`: it is then not in its Pydantic schema,
            # and reading `data.<field>` here answered 500 to every call
            # (measured on `exemples/02_boutique.ml`, for the only role allowed
            # to call the route). The transition lives in the route that
            # ACTUALLY writes the field — see `_generate_postpayment_routes`.
            if rule["field"] in postpayment_upd:
                continue
            # The state is read BEFORE the transaction: the refusal that
            # follows must be able to close the connection, which the writes'
            # `except IntegrityError` would not do for it.
            api_lines += [
                f"    cursor.execute('SELECT \"{rule['field']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "    _etat_avant = cursor.fetchone()",
                # THE hole the first version left open: cancelling gave the
                # stock back, then REACTIVATING the order left it alive without
                # consuming anything — free stock, the same family as the point
                # 77 exploits. Taking it back on return would assume it is
                # still available, which nothing guarantees: the released state
                # is therefore TERMINAL, and the message says what to do
                # instead.
                f"    if (_etat_avant and _etat_avant[0] == {rule['value']!r}",
                f"            and data.{rule['field']} != {rule['value']!r}):",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            \"This record is {rule['value']}: what it had "
                f"consumed has been returned, \"",
                "            'and nothing guarantees it is still available. "
                "Create a new one.'))",
                f"    _bascule = (_etat_avant and _etat_avant[0] != {rule['value']!r}",
                f"                and data.{rule['field']} == {rule['value']!r})",
            ]
            lines_write.append("if _bascule:")
            # No floor: we give back a state that existed and was valid (same
            # reason as point 92). Single source shared with the post-payment
            # route.
            lines_write += self._lines_restitution(child, fk_child)
        return api_lines, lines_write

    def _counts_update(self, base_target):
        """Applies the quantity DELTA to a floored stock."""
        lines_write = []
        # BRICK 19 (point 91): the count follows the UPDATED quantity.
        # `decrements` was armed only at creation: creating a line at 1 then
        # setting it to 4 billed four pairs and counted down only one (checked
        # — stock 16 -> 15 for €528 billed). It is the point 78 defect moved
        # from money to goods.
        #
        # We apply the DELTA, not the new quantity: the line has already
        # consumed its old value. A negative delta gives stock back, and the
        # `>= floor` condition stays true — no need to handle both directions
        # separately. Quantity and foreign key are reread FROM THE DATABASE:
        # this route does not write foreign keys (point 78 again).
        #
        # FIX (point 92): this loop read `reputation_rules_here`, a variable of
        # the `Create` branch — hence the rules of the LAST entity created, not
        # of the one being updated. Two consequences, both checked: a spec with
        # an `Update` and no `Create` at all made the compiler CRASH (variable
        # never assigned), and an `Update` preceded by the creation of ANOTHER
        # entity inherited its rules — editing a review counted down a
        # product's stock. The defect was born with the count on PUT (point
        # 91): a branch that reads another's variable works as long as route
        # order puts them side by side.
        for rule in self.reputation_rules_by_trigger.get(base_target, []):
            if not rule.amount_field:
                continue  # counting down a constant: nothing varies
            floor = rule.minimum
            if floor is None or rule.direction != "decrements":
                continue  # without a declared floor, nothing to guarantee (point 86)
            fk_target = rule.target_fk
            field = rule.amount_field
            target = rule.target_entity.lower()
            vise = rule.target_field
            lines_write += [
                f"cursor.execute('SELECT \"{field}\", \"{fk_target}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "_avant = cursor.fetchone()",
                "if _avant and _avant[1] is not None:",
                f"    _delta = int(data.{field}) - int(_avant[0] or 0)",
                "    if _delta != 0:",
                f"        cursor.execute('UPDATE \"{target}\" SET \"{vise}\" = "
                f'"{vise}" - ? WHERE id = ? AND "{vise}" - ? >= ?\', '
                "(_delta, _avant[1], _delta, "
                f"{floor}))",
                "        if cursor.rowcount == 0:",
                "            conn.rollback(); conn.close()",
                "            raise HTTPException(status_code=409, detail=(",
                f"                '{rule.target_entity}.{vise} insufficient: "
                f"the requested quantity exceeds what remains available.'))",
            ]
        return lines_write

    def _write_update(self, base_target, written, names_derives):
        """The UPDATE statement, or nothing when the server fills everything."""
        lines = []
        if written:
            update_stmt = ", ".join([f'"{f}" = ?' for f in written])
            lines.append(f"query = 'UPDATE \"{base_target.lower()}\" SET {update_stmt} WHERE id = ?'")
            values_list = ", ".join([
                f"_calcul_{f}" if f in names_derives else f"data.{f}"
                for f in written
            ])
            lines.append(f"cursor.execute(query, ({values_list}, id))")
        else:
            # Entity whose attributes are ALL filled by the server: "SET  WHERE
            # id = ?" would be invalid SQL. Nothing to write is a success, not
            # an error.
            lines.append("pass  # no field the client can modify")
        return lines

    def _recomputes_aggregated_update(self, base_target):
        """Recomputes the parent total of the updated line."""
        lines_write = []
        # ADDED (brick 12, point 82): the parent's total follows the updated
        # line. The parent is reread FROM THE DATABASE, never taken from the
        # request body — the Update route does not write foreign keys, so
        # `data.<fk>` can designate a parent this line does not belong to: we
        # would recompute another order's total, and not the real one's.
        # Exactly the point 78 lesson, on another brick.
        for recompute in self._aggregation_recomputes(base_target):
            var = f"_parent_{recompute['fk_column']}"
            lines_write += [
                f"cursor.execute('SELECT \"{recompute['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"{var} = cursor.fetchone()",
                f"if {var}:",
                f"    cursor.execute({recompute['sql']!r}, ({var}[0], {var}[0]))",
            ]
        return lines_write

    def _wrap_writes(self, base_target, lines_write):
        """Commits the writes, inside a try when the entity has a unique."""
        api_lines = []
        # POINT 85: the Update route wrote NO foreign key, so it could not
        # raise an IntegrityError — hence the absence of a guard until now.
        # 'unique' changes that: a PUT duplicating a unique value gave 500 and
        # left the connection open. The guard is placed only when the entity
        # carries a 'unique', so the output stays identical everywhere else.
        uniques_upd = self._unique_fields(base_target)
        if uniques_upd:
            api_lines.append("    try:")
            api_lines += [f"        {line}" for line in lines_write]
            api_lines.append("        conn.commit()")
            api_lines.append("    except _DATABASE_INTEGRITY_ERRORS:")
            api_lines.append("        conn.rollback(); conn.close()")
            api_lines.append("        raise HTTPException(status_code=409, detail=(")
            api_lines.append(
                f"            'Value already in use: {', '.join(uniques_upd)} "
                f"must be unique.'))")
            api_lines.append("    conn.close()")
        else:
            api_lines += [f"    {line}" for line in lines_write]
            api_lines.append("    conn.commit(); conn.close()")
        return api_lines
