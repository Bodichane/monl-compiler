"""WHO owns a row — directly, or through a chain.

`_transitive_chain` and `_owner_lookup_sql` are the SINGLE source of the
ownership join (bricks 11 and 24): do not rewrite it elsewhere.
POINT 99: `_identity_fk_columns` decides between a foreign key that
designates the ACCOUNTS registry and one that designates a business table
— and only ACTOR parents are candidates."""

from . import sql


class ProprietaireMixin:
    """WHO owns a row — directly, or through a chain."""

    def _fk_to(self, child, parent):
        """Foreign key column on 'child' that designates 'parent'.

        Same convention and same guard as plan_derivations: if the column is
        missing, validation and foreign key placement have diverged — and writing
        a join on None would make everything visible to everyone."""
        for p in self._compute_fk_placements().get(child, []):
            if p["owner_entity"] == parent:
                return p["fk_column"]
        raise ValueError(
            f"Generation: no foreign-key column of '{child}' points to "
            f"'{parent}', although the validator required this relation for a "
            f"transitive ownership chain."
        )

    def _transitive_chain(self, entity):
        """Transitive ownership chain of 'entity', or None (bricks 11 and 24).

        Returns what ALL access-control joins need, whatever the depth: the actor
        at the end of the chain, the column that, on the LAST link, carries the
        owning account's identifier ('actor_fk'), and the 'hops' list of links,
        from bottom to top, each with its table and the foreign key column that,
        on the level just below, designates that link:
          - hops[0].ref: on 'entity', points to hops[0].table;
          - hops[i].ref: on hops[i-1].table, points to hops[i].table.
        Single source of truth for the brick: routes, schemas and the frontend
        contract all go through here."""
        chaine = self.transitive_ownership.get(entity)
        if not chaine:
            return None
        hops_raw = chaine["chain"]
        acteur = chaine["actor"]
        if not hops_raw:
            raise ValueError(
                f"Generation: '{entity}' has transitive ownership but its chain "
                f"is empty -- the validator diverged. Failing rather than joining "
                f"on nothing."
            )
        # Bottom link: the foreign key on 'entity' toward the first link.
        hop_bas = {"table": hops_raw[0].lower(),
                   "ref": self._fk_to(entity, hops_raw[0])}
        hops = [hop_bas]
        for i in range(1, len(hops_raw)):
            hops.append({"table": hops_raw[i].lower(),
                         "ref": self._fk_to(hops_raw[i - 1], hops_raw[i])})
        actor_fk = self._fk_to(hops_raw[-1], acteur)
        return {"via": hops_raw[0], "via_fk": hop_bas["ref"],
                "via_table": hop_bas["table"], "actor": acteur,
                "actor_fk": actor_fk, "hops": hops, "len": len(hops)}

    def _chain_read_where(self, entity, actor_frag):
        """SQL 'WHERE' fragment (sql.Sql object) that limits 'entity' to the current
        account's rows. 'actor_frag' is the account value, bound by sql.bind —
        never a text fragment.

        Under a chain of one or more links, one nested 'IN' per link: the current
        level's foreign key column is compared with the next link's identifiers,
        up to the final link filtered by 'actor_fk = ?'. A missing link yields no
        row (an orphan row belongs to nobody). Returns None if 'entity' is not
        under transitive ownership."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        frag = sql.cat(sql.ident(chaine["actor_fk"]), sql.kw(" = "), actor_frag)
        for h in reversed(chaine["hops"]):
            frag = sql.cat(sql.ident(h["ref"]), sql.kw(" IN (SELECT id FROM "),
                           sql.ident(h["table"]), sql.kw(" WHERE "), frag,
                           sql.kw(")"))
        return sql.cat(sql.kw(" WHERE "), frag)

    def _chain_owner_scalar(self, entity, first_hop):
        """Scalar subquery (sql.Sql object) that returns the ACCOUNT id of a
        record's owner, starting from the id of the FIRST link. 'first_hop' is
        that FIRST link as an sql.Sql fragment — either a bound value (sql.bind,
        for routes that receive the foreign key from the client) or a subquery
        (the _chain_owner_from_row case). In every case, no value crosses the SQL
        text.

        Climbs the chain link by link: the current level's foreign key column
        designates the next link, and the final 'actor_fk' selection returns the
        account. Any missing link gives NULL hence "belongs to nobody". None if
        'entity' is not transitive."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        hops = chaine["hops"]
        expr = sql.cat(sql.kw("("), first_hop, sql.kw(")"))
        for i in range(1, len(hops)):
            h = hops[i]
            prev = hops[i - 1]
            expr = sql.cat(sql.kw('(SELECT '), sql.ident(h["ref"]),
                           sql.kw(' FROM '), sql.ident(prev["table"]),
                           sql.kw(' WHERE id = '), expr, sql.kw(')'))
        dernier = hops[-1]
        return sql.cat(sql.kw('(SELECT '), sql.ident(chaine["actor_fk"]),
                       sql.kw(' FROM '), sql.ident(dernier["table"]),
                       sql.kw(' WHERE id = '), expr, sql.kw(')'))

    def _chain_owner_from_row(self, entity, id_frag=None):
        """ACCOUNT id of the owner of a row of 'entity' (sql.Sql object), under a
        transitive chain of any depth. None if not transitive. 'id_frag' is the
        row's identifier as an sql.Sql fragment (by default the bound value 'id',
        the _owner_lookup_sql use)."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        if id_frag is None:
            id_frag = sql.bind("id")
        ref_bas = chaine["hops"][0]["ref"]
        first_hop = sql.cat(sql.kw('(SELECT '), sql.ident(ref_bas),
                            sql.kw(' FROM '), sql.ident(entity.lower()),
                            sql.kw(' WHERE id = '), id_frag, sql.kw(')'))
        return self._chain_owner_scalar(entity, first_hop)

    def _chain_join(self, entity, alias_root="t"):
        """Sequence of JOINs that climbs from 'entity' up to the final link.

        Returns (from_sql, last_link_alias, actor_fk) for the payment routes: each
        link joins its parent through its foreign key, and the last link
        'last_link_alias' carries the account's 'actor_fk' column. The amount, the
        state and the owner thus come out of the SAME read — the point 87
        invariant. Carries no client value, only identifiers and internal
        aliases."""
        chaine = self._transitive_chain(entity)
        # (called only when the chain is not None; otherwise a clear error)
        depuis = sql.cat(sql.ident(entity.lower()), sql.kw(f" {alias_root}"))
        cur = alias_root
        for i, h in enumerate(chaine["hops"]):
            alias = f"m{i + 1}"
            depuis = sql.cat(depuis, sql.kw(" JOIN "), sql.ident(h["table"]),
                             sql.kw(f" {alias} ON {alias}.id = {cur}."),
                             sql.ident(h["ref"]))
            cur = alias
        return depuis.text, cur, chaine["actor_fk"]

    def _owner_lookup_sql(self, entity, owner_entity):
        """Query that returns the ACCOUNT id of a record's owner, and the actor to
        check against. Shared by Update and Delete (routes.py) — two blocks
        identical until then, which would have had to be fixed twice.

        Under transitive ownership (brick 11), it is a join on the intermediate;
        it returns the same thing as under direct ownership (an account id), so
        the comparison that follows at the caller is unchanged. A missing
        intermediate yields no row: an orphan row belongs to nobody, and the
        caller's 404 fits."""
        chaine = self._transitive_chain(entity)
        if chaine:
            # Bricks 11 and 24: a scalar subquery climbs the whole chain up to
            # the account, whatever its depth. It returns an account id (None
            # if a link is missing), so the comparison at the caller is
            # unchanged compared with direct ownership.
            return chaine["actor"], sql.cat(
                sql.kw("SELECT "), self._chain_owner_from_row(entity))
        return owner_entity, sql.cat(
            sql.kw("SELECT "), sql.ident(f"{owner_entity.lower()}_id"),
            sql.kw(" FROM "), sql.ident(entity.lower()),
            sql.kw(" WHERE id = "), sql.bind("id"))

    def _get_incoming_relation(self, entity):
        """Returns the first incoming relation on 'entity' (hasMany, hasOne, or
        belongsTo — all handled now, see _compute_fk_placements), the one that
        provides the foreign key column in schema.sql, or None if there is none.
        Used to fill that column at creation and for ownership access control
        ('ownedBy')."""
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return None
        # FIX (beta 3): with several incoming relations, taking the first
        # declared one amounted to picking the "owner" by the accident of the
        # spec's writing order. 'ownedBy' rules explicitly name the owning
        # entity: it is authoritative when it exists. Failing that, we keep the
        # first declared relation.
        owners = {v for k, v in self.ownership.items() if k.split(".", 1)[0] == entity}
        chosen = next((p for p in placements if p["owner_entity"] in owners), placements[0])
        return {"source": chosen["owner_entity"], "fk_column": chosen["fk_column"]}

    def _client_fk_columns(self, entity):
        """Foreign key columns the CLIENT must supply at creation.

        The exact complement of `_identity_fk_columns`: every parent the token
        does not designate must be designated by the caller, otherwise the column
        stays NULL and the requested attachment disappears (a comment without its
        article, a variant without its product). Two exclusions, and only two —
        the identity column, filled from the JWT, and a counter's target, declared
        separately by `schemas.py` and the `is_reputation_fk` branch of
        `routes.py`: repeating it here would write it twice.

        On a public creation, no identity is available and the historical
        behavior (columns left NULL) is kept.

        POINT 99: the "no identity column" case is no longer reserved to
        transitive entities. A child entity of a BUSINESS table (a variant and its
        product) has no owner deduced from the token: all its foreign keys
        therefore come from the client."""
        if (entity, "Create") in self.public_actions:
            return []
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return []
        exclues = set(self._identity_fk_columns().get(entity, set()))
        # POINT 92: a counter target's column is the one the counter plan
        # designates for EACH rule, not the one of the first incoming relation.
        # With two relations (Post and Member), `_get_incoming_relation` may
        # designate Post while the identity fills member_id; the old decision
        # then excluded post_id from the INSERT and created an orphan row. The
        # `is_reputation_fk` branch of routes.py already writes each target: it
        # is excluded here so it is written exactly once.
        exclues.update(self._counter_fk_columns(entity))
        # Brick 11 (point 81): under transitive ownership, the "owner" parent
        # is precisely the one the CLIENT must designate ("I attach this line
        # to THIS order") -- it is no longer deduced from the token. It
        # therefore joins the other parents (no identity column exists then),
        # and the Create route then checks that the designated record really
        # belongs to the caller.
        return [p["fk_column"] for p in placements if p["fk_column"] not in exclues]

    def _identity_fk_columns(self):
        """Foreign key columns filled from the caller's JWT identity.

        Returns {entity: {columns}}. These are the ones the Create route fills
        with 'current_user_id' (an account identifier), not with a value from the
        request body — they therefore reference the accounts registry, not the
        business table of the same name. It is the SINGLE source of that
        distinction: the SQL schema draws its 'REFERENCES' from it, the contract
        its 'references_account', the Create route its 'populate_owner', the
        payment route the column it compares with the caller, and 'requiresOwn'
        the column where to look for a profile.

        POINT 99: the parent must be an ACTOR. "Filled from the caller's
        identity" only makes sense if the parent IS an account: a child entity of
        a business table (a variant and its product) has no owner to deduce from
        the token. Without this condition, such a column received
        `current_user_id` and declared itself `REFERENCES _monl_users` — the
        variant was attached to the seller who created it, never to its product,
        and the client could designate no parent. The column's name said one
        thing, its content another: the point 80 defect, from the other end of the
        same mechanism.

        The choice does NOT depend on the declaration order of relations: only
        actor parents are candidates, and the 'ownedBy' rule decides between them
        if there are several.

        The result depends only on the IR, frozen at construction: it is computed
        ONCE. Seven emitters query it from their loops — measured at 5,352 calls
        on a 1,668-line spec, each rescanning every entity and every relation."""
        if self._identity_fk_caches is not None:
            return self._identity_fk_caches
        route_map = self._compute_route_map()
        creatable = {plan.base_target for (act, _k), plan in route_map.items()
                     if act == "Create"}
        placements = self._compute_fk_placements()
        identity_cols = {}
        for entity in self.entities:
            colonne = self._colonne_d_identite(entity, creatable, placements)
            if colonne is not None:
                identity_cols.setdefault(entity, set()).add(colonne)
        self._identity_fk_caches = identity_cols
        return identity_cols

    def _colonne_d_identite(self, entity, creatable, placements):
        """The column an entity fills from the token, or None.

        Extracted from `_identity_fk_columns` to stay under the complexity
        ceiling; the three exclusions and the choice stay the same."""
        if entity not in creatable:
            return None
        if (entity, "Create") in self.public_actions:
            return None  # no reliable identity: the column stays NULL
        if entity in self.transitive_ownership:
            # Brick 11: the column contains an intermediate record id, not an
            # account id -- it therefore references the real business table,
            # not '_monl_users'.
            return None
        cibles_compteur = {r.target_entity
                           for r in self.reputation_rules_by_trigger.get(entity, [])}
        candidats = [p for p in placements.get(entity, [])
                     if p["owner_entity"] in self.actors
                     # target chosen by the client: a real business reference
                     and p["owner_entity"] not in cibles_compteur]
        if not candidats:
            return None
        proprietaires = {v for k, v in self.ownership.items()
                         if k.split(".", 1)[0] == entity}
        choisi = next((p for p in candidats if p["owner_entity"] in proprietaires),
                      candidats[0])
        return choisi["fk_column"]
