"""The `Create` route.

It is the longest in the generator, and for good reason: it carries the
stock count, derivation, aggregation, the `requiresOwn` prerequisite,
numbering, timestamping and the payment lock — all in THE SAME transaction
as the insertion."""

from . import sql


class CreationRoutesMixin:
    """The `Create` route."""

    def _generate_create_route_lines(self, plan, context, act_type):
        """Renders the ``Create`` route family."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        is_public = context["is_public"]
        # ADDED (post-v6, roadmap): if the entity has an incoming relation
        # (e.g. "relation User hasMany Todo"), the matching foreign key column
        # (e.g. "user_id") is now really filled at creation, from the caller's
        # JWT identity.
        #
        # FIX OF A PRE-EXISTING GAP: this column had been generated in
        # schema.sql since the very first versions, but never included in the
        # INSERT query — it stayed NULL for every record created, making
        # relations inert at runtime despite their presence in the schema.
        counter_fk_columns = self._counter_fk_columns(base_target)
        # POINT 99: the question "is this column filled from the token?" has
        # ONE answer, `_identity_fk_columns`, and this line reads it instead of
        # recomputing it. The four conditions that lived here (public route,
        # counter target, transitive ownership, and now non-actor parent) are
        # gathered there: keeping them in two places meant two places where
        # they could diverge — and the fourth was missing from both. Reminder
        # of the first three: a public route has no reliable caller identity; a
        # counter target is chosen by the client ("I like THIS post"); and
        # under transitive ownership, it is the client who designates the
        # attachment ("this line goes in THIS order") — writing
        # `current_user_id` there was the point 80 defect.
        chaine_create = self._transitive_chain(base_target)
        columns_identity = self._identity_fk_columns().get(base_target, set())
        column_identity = sorted(columns_identity)[0] if columns_identity else None
        populate_owner = column_identity is not None
        checked_parent = bool(chaine_create) and not is_public
        # ADDED (roadmap, capability ecosystem -- follow-up to brick 1): a
        # 'generated' field is filled from the current account's anonymous
        # pseudonym (already carried by the JWT since /login), never from the
        # request body -- incompatible with 'public' (validated by
        # ast_validator.py), so the caller is necessarily authenticated here.
        generated_here = self.generated_fields_by_entity.get(base_target, [])
        message_here = self.message_rules_by_trigger.get(base_target)
        # ADDED (brick 17, point 90): the profile the caller must already own.
        # It is looked up by its ACCOUNT identifier, so the route needs
        # `current_user_id` even when nothing else required it.
        fiche_required = self._profile_lookup(base_target)
        create_deps_suffix = self._dependencies_create(
            context, populate_owner or checked_parent or fiche_required or message_here,
            generated_here)

        api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def create_{base_target.lower()}(data: {base_target}Schema{create_deps_suffix}):")
        api_lines.append(context["security_check"])
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        fields = [
            field for field, type_ in self.entities[base_target].items()
            if type_ != "Upload"
        ]
        insert_columns = list(fields)
        api_lines += self._prerequisites_create(
            base_target, fiche_required, chaine_create, checked_parent)
        derives_here = self.derived_by_entity.get(base_target, ())
        api_lines += self._calculations_derives_create(derives_here)
        computed, lines_numbering = self._values_server_create(
            base_target, derives_here)
        value_exprs = [
            computed.get(f, "current_anon_handle" if f in generated_here
                         else f"data.{f}")
            for f in fields
        ]
        if populate_owner:
            insert_columns.append(column_identity)
            value_exprs.append("current_user_id")
        for counter_fk in counter_fk_columns:
            insert_columns.append(counter_fk)
            value_exprs.append(f"data.{counter_fk}")
        # Every parent the token does not designate must be designated by the
        # caller. Three cases lead there: the SECONDARY parents of an owned
        # entity (a comment and its article); under transitive ownership, the
        # owning parent itself — which the check above has just validated; and
        # since point 99, ALL the parents of a child entity of a business
        # table, which has no owner to deduce. On a public creation the list is
        # empty and the columns stay NULL, the historical behavior kept.
        for _client_fk in self._client_fk_columns(base_target):
            insert_columns.append(_client_fk)
            value_exprs.append(f"data.{_client_fk}")
        columns = ", ".join(f'"{c}"' for c in insert_columns)
        placeholders = ", ".join(["?"] * len(insert_columns))
        api_lines.append(f"    query = 'INSERT INTO \"{base_target.lower()}\" ({columns}) VALUES ({placeholders}) RETURNING id'")
        values_list = ", ".join(value_exprs)
        # FIX (beta, transactional integrity): the insertion and the linked
        # 'increments'/'decrements' effects run in A SINGLE transaction, with a
        # single commit at the end and a rollback on error. Before, an
        # intermediate commit after the INSERT then a separate commit per
        # effect could leave a partial state if the process stopped in between
        # (row created but counter not updated, or the reverse). A nonexistent
        # effect target still raises no error (UPDATE with no matching row) —
        # it simply does nothing.
        api_lines.append("    try:")
        api_lines += lines_numbering
        api_lines.append(f"        cursor.execute(query, ({values_list},))")
        api_lines.append("        row_id = cursor.fetchone()[0]")
        # ADDED (brick 12, point 82): the parent's total is recomputed IN the
        # same transaction as the line's insertion. A separate commit could
        # leave a line created and a total lagging behind — that is, a cart
        # that does not say what it costs, and on a 'payable' entity, a wrong
        # amount to charge.
        for recompute in self._aggregation_recomputes(base_target):
            parent = f"data.{recompute['fk_column']}"
            api_lines.append(
                f"        cursor.execute({recompute['sql']!r}, ({parent}, {parent}))")
        api_lines += self._effects_counters_create(base_target)
        api_lines.append("        conn.commit()")
        api_lines += self._conflicts_integrity_create(base_target)
        api_lines.append("    except Exception:")
        api_lines.append("        conn.rollback(); conn.close(); raise")
        api_lines.append("    conn.close()")
        if message_here:
            # The business commit is done before the thread starts. An SMTP
            # failure can therefore neither cancel the row nor turn a business
            # route into a route waiting on the network.
            api_lines.append(
                f"    _declencher_message({base_target!r}, current_user_id, row_id)")
        api_lines.append("    return {'status': 'success', 'id': row_id}")
        api_lines.append("")

        return api_lines

    @staticmethod
    def _dependencies_create(context, need_of_account, generated_here):
        """The route's dependency suffix: account id and anonymous pseudonym."""
        create_deps = context["dependency_injection"]
        if need_of_account:
            create_deps += ", current_user_id: int = Depends(get_current_user_id)" if create_deps else "current_user_id: int = Depends(get_current_user_id)"
        if generated_here:
            create_deps += ", current_anon_handle: str = Depends(get_current_anon_handle)" if create_deps else "current_anon_handle: str = Depends(get_current_anon_handle)"
        return f", {create_deps}" if create_deps else ""

    def _prerequisites_create(self, base_target, fiche_required, chaine_create, checked_parent):
        """Profile, parent ownership and payment lock: refused before anything."""
        api_lines = []
        # ADDED (brick 17, point 90): "no ordering without identifying
        # yourself". The check comes FIRST, before even the parent check and
        # any calculation: a caller without a profile has no business learning
        # whether a given product exists, nor consuming stock. 409 and not 403
        # — no permission is missing, it is a state to fix, and the message
        # says which one.
        if fiche_required:
            table_fiche, column_fiche = fiche_required
            api_lines += [
                f"    cursor.execute('SELECT 1 FROM \"{table_fiche}\" "
                f'WHERE "{column_fiche}" = ?\', (current_user_id,))',
                "    if not cursor.fetchone():",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                # No article before the entity name: it has no gender, and "un
                # Commande" read badly.
                f"            \"Create your {self.required_profiles[base_target]} "
                f"profile first: a \"",
                f"            '{base_target} record without it could not be "
                f"attached to anyone.'))",
            ]
        # ADDED (brick 11, point 81): the check that replaces filling from the
        # token. Without it, the brick would open a wider hole than the one it
        # closes: any account could add a line to someone else's order. It
        # comes BEFORE everything else ('derivedFrom' calculations included): a
        # caller who has no business there must not even learn whether a given
        # product exists.
        #
        # A single answer for "does not exist" and "not yours": distinguishing
        # them would allow enumerating other people's orders, exactly what the
        # detail read's 404 avoids.
        if checked_parent:
            # The chain (transitive, of any depth) is climbed in one go, from
            # the parent the CLIENT designates through its foreign key
            # (data.<fk>). A missing or foreign parent gets the same refusal:
            # the scalar is NULL or a different account. A single 403 for "does
            # not exist" and "not yours": distinguishing them would allow
            # enumerating other people's orders, exactly what the detail read's
            # 404 avoids.
            #
            # The value the CLIENT designates (data.<fk>) enters through
            # sql.bind: it comes out as '?' + bound parameter, never in the
            # text. It is the point 107 defect class made impossible — text and
            # params come out TOGETHER from the Sql object.
            _owner_q = self._chain_owner_scalar(
                base_target, sql.bind(f"data.{chaine_create['via_fk']}"))
            _sql_lit, _params_lit = sql.execute_args(_owner_q, prefix="SELECT ")
            api_lines += [
                f"    cursor.execute({_sql_lit}, {_params_lit})",
                "    _parent = cursor.fetchone()",
                "    if not _parent or _parent[0] is None or _parent[0] != current_user_id:",
                "        conn.close()",
                "        raise HTTPException(status_code=403, detail=(",
                f"            \"Access control: this {chaine_create['via']} does not \"",
                "            'belong to you, or does not exist.'))",
            ]
        # ADDED (brick 18, point 91): no line is added to an ALREADY SETTLED
        # order. The parent comes from `data.<fk>` here — the client designates
        # it — but it was validated just above by transitive ownership, so it
        # is indeed THEIR order. The guard comes before any calculation and
        # before any stock count: a refused write must have consumed nothing.
        for lock in self._payment_locked_parents(base_target):
            api_lines += self._payment_lock_lines(
                lock["table"], f"data.{lock['fk_column']}",
                lock["entity"], var="_parent_regle")
        return api_lines

    def _calculations_derives_create(self, derives_here):
        """Each derivedFrom amount, calculated from the designated row."""
        # ADDED (brick 10, point 77): a 'derivedFrom' field is not in `data` —
        # the server calculates it here, BEFORE the insertion, by reading the
        # price on the linked row the client designated. A 409 is better than a
        # wrong amount: a bogus reference must stop the order, not create it at
        # zero euros.
        api_lines = []
        for rule in derives_here:
            fk_col = rule.source_fk
            var = f"_calcul_{rule.field}"
            api_lines += [
                f"    cursor.execute('SELECT \"{rule.source_field}\" FROM "
                f'"{rule.source_entity.lower()}" WHERE id = ?\', '
                f"(data.{fk_col},))",
                f"    _src_{rule.field} = cursor.fetchone()",
                f"    if not _src_{rule.field}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{rule.source_entity} not found: unable to calculate "
                f"{rule.field}.'))",
                f"    if data.{rule.factor} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'The quantity must be strictly positive.'))",
                f"    {var} = round(float(_src_{rule.field}[0] or 0) "
                f"* int(data.{rule.factor}), 2)",
            ]
        return api_lines
