"""Génération du schéma SQL (schema.sql).

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class SqlSchemaMixin:
    def _generate_sql(self):
        """Génère un schéma SQL déterministe préservant les données existantes (Bug #3)."""
        sql_lines = [f"-- Socle DB Déterministe généré automatiquement pour {self.app_name}\n"]

        # AJOUT (roadmap) : table système du registre d'utilisateurs réel. Elle
        # existe indépendamment de la spec (toute application générée en a
        # besoin pour /register et /login), donc elle est injectée ici plutôt
        # que déclarée par l'utilisateur dans le DSL.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_users (")
        sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
        sql_lines.append("    username VARCHAR(255) UNIQUE NOT NULL,")
        sql_lines.append("    password_hash VARCHAR(255) NOT NULL,")
        sql_lines.append("    salt VARCHAR(255) NOT NULL,")
        sql_lines.append("    actor VARCHAR(255) NOT NULL,")
        # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
        # pseudonyme anonyme stable, généré une seule fois à l'inscription
        # (voir /register), indépendant de la spec -- toujours présent,
        # utilisé seulement si un champ 'generated' le référence.
        sql_lines.append("    anon_handle VARCHAR(255) UNIQUE NOT NULL" +
                         ("," if self.auth_features.get("totp") else ""))
        if self.auth_features.get("totp"):
            # BRIQUE B4 : NULL signifie « double facteur non activé ». Une
            # base existante n'est jamais convertie et un compte historique
            # reste donc connectable.
            sql_lines.append("    totp_secret VARCHAR(64),")
            sql_lines.append("    totp_enabled BOOLEAN,")
            sql_lines.append("    totp_last_step BIGINT")
        sql_lines.append(");\n")

        # AJOUT (roadmap, révocation de token) : liste noire persistante des
        # tokens explicitement révoqués via /logout, avant leur expiration
        # naturelle.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_revoked_tokens (")
        sql_lines.append("    jti VARCHAR(64) PRIMARY KEY,")
        sql_lines.append("    revoked_at TIMESTAMP NOT NULL,")
        # CORRECTIF (bêta 3) : sans date d'expiration, la liste noire ne pouvait
        # pas être purgée — elle grossissait indéfiniment et était consultée à
        # chaque requête authentifiée. Un jeton expiré est de toute façon
        # rejeté par la vérification de signature : le garder en liste noire
        # n'apporte rien.
        # DOUBLE PRECISION est compris par SQLite (même affinité réelle) et
        # porte un type natif explicite côté PostgreSQL.
        sql_lines.append("    expires_at DOUBLE PRECISION")
        sql_lines.append(");\n")

        # AJOUT (roadmap long terme, rate limiting multi-workers) : la
        # limitation de débit était jusqu'ici un dictionnaire en mémoire de
        # processus (_RATE_LIMIT_ATTEMPTS), donc NON partagé entre plusieurs
        # workers uvicorn/gunicorn : un attaquant réparti sur N workers
        # obtenait N fois le quota. Chaque tentative est désormais
        # enregistrée en base (partagée par tous les workers), avec l'IP, le
        # bucket ('login'/'register') et l'instant. L'index accélère la
        # fenêtre glissante et la purge.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_rate_limit (")
        sql_lines.append("    bucket VARCHAR(32) NOT NULL,")
        sql_lines.append("    client_ip VARCHAR(64) NOT NULL,")
        sql_lines.append("    attempted_at DOUBLE PRECISION NOT NULL")
        sql_lines.append(");")
        sql_lines.append('CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup ON _monl_rate_limit (bucket, client_ip, attempted_at);\n')

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

        # BRIQUE 22 (point 102) : les compteurs des numéros lisibles. Table
        # SYSTÈME et non colonne métier — compter les enregistrements existants
        # redonnerait le numéro d'un supprimé. La clé PRIMAIRE porte la période :
        # c'est elle qui fait repartir la séquence à chaque année (ou mois, ou
        # jour) sans qu'une ligne ait à être effacée, et elle vaut '' quand le
        # gabarit ne porte aucune date — la séquence est alors globale.
        # Écrite sans condition : une table système vide ne coûte rien, et la
        # rendre conditionnelle ferait dépendre la MIGRATION d'une base
        # existante de la règle qu'on vient d'ajouter.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monl_sequences (")
        sql_lines.append("    entite VARCHAR(64) NOT NULL,")
        sql_lines.append("    champ VARCHAR(64) NOT NULL,")
        sql_lines.append("    periode VARCHAR(16) NOT NULL,")
        sql_lines.append("    dernier INTEGER NOT NULL DEFAULT 0,")
        sql_lines.append("    PRIMARY KEY (entite, champ, periode)")
        sql_lines.append(");\n")

        # Historique lisible des migrations, y compris les ajouts automatiques.
        # La table est créée dans l'artefact initial et reste rattrapée par
        # init_db() pour les bases produites avant A2.
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

        # CORRECTIF (roadmap) : placement des FK généralisé aux 3 types de
        # relation (hasMany, hasOne, belongsTo) via _compute_fk_placements,
        # au lieu de ne traiter que 'hasMany' comme précédemment.
        fk_placements = self._compute_fk_placements()

        for ent_name, attrs in self.entities.items():
            # CORRECTIF (roadmap, bug signalé -- collision avec un mot-clé SQL
            # réservé) : une entité nommée "Order" (ou toute autre déclarée
            # dans la spec qui coïncide avec un mot-clé SQLite comme ORDER,
            # GROUP, SELECT...) faisait échouer schema.sql sans que rien ne le
            # signale clairement à la compilation -- juste une erreur SQL
            # silencieuse au démarrage du serveur. Les noms de table ET de
            # colonne sont désormais systématiquement entre guillemets
            # doubles (échappement d'identifiant standard SQL, supporté par
            # SQLite), qu'ils entrent ou non en collision -- plus fiable que
            # de maintenir une liste de mots réservés à jour.
            sql_lines.append(f'CREATE TABLE IF NOT EXISTS "{ent_name.lower()}" (')
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f'    "{attr_name}" {sql_type},')
            # AJOUT (brique paiement, point 74) : deux colonnes de suivi du
            # règlement, jamais fournies par le client (retirées des schémas
            # d'entrée, comme un champ 'generated'). 'en_attente' au départ :
            # une commande existe avant d'être payée.
            if ent_name in getattr(self, "payable_by_entity", {}):
                sql_lines.append('    "payment_status" VARCHAR(32) DEFAULT \'en_attente\',')
                sql_lines.append('    "payment_ref" VARCHAR(255),')

            # CORRECTIF (roadmap, second bug -- masqué jusqu'ici par le
            # premier) : les colonnes de clé étrangère et leur contrainte
            # 'FOREIGN KEY' étaient auparavant émises l'une après l'autre,
            # par relation. Dès qu'une entité a 2 relations ou plus (ex.
            # OrderItem -> Order ET Product), ça produit une colonne après
            # une contrainte de table -- invalide en SQL standard (SQLite y
            # compris) : toutes les définitions de colonnes doivent précéder
            # toute contrainte de table. Les colonnes FK sont maintenant
            # toutes déclarées d'abord, puis toutes les contraintes
            # 'FOREIGN KEY' ensuite.
            for placement in fk_placements.get(ent_name, []):
                fk_col = placement["fk_column"]
                unique_kw = " UNIQUE" if placement["unique"] else ""
                sql_lines.append(f'    "{fk_col}" INTEGER{unique_kw},')

            # CORRECTIF (bêta 3, intégrité référentielle) : voir
            # _identity_fk_columns — une colonne peuplée depuis l'identité de
            # l'appelant contient un identifiant de COMPTE, pas un identifiant
            # de ligne métier. Elle référence donc '_monl_users'. Les autres
            # (cibles explicites fournies par le client) référencent bien la
            # table métier. L'incohérence était invisible tant que SQLite
            # n'appliquait pas les contraintes.
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
