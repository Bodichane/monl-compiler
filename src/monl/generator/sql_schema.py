"""Generation of the SQL schema (schema.sql).

Extracted from the former monolithic module src/generator.py (1307 lines)
when it was split into a package — see docs/design_decisions.md."""


class SqlSchemaMixin:
    def _generate_sql(self):
        """Generates a deterministic SQL schema that preserves existing data (Bug #3)."""
        sql_lines = [f"-- Deterministic DB foundation generated automatically for {self.app_name}\n"]

        # ADDED (roadmap): system table of the real user registry. It exists
        # regardless of the spec (every generated application needs it for
        # /register and /login), so it is injected here rather than declared by
        # the user in the DSL.
        sql_lines += self._user_registry_sql_lines()

        # ADDED (roadmap, token revocation): persistent blocklist of tokens
        # explicitly revoked through /logout, before their natural expiry.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_revoked_tokens (")
        sql_lines.append("    jti VARCHAR(64) PRIMARY KEY,")
        sql_lines.append("    revoked_at TIMESTAMP NOT NULL,")
        # FIX (beta 3): without an expiry date, the blocklist could not be
        # purged — it grew forever and was consulted on every authenticated
        # request. An expired token is rejected by the signature check anyway:
        # keeping it in the blocklist adds nothing.
        #
        # DOUBLE PRECISION is understood by SQLite (same real affinity) and
        # carries an explicit native type on the PostgreSQL side.
        sql_lines.append("    expires_at DOUBLE PRECISION")
        sql_lines.append(");\n")

        # ADDED (long-term roadmap, multi-worker rate limiting): rate limiting
        # used to be an in-process memory dictionary (_RATE_LIMIT_ATTEMPTS),
        # hence NOT shared between several uvicorn/gunicorn workers: an
        # attacker spread over N workers got N times the quota. Each attempt is
        # now recorded in the database (shared by every worker), with the IP,
        # the bucket ('login'/'register') and the time. The index speeds up the
        # sliding window and the purge.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_rate_limit (")
        sql_lines.append("    bucket VARCHAR(32) NOT NULL,")
        sql_lines.append("    client_ip VARCHAR(64) NOT NULL,")
        sql_lines.append("    attempted_at DOUBLE PRECISION NOT NULL")
        sql_lines.append(");")
        sql_lines.append('CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup ON _monl_rate_limit (bucket, client_ip, attempted_at);\n')

        sql_lines += self._verification_sql_lines()
        if self.auth_features.get("lockout"):
            sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_account_lockouts (")
            sql_lines.append("    user_id INTEGER PRIMARY KEY,")
            sql_lines.append("    failed_count INTEGER NOT NULL,")
            sql_lines.append("    first_failed_at DOUBLE PRECISION NOT NULL,")
            sql_lines.append("    locked_until DOUBLE PRECISION,")
            sql_lines.append("    FOREIGN KEY (user_id) REFERENCES _monl_users(id)")
            sql_lines.append(");\n")

        if self.auth_features.get("password_reset"):
            sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_password_reset_tokens (")
            sql_lines.append("    token_hash VARCHAR(64) PRIMARY KEY,")
            sql_lines.append("    user_id INTEGER NOT NULL,")
            sql_lines.append("    created_at DOUBLE PRECISION NOT NULL,")
            sql_lines.append("    expires_at DOUBLE PRECISION NOT NULL,")
            sql_lines.append("    used_at DOUBLE PRECISION,")
            sql_lines.append("    FOREIGN KEY (user_id) REFERENCES _monl_users(id)")
            sql_lines.append(");")
            sql_lines.append("CREATE INDEX IF NOT EXISTS idx_password_reset_user ON _monl_password_reset_tokens (user_id, expires_at);\n")

        if self.auth_features.get("refresh_tokens"):
            sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_refresh_tokens (")
            sql_lines.append("    token_hash VARCHAR(64) PRIMARY KEY,")
            sql_lines.append("    user_id INTEGER NOT NULL,")
            sql_lines.append("    issued_at DOUBLE PRECISION NOT NULL,")
            sql_lines.append("    expires_at DOUBLE PRECISION NOT NULL,")
            sql_lines.append("    revoked_at DOUBLE PRECISION,")
            sql_lines.append("    FOREIGN KEY (user_id) REFERENCES _monl_users(id)")
            sql_lines.append(");")
            sql_lines.append("CREATE INDEX IF NOT EXISTS idx_refresh_user ON _monl_refresh_tokens (user_id, expires_at);\n")

        # BRICK 22 (point 102): the counters of readable numbers. A SYSTEM
        # table and not a business column — counting the existing records would
        # give back a deleted one's number. The PRIMARY key carries the period:
        # it is what restarts the sequence every year (or month, or day)
        # without any row having to be erased, and it is '' when the template
        # carries no date — the sequence is then global.
        #
        # Written unconditionally: an empty system table costs nothing, and
        # making it conditional would make the MIGRATION of an existing
        # database depend on the rule just added.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_sequences (")
        sql_lines.append("    entite VARCHAR(64) NOT NULL,")
        sql_lines.append("    champ VARCHAR(64) NOT NULL,")
        sql_lines.append("    periode VARCHAR(16) NOT NULL,")
        sql_lines.append("    dernier INTEGER NOT NULL DEFAULT 0,")
        sql_lines.append("    PRIMARY KEY (entite, champ, periode)")
        sql_lines.append(");\n")

        # Readable migration history, including automatic additions. The table
        # is created in the initial artifact and caught up by init_db() for
        # databases produced before A2.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_migrations (")
        sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
        sql_lines.append("    migration_name VARCHAR(255) NOT NULL,")
        sql_lines.append("    operation_index INTEGER NOT NULL,")
        sql_lines.append("    operation VARCHAR(64) NOT NULL,")
        sql_lines.append("    table_name VARCHAR(255) NOT NULL,")
        sql_lines.append("    direction VARCHAR(8) NOT NULL,")
        sql_lines.append("    details TEXT NOT NULL,")
        sql_lines.append("    applied_at TIMESTAMP NOT NULL,")
        sql_lines.append("    schema_fingerprint VARCHAR(64) NOT NULL")
        sql_lines.append(");\n")

        # FIX (roadmap): FK placement generalized to the 3 relation types
        # (hasMany, hasOne, belongsTo) through _compute_fk_placements, instead
        # of handling only 'hasMany' as before.
        fk_placements = self._compute_fk_placements()

        for ent_name, attrs in self.entities.items():
            # FIX (roadmap, reported bug -- collision with a reserved SQL
            # keyword): an entity named "Order" (or any other declared in the
            # spec that matches a SQLite keyword such as ORDER, GROUP,
            # SELECT...) made schema.sql fail with nothing clearly reported at
            # compile time -- just a silent SQL error at server startup. Table
            # AND column names are now always double-quoted (standard SQL
            # identifier escaping, supported by SQLite), whether or not they
            # collide -- more reliable than maintaining a list of reserved
            # words.
            sql_lines.append(f'CREATE TABLE IF NOT EXISTS "{ent_name.lower()}" (')
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f'    "{attr_name}" {sql_type},')
            # ADDED (payment brick, point 74): two payment tracking columns,
            # never supplied by the client (removed from the input schemas,
            # like a 'generated' field). 'en_attente' at the start: an order
            # exists before it is paid.
            if ent_name in getattr(self, "payable_by_entity", {}):
                sql_lines.append('    "payment_status" VARCHAR(32) DEFAULT \'en_attente\',')
                sql_lines.append('    "payment_ref" VARCHAR(255),')

            # FIX (roadmap, second bug -- hidden until now by the first):
            # foreign key columns and their 'FOREIGN KEY' constraint used to be
            # emitted one after the other, per relation. As soon as an entity
            # has 2 or more relations (e.g. OrderItem -> Order AND Product),
            # that produces a column after a table constraint -- invalid in
            # standard SQL (SQLite included): every column definition must
            # precede every table constraint. FK columns are now all declared
            # first, then all the 'FOREIGN KEY' constraints.
            for placement in fk_placements.get(ent_name, []):
                fk_col = placement["fk_column"]
                unique_kw = " UNIQUE" if placement["unique"] else ""
                sql_lines.append(f'    "{fk_col}" INTEGER{unique_kw},')

            # FIX (beta 3, referential integrity): see _identity_fk_columns — a
            # column filled from the caller's identity contains an ACCOUNT
            # identifier, not a business row identifier. It therefore
            # references '_monl_users'. The others (explicit targets supplied
            # by the client) do reference the business table. The inconsistency
            # was invisible as long as SQLite did not enforce constraints.
            identity_cols = self._identity_fk_columns().get(ent_name, set())
            for placement in fk_placements.get(ent_name, []):
                fk_col = placement["fk_column"]
                if fk_col in identity_cols:
                    sql_lines.append(f'    FOREIGN KEY ("{fk_col}") REFERENCES _monl_users(id),')
                else:
                    owner_table = placement["owner_entity"].lower()
                    sql_lines.append(f'    FOREIGN KEY ("{fk_col}") REFERENCES "{owner_table}"(id),')

            sql_lines[-1] = sql_lines[-1].rstrip(",")
            sql_lines.append(");\n")
        return "\n".join(sql_lines)

    def _user_registry_sql_lines(self):
        """Registry columns: historical state and declared options."""
        sql_lines = []
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_users (")
        sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
        sql_lines.append("    username VARCHAR(255) UNIQUE NOT NULL,")
        sql_lines.append("    password_hash VARCHAR(255) NOT NULL,")
        sql_lines.append("    salt VARCHAR(255) NOT NULL,")
        sql_lines.append("    actor VARCHAR(255) NOT NULL,")
        # ADDED (roadmap, capability ecosystem -- follow-up to brick 1): a
        # stable anonymous pseudonym, generated only once at registration (see
        # /register), independent of the spec -- always present, used only if a
        # 'generated' field refers to it.
        sql_lines.append("    anon_handle VARCHAR(255) UNIQUE NOT NULL" +
                         ("," if self.auth_features else ""))
        if self.auth_features:
            sql_lines.append("    token_version INTEGER NOT NULL DEFAULT 0" +
                             ("," if self.auth_features.get("totp") or self.auth_features.get("verify_email") else ""))
        if self.auth_features.get("verify_email"):
            sql_lines.append("    email_verified INTEGER NOT NULL DEFAULT 1" +
                             ("," if self.auth_features.get("totp") else ""))
        if self.auth_features.get("totp"):
            # BRICK B4: NULL means "two-factor not enabled". An existing
            # database is never converted, so a historical account stays able
            # to log in.
            sql_lines.append("    totp_secret VARCHAR(64),")
            sql_lines.append("    totp_enabled BOOLEAN,")
            sql_lines.append("    totp_last_step BIGINT")
        sql_lines.append(");\n")

        return sql_lines
