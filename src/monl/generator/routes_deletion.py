"""The `Delete` route, and workflow actions.

The parent is read BEFORE the `DELETE`: afterwards the foreign key is gone
and nothing says what to give back or to whom (points 82 and 92)."""

from . import sql


class SuppressionRoutesMixin:
    """The `Delete` route, and workflow actions."""

    # The three methods below are extracted from `_generate_delete_route_lines`
    # (complexity ceiling); emitted text byte-identical.
    def _controle_de_suppression(self, base_target, access, is_public, dependency_injection):
        """(dependencies, ownership check lines) of a Delete route."""
        owner_entity = access.owner_entity
        apply_ownership = owner_entity and not is_public
        # ADDED (roadmap, "two-party access" brick) — see the equivalent
        # comment on the Update route.
        delete_parties = access.party_fields
        apply_delete_parties = bool(delete_parties) and not is_public
        delete_supers = access.supervisors
        apply_delete_super = bool(delete_supers) and apply_delete_parties
        delete_deps = dependency_injection
        ownership_check_lines = []
        if apply_delete_parties:
            delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
            cols_literal = ", ".join(f'\"{c}\"' for c in delete_parties)
            ownership_check_lines = [
                "    _p_conn = _connect(); _p_cur = _p_conn.cursor()",
                f"    _p_cur.execute('SELECT {cols_literal} FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                "    _p_row = _p_cur.fetchone(); _p_conn.close()",
                "    if not _p_row: raise HTTPException(status_code=404, detail='Record not found')",
            ]
            if apply_delete_super:
                _superset = ", ".join(f'"{s}"' for s in delete_supers)
                ownership_check_lines.append(f"    if current_actor not in {{{_superset}}}:")
                ownership_check_lines.append("        if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Access control: only the resource's parties can perform this action\")")
            else:
                ownership_check_lines.append("    if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Access control: only the resource's parties can perform this action\")")
        elif apply_ownership:
            check_actor, owner_select = self._owner_lookup_sql(base_target, owner_entity)
            delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
            # See the equivalent comment in the "Update" block above: the
            # ownership check applies only to the actor explicitly designated
            # as owner by 'ownedBy'.
            ownership_check_lines = [
                f"    if current_actor == \"{check_actor}\":",
                "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                f"        _owner_cur.execute({owner_select.text!r}, {sql.params_tuple(owner_select)})",
                "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                "        if not _owner_row: raise HTTPException(status_code=404, detail='Record not found')",
                "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                "detail=\"Access control: only the resource's owner can perform this action\")",
            ]
        return delete_deps, ownership_check_lines

    def _garde_dernier_profil(self, base_target):
        """Refuses to delete the last profile that other records depend on."""
        api_lines = []
        dependantes = self._profile_dependents(base_target)
        col_compte = self._profile_account_column(base_target)
        if dependantes and col_compte:
            api_lines += [
                f"    cursor.execute('SELECT COUNT(*) FROM "
                f'"{base_target.lower()}" WHERE "{col_compte}" = ?\', '
                "(current_user_id,))",
                "    _restantes = cursor.fetchone()[0] - 1",
                "    if _restantes <= 0:",
            ]
            for nom, table, colonne in dependantes:
                api_lines += [
                    f"        cursor.execute('SELECT COUNT(*) FROM "
                    f'"{table}" WHERE "{colonne}" = ?\', (current_user_id,))',
                    "        _dep = cursor.fetchone()[0]",
                    "        if _dep:",
                    "            conn.close()",
                    "            raise HTTPException(status_code=409, detail=(",
                    # The entity name as the SPEC writes it: the vocabulary the
                    # project's author recognizes, and the frontend contract's.
                    f"                f'Deletion impossible: {{_dep}} "
                    f"{nom} record(s) depend on this profile. '",
                    "                'Without it, they would no longer be attached to "
                    "anyone.'))",
                ]
        return api_lines

    def _lectures_de_restitution(self, base_target):
        """Reads, BEFORE the DELETE, what each counter rule must give back."""
        api_lines = []
        restitutions = []
        for indice, rule in enumerate(
                self.reputation_rules_by_trigger.get(base_target, [])):
            fk_cible = rule.target_fk
            var = f"_rendu_{indice}"
            champ = rule.amount_field
            # The quantity and the foreign key are read BEFORE the DELETE:
            # afterwards the row no longer exists and nothing says what to give
            # back or to whom. Same reason as point 82, two lines above.
            colonnes = f'"{champ}", "{fk_cible}"' if champ else f'"{fk_cible}"'
            api_lines += [
                f"    cursor.execute('SELECT {colonnes} FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {var} = cursor.fetchone()",
            ]
            restitutions.append({
                "var": var,
                # Counting down subtracts: giving back adds.
                "op": "+" if rule.direction == "decrements" else "-",
                "table": rule.target_entity.lower(),
                "champ": rule.target_field,
                "montant": (f"int({var}[0] or 0)" if champ
                            else str(rule.amount)),
                "fk_index": 1 if champ else 0,
            })
        return api_lines, restitutions

    def _generate_delete_route_lines(self, plan, context, act_type):
        """Renders the ``Delete`` route family."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        delete_deps, ownership_check_lines = self._controle_de_suppression(
            base_target, access, is_public, dependency_injection)

        delete_deps_suffix = f", {delete_deps}" if delete_deps else ""
        api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def delete_{base_target.lower()}(id: int{delete_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.extend(ownership_check_lines)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        # POINT 96: the counterpart of `requiresOwn` on DELETION. The rule has
        # guarded creation since point 90; nothing then prevented deleting
        # one's profile and leaving the order without a recipient — checked on
        # `projets/SneakerLab`: 1 order, 0 profiles. The check applies to the
        # LAST profile only: `requiresOwn` requires "at least one", so deleting
        # the second to last stays legitimate.
        api_lines += self._garde_dernier_profil(base_target)
        # BRICK 18 (point 91): deleting erases the trace of a charge. The 409
        # the foreign key returned protected nothing — removing the lines first
        # was enough, and the paid order vanished from the database (checked).
        if self._payment_lock_field(base_target):
            api_lines += self._payment_lock_lines(
                base_target.lower(), "id", base_target)
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
        # FIX (beta 3): foreign keys are now really enforced (PRAGMA
        # foreign_keys), so deleting a record that is still referenced raises
        # an IntegrityError. It is translated into an explicit 409 rather than
        # a 500: it is a client error (deletion order), not a server failure.
        #
        # ADDED (brick 12, point 82): the parent is read BEFORE the deletion —
        # afterwards the row no longer exists and its foreign key with it, so
        # nothing says which total to recompute. Removing an item from a cart
        # without bringing the total down is exactly where the sum would lie,
        # and on a 'payable' entity we would charge for a returned item.
        recalculs_del = self._aggregation_recomputes(base_target)
        for recalcul in recalculs_del:
            var = f"_parent_{recalcul['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{recalcul['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {var} = cursor.fetchone()",
            ]
        # BRICK 15 (point 92): deletion UNDOES the count. The third branch, the
        # one people forget — point 82 had named it for aggregation and handled
        # it; the count, however, was armed only on creation (point 86) and
        # then on update (point 91), never on deletion. Measured on SneakerLab:
        # ordering three pairs then emptying the cart left the stock at 9 out
        # of 12. The parent's total did come back down to zero — a database
        # contradicting itself, and a catalog running out without a single pair
        # sold.
        #
        # The restoration carries NO floor safeguard, on purpose: it restores a
        # state that existed and was valid. A returned `decrements` only goes
        # up, a taken back `increments` does not go below the value before
        # creation. Refusing a deletion because of a floor would forbid
        # cancelling an order — exactly what is being fixed here.
        lignes_restitution, restitutions = self._lectures_de_restitution(base_target)
        api_lines += lignes_restitution
        upload_refs = []
        for upload in self.upload_fields_by_entity.get(base_target, []):
            ref_var = f"_upload_ref_{upload['field']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{upload['field']}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                f"    {ref_var} = cursor.fetchone()",
            ]
            upload_refs.append((upload, ref_var))
        api_lines.append("    try:")
        api_lines.append(f"        cursor.execute('DELETE FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
        for recalcul in recalculs_del:
            var = f"_parent_{recalcul['fk_column']}"
            api_lines += [
                f"        if {var}:",
                f"            cursor.execute({recalcul['sql']!r}, ({var}[0], {var}[0]))",
            ]
        for rendu in restitutions:
            var = rendu["var"]
            api_lines += [
                f"        if {var} and {var}[{rendu['fk_index']}] is not None:",
                f"            cursor.execute('UPDATE \"{rendu['table']}\" SET "
                f'"{rendu["champ"]}" = "{rendu["champ"]}" {rendu["op"]} ? '
                f"WHERE id = ?', ({rendu['montant']}, {var}[{rendu['fk_index']}]))",
            ]
        api_lines.append("        conn.commit()")
        api_lines.append("    except _DATABASE_INTEGRITY_ERRORS:")
        api_lines.append("        conn.rollback(); conn.close()")
        api_lines.append("        raise HTTPException(status_code=409, detail=(")
        api_lines.append("            'Deletion impossible: this record is still referenced '")
        api_lines.append("            'by linked data. Delete them first.'")
        api_lines.append("        ))")
        api_lines.append("    conn.close()")
        for upload, ref_var in upload_refs:
            api_lines += [
                f"    if {ref_var} and {ref_var}[0]:",
                f"        _remove_upload({base_target.lower()!r}, id, {upload['field']!r}, {ref_var}[0])",
            ]
        api_lines.append("    return {'status': 'success', 'id': id}")
        api_lines.append("")

        return api_lines

    def _generate_execute_route_lines(self, plan, context, act_type):
        """Renders the ``Execute`` route family."""
        api_lines = []
        target = context["target"]
        tag = context["tag"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        api_lines.append(f"@app.post('/workflow/{tag.lower()}/{target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
        api_lines.append(security_check)
        # FIX (point 85): `.dict()` is DEPRECATED in Pydantic v2 and will be
        # removed in v3 — checked by triggering it. Every generated backend
        # with a 'custom' block would have stopped working on its first install
        # on Pydantic 3, without anything in the repository saying so (no
        # example, no test exercised this path: the coverage gap is what found
        # it).
        api_lines.append(f"    result = sandbox_ai.{target}(payload.model_dump())")
        api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
        api_lines.append("")

        return api_lines
