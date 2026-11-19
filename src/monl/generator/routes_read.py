"""The read routes: list and detail.

A `SELECT *`: any column added by a brick comes out in the responses and
must therefore be declared in the contract (point 76)."""

from types import SimpleNamespace

from . import sql


class ReadRoutesMixin:
    """The read routes: list and detail."""

    def _generate_read_route_lines(self, plan, context, act_type):
        """Renders the ``Read`` route family."""
        # BRICK B3: keep the historical path byte for byte when the spec
        # declares no list capability. The new emission is isolated below so
        # that pagination and the golden artifacts stay unchanged for every
        # existing spec.
        if (self.filterable_fields_by_entity.get(context["base_target"])
                or self.sortable_fields_by_entity.get(context["base_target"])):
            return self._generate_read_route_lines_with_query(plan, context, act_type)
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        security_check = context["security_check"]
        e = self._state_read(context)
        masked = e.masked
        categorized_here = e.categorized_here
        read_dep_suffix = e.read_dep_suffix
        mask_literal = ", ".join(f"'{f}'" for f in e.masked)
        parties_where = parties_params = ""
        if e.apply_read_parties:
            parties_where = " OR ".join(f'\"{c}\" = ?' for c in e.read_parties)
            parties_params = ", ".join(["current_user_id"] * len(e.read_parties))
        list_params = f"limit: int = 50, offset: int = 0{read_dep_suffix}"
        api_lines.append(f"@app.get('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def list_{base_target.lower()}({list_params}):")
        api_lines.append(security_check)
        api_lines.append("    limit = max(1, min(limit, 200))")
        api_lines.append("    offset = max(0, offset)")
        api_lines += self._where_list_read(e, parties_where, parties_params)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        api_lines += self._queries_list_read(
            base_target, e, parties_where, parties_params)
        api_lines.append("    rows = cursor.fetchall()")
        api_lines.append("    _columns = [d[0] for d in cursor.description]  # real column order in the database (robust to migrations)")
        api_lines.append("    conn.close()")
        api_lines.append("    named_rows = [dict(zip(_columns, row)) for row in rows]")
        row_loop_lines = []
        if masked:
            row_loop_lines.append(f"        for _f in [{mask_literal}]: _r.pop(_f, None)")
        for cf in categorized_here:
            row_loop_lines.extend(self._emit_categorization_lines(cf, "_r", "        "))
        if row_loop_lines:
            api_lines.append("    for _r in named_rows:")
            api_lines.extend(row_loop_lines)
        api_lines.append("    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}")
        api_lines.append("")

        api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def read_{base_target.lower()}(id: int{read_dep_suffix}):")
        api_lines.append(security_check)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
        api_lines.append("    row = cursor.fetchone()")
        api_lines.append("    _columns = [d[0] for d in cursor.description]  # real column order in the database (robust to migrations)")
        api_lines.append("    conn.close()")
        api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Record not found')")
        api_lines.append("    named_row = dict(zip(_columns, row))")
        api_lines += self._guards_detail_read(base_target, e)
        if masked:
            api_lines.append(f"    for _f in [{mask_literal}]: named_row.pop(_f, None)")
        for cf in categorized_here:
            api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
        api_lines.append("    return {'status': 'success', 'data': named_row}")
        api_lines.append("")

        return api_lines


    def _state_read(self, context):
        """Who may list and read what: shared by both Read emitters.

        Masking, the publicWhen condition and its exemptions, the parties,
        the direct or transitive owner, and the dependencies they need.
        Computed once here so the filtered list (brick B3) cannot drift."""
        base_target = context["base_target"]
        access = context["access"]
        is_public = context["is_public"]
        read_dep_suffix = context["dep_suffix"]
        # ADDED (roadmap point 3, completed): a list route, in addition to the
        # existing read by ID — until then there was no way to enumerate an
        # entity's records without already knowing their identifiers one by
        # one.
        #
        # ADDED (roadmap, pagination): 'limit'/'offset' as query parameters
        # (default 50, capped at 200), plus the total number of records —
        # without it, a large table would return everything at once, unbounded.
        #
        # FIX (roadmap, visual front end): rows are now returned as named
        # objects {column: value} rather than raw positional arrays — a front
        # end (or any client) no longer needs to know the exact order of the
        # SQL columns to display the data correctly.
        #
        # ADDED (roadmap, capability ecosystem -- brick 2): hidden fields
        # ('hidden' rule) are removed from the response, after the named dict
        # is built but before it is returned -- never removed from the
        # database, never visible to anyone through this route, whoever calls
        # it (unlike 'restrictedTo', which allows a specific actor).
        masked = self.hidden_fields_by_entity.get(base_target, [])
        # ADDED (roadmap, capability ecosystem -- brick 5): 'categorized'
        # fields replaced by their category label, in the same pass as the
        # masking above — a single walk per row for both transformations.
        categorized_here = self.categorized_fields_by_entity.get(base_target, [])
        public_condition = access.public_condition
        condition_fragment = None
        # POINT 116: WHO escapes the condition. Without an exemption,
        # 'publicWhen' hid the filtered content FROM EVERYONE — the moderator
        # who had just hidden a post could neither list nor reread it (404),
        # and a draft's author never found their draft again. One-way
        # moderation, checked against a real server.
        #
        # Two exemptions, both DECLARATIVE:
        # - the SUPERVISOR named by 'sharedBy' on the same reference: the exact
        #   counterpart of the supervisor of accessibleBy (brick 23, point 106)
        #   and of ownedBy (point 88) — same keyword, same meaning;
        # - the OWNER, through their identity column (point 99): they see their
        #   own records whatever their state.
        #
        # Nothing implicit: a role that reads the entity without being declared
        # supervisor stays subject to the condition, otherwise "hidden" would
        # mean nothing as soon as someone is logged in.
        condition_supervisors, condition_owner_columns = (
            self._condition_exemptions(base_target))
        apply_condition_identity = bool(
            condition_supervisors or condition_owner_columns)
        if public_condition:
            condition_fragment = sql.cat(
                sql.ident(public_condition.field), sql.kw(" = "),
                sql.bind(repr(public_condition.value)))
        # ADDED (roadmap, "two-party access" brick): if an 'accessibleBy' rule
        # targets Read, the list returns only the records where the caller is
        # one of the parties (WHERE col1 = ? OR col2 = ? ...), and the read by
        # ID checks membership before answering. As for 'ownedBy', 'public'
        # wins if both are declared (no caller identity on a public route).
        read_parties = access.party_fields
        apply_read_parties = bool(read_parties) and not is_public
        read_supers = access.supervisors
        apply_read_super = bool(read_supers) and apply_read_parties
        if apply_condition_identity:
            read_dep_suffix += ", _ident: dict = Depends(get_optional_identity)"
        if apply_read_parties:
            read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"

        # FIX (beta 3, data leak between accounts): an 'ownedBy' rule on Read
        # now really restricts reading. The filter is built at runtime because
        # it depends on the caller's role: only the actor designated as owner
        # is limited to their records; a third role allowed to read the entity
        # (manager, supervisor) still sees everything.
        read_owner = access.owner_entity
        apply_read_owner = bool(read_owner) and not is_public and not apply_read_parties
        # ADDED (brick 11, point 81): under transitive ownership, the named
        # owner is an ENTITY, never a value `current_actor` could take — the
        # actor to compare is the one at the end of the chain. And the filter
        # becomes a subquery on the intermediate: comparing the column directly
        # with `current_user_id` would set a record id against an account id,
        # which was the point 80 defect.
        chaine_lecture = self._transitive_chain(base_target) if apply_read_owner else None
        read_actor = own_where_sql = None
        if apply_read_owner:
            if chaine_lecture:
                read_actor = chaine_lecture["actor"]
                # Bricks 11 and 24: the filter is an IN nested per link,
                # whatever the depth of the chain. The account is bound
                # (sql.bind), never pasted into the text.
                own_where_sql = self._chain_read_where(
                    base_target, sql.bind("current_user_id"))
            else:
                read_actor = read_owner
                own_where_sql = sql.cat(
                    sql.kw(' WHERE '), sql.ident(f"{read_owner.lower()}_id"),
                    sql.kw(' = '), sql.bind("current_user_id"))
            if condition_fragment:
                own_where_sql = sql.cat(
                    own_where_sql, sql.kw(" AND "), condition_fragment)
            if ", current_user_id" not in read_dep_suffix:
                read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"
        return SimpleNamespace(
            masked=masked,
            categorized_here=categorized_here,
            public_condition=public_condition,
            condition_fragment=condition_fragment,
            condition_supervisors=condition_supervisors,
            condition_owner_columns=condition_owner_columns,
            apply_condition_identity=apply_condition_identity,
            read_parties=read_parties,
            apply_read_parties=apply_read_parties,
            read_supers=read_supers,
            apply_read_super=apply_read_super,
            read_dep_suffix=read_dep_suffix,
            read_owner=read_owner,
            apply_read_owner=apply_read_owner,
            chaine_lecture=chaine_lecture,
            read_actor=read_actor,
            own_where_sql=own_where_sql,
        )

    def _where_list_read(self, e, parties_where, parties_params):
        """The runtime WHERE of the list: owner, supervisor or publicWhen."""
        condition_fragment = e.condition_fragment
        condition_supervisors = e.condition_supervisors
        condition_owner_columns = e.condition_owner_columns
        apply_condition_identity = e.apply_condition_identity
        read_supers = e.read_supers
        apply_read_super = e.apply_read_super
        apply_read_owner = e.apply_read_owner
        read_actor = e.read_actor
        own_where_sql = e.own_where_sql
        api_lines = []
        if apply_read_owner:
            api_lines.append("    _own_where, _own_params = '', ()")
            api_lines.append(f"    if current_actor == \"{read_actor}\":")
            api_lines.append(f"        _own_where = {own_where_sql.text!r}")
            api_lines.append(f"        _own_params = {sql.params_tuple(own_where_sql)}")
        elif apply_read_super:
            # The supervisor sees everything (empty WHERE); the parties stay
            # confined to their columns. Same conditional mechanism as the
            # ownedBy branch just above.
            _superset = ", ".join(f'"{s}"' for s in read_supers)
            api_lines.append("    _own_where, _own_params = '', ()")
            api_lines.append(f"    if current_actor not in {{{_superset}}}:")
            api_lines.append(f"        _own_where = ' WHERE {parties_where}'")
            api_lines.append(f"        _own_params = ({parties_params},)")
        elif apply_condition_identity:
            # POINT 116: the 'publicWhen' WHERE is decided at runtime, exactly
            # like the two branches above. By default the condition applies; a
            # declared supervisor lifts it entirely, an owner ADDS their own
            # rows to it (OR), it does not replace it — otherwise they would
            # lose the others' public content.
            base_where = sql.cat(sql.kw(" WHERE "), condition_fragment)
            api_lines.append(f"    _own_where = {base_where.text!r}")
            api_lines.append(f"    _own_params = {sql.params_tuple(base_where)}")
            if condition_owner_columns:
                frags = [sql.kw(" WHERE ("), condition_fragment]
                for col in condition_owner_columns:
                    frags += [sql.kw(" OR "), sql.ident(col), sql.kw(" = "),
                              sql.bind("_ident.get('user_id')")]
                owner_where = sql.cat(*frags, sql.kw(")"))
                api_lines.append("    if _ident.get('user_id'):")
                api_lines.append(f"        _own_where = {owner_where.text!r}")
                api_lines.append(f"        _own_params = {sql.params_tuple(owner_where)}")
            if condition_supervisors:
                _condset = ", ".join(f'"{s}"' for s in condition_supervisors)
                api_lines.append(f"    if _ident.get('actor') in {{{_condset}}}:")
                api_lines.append("        _own_where, _own_params = '', ()")
        return api_lines

    def _queries_list_read(self, base_target, e, parties_where, parties_params):
        """COUNT then page query, under the ACL WHERE."""
        condition_fragment = e.condition_fragment
        apply_condition_identity = e.apply_condition_identity
        apply_read_parties = e.apply_read_parties
        apply_read_super = e.apply_read_super
        apply_read_owner = e.apply_read_owner
        api_lines = []
        if apply_read_owner or apply_read_super or apply_condition_identity:
            api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"' + _own_where, _own_params)")
            api_lines.append("    total = cursor.fetchone()[0]")
            api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\"' + _own_where + ' LIMIT ? OFFSET ?', _own_params + (limit, offset))")
        elif apply_read_parties:
            api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\" WHERE {parties_where}', ({parties_params},))")
        else:
            if condition_fragment:
                api_lines.append(
                    f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\" WHERE "
                    f"{condition_fragment.text}', {sql.params_tuple(condition_fragment)})")
            else:
                api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"')")
        if not (apply_read_owner or apply_read_super or apply_condition_identity):
            api_lines.append("    total = cursor.fetchone()[0]")
            if apply_read_parties:
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE {parties_where} LIMIT ? OFFSET ?', ({parties_params}, limit, offset))")
            elif condition_fragment:
                params = sql.params_tuple(condition_fragment)
                api_lines.append(
                    f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE "
                    f"{condition_fragment.text} LIMIT ? OFFSET ?', "
                    f"{params[:-1]}limit, offset))")
            else:
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" LIMIT ? OFFSET ?', (limit, offset))")
        return api_lines

    def _guards_detail_read(self, base_target, e):
        """Detail read guards: publicWhen 404, owner 404, parties 403."""
        public_condition = e.public_condition
        condition_supervisors = e.condition_supervisors
        condition_owner_columns = e.condition_owner_columns
        apply_condition_identity = e.apply_condition_identity
        read_parties = e.read_parties
        apply_read_parties = e.apply_read_parties
        read_supers = e.read_supers
        apply_read_super = e.apply_read_super
        read_owner = e.read_owner
        apply_read_owner = e.apply_read_owner
        chaine_lecture = e.chaine_lecture
        read_actor = e.read_actor
        api_lines = []
        if public_condition:
            # POINT 116: the same exemptions as in the list, otherwise the
            # supervisor would list a record they could not open. 404 and never
            # 403 for the others: on sequential identifiers, distinguishing
            # "does not exist" from "hidden" would let someone count what was
            # removed.
            guard = (f"    if named_row.get({public_condition.field!r}) != "
                     f"{public_condition.value!r}")
            if apply_condition_identity:
                exemptions = []
                if condition_supervisors:
                    _condset = ", ".join(f'"{s}"' for s in condition_supervisors)
                    exemptions.append(f"_ident.get('actor') in {{{_condset}}}")
                for col in condition_owner_columns:
                    exemptions.append(
                        f"(_ident.get('user_id') and named_row.get({col!r}) "
                        f"== _ident.get('user_id'))")
                guard += " and not (" + " or ".join(exemptions) + ")"
            api_lines.append(
                guard + ": raise HTTPException(status_code=404, detail='Record not found')")
        if apply_read_owner:
            # 404 and not 403: on an entity with sequential identifiers, a 403
            # would confirm that someone else's record exists — enumerating the
            # identifiers would be enough to count a third party's expenses or
            # orders. A record one is not allowed to read must be
            # indistinguishable from a missing one.
            if chaine_lecture:
                # A single scalar subquery climbs the whole chain up to the
                # account, whatever its depth. A missing link gives NULL hence
                # "belongs to nobody", and 404 is the right answer for both
                # cases.
                _owner_q = self._chain_owner_scalar(
                    base_target,
                    sql.bind(f"named_row.get('{chaine_lecture['via_fk']}')"))
                _sql_lit, _params_lit = sql.execute_args(_owner_q, prefix="SELECT ")
                api_lines += [
                    f"    if current_actor == \"{read_actor}\":",
                    "        _tc = _connect(); _tcur = _tc.cursor()",
                    f"        _tcur.execute({_sql_lit}, {_params_lit})",
                    "        _tr = _tcur.fetchone(); _tc.close()",
                    "        if not _tr or _tr[0] is None or _tr[0] != current_user_id:",
                    "            raise HTTPException(status_code=404, detail='Record not found')",
                ]
            else:
                api_lines.append(f"    if current_actor == \"{read_actor}\" and "
                                 f"named_row.get('{read_owner.lower()}_id') != current_user_id:")
                api_lines.append("        raise HTTPException(status_code=404, detail='Record not found')")
        if apply_read_parties:
            # The check happens BEFORE 'hidden' masking: a party column can
            # legitimately be hidden on read while serving access control.
            parties_tuple = ", ".join(f"named_row.get('{c}')" for c in read_parties)
            if apply_read_super:
                _superset = ", ".join(f'"{s}"' for s in read_supers)
                api_lines.append(f"    if current_actor not in {{{_superset}}}:")
                api_lines.append(f"        if current_user_id not in ({parties_tuple}):")
                api_lines.append("            raise HTTPException(status_code=403, detail=\"Access control: only the resource's parties can read it\")")
            else:
                api_lines.append(f"    if current_user_id not in ({parties_tuple}):")
                api_lines.append("        raise HTTPException(status_code=403, detail=\"Access control: only the resource's parties can read it\")")
        return api_lines

    def _list_query_annotation(self, entity, field):
        """FastAPI type of the exact filter parameter declared in the spec."""
        choices = self.enumerated_fields.get(entity, {}).get(field)
        if choices:
            return "Optional[Literal[{}]]".format(
                ", ".join(repr(value) for value in choices))
        type_map = {
            "Integer": "int", "Float": "float", "Money": "float",
            "Boolean": "bool",
        }
        return f"Optional[{type_map.get(self.entities[entity][field], 'str')}]"
