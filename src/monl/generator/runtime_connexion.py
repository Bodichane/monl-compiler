"""Inscription, connexion, déconnexion, et les gardes qui les entourent.

Un rôle n'est inscriptible que s'il porte `selfRegister` : c'est cette
frontière qui empêche un client anonyme de s'attribuer un rôle privilégié.
401 et jamais 422 à la connexion — un identifiant mal formé n'existe pas,
et le dire apprendrait la règle à un attaquant."""

class ConnexionRuntimeMixin:
    """Inscription, connexion, déconnexion, et les gardes qui les entourent."""

    def _socle_authentification(self, api_lines):
        """Inscription, connexion, déconnexion — et les gardes qui les entourent."""
        auth_checks = bool(self.auth_features.get("lockout") or self.auth_features.get("totp"))
        login_request_extra = (["    totp_code: Optional[str] = None"]
                               if self.auth_features.get("totp") else [])
        if auth_checks:
            select = "SELECT id, password_hash, salt, actor, anon_handle"
            if self.auth_features.get("totp"):
                select += ", totp_secret, totp_enabled, totp_last_step"
            lookup_lines = [
                f"    cursor.execute('{select} FROM _monl_users WHERE username = ?', (_identifiant,))",
                "    row = cursor.fetchone(); conn.close()",
                "    if not row:",
                "        db_user_id, stored_hash, salt_hex, actor, anon_handle = None, _DUMMY_HASH, _DUMMY_SALT_HEX, '', ''",
            ]
            if self.auth_features.get("totp"):
                lookup_lines.append("        totp_secret, totp_enabled, totp_last_step = None, False, None")
            lookup_lines += [
                "    else:",
            ]
            if self.auth_features.get("totp"):
                lookup_lines.append("        db_user_id, stored_hash, salt_hex, actor, anon_handle, totp_secret, totp_enabled, totp_last_step = row")
            else:
                lookup_lines.append("        db_user_id, stored_hash, salt_hex, actor, anon_handle = row")
            lookup_lines += [
                "    _candidate_hash = _hash_password(req.password if row else req.password[:256], salt_hex)",
            ]
            if self.auth_features.get("lockout"):
                lookup_lines += [
                    "    if db_user_id is not None and _account_lock_active(db_user_id):",
                    "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
                ]
            lookup_lines += [
                "    if not hmac.compare_digest(_candidate_hash, stored_hash):",
            ]
            if self.auth_features.get("lockout"):
                lookup_lines.append("        if db_user_id is not None: _record_account_failure(db_user_id)")
            lookup_lines += [
                "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            ]
            if self.auth_features.get("totp"):
                lookup_lines += [
                    "    if totp_enabled and not _consume_totp(db_user_id, totp_secret, req.totp_code):",
                ]
                if self.auth_features.get("lockout"):
                    lookup_lines.append("        _record_account_failure(db_user_id)")
                lookup_lines += [
                    "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
                ]
        else:
            lookup_lines = [
                "    cursor.execute('SELECT id, password_hash, salt, actor, anon_handle FROM _monl_users WHERE username = ?', (_identifiant,))",
                "    row = cursor.fetchone(); conn.close()",
                "    if not row:",
                "        hmac.compare_digest(_hash_password(req.password[:256], _DUMMY_SALT_HEX), _DUMMY_HASH)",
                "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
                "    db_user_id, stored_hash, salt_hex, actor, anon_handle = row",
                "    if not hmac.compare_digest(_hash_password(req.password, salt_hex), stored_hash):",
                "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            ]
        success_lines = (["    _clear_account_failures(db_user_id)"]
                         if self.auth_features.get("lockout") else [])
        if self.auth_features.get("refresh_tokens"):
            login_return_lines = [
                "    _refresh_conn = _connect(); _refresh_cursor = _refresh_conn.cursor()",
                "    refresh_token = _issue_refresh_token(_refresh_cursor, db_user_id)",
                "    _refresh_conn.commit(); _refresh_conn.close()",
                "    return {'access_token': token, 'token_type': 'bearer', 'refresh_token': refresh_token}\n",
            ]
        else:
            login_return_lines = [
                "    return {'access_token': token, 'token_type': 'bearer'}\n",
            ]

        api_lines += [
            "def _hash_password(password: str, salt_hex: str) -> str:",
            "    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()\n",
            "# CORRECTIF (bêta 3, énumération de comptes par canal temporel) :",
            "# '/login' renvoyait 401 immédiatement quand le compte n'existait pas,",
            "# sans dérouler les 100 000 itérations PBKDF2 — l'écart de temps de",
            "# réponse (~100 ms) révélait quels noms d'utilisateur existent.",
            "# On hache donc toujours, contre ce sel factice fixe le cas échéant.",
            "_DUMMY_SALT_HEX = '6d6f6e6c2d64756d6d792d73616c742d'",
            "_DUMMY_HASH = _hash_password('monl-dummy-password', _DUMMY_SALT_HEX)\n",

            # CORRECTIF (roadmap) : limitation de débit généralisée à un
            # nom de "bucket" (au lieu d'être câblée uniquement pour /login),
            # pour pouvoir protéger /register également — sans ça, /register
            # pouvait être utilisée pour créer des comptes en masse ou pour
            # énumérer les noms d'utilisateur déjà pris (via le code 409).
            # LIMITE ASSUMÉE (prototype) : compteur en mémoire du processus,
            # non distribué, remis à zéro au redémarrage du serveur —
            # suffisant pour freiner un script naïf, pas une attaque distribuée
            # à grande échelle (nécessiterait Redis ou équivalent en prod).
            "RATE_LIMIT_WINDOW_SECONDS = 60",
            "RATE_LIMIT_MAX_ATTEMPTS = 5\n",
            "# AJOUT (bêta, déploiement derrière un proxy) : par défaut on utilise",
            "# l'IP de la connexion directe (request.client.host). Si l'application",
            "# tourne derrière un reverse proxy de confiance (nginx, Traefik...),",
            "# activer MONL_TRUST_PROXY=1 fait lire la première IP de l'en-tête",
            "# X-Forwarded-For — sinon un client direct pourrait usurper cet en-tête",
            "# pour contourner la limitation de débit. On ne fait donc confiance à",
            "# l'en-tête QUE si l'opérateur l'a explicitement autorisé.",
            "_TRUST_PROXY = os.environ.get('MONL_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')",
            "def _client_ip(request: Request) -> str:",
            "    if _TRUST_PROXY:",
            "        fwd = request.headers.get('x-forwarded-for')",
            "        if fwd:",
            "            return fwd.split(',')[0].strip() or 'unknown'",
            "    return request.client.host if request.client else 'unknown'\n",
            "# AJOUT (roadmap long terme, rate limiting multi-workers) : compteur",
            "# de tentatives persisté en base plutôt qu'en mémoire de processus,",
            "# pour que le quota soit partagé par tous les workers uvicorn/gunicorn",
            "# (voir _monl_rate_limit dans schema.sql). Fenêtre glissante :",
            "# on compte les tentatives récentes, on purge les anciennes, puis on",
            "# enregistre la tentative courante.",
            "# CORRECTIF (bêta 3, TOCTOU) : le comptage et l'enregistrement de la",
            "# tentative se faisaient en deux exécutions autocommit distinctes —",
            "# N requêtes parallèles lisaient toutes le même compteur avant que",
            "# l'une d'elles ne l'incrémente, et passaient donc toutes le quota.",
            "# Le tout est désormais dans une transaction en écriture immédiate :",
            "# SQLite sérialise les writers, le quota redevient exact, y compris",
            "# entre workers puisqu'il est persisté en base.",
            "def _check_rate_limit(bucket: str, client_ip: str):",
            "    now = datetime.datetime.now(datetime.timezone.utc).timestamp()",
            "    cutoff = now - RATE_LIMIT_WINDOW_SECONDS",
            "    conn = _connect(); conn.isolation_level = None; cursor = conn.cursor()",
            "    try:",
            "        cursor.execute('BEGIN IMMEDIATE')",
            "        cursor.execute('DELETE FROM _monl_rate_limit WHERE attempted_at < ?', (cutoff,))",
            "        cursor.execute('SELECT COUNT(*) FROM _monl_rate_limit WHERE bucket = ? AND client_ip = ? AND attempted_at >= ?', (bucket, client_ip, cutoff))",
            "        recent = cursor.fetchone()[0]",
            "        if recent >= RATE_LIMIT_MAX_ATTEMPTS:",
            "            cursor.execute('COMMIT')",
            "            raise HTTPException(status_code=429, detail=f'Trop de tentatives ({bucket}). "
            "Réessayez dans {RATE_LIMIT_WINDOW_SECONDS} secondes.')",
            "        cursor.execute('INSERT INTO _monl_rate_limit (bucket, client_ip, attempted_at) VALUES (?, ?, ?)', (bucket, client_ip, now))",
            "        cursor.execute('COMMIT')",
            "    finally:",
            "        conn.close()\n",

            "@app.post('/register', tags=['Authentication'])",
            "def register(req: RegisterRequest, request: Request):",
            "    _check_rate_limit('register', _client_ip(request))",
            "    if req.actor not in VALID_ACTORS:",
            "        raise HTTPException(status_code=400, detail=f\"Acteur invalide. Acteurs valides : {VALID_ACTORS}\")",
            "    if req.actor not in SELF_REGISTER_ACTORS:",
            "        raise HTTPException(status_code=403, detail=(",
            "            f\"Le rôle '{req.actor}' n'est pas ouvert à l'inscription libre. \"",
            "            'Les comptes de ce rôle sont créés hors ligne : python3 manage.py adduser.'",
            "        ))",
            "    if len(req.password) < 8:",
            "        raise HTTPException(status_code=400, detail='Le mot de passe doit contenir au moins 8 caractères.')",
            "    if len(req.password) > 256:",
            "        raise HTTPException(status_code=400, detail='Mot de passe trop long (256 caractères maximum).')",
            # POINT 95 : la forme est contrôlée AVANT toute écriture, et la
            # valeur normalisée AVANT le contrôle d'unicité — l'inverse
            # laisserait 'Jean@Ex.com' passer à côté de 'jean@ex.com'.
            "    _identifiant = _normalize_identifier(req.username)",
            "    _check_identifier(_identifiant)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('SELECT id FROM _monl_users WHERE username = ?', (_identifiant,))",
            "    if cursor.fetchone():",
            "        conn.close()",
            # Le message doit nommer ce qui est réellement en conflit : sur une
            # inscription par e-mail, « ce nom d'utilisateur » ne veut rien dire
            # — et le conflit est souvent invisible pour l'appelant, puisqu'il
            # porte sur la forme NORMALISÉE de ce qu'il a tapé.
            "        raise HTTPException(status_code=409, detail=_conflit_identifiant())",
            "    salt_hex = os.urandom(16).hex()",
            "    pwd_hash = _hash_password(req.password, salt_hex)",
            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # pseudonyme anonyme stable, généré une seule fois ici (jamais
            # recalculé, jamais fourni par le client) -- 'Anon#' suivi de 4
            # chiffres aléatoires, avec quelques tentatives en cas de
            # collision (contrainte UNIQUE sur la colonne) plutôt qu'un échec
            # d'inscription pour une coïncidence statistiquement rare.
            "    anon_handle = None",
            "    for _ in range(10):",
            "        _candidate = f'Anon#{secrets.randbelow(9000) + 1000}'",
            "        cursor.execute('SELECT 1 FROM _monl_users WHERE anon_handle = ?', (_candidate,))",
            "        if not cursor.fetchone():",
            "            anon_handle = _candidate",
            "            break",
            "    if anon_handle is None:",
            "        conn.close()",
            "        raise HTTPException(status_code=500, detail='Impossible de générer un pseudonyme unique, réessayez.')",
            "    cursor.execute('INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) VALUES (?, ?, ?, ?, ?) RETURNING id',",
            "                   (_identifiant, pwd_hash, salt_hex, req.actor, anon_handle))",
            "    new_user_id = cursor.fetchone()[0]",
            "    conn.commit(); conn.close()",
            "    return {'status': 'success', 'user_id': new_user_id}\n",

            "class LoginRequest(BaseModel):",
            "    username: str",
            "    password: str\n",
            *login_request_extra,
            *( ["\n"] if login_request_extra else [] ),

            "@app.post('/login', tags=['Authentication'])",
            "def login(req: LoginRequest, request: Request):",
            "    _check_rate_limit('login', _client_ip(request))",
            # POINT 95 : MÊME normalisation qu'à l'inscription, et c'est la
            # moitié qui compte. Normaliser d'un seul côté crée des comptes
            # auxquels on ne peut plus se connecter — la casse d'une adresse ne
            # se retient pas. Aucun contrôle de FORME ici en revanche : un
            # identifiant mal formé n'existe simplement pas en base, et le 401
            # habituel répond sans révéler la règle.
            "    _identifiant = _normalize_identifier(req.username)",
            "    conn = _connect(); cursor = conn.cursor()",
            *lookup_lines,
            "    payload = {",
            "        'sub': _identifiant,",
            "        'actor': actor,",
            "        'user_id': db_user_id,",
            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # porté par le JWT comme 'actor'/'user_id', pour que les champs
            # 'generated' n'aient jamais besoin d'une requête DB séparée.
            "        'anon_handle': anon_handle,",
            # AJOUT (roadmap, révocation de token) : identifiant unique par
            # token (jti), nécessaire pour pouvoir le révoquer individuellement
            # via /logout sans avoir à invalider tous les tokens de l'utilisateur.
            "        'jti': secrets.token_hex(16),",
            ("        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)"
             if self.auth_features.get('refresh_tokens') else
             "        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS)"),
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            *success_lines,
            *login_return_lines,

            # AJOUT (roadmap, révocation de token) : /logout enregistre le jti
            # du token courant dans une liste noire persistante — toute
            # présentation ultérieure de ce même token est alors rejetée,
            # même s'il n'a pas encore atteint sa date d'expiration naturelle.
            "@app.post('/logout', tags=['Authentication'])",
            "def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):",
            "    payload = _decode_and_verify_token(credentials)",
            "    jti = payload.get('jti')",
            "    if not jti:",
            "        raise HTTPException(status_code=400, detail='Ce token ne supporte pas la révocation (jti manquant).')",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('INSERT INTO _monl_revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING',",
            "                   (jti, datetime.datetime.now(datetime.timezone.utc).isoformat(), payload.get('exp')))",
            "    _purge_revoked_tokens(cursor)",
            *(["    cursor.execute('UPDATE _monl_refresh_tokens SET revoked_at = ? WHERE user_id = ?', (datetime.datetime.now(datetime.timezone.utc).timestamp(), payload.get('user_id')))" ] if self.auth_features.get("refresh_tokens") else []),
            "    conn.commit(); conn.close()",
            "    return {'status': 'success', 'detail': 'Token révoqué.'}\n",
            *self._generate_auth_feature_routes(),
            "# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---"
        ]
        return api_lines
