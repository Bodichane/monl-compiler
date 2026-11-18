"""The `Create` route.

It is the longest in the generator, and for good reason: it carries the
stock count, derivation, aggregation, the `requiresOwn` prerequisite,
numbering, timestamping and the payment lock — all in THE SAME transaction
as the insertion."""

from . import sql


class CreationRoutesMixin:
    """La route `Create`."""

    def _generate_create_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Create``."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        # ADDED (post-v6, roadmap): if the entity has an incoming relation
        # (e.g. "relation User hasMany Todo"), the matching foreign key column
        # (e.g. "user_id") is now really filled at creation, from the caller's
        # JWT identity.
        #
        # FIX OF A PRE-EXISTING GAP: this column had been generated in
        # schema.sql since the very first versions, but never included in the
        # INSERT query — it stayed NULL for every record created, making
        # relations inert at runtime despite their presence in the schema.
        reputation_rules_here = self.reputation_rules_by_trigger.get(base_target, [])
        counter_fk_columns = self._counter_fk_columns(base_target)
        is_reputation_fk = bool(counter_fk_columns)
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
        colonnes_identite = self._identity_fk_columns().get(base_target, set())
        colonne_identite = sorted(colonnes_identite)[0] if colonnes_identite else None
        populate_owner = colonne_identite is not None
        verifie_parent = bool(chaine_create) and not is_public
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
        fiche_exigee = self._profile_lookup(base_target)
        create_deps = dependency_injection
        if populate_owner or verifie_parent or fiche_exigee or message_here:
            create_deps += ", current_user_id: int = Depends(get_current_user_id)" if create_deps else "current_user_id: int = Depends(get_current_user_id)"
        if generated_here:
            create_deps += ", current_anon_handle: str = Depends(get_current_anon_handle)" if create_deps else "current_anon_handle: str = Depends(get_current_anon_handle)"
        create_deps_suffix = f", {create_deps}" if create_deps else ""

        api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def create_{base_target.lower()}(data: {base_target}Schema{create_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        fields = [
            field for field, type_ in self.entities[base_target].items()
            if type_ != "Upload"
        ]
        insert_columns = list(fields)
        # ADDED (brick 17, point 90): "no ordering without identifying
        # yourself". The check comes FIRST, before even the parent check and
        # any calculation: a caller without a profile has no business learning
        # whether a given product exists, nor consuming stock. 409 and not 403
        # — no permission is missing, it is a state to fix, and the message
        # says which one.
        if fiche_exigee:
            table_fiche, colonne_fiche = fiche_exigee
            api_lines += [
                f"    cursor.execute('SELECT 1 FROM \"{table_fiche}\" "
                f'WHERE "{colonne_fiche}" = ?\', (current_user_id,))',
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
        if verifie_parent:
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
        for verrou in self._payment_locked_parents(base_target):
            api_lines += self._payment_lock_lines(
                verrou["table"], f"data.{verrou['fk_column']}",
                verrou["entity"], var="_parent_regle")
        # ADDED (brick 10, point 77): a 'derivedFrom' field is not in `data` —
        # the server calculates it here, BEFORE the insertion, by reading the
        # price on the linked row the client designated. A 409 is better than a
        # wrong amount: a bogus reference must stop the order, not create it at
        # zero euros.
        derives_ici = self.derived_by_entity.get(base_target, ())
        for regle in derives_ici:
            fk_col = regle.source_fk
            var = f"_calcul_{regle.field}"
            api_lines += [
                f"    cursor.execute('SELECT \"{regle.source_field}\" FROM "
                f'"{regle.source_entity.lower()}" WHERE id = ?\', '
                f"(data.{fk_col},))",
                f"    _src_{regle.field} = cursor.fetchone()",
                f"    if not _src_{regle.field}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{regle.source_entity} not found: unable to calculate "
                f"{regle.field}.'))",
                f"    if data.{regle.factor} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'The quantity must be strictly positive.'))",
                f"    {var} = round(float(_src_{regle.field}[0] or 0) "
                f"* int(data.{regle.factor}), 2)",
            ]
        calcules = {r.field: f"_calcul_{r.field}" for r in derives_ici}
        calcules.update(dict.fromkeys(self.event_counters_by_entity.get(base_target, ()), "0"))
        # ADDED (brick 12, point 82): an order is born without lines, so its
        # total is born at 0 — never NULL, which no frontend knows how to
        # display, and never from `data` (the field is no longer there). The
        # sum will follow the lines, write by write.
        for nom_somme in self._aggregated_field_names(base_target):
            calcules[nom_somme] = "0"
        # ADDED (brick 16, point 89): the creation moment. Written here, only
        # once, and removed from the Update route's SET — a creation date that
        # moves is not a creation date.
        for nom_date in self.timestamp_fields_by_entity.get(base_target, []):
            calcules[nom_date] = "_horodatage()"
        # BRICK 25 (point 113): a field reserved to the `apres-paiement` route
        # is absent from the generic input schema. At creation it is therefore
        # born empty, exactly like a tracking value that does not exist yet.
        # Letting it fall through to the `data.<field>` fallback gave an
        # AttributeError and a 500 on EVERY creation of the entity — discovered
        # on CodexShop's real checkout, where fulfillmentStatus and
        # trackingNumber are legitimately unknown before payment.
        postpaiement_ici = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        for nom_postpaiement in postpaiement_ici:
            # POINT 191: the order of the `oneOf` is the life cycle (point 96).
            # A status reserved to post-payment is therefore born in its first
            # state; data without a closed list (tracking number, etc.) stays
            # legitimately unknown. `enumerated_fields` is the single source
            # already consumed by the Pydantic `Literal`s, and `repr()`
            # protects the generated literal as everywhere else.
            calcules[nom_postpaiement] = self._valeur_initiale_postpaiement(
                base_target, nom_postpaiement)
        # BRICK 22 (point 102): the readable number. The counter is read AND
        # incremented in the database; these lines therefore go INTO the `try`
        # below, not here — outside the transaction, a refused insertion would
        # leave the counter advanced and the next number would skip. Never
        # `MAX(...) + 1` on the business table: it would give back a deleted
        # record's number, and would go wrong as soon as two creations cross.
        lignes_numerotation = []
        for regle in self.numbered_fields_by_entity.get(base_target, []):
            var = f"_numero_{regle['field']}"
            lignes_numerotation.append(
                f"        {var} = _attribuer_numero(cursor, "
                f"{base_target!r}, {regle['field']!r}, "
                f"{regle['format']!r}, {regle['periode']!r})")
            calcules[regle["field"]] = var
        value_exprs = [
            calcules.get(f, "current_anon_handle" if f in generated_here
                         else f"data.{f}")
            for f in fields
        ]
        if populate_owner:
            insert_columns.append(colonne_identite)
            value_exprs.append("current_user_id")
        if is_reputation_fk:
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
        api_lines += lignes_numerotation
        api_lines.append(f"        cursor.execute(query, ({values_list},))")
        api_lines.append("        row_id = cursor.fetchone()[0]")
        # ADDED (brick 12, point 82): the parent's total is recomputed IN the
        # same transaction as the line's insertion. A separate commit could
        # leave a line created and a total lagging behind — that is, a cart
        # that does not say what it costs, and on a 'payable' entity, a wrong
        # amount to charge.
        for recalcul in self._aggregation_recomputes(base_target):
            parent = f"data.{recalcul['fk_column']}"
            api_lines.append(
                f"        cursor.execute({recalcul['sql']!r}, ({parent}, {parent}))")
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
            fk_vers_cible = rule.target_fk
            fk_value_expr = f"data.{fk_vers_cible}"
            # BRICK 14 (point 86): the quantity is either a constant or a field
            # of the request body ('by quantity').
            quantite = (f"data.{rule.amount_field}" if rule.amount_field
                        else str(rule.amount))
            # THE heart of the brick. A count that can go below its floor is a
            # stock that LIES: the shop would show -3 pairs available, and
            # would have charged for the eight it did not have. The safeguard
            # is not a hard-coded "stock" exception — it comes from the point
            # 85 'min' DECLARATION on the targeted field. A reputation without
            # 'min' keeps going below zero, as is its right.
            borne = rule.minimum
            if borne is not None and rule.direction == "decrements":
                # ONE single statement: the condition and the write are
                # evaluated together, so two simultaneous orders cannot read
                # the same stock and count it down twice.
                api_lines.append(
                    f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = "
                    f'"{target_field}" - ? WHERE id = ? AND "{target_field}" - ? >= ?\', '
                    f"({quantite}, {fk_value_expr}, {quantite}, {borne}))")
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
                    f"WHERE id = ?', ({quantite}, {fk_value_expr}))"
                )
        api_lines.append("        conn.commit()")
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
        uniques_ici = self._unique_fields(base_target)
        once_ici = [index for index in self._compute_once_per_indexes()
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
        once_names = tuple(index[2] for index in once_ici)
        once_signatures = tuple(
            f"{table}.{col}" for table, columns, _index in once_ici for col in columns)
        api_lines.append("    except _DATABASE_INTEGRITY_ERRORS as _err:")
        api_lines.append("        conn.rollback(); conn.close()")
        api_lines.append(
            f"        _integrity_kind = _database_integrity_kind(_err, {once_names!r}, "
            f"{once_signatures!r})")
        if once_ici:
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
        if uniques_ici:
            api_lines.append(
                f"                'Value already in use: {', '.join(uniques_ici)} "
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
