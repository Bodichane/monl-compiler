"""The `Update` route.

The amount is RECOMPUTED here from the STORED foreign key, never the one
in the request body — the point 78 lesson: computing from `data.<fk>` let
someone be billed €89 for a €189 item."""

from . import sql


class ModificationRoutesMixin:
    """La route `Update`."""

    def _generate_update_route_lines(self, plan, context, act_type):
        """Renders the ``Update`` route family."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
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
        update_deps = dependency_injection
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

        update_deps_suffix = f", {update_deps}" if update_deps else ""
        api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def update_{base_target.lower()}(id: int, data: {base_target}Schema{update_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.extend(ownership_check_lines)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
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
        for verrou in self._payment_locked_parents(base_target):
            lien = f"_verrou_{verrou['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{verrou['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {lien} = cursor.fetchone()",
                f"    if {lien} and {lien}[0] is not None:",
            ]
            api_lines += self._payment_lock_lines(
                verrou["table"], f"{lien}[0]", verrou["entity"],
                indent="        ", var="_parent_regle")
        fields = list(self.entities[base_target].keys())
        # FIX (point 78): a 'generated' field is NOT in the Pydantic schema,
        # yet this route read `data.<field>` for ALL attributes -- hence 500
        # (AttributeError) on every entity combining 'generated' and 'Update'.
        # Latent until now: no example combined them. A field filled by the
        # server has no business being rewritten from the request body;
        # excluding it also preserves its value (the pseudonym must not
        # change).
        generated_upd = self.generated_fields_by_entity.get(base_target, [])
        # ADDED (brick 10, point 77): a 'derivedFrom' field is RECOMPUTED here.
        # Leaving it as is would merely move the flaw: create at quantity 1
        # then update to quantity 5 without recomputing would give five items
        # for the price of one.
        derives_upd = self.derived_by_entity.get(base_target, ())
        noms_derives = {r.field for r in derives_upd}
        for regle in derives_upd:
            fk_col = regle.source_fk
            champ = regle.field
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
                f"    _lien_{champ} = cursor.fetchone()",
                f"    if not _lien_{champ}:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Record not found')",
                f"    cursor.execute('SELECT \"{regle.source_field}\" FROM "
                f'"{regle.source_entity.lower()}" WHERE id = ?\', '
                f"(_lien_{champ}[0],))",
                f"    _src_{champ} = cursor.fetchone()",
                f"    if not _src_{champ}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{regle.source_entity} not found: unable to recalculate "
                f"{champ}.'))",
                f"    if data.{regle.factor} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'The quantity must be strictly positive.'))",
                f"    _calcul_{champ} = round(float(_src_{champ}[0] or 0) "
                f"* int(data.{regle.factor}), 2)",
            ]
        # ADDED (brick 12, point 82): a 'sumOf' field is not in `data` and has
        # no place in the SET — rewriting it from the request would hand back
        # to the client the total just taken away from them, and reading
        # `data.<field>` would give 500 (the point 78 defect, on another
        # brick).
        sommes_upd = set(self._aggregated_field_names(base_target))
        # ADDED (brick 16, point 89): the creation moment is written at
        # creation, period. Excluding it from the SET is what makes it
        # trustworthy; leaving it there would also have given 500
        # (`data.<field>` absent from the schema), the point 78 defect.
        horodates_upd = set(self.timestamp_fields_by_entity.get(base_target, []))
        # BRICK 22 (point 102): an order number that changes is no longer a
        # reference — the client wrote it down, and so did the seller.
        horodates_upd |= {n["field"] for n
                          in self.numbered_fields_by_entity.get(base_target, [])}
        # Same exclusion on the generic Update: these fields do not exist in
        # its Pydantic schema and are written only through the route dedicated
        # to the supervisor.
        postpaiement_upd = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        ecrits = [f for f in fields
                  if f not in generated_upd and f not in sommes_upd
                  and (base_target, f) not in self.event_counters
                  and f not in horodates_upd
                  and f not in postpaiement_upd
                  and self.entities[base_target][f] != "Upload"]
        # POINT 85: the writes are gathered BEFORE being emitted, so they can
        # be wrapped in a try when the entity carries a 'unique'. SQLite raises
        # at `execute`, not at `commit` — a guard around the commit alone gave
        # 500 (checked against a real server, not inferred).
        lignes_ecriture = []
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
        for regle in self.release_rules_by_entity.get(base_target, []):
            enfant = regle["releases"]
            fk_enfant = self._fk_enfant_libere(base_target, enfant)
            if not fk_enfant:
                continue
            # The field may have been removed from THIS route by
            # `writableAfterPayment`: it is then not in its Pydantic schema,
            # and reading `data.<field>` here answered 500 to every call
            # (measured on `exemples/02_boutique.ml`, for the only role allowed
            # to call the route). The transition lives in the route that
            # ACTUALLY writes the field — see `_generate_postpayment_routes`.
            if regle["field"] in postpaiement_upd:
                continue
            # The state is read BEFORE the transaction: the refusal that
            # follows must be able to close the connection, which the writes'
            # `except IntegrityError` would not do for it.
            api_lines += [
                f"    cursor.execute('SELECT \"{regle['field']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "    _etat_avant = cursor.fetchone()",
                # THE hole the first version left open: cancelling gave the
                # stock back, then REACTIVATING the order left it alive without
                # consuming anything — free stock, the same family as the point
                # 77 exploits. Taking it back on return would assume it is
                # still available, which nothing guarantees: the released state
                # is therefore TERMINAL, and the message says what to do
                # instead.
                f"    if (_etat_avant and _etat_avant[0] == {regle['value']!r}",
                f"            and data.{regle['field']} != {regle['value']!r}):",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            \"This record is {regle['value']}: what it had "
                f"consumed has been returned, \"",
                "            'and nothing guarantees it is still available. "
                "Create a new one.'))",
                f"    _bascule = (_etat_avant and _etat_avant[0] != {regle['value']!r}",
                f"                and data.{regle['field']} == {regle['value']!r})",
            ]
            lignes_ecriture.append("if _bascule:")
            # No floor: we give back a state that existed and was valid (same
            # reason as point 92). Single source shared with the post-payment
            # route.
            lignes_ecriture += self._lignes_restitution(enfant, fk_enfant)
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
            plancher = rule.minimum
            if plancher is None or rule.direction != "decrements":
                continue  # without a declared floor, nothing to guarantee (point 86)
            fk_cible = rule.target_fk
            champ = rule.amount_field
            cible = rule.target_entity.lower()
            vise = rule.target_field
            lignes_ecriture += [
                f"cursor.execute('SELECT \"{champ}\", \"{fk_cible}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "_avant = cursor.fetchone()",
                "if _avant and _avant[1] is not None:",
                f"    _delta = int(data.{champ}) - int(_avant[0] or 0)",
                "    if _delta != 0:",
                f"        cursor.execute('UPDATE \"{cible}\" SET \"{vise}\" = "
                f'"{vise}" - ? WHERE id = ? AND "{vise}" - ? >= ?\', '
                "(_delta, _avant[1], _delta, "
                f"{plancher}))",
                "        if cursor.rowcount == 0:",
                "            conn.rollback(); conn.close()",
                "            raise HTTPException(status_code=409, detail=(",
                f"                '{rule.target_entity}.{vise} insufficient: "
                f"the requested quantity exceeds what remains available.'))",
            ]
        if ecrits:
            update_stmt = ", ".join([f'"{f}" = ?' for f in ecrits])
            lignes_ecriture.append(f"query = 'UPDATE \"{base_target.lower()}\" SET {update_stmt} WHERE id = ?'")
            values_list = ", ".join([
                f"_calcul_{f}" if f in noms_derives else f"data.{f}"
                for f in ecrits
            ])
            lignes_ecriture.append(f"cursor.execute(query, ({values_list}, id))")
        else:
            # Entity whose attributes are ALL filled by the server: "SET  WHERE
            # id = ?" would be invalid SQL. Nothing to write is a success, not
            # an error.
            lignes_ecriture.append("pass  # no field the client can modify")
        # ADDED (brick 12, point 82): the parent's total follows the updated
        # line. The parent is reread FROM THE DATABASE, never taken from the
        # request body — the Update route does not write foreign keys, so
        # `data.<fk>` can designate a parent this line does not belong to: we
        # would recompute another order's total, and not the real one's.
        # Exactly the point 78 lesson, on another brick.
        for recalcul in self._aggregation_recomputes(base_target):
            var = f"_parent_{recalcul['fk_column']}"
            lignes_ecriture += [
                f"cursor.execute('SELECT \"{recalcul['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"{var} = cursor.fetchone()",
                f"if {var}:",
                f"    cursor.execute({recalcul['sql']!r}, ({var}[0], {var}[0]))",
            ]
        # POINT 85: the Update route wrote NO foreign key, so it could not
        # raise an IntegrityError — hence the absence of a guard until now.
        # 'unique' changes that: a PUT duplicating a unique value gave 500 and
        # left the connection open. The guard is placed only when the entity
        # carries a 'unique', so the output stays identical everywhere else.
        uniques_upd = self._unique_fields(base_target)
        if uniques_upd:
            api_lines.append("    try:")
            api_lines += [f"        {ligne}" for ligne in lignes_ecriture]
            api_lines.append("        conn.commit()")
            api_lines.append("    except _DATABASE_INTEGRITY_ERRORS:")
            api_lines.append("        conn.rollback(); conn.close()")
            api_lines.append("        raise HTTPException(status_code=409, detail=(")
            api_lines.append(
                f"            'Value already in use: {', '.join(uniques_upd)} "
                f"must be unique.'))")
            api_lines.append("    conn.close()")
        else:
            api_lines += [f"    {ligne}" for ligne in lignes_ecriture]
            api_lines.append("    conn.commit(); conn.close()")
        api_lines.append("    return {'status': 'success', 'id': id}")
        api_lines.append("")

        return api_lines
