"""La lecture avec filtrage et tri déclarés (brique B3)."""

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
                sql.ident(public_condition["field"]), sql.kw(" = "),
                sql.bind(repr(public_condition["value"])))

        read_parties = access.party_fields
        apply_read_parties = bool(read_parties) and not is_public
        read_supers = access.supervisors
        apply_read_super = bool(read_supers) and apply_read_parties
        read_dep_suffix = dep_suffix
        if apply_condition_identity:
            read_dep_suffix += ", _ident: dict = Depends(get_optional_identity)"
        if apply_read_parties:
            read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"

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
                    sql.ident(f"{read_owner.lower()}_id"),
                    sql.kw(" = "), sql.bind("current_user_id"))
            if condition_fragment:
                owner_where = sql.cat(owner_where, sql.kw(" AND "), condition_fragment)
            if ", current_user_id" not in read_dep_suffix:
                read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"

        filter_fragments = {}
        for field in filter_fields:
            # La valeur est le nom de la variable Python générée pour ce champ;
            # sql.bind refuse toute autre porte d'entrée.
            fragment = sql.cat(sql.ident(field), sql.kw(" = "), sql.bind(field))
            filter_fragments[field] = fragment

        list_params = ["limit: int = 50", "offset: int = 0"]
        list_params.extend(
            f"{field}: {self._list_query_annotation(base_target, field)} = None"
            for field in filter_fields)
        if sort_fields:
            list_params.extend(["sort: Optional[str] = None",
                                "direction: str = 'asc'"])
        if read_dep_suffix:
            list_params.append(read_dep_suffix.lstrip(", "))
        api_lines += [
            f"@app.get('/{table}', tags=['{tag}'])",
            f"def list_{table}({', '.join(list_params)}):",
            security_check,
            "    limit = max(1, min(limit, 200))",
            "    offset = max(0, offset)",
        ]

        if apply_read_owner:
            api_lines += [
                "    _base_where, _base_params = '', ()",
                f"    if current_actor == {read_actor!r}:",
                f"        _base_where = {owner_where.text!r}",
                f"        _base_params = {sql.params_tuple(owner_where)}",
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
                f"    if current_actor not in {{{supers}}}:",
                f"        _base_where = {parties.text!r}",
                f"        _base_params = {sql.params_tuple(parties)}",
            ]
        elif apply_condition_identity:
            base_where = sql.cat(sql.kw(" WHERE "), condition_fragment)
            api_lines += [
                f"    _base_where = {base_where.text!r}",
                f"    _base_params = {sql.params_tuple(base_where)}",
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
                    f"        _base_where = {owner_condition.text!r}",
                    f"        _base_params = {sql.params_tuple(owner_condition)}",
                ]
            if condition_supervisors:
                supervisors = ", ".join(repr(actor)
                                         for actor in sorted(condition_supervisors))
                api_lines += [
                    f"    if _ident.get('actor') in {{{supervisors}}}:",
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
                f"    _base_where = {parties.text!r}",
                f"    _base_params = {sql.params_tuple(parties)}",
            ]
        else:
            api_lines += ["    _base_where, _base_params = '', ()"]

        api_lines += [
            "    _filter_parts, _filter_params = [], []",
        ]
        for field in filter_fields:
            fragment = filter_fragments[field]
            api_lines += [
                f"    if {field} is not None:",
                f"        _filter_parts.append({fragment.text!r})",
                f"        _filter_params.append({field})",
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
                f"{field!r}: {sql.ident(field).text!r}" for field in sort_fields)
            directions = ", ".join(
                f"{direction!r}: {sql.kw(direction.upper()).text!r}"
                for direction in ("asc", "desc"))
            api_lines += [
                f"    _sort_columns = {{{columns}}}",
                f"    _sort_directions = {{{directions}}}",
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
            f"    cursor.execute('SELECT COUNT(*) FROM \"{table}\"' + _query_where, _query_params)",
            "    total = cursor.fetchone()[0]",
            f"    cursor.execute('SELECT * FROM \"{table}\"' + _query_where + _order_by + ' LIMIT ? OFFSET ?', _query_params + (limit, offset))",
            "    rows = cursor.fetchall()",
            "    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)",
            "    conn.close()",
            "    named_rows = [dict(zip(_columns, row)) for row in rows]",
        ]
        row_loop_lines = []
        if masked:
            row_loop_lines.append(f"        for _f in [{mask_literal}]: _r.pop(_f, None)")
        for cf in categorized_here:
            row_loop_lines.extend(self._emit_categorization_lines(cf, "_r", "        "))
        if row_loop_lines:
            api_lines += ["    for _r in named_rows:", *row_loop_lines]
        api_lines += [
            "    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}",
            "",
            f"@app.get('/{table}/{{id}}', tags=['{tag}'])",
            f"def read_{table}(id: int{read_dep_suffix}):",
            security_check,
            "    conn = _connect(); cursor = conn.cursor()",
            f"    cursor.execute('SELECT * FROM \"{table}\" WHERE id = ?', (id,))",
            "    row = cursor.fetchone()",
            "    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)",
            "    conn.close()",
            "    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
            "    named_row = dict(zip(_columns, row))",
        ]
        if public_condition:
            guard = (f"    if named_row.get({public_condition['field']!r}) != "
                     f"{public_condition['value']!r}")
            if apply_condition_identity:
                exemptions = []
                if condition_supervisors:
                    supervisors = ", ".join(repr(actor)
                                             for actor in sorted(condition_supervisors))
                    exemptions.append(f"_ident.get('actor') in {{{supervisors}}}")
                exemptions.extend(
                    f"(_ident.get('user_id') and named_row.get({column!r}) == _ident.get('user_id'))"
                    for column in condition_owner_columns)
                guard += " and not (" + " or ".join(exemptions) + ")"
            api_lines.append(
                guard + ": raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
        if apply_read_owner:
            if chain:
                owner_query = self._chain_owner_scalar(
                    base_target, sql.bind(f"named_row.get('{chain['via_fk']}')"))
                sql_literal, params_literal = sql.execute_args(owner_query, prefix="SELECT ")
                api_lines += [
                    f"    if current_actor == {read_actor!r}:",
                    "        _tc = _connect(); _tcur = _tc.cursor()",
                    f"        _tcur.execute({sql_literal}, {params_literal})",
                    "        _tr = _tcur.fetchone(); _tc.close()",
                    "        if not _tr or _tr[0] is None or _tr[0] != current_user_id:",
                    "            raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                ]
            else:
                api_lines += [
                    f"    if current_actor == {read_actor!r} and named_row.get('{read_owner.lower()}_id') != current_user_id:",
                    "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                ]
        if apply_read_parties:
            parties_tuple = ", ".join(f"named_row.get('{column}')"
                                       for column in read_parties)
            if apply_read_super:
                supervisors = ", ".join(repr(actor)
                                         for actor in sorted(read_supers))
                api_lines += [
                    f"    if current_actor not in {{{supervisors}}}:",
                    f"        if current_user_id not in ({parties_tuple},):",
                    "            raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")",
                ]
            else:
                api_lines += [
                    f"    if current_user_id not in ({parties_tuple},):",
                    "        raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")",
                ]
        if masked:
            api_lines.append(f"    for _f in [{mask_literal}]: named_row.pop(_f, None)")
        for cf in categorized_here:
            api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
        api_lines += [
            "    return {'status': 'success', 'data': named_row}",
            "",
        ]
        return api_lines
