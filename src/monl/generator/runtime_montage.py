"""Le socle de base de données monté dans app.py, et les téléversements."""

class MontageRuntimeMixin:
    """Le socle de base de données monté dans app.py, et les téléversements."""

    def _socle_base_et_uploads(self, api_lines, totp_migration_lines):
        """Le socle de base de données, ses migrations, et les téléversements."""
        if self._condition_identity_needed():
            api_lines += [
                "def get_optional_identity(request: Request) -> dict:",
                "    _auth = request.headers.get('authorization') or ''",
                "    if not _auth.lower().startswith('bearer '):",
                "        return {}",
                "    _creds = HTTPAuthorizationCredentials(scheme='Bearer', credentials=_auth[7:].strip())",
                "    try:",
                "        return _decode_and_verify_token(_creds)",
                "    except HTTPException:",
                "        return {}\n",
            ]
        legacy_db_start = len(api_lines)
        api_lines += [
            # CORRECTIF (bêta 3) : '@app.on_event' est déprécié par Starlette et
            # disparaîtra ; le cycle de vie passe par un gestionnaire 'lifespan'.
            # init_db() ouvre volontairement une connexion SANS contrainte de clé
            # étrangère : création du schéma, migrations additives et données de
            # démonstration doivent pouvoir s'exécuter dans n'importe quel ordre.
            "def _table_exists(cursor, table):",
            "    if _DATABASE_KIND == 'postgresql':",
            "        cursor.execute('SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ?', (table,))",
            "    else:",
            "        cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=?', (table,))",
            "    return cursor.fetchone() is not None",
            "",
            "def _table_columns(cursor, table):",
            "    if _DATABASE_KIND == 'postgresql':",
            "        cursor.execute('SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?', (table,))",
            "        return {row[0] for row in cursor.fetchall()}",
            "    cursor.execute(f'PRAGMA table_info(\"{table}\")')",
            "    return {row[1] for row in cursor.fetchall()}",
            "",
            "def init_db():",
            "    conn = _connect()",
            "    if _DATABASE_KIND == 'sqlite':",
            "        _activer_wal(conn)",
            "    try:",
            "        with open('schema.sql', 'r', encoding='utf-8') as f:",
            "            conn.executescript(_schema_for_database(f.read()))",
            "        conn.commit()",
            "    except Exception as e:",
            "        conn.rollback()",
            "        raise RuntimeError(f'Initialisation du schéma échouée : {e}') from e",
            "    # AJOUT (roadmap long terme, migrations sans perte de données) :",
            "    # après le CREATE TABLE IF NOT EXISTS (qui ne modifie jamais une",
            "    # table déjà présente), on rattrape les colonnes ajoutées à la",
            "    # spec depuis la dernière compilation. Pour chaque table, on",
            "    # compare les colonnes attendues aux colonnes réelles",
            "    # (PRAGMA table_info) et on ajoute les manquantes par ALTER TABLE",
            "    # ADD COLUMN — opération purement additive : aucune donnée",
            "    # existante n'est lue, déplacée ou supprimée. Les colonnes",
            "    # retirées de la spec sont laissées en place (SQLite ne supporte",
            "    # pas DROP COLUMN sans reconstruction, et les supprimer",
            "    # détruirait des données — voir docs/MIGRATIONS.md).",
            "    try:",
            "        _cur = conn.cursor()",
            "        for _table, _cols in _EXPECTED_COLUMNS.items():",
            "            if not _table_exists(_cur, _table):",
            "                continue  # table absente : le CREATE l'a déjà couverte, ou spec sans données",
            "            _existing = _table_columns(_cur, _table)",
            "            for _col, _sql_type in _cols:",
            "                if _col not in _existing:",
            "                    _cur.execute(f'ALTER TABLE \"{_table}\" ADD COLUMN \"{_col}\" {_sql_type}')",
            "                    print(f'🔧 Migration : colonne \"{_col}\" ajoutée à \"{_table}\" ({_sql_type}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        conn.rollback()",
            "        raise RuntimeError(f'Migration additive échouée : {e}') from e",
            # POINT 85 : les index uniques, APRÈS la migration additive (la
            # colonne à indexer peut venir d'être ajoutée). Chacun dans son
            # propre try : un échec doit nommer SON champ, pas faire taire les
            # suivants. Sur une base qui contient déjà des doublons, l'index ne
            # peut pas être créé -- c'est un changement non automatisable
            # (docs/MIGRATIONS.md), donc on le DIT au lieu de l'avaler.
            "    for _table, _col, _index in _UNIQUE_INDEXES:",
            "        try:",
            "            conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS \"{_index}\" ON \"{_table}\" (\"{_col}\")')",
            "            conn.commit()",
            "        except _DATABASE_INTEGRITY_ERRORS:",
            "            conn.rollback()",
            "            _dups = conn.execute(f'SELECT COUNT(*) FROM (SELECT \"{_col}\" FROM \"{_table}\" GROUP BY \"{_col}\" HAVING COUNT(*) > 1)').fetchone()[0]",
            "            print(f'❌ \"{_table}\".\"{_col}\" est déclaré unique dans la spec, mais la base contient déjà {_dups} valeur(s) en double : l\\'unicité NE PEUT PAS être appliquée. Dédoublonner, puis redémarrer (docs/MIGRATIONS.md).')",
            "        except Exception as e:",
            "            conn.rollback()",
            "            print(f'⚠️ Index unique sur \"{_table}\".\"{_col}\" ignoré : {e}')",
            "    for _table, _cols, _index in _ONCE_PER_INDEXES:",
            "        try:",
            "            _columns = ', '.join(f'\"{_col}\"' for _col in _cols)",
            "            conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS \"{_index}\" ON \"{_table}\" ({_columns})')",
            "            conn.commit()",
            "        except _DATABASE_INTEGRITY_ERRORS:",
            "            conn.rollback()",
            "            _columns = ', '.join(f'\"{_col}\"' for _col in _cols)",
            "            print(f'❌ Unicité métier déjà violée sur \"{_table}\" ({_columns}) : corriger les doublons avant de redémarrer.')",
            "        except Exception as e:",
            "            conn.rollback()",
            "            print(f'⚠️ Index oncePer sur \"{_table}\" ignoré : {e}')",
            # POINT 89 : la migration additive rattrape une colonne, jamais son
            # contenu. Pour toutes les autres briques ça n'a aucune importance
            # (une colonne vide est une colonne vide) ; pour une date de
            # création, c'est irréparable — l'instant est passé et le serveur ne
            # l'a pas vu. La remplir avec l'heure du démarrage daterait toutes
            # les vieilles commandes d'aujourd'hui : ce serait une base de
            # données qui MENT, ce qui est pire que des cases vides. On compte,
            # on nomme, et on laisse à NULL.
            "    for _table, _col in _TIMESTAMP_COLUMNS:",
            "        try:",
            "            _sans = conn.execute(f'SELECT COUNT(*) FROM \"{_table}\" WHERE \"{_col}\" IS NULL').fetchone()[0]",
            "            if _sans:",
            "                print(f'ℹ️ \"{_table}\".\"{_col}\" : {_sans} enregistrement(s) créé(s) avant l\\'ajout de l\\'horodatage restent sans date. Elle ne peut pas être reconstituée — les dater après coup serait faux.')",
            "        except Exception:",
            "            pass  # table absente : rien à compter",
            # POINT 102 : même constat, même raison, sur les numéros lisibles.
            # Numéroter après coup prétendrait un ordre d'arrivée que le serveur
            # n'a pas observé — et sur un carnet de commandes, un numéro inventé
            # se retrouve sur une facture.
            "    for _table, _col in _NUMBERED_COLUMNS:",
            "        try:",
            "            _sans = conn.execute(f'SELECT COUNT(*) FROM \"{_table}\" WHERE \"{_col}\" IS NULL').fetchone()[0]",
            "            if _sans:",
            "                print(f'ℹ️ \"{_table}\".\"{_col}\" : {_sans} enregistrement(s) créé(s) avant l\\'ajout de la numérotation restent sans numéro. La séquence repart de 1 ; leur attribuer un numéro maintenant inventerait un ordre d\\'arrivée.')",
            "        except Exception:",
            "            pass  # table absente : rien à compter",
            # POINT 95 : même honnêteté que ci-dessus, sur les comptes. Déclarer
            # 'identifier: email' n'efface pas les comptes ouverts avant : ils
            # existent, leur mot de passe est valide, et ils continuent de se
            # connecter. Les convertir serait impossible (on n'invente pas une
            # adresse) et les supprimer serait pire. On les COMPTE et on le dit
            # — sans quoi l'auteur croirait sa règle appliquée partout.
            "    if AUTH_IDENTIFIER_FORMS and 'libre' not in AUTH_IDENTIFIER_FORMS:",
            "        try:",
            "            _anciens = [r[0] for r in conn.execute('SELECT username FROM _monl_users').fetchall()]",
            "            _hors = [u for u in _anciens if not _forme_valide(u)]",
            "            if _hors:",
            "                print(f'ℹ️ {len(_hors)} compte(s) existant(s) ne suivent pas la forme d\\'identifiant déclarée ({\", \".join(AUTH_IDENTIFIER_FORMS)}) : {\", \".join(_hors[:5])}{\"…\" if len(_hors) > 5 else \"\"}. Ils continuent de fonctionner ; la règle ne vaut que pour les inscriptions à venir.')",
            "        except Exception:",
            "            pass",
            "    # AJOUT (roadmap frontend, bloc 'seed') : insertion des données de",
            "    # démonstration si (et seulement si) la table est VIDE — idempotent,",
            "    # donc un redémarrage n'empile pas les doublons, et des données",
            "    # réelles créées par l'utilisateur ne sont jamais écrasées.",
            "    try:",
            "        _scur = conn.cursor()",
            "        for _table, _rows in _SEED_DATA.items():",
            "            _scur.execute(f'SELECT COUNT(*) FROM \"{_table}\"')",
            "            if _scur.fetchone()[0] > 0:",
            "                continue  # déjà des données : on ne touche à rien",
            "            _poses = 0",
            "            for _entree in _rows:",
            "                _row = dict(_entree['values'])",
            # BRIQUE 21 (point 100) : le rattachement se résout ICI, par une
            # lecture du parent, et jamais par un rang calculé à la compilation.
            # Le parent peut avoir été semé à l'instant (cas normal) comme
            # préexister dans une base déjà peuplée : dans les deux cas c'est son
            # `id` réel qu'on écrit.
            "                _p = _entree.get('parent')",
            "                if _p:",
            "                    _scur.execute(f'SELECT id FROM \"{_p[\"table\"]}\" WHERE \"{_p[\"field\"]}\" = ?', (_p['value'],))",
            "                    _cible = _scur.fetchone()",
            "                    if not _cible:",
            # Jamais en silence : une vitrine amputée sans un mot enverrait
            # chercher la panne dans le frontend.
            "                        print(f'⚠️ Donnée de démonstration ignorée : aucun \"{_p[\"table\"]}\" dont {_p[\"field\"]} vaut \"{_p[\"value\"]}\" pour y rattacher une ligne de \"{_table}\".')",
            "                        continue",
            "                    _row[_p['column']] = _cible[0]",
            "                _cols = list(_row.keys())",
            "                _placeholders = ', '.join(['?'] * len(_cols))",
            "                _colnames = ', '.join(f'\"{_c}\"' for _c in _cols)",
            "                _scur.execute(f'INSERT INTO \"{_table}\" ({_colnames}) VALUES ({_placeholders})', tuple(_row.values()))",
            "                _poses += 1",
            "            if _poses:",
            "                print(f'🌱 Données de démonstration insérées dans \"{_table}\" ({_poses}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Données de démonstration ignorées : {e}')",
            "    # CORRECTIF (bêta 3) : migration de la table système des jetons",
            "    # révoqués (colonne 'expires_at' ajoutée en bêta 3), pour qu'une",
            "    # base créée par une version antérieure continue de fonctionner.",
            "    try:",
            "        _sys_cur = conn.cursor()",
            "        if not _table_exists(_sys_cur, '_monl_revoked_tokens'):",
            "            raise RuntimeError('table _monl_revoked_tokens absente')",
            "        if 'expires_at' not in _table_columns(_sys_cur, '_monl_revoked_tokens'):",
            "            _sys_cur.execute('ALTER TABLE _monl_revoked_tokens ADD COLUMN expires_at DOUBLE PRECISION')",
            "        _purge_revoked_tokens(_sys_cur)",
            *totp_migration_lines,
            "        conn.commit()",
            "    except Exception as e:",
            "        conn.rollback()",
            "        raise RuntimeError(f'Migration système échouée : {e}') from e",
            "    finally:",
            "        conn.close()\n",

            "__MONL_DB_END__",
            "@asynccontextmanager",
            "async def _lifespan(_app: FastAPI):",
            "    try:",
            "        init_db()",
            "        yield",
            "    finally:",
            "        _close_database_pool()\n",
            # CORRECTIF (bêta 3) : '/docs' et '/openapi.json' publiaient la
            # surface complète de l'API en toutes circonstances. Indispensable
            # en développement, rarement souhaitable en déploiement :
            # MONL_DOCS=off les désactive sans toucher au code généré.
            "_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'",
            f"app = FastAPI(title='{self.app_name} - Secure Core', lifespan=_lifespan,",
            "               docs_url='/docs' if _docs_actives else None,",
            "               redoc_url='/redoc' if _docs_actives else None,",
            "               openapi_url='/openapi.json' if _docs_actives else None)\n",

            # Déploiement : CORS est opt-in. Une liste explicite est la seule
            # forme acceptée ; '*' ouvrirait l'API à n'importe quelle origine.
            "_CORS_ORIGINS = [origin.strip() for origin in os.environ.get(",
            "    'MONL_CORS_ORIGINS', '').split(',') if origin.strip()]",
            "if '*' in _CORS_ORIGINS:",
            "    raise RuntimeError(",
            "        \"MONL_CORS_ORIGINS refuse l'origine '*' : listez des origines \"",
            "        'explicites, séparées par des virgules.'",
            "    )",
            "if _CORS_ORIGINS:",
            "    from fastapi.middleware.cors import CORSMiddleware",
            "    app.add_middleware(",
            "        CORSMiddleware,",
            "        allow_origins=_CORS_ORIGINS,",
            "        allow_credentials=True,",
            f"        allow_methods={self._cors_methods()!r},",
            "        allow_headers=['Authorization', 'Content-Type', 'X-Request-ID'],",
            "        expose_headers=['X-Request-ID'],",
            "    )\n",

            # Healthchecks infra : ils ne sont ni dans les workflows ni dans
            # le contrat frontend. La vivacité ne touche jamais SQLite ; la
            # readiness exécute une seule requête triviale.
            "@app.get('/health', include_in_schema=False)",
            "def health():",
            "    return {'status': 'ok'}\n",
            "@app.get('/health/ready', include_in_schema=False)",
            "def health_ready():",
            "    conn = None",
            "    try:",
            "        conn = _connect()",
            "        conn.execute('SELECT 1')",
            "        return {'status': 'ready'}",
            "    except Exception:",
            "        raise HTTPException(status_code=503, detail='Service indisponible') from None",
            "    finally:",
            "        if conn is not None:",
            "            conn.close()\n",

            # Logs structurés opt-in. Aucun corps ni en-tête entrant n'est
            # copié dans le journal ; le chemin est privé de sa query string.
            "_LOG_JSON = os.environ.get('MONL_LOG_FORMAT', '').strip().lower() == 'json'",
            "_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')",
            "def _request_id(request):",
            "    candidate = request.headers.get('x-request-id', '')",
            "    if _REQUEST_ID_RE.fullmatch(candidate):",
            "        return candidate",
            "    return secrets.token_hex(16)\n",
            "def _write_request_log(request, request_id, status_code, started):",
            "    print(json.dumps({",
            "        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),",
            "        'method': request.method,",
            "        'path': request.url.path,",
            "        'status_code': status_code,",
            "        'duration_ms': round((time.perf_counter() - started) * 1000, 3),",
            "        'request_id': request_id,",
            "    }, ensure_ascii=False), flush=True)\n",
            "if _LOG_JSON:",
            "    @app.middleware('http')",
            "    async def _structured_request_log(request: Request, call_next):",
            "        started = time.perf_counter()",
            "        request_id = _request_id(request)",
            "        try:",
            "            response = await call_next(request)",
            "        except Exception:",
            "            _write_request_log(request, request_id, 500, started)",
            "            raise",
            "        response.headers['X-Request-ID'] = request_id",
            "        _write_request_log(request, request_id, response.status_code, started)",
            "        return response\n",

            # Redirection de la racine vers la documentation Swagger/OpenAPI
            # auto-générée par FastAPI — le seul front que monl fournit
            # encore (pivot, point 41) : l'interface réelle vient de l'IA
            # frontend, servie sur '/site' par 'monl run' (wrapper serve.py).
            f"from fastapi.responses import RedirectResponse{', FileResponse' if self.upload_fields else ''}\n",
            "@app.get('/', include_in_schema=False)",
            "async def root():",
            "    return RedirectResponse(url='/docs')\n",
        ]

        legacy_db_end = api_lines.index("__MONL_DB_END__")
        api_lines = (api_lines[:legacy_db_start]
                     + self._generate_database_runtime_lines()
                     + api_lines[legacy_db_end + 1:])

        if self.upload_fields:
            api_lines += self._generate_upload_runtime_lines()

        api_lines += [

            # CORRECTIF (roadmap) : remplacement du modèle "actor/user_id
            # auto-déclarés par le client" par un vrai registre d'utilisateurs
            # (table _monl_users, mot de passe haché avec sel via PBKDF2-
            # HMAC-SHA256, 100 000 itérations — pas de dépendance externe type
            # bcrypt nécessaire). LIMITE ASSUMÉE (prototype) : pas de politique
            # de mot de passe, pas de vérification d'email, pas de récupération
            # de compte — voir docs/design_decisions.md.
            "class RegisterRequest(BaseModel):",
            "    username: str",
            "    password: str",
            "    actor: str\n",
        ]
        return api_lines
