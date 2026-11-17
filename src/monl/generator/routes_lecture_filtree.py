"""La lecture avec filtrage et tri déclarés (brique B3)."""

from string import Template

from . import sql


class LectureFiltreeRoutesMixin:
    """La lecture avec filtrage et tri déclarés (brique B3)."""

    def _generate_read_route_lines_with_query(self, plan, context, act_type):
        """Liste avec filtres exacts et tri whitelisté (brique B3).

        Cette voie est conditionnelle. Elle compose toujours le WHERE d'ACL
        avant d'y ajouter les égalités de filtre. Les fragments de colonne et
        de direction sont produits par ``generator.sql`` au moment de la
        compilation ; à l'exécution le client ne choisit qu'une clé déjà
        présente dans les dictionnaires générés.
        """
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dep_suffix = context["dep_suffix"]
        filter_fields = self.filterable_fields_by_entity.get(base_target, [])
        sort_fields = self.sortable_fields_by_entity.get(base_target, [])
        table = base_target.lower()

        masked = self.hidden_fields_by_entity.get(base_target, [])
        mask_literal = ", ".join(repr(field) for field in masked)
        categorized_here = self.categorized_fields_by_entity.get(base_target, [])
        public_condition = access.public_condition
        condition_fragment = None
        condition_supervisors, condition_owner_columns = (
            self._condition_exemptions(base_target))
        apply_condition_identity = bool(
            condition_supervisors or condition_owner_columns)
        if public_condition:
            condition_fragment = sql.cat(
                sql.ident(public_condition.field), sql.kw(" = "),
                sql.bind(repr(public_condition.value)))

        read_parties = access.party_fields
        apply_read_parties = bool(read_parties) and not is_public
        read_supers = access.supervisors
        apply_read_super = bool(read_supers) and apply_read_parties
        read_dep_suffix = dep_suffix
        if apply_condition_identity:
            read_dep_suffix = Template('$v0, _ident: dict = Depends(get_optional_identity)').substitute(v0=read_dep_suffix)
        if apply_read_parties:
            read_dep_suffix = Template('$v0, current_user_id: int = Depends(get_current_user_id)').substitute(v0=read_dep_suffix)

        read_owner = access.owner_entity
        apply_read_owner = bool(read_owner) and not is_public and not apply_read_parties
        chain = self._transitive_chain(base_target) if apply_read_owner else None
        read_actor = None
        owner_where = None
        if apply_read_owner:
            if chain:
                read_actor = chain["actor"]
                owner_where = self._chain_read_where(
                    base_target, sql.bind("current_user_id"))
            else:
                read_actor = read_owner
                owner_where = sql.cat(
                    sql.kw(" WHERE "),
                    sql.ident(Template('${v0}_id').substitute(v0=read_owner.lower())),
                    sql.kw(" = "), sql.bind("current_user_id"))
            if condition_fragment:
                owner_where = sql.cat(owner_where, sql.kw(" AND "), condition_fragment)
            if ", current_user_id" not in read_dep_suffix:
                read_dep_suffix = Template('$v0, current_user_id: int = Depends(get_current_user_id)').substitute(v0=read_dep_suffix)

        filter_fragments = {}
        for field in filter_fields:
            # La valeur est le nom de la variable Python générée pour ce champ;
            # sql.bind refuse toute autre porte d'entrée.
            fragment = sql.cat(sql.ident(field), sql.kw(" = "), sql.bind(field))
            filter_fragments[field] = fragment

        list_params = ["limit: int = 50", "offset: int = 0"]
        list_params.extend(
            Template('$v0: $v1 = None').substitute(v0=field, v1=self._list_query_annotation(base_target, field))
            for field in filter_fields)
        if sort_fields:
            list_params.extend(["sort: Optional[str] = None",
                                "direction: str = 'asc'"])
        if read_dep_suffix:
            list_params.append(read_dep_suffix.lstrip(", "))
        api_lines += [
            Template("@app.get('/$v0', tags=['$v1'])").substitute(v0=table, v1=tag),
            Template('def list_$v0($v1):').substitute(v0=table, v1=', '.join(list_params)),
            security_check,
            "    limit = max(1, min(limit, 200))",
            "    offset = max(0, offset)",
        ]

        if apply_read_owner:
            api_lines += [
                "    _base_where, _base_params = '', ()",
                Template('    if current_actor == $v0:').substitute(v0=repr(read_actor)),
                Template('        _base_where = $v0').substitute(v0=repr(owner_where.text)),
                Template('        _base_params = $v0').substitute(v0=sql.params_tuple(owner_where)),
            ]
        elif apply_read_super:
            # `sql.cat` n'est pas un builder de listes : construire ce fragment
            # explicitement garde chaque colonne issue de la spec sous ident().
            party_parts = [sql.kw(" WHERE (")]
            for index, column in enumerate(read_parties):
                if index:
                    party_parts.append(sql.kw(" OR "))
                party_parts.extend([
                    sql.ident(column), sql.kw(" = "), sql.bind("current_user_id")])
            party_parts.append(sql.kw(")"))
            parties = sql.cat(*party_parts)
            supers = ", ".join(repr(actor) for actor in sorted(read_supers))
            api_lines += [
                "    _base_where, _base_params = '', ()",
                Template('    if current_actor not in {$v0}:').substitute(v0=supers),
                Template('        _base_where = $v0').substitute(v0=repr(parties.text)),
                Template('        _base_params = $v0').substitute(v0=sql.params_tuple(parties)),
            ]
        elif apply_condition_identity:
            base_where = sql.cat(sql.kw(" WHERE "), condition_fragment)
            api_lines += [
                Template('    _base_where = $v0').substitute(v0=repr(base_where.text)),
                Template('    _base_params = $v0').substitute(v0=sql.params_tuple(base_where)),
            ]
            if condition_owner_columns:
                owner_parts = [sql.kw(" WHERE ("), condition_fragment]
                for column in condition_owner_columns:
                    owner_parts.extend([
                        sql.kw(" OR "), sql.ident(column), sql.kw(" = "),
                        sql.bind("_ident.get('user_id')")])
                owner_parts.append(sql.kw(")"))
                owner_condition = sql.cat(*owner_parts)
                api_lines += [
                    "    if _ident.get('user_id'):",
                    Template('        _base_where = $v0').substitute(v0=repr(owner_condition.text)),
                    Template('        _base_params = $v0').substitute(v0=sql.params_tuple(owner_condition)),
                ]
            if condition_supervisors:
                supervisors = ", ".join(repr(actor)
                                         for actor in sorted(condition_supervisors))
                api_lines += [
                    Template("    if _ident.get('actor') in {$v0}:").substitute(v0=supervisors),
                    "        _base_where, _base_params = '', ()",
                ]
        elif apply_read_parties:
            party_parts = [sql.kw(" WHERE (")]
            for index, column in enumerate(read_parties):
                if index:
                    party_parts.append(sql.kw(" OR "))
                party_parts.extend([
                    sql.ident(column), sql.kw(" = "), sql.bind("current_user_id")])
            party_parts.append(sql.kw(")"))
            parties = sql.cat(*party_parts)
            api_lines += [
                Template('    _base_where = $v0').substitute(v0=repr(parties.text)),
                Template('    _base_params = $v0').substitute(v0=sql.params_tuple(parties)),
            ]
        else:
            api_lines += ["    _base_where, _base_params = '', ()"]

        api_lines += [
            "    _filter_parts, _filter_params = [], []",
        ]
        for field in filter_fields:
            fragment = filter_fragments[field]
            api_lines += [
                Template('    if $v0 is not None:').substitute(v0=field),
                Template('        _filter_parts.append($v0)').substitute(v0=repr(fragment.text)),
                Template('        _filter_params.append($v0)').substitute(v0=field),
            ]
        api_lines += [
            "    if _filter_parts:",
            "        _filter_where = ' AND '.join(_filter_parts)",
            "        if _base_where:",
            "            _query_where = _base_where + ' AND ' + _filter_where",
            "            _query_params = _base_params + tuple(_filter_params)",
            "        else:",
            "            _query_where = ' WHERE ' + _filter_where",
            "            _query_params = tuple(_filter_params)",
            "    else:",
            "        _query_where, _query_params = _base_where, _base_params",
        ]
        if sort_fields:
            columns = ", ".join(
                Template('$v0: $v1').substitute(v0=repr(field), v1=repr(sql.ident(field).text)) for field in sort_fields)
            directions = ", ".join(
                Template('$v0: $v1').substitute(v0=repr(direction), v1=repr(sql.kw(direction.upper()).text))
                for direction in ("asc", "desc"))
            api_lines += [
                Template('    _sort_columns = {$v0}').substitute(v0=columns),
                Template('    _sort_directions = {$v0}').substitute(v0=directions),
                "    _order_by = ''",
                "    if sort is not None:",
                "        _sort_column = _sort_columns.get(sort)",
                "        if _sort_column is None:",
                "            raise HTTPException(status_code=422, detail='Colonne de tri non déclarée')",
                "        _sort_direction = _sort_directions.get(direction.lower())",
                "        if _sort_direction is None:",
                "            raise HTTPException(status_code=422, detail=\"Sens de tri attendu : asc ou desc\")",
                "        _order_by = ' ORDER BY ' + _sort_column + ' ' + _sort_direction",
            ]
        else:
            api_lines.append("    _order_by = ''")
        api_lines += [
            "    conn = _connect(); cursor = conn.cursor()",
            Template('    cursor.execute(\'SELECT COUNT(*) FROM "$v0"\' + _query_where, _query_params)').substitute(v0=table),
            "    total = cursor.fetchone()[0]",
            Template('    cursor.execute(\'SELECT * FROM "$v0"\' + _query_where + _order_by + \' LIMIT ? OFFSET ?\', _query_params + (limit, offset))').substitute(v0=table),
            "    rows = cursor.fetchall()",
            "    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)",
            "    conn.close()",
            "    named_rows = [dict(zip(_columns, row)) for row in rows]",
        ]
        row_loop_lines = []
        if masked:
            row_loop_lines.append(Template('        for _f in [$v0]: _r.pop(_f, None)').substitute(v0=mask_literal))
        for cf in categorized_here:
            row_loop_lines.extend(self._emit_categorization_lines(cf, "_r", "        "))
        if row_loop_lines:
            api_lines += ["    for _r in named_rows:", *row_loop_lines]
        api_lines += [
            "    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}",
            "",
            Template("@app.get('/$v0/{id}', tags=['$v1'])").substitute(v0=table, v1=tag),
            Template('def read_$v0(id: int$v1):').substitute(v0=table, v1=read_dep_suffix),
            security_check,
            "    conn = _connect(); cursor = conn.cursor()",
            Template('    cursor.execute(\'SELECT * FROM "$v0" WHERE id = ?\', (id,))').substitute(v0=table),
            "    row = cursor.fetchone()",
            "    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)",
            "    conn.close()",
            "    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
            "    named_row = dict(zip(_columns, row))",
        ]
        if public_condition:
            guard = (Template('    if named_row.get($v0) != $v1').substitute(v0=repr(public_condition.field), v1=repr(public_condition.value)))
            if apply_condition_identity:
                exemptions = []
                if condition_supervisors:
                    supervisors = ", ".join(repr(actor)
                                             for actor in sorted(condition_supervisors))
                    exemptions.append(Template("_ident.get('actor') in {$v0}").substitute(v0=supervisors))
                exemptions.extend(
                    Template("(_ident.get('user_id') and named_row.get($v0) == _ident.get('user_id'))").substitute(v0=repr(column))
                    for column in condition_owner_columns)
                guard = Template('$v0 and not ($v1)').substitute(
                    v0=guard, v1=" or ".join(exemptions))
            api_lines.append(Template(
                "$v0: raise HTTPException(status_code=404, detail='Enregistrement introuvable')"
            ).substitute(v0=guard))
        if apply_read_owner:
            if chain:
                owner_query = self._chain_owner_scalar(
                    base_target, sql.bind(Template("named_row.get('$v0')").substitute(v0=chain['via_fk'])))
                sql_literal, params_literal = sql.execute_args(owner_query, prefix="SELECT ")
                api_lines += [
                    Template('    if current_actor == $v0:').substitute(v0=repr(read_actor)),
                    "        _tc = _connect(); _tcur = _tc.cursor()",
                    Template('        _tcur.execute($v0, $v1)').substitute(v0=sql_literal, v1=params_literal),
                    "        _tr = _tcur.fetchone(); _tc.close()",
                    "        if not _tr or _tr[0] is None or _tr[0] != current_user_id:",
                    "            raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                ]
            else:
                api_lines += [
                    Template("    if current_actor == $v0 and named_row.get('${v1}_id') != current_user_id:").substitute(v0=repr(read_actor), v1=read_owner.lower()),
                    "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                ]
        if apply_read_parties:
            parties_tuple = ", ".join(Template("named_row.get('$v0')").substitute(v0=column)
                                       for column in read_parties)
            if apply_read_super:
                supervisors = ", ".join(repr(actor)
                                         for actor in sorted(read_supers))
                api_lines += [
                    Template('    if current_actor not in {$v0}:').substitute(v0=supervisors),
                    Template('        if current_user_id not in ($v0,):').substitute(v0=parties_tuple),
                    "            raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")",
                ]
            else:
                api_lines += [
                    Template('    if current_user_id not in ($v0,):').substitute(v0=parties_tuple),
                    "        raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")",
                ]
        if masked:
            api_lines.append(Template('    for _f in [$v0]: named_row.pop(_f, None)').substitute(v0=mask_literal))
        for cf in categorized_here:
            api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
        api_lines += [
            "    return {'status': 'success', 'data': named_row}",
            "",
        ]
        return api_lines
