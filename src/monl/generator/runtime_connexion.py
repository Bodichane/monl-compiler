"""Registration, login, logout, and the guards around them.

A role can register only if it carries `selfRegister`: that boundary is
what prevents an anonymous client from granting itself a privileged role.
401 and never 422 at login — a malformed identifier does not exist, and
saying so would teach the rule to an attacker."""

from string import Template


class ConnexionRuntimeMixin:
    """Registration, login, logout, and the guards around them."""

    def _lignes_connexion_gardee(self):
        """Reads the account at login when `lockout` or `totp` arm guards. Extracted
        from `_socle_authentification` to stay under the complexity ceiling; the
        emitted lines are unchanged."""
        select = Template(r"""SELECT id, password_hash, salt, actor, anon_handle${version}""").substitute(version=self._colonne_version())
        if self.auth_features.get("totp"):
            select = Template(r"""${select}, totp_secret, totp_enabled, totp_last_step""").substitute(select=select)
        lookup_lines = [
            Template(r"""    cursor.execute('${select} FROM _monl_users WHERE username = ?', (_identifiant,))""").substitute(select=select),
            *Template(r"""    row = cursor.fetchone(); conn.close()
    if not row:
        db_user_id, stored_hash, salt_hex, actor, anon_handle = None, _DUMMY_HASH, _DUMMY_SALT_HEX, '', ''""").substitute().split("\n"),
        ]
        if self.auth_features.get("totp"):
            lookup_lines.append("        totp_secret, totp_enabled, totp_last_step = None, False, None")
        lookup_lines.extend([
            Template(r"""    else:""").substitute(),
        ])
        if self.auth_features.get("totp"):
            lookup_lines.append("        db_user_id, stored_hash, salt_hex, actor, anon_handle, token_version, totp_secret, totp_enabled, totp_last_step = row")
        else:
            lookup_lines.append("        db_user_id, stored_hash, salt_hex, actor, anon_handle, token_version = row")
        lookup_lines.extend([
            Template(r"""    _candidate_hash = _hash_password(req.password if row else req.password[:256], salt_hex)""").substitute(),
        ])
        if self.auth_features.get("lockout"):
            lookup_lines.extend([
                # The missing account also pays for reading the lock, on
                # `None`: no row can
                # match this dummy value, so no UPDATE can be emitted.
                *Template(r"""    if _account_lock_active(db_user_id):
        raise HTTPException(status_code=401, detail='Invalid credentials.')""").substitute().split("\n"),
            ])
        lookup_lines.extend([
            Template(r"""    if not hmac.compare_digest(_candidate_hash, stored_hash):""").substitute(),
        ])
        if self.auth_features.get("lockout"):
            lookup_lines.append("        if db_user_id is not None: _record_account_failure(db_user_id)")
        lookup_lines.extend([
            Template(r"""        raise HTTPException(status_code=401, detail='Invalid credentials.')""").substitute(),
        ])
        if self.auth_features.get("totp"):
            lookup_lines.extend([
                Template(r"""    if totp_enabled and not _consume_totp(db_user_id, totp_secret, req.totp_code):""").substitute(),
            ])
            if self.auth_features.get("lockout"):
                lookup_lines.append("        _record_account_failure(db_user_id)")
            lookup_lines.extend([
                Template(r"""        raise HTTPException(status_code=401, detail='Invalid credentials.')""").substitute(),
            ])
        return lookup_lines

    def _socle_authentification(self, api_lines):
        """Registration, login, logout — and the guards around them."""
        auth_checks = bool(self.auth_features.get("lockout") or self.auth_features.get("totp"))
        login_request_extra = ([Template(r"""    totp_code: Optional[str] = None""").substitute()]
                               if self.auth_features.get("totp") else [])
        if auth_checks:
            lookup_lines = self._lignes_connexion_gardee()
        else:
            lookup_lines = [
                *Template(r"""    cursor.execute('SELECT id, password_hash, salt, actor, anon_handle FROM _monl_users WHERE username = ?', (_identifiant,))
    row = cursor.fetchone(); conn.close()
    if not row:
        hmac.compare_digest(_hash_password(req.password[:256], _DUMMY_SALT_HEX), _DUMMY_HASH)
        raise HTTPException(status_code=401, detail='Invalid credentials.')
    db_user_id, stored_hash, salt_hex, actor, anon_handle = row
    if not hmac.compare_digest(_hash_password(req.password, salt_hex), stored_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials.')""").substitute().split("\n"),
            ]
        lookup_lines = self._lookup_avec_version(lookup_lines, auth_checks)
        lookup_lines = self._lookup_avec_verification(lookup_lines)
        success_lines = ([Template(r"""    _clear_account_failures(db_user_id)""").substitute()]
                         if self.auth_features.get("lockout") else [])
        if self.auth_features.get("refresh_tokens"):
            login_return_lines = [
                *Template(r"""    _refresh_conn = _connect(); _refresh_cursor = _refresh_conn.cursor()
    refresh_token = _issue_refresh_token(_refresh_cursor, db_user_id)
    _refresh_conn.commit(); _refresh_conn.close()""").substitute().split("\n"),
                Template(r"""    return {'access_token': token, 'token_type': 'bearer', 'refresh_token': refresh_token}
""").substitute(),
            ]
        else:
            login_return_lines = [
                Template(r"""    return {'access_token': token, 'token_type': 'bearer'}
""").substitute(),
            ]

        api_lines.extend([
            # POINT 95: the form is checked BEFORE any write, and the value
            # normalized BEFORE the uniqueness check — the reverse would let
            # 'Jean@Ex.com' slip past 'jean@ex.com'. The message must name what
            # is really in conflict: for an email registration, "this username"
            # means nothing — and the conflict is often invisible to the
            # caller, since it is on the NORMALIZED form of what they typed.
            # ADDED (roadmap, capability ecosystem -- follow-up to brick 1): a
            # stable anonymous pseudonym, generated only once here (never
            # recomputed, never supplied by the client) -- 'Anon#' followed by
            # 4 random digits, with a few retries on collision (UNIQUE
            # constraint on the column) rather than a registration failure for
            # a statistically rare coincidence.
            # POINT 95: the SAME normalization as at registration, and this is
            # the half that matters. Normalizing on one side only creates
            # accounts nobody can log into anymore — nobody remembers the case
            # of an address. No FORM check here, however: a malformed
            # identifier simply does not exist in the database, and the usual
            # 401 answers without revealing the rule.
            # ADDED (roadmap, capability ecosystem -- follow-up to brick 1):
            # carried by the JWT as 'actor'/'user_id', so that 'generated'
            # fields never need a separate DB query.
            # ADDED (roadmap, token revocation): a unique identifier per token
            # (jti), needed to revoke it individually through /logout without
            # invalidating all of the user's tokens.
            Template(r"""def _hash_password(password: str, salt_hex: str) -> str:""").substitute(),
            Template(r"""    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()
""").substitute(),
            *Template(r"""# FIX (beta 3, account enumeration through a timing channel):
# '/login' returned 401 immediately when the account did not exist,
# without running the 100,000 PBKDF2 iterations — the response-time gap
# (~100 ms) revealed which usernames exist. So we always hash, against
# this fixed dummy salt when needed.
_DUMMY_SALT_HEX = '6d6f6e6c2d64756d6d792d73616c742d'""").substitute().split("\n"),
            Template(r"""_DUMMY_HASH = _hash_password('monl-dummy-password', _DUMMY_SALT_HEX)
""").substitute(),

            # FIX (roadmap): rate limiting generalized to a "bucket" name
            # (instead of being wired only for /login), so /register can be
            # protected too — without it, /register could be used to create
            # accounts en masse or to enumerate usernames already taken
            # (through the 409 code).
            # ACCEPTED LIMIT (prototype): an in-process memory counter, not
            # distributed, reset when the server restarts — enough to slow down
            # a naive script, not a large-scale distributed attack (that would
            # need Redis or equivalent in production).
            Template(r"""RATE_LIMIT_WINDOW_SECONDS = 60""").substitute(),
            Template(r"""RATE_LIMIT_MAX_ATTEMPTS = 5
""").substitute(),
            *Template(r"""# ADDED (beta, deployment behind a proxy): by default we use the IP of
# the direct connection (request.client.host). If the application runs
# behind a trusted reverse proxy (nginx, Traefik...), setting
# MONL_TRUST_PROXY=1 reads the first IP of the X-Forwarded-For header —
# otherwise a direct client could spoof that header to bypass rate
# limiting. So the header is trusted ONLY if the operator explicitly
# allowed it.
_TRUST_PROXY = os.environ.get('MONL_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')
def _client_ip(request: Request) -> str:
    if _TRUST_PROXY:
        fwd = request.headers.get('x-forwarded-for')
        if fwd:
            return fwd.split(',')[0].strip() or 'unknown'""").substitute().split("\n"),
            Template(r"""    return request.client.host if request.client else 'unknown'
""").substitute(),
            *Template(r"""# ADDED (long-term roadmap, multi-worker rate limiting): attempt counter persisted in the
# database rather than in process memory, so that the quota is shared by all uvicorn/gunicorn
# workers (see _monl_rate_limit in schema.sql). Sliding window: recent attempts are counted,
# old ones purged, then the current attempt is recorded.
# FIX (beta 3, TOCTOU): counting and recording the attempt happened in two separate autocommit
# executions — N parallel requests all read the same counter before one of them incremented
# it, and so all passed the quota. The whole thing is now in an immediate write transaction:
# SQLite serializes the writers, the quota is exact again, including across workers since it
# is persisted in the database.
def _check_rate_limit(bucket: str, client_ip: str):
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    conn = _connect(); conn.isolation_level = None; cursor = conn.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('DELETE FROM _monl_rate_limit WHERE attempted_at < ?', (cutoff,))
        cursor.execute('SELECT COUNT(*) FROM _monl_rate_limit WHERE bucket = ? AND client_ip = ? AND attempted_at >= ?', (bucket, client_ip, cutoff))
        recent = cursor.fetchone()[0]
        if recent >= RATE_LIMIT_MAX_ATTEMPTS:
            cursor.execute('COMMIT')
            raise HTTPException(status_code=429, detail=f'Too many attempts ({bucket}). Try again in {RATE_LIMIT_WINDOW_SECONDS} seconds.')
        cursor.execute('INSERT INTO _monl_rate_limit (bucket, client_ip, attempted_at) VALUES (?, ?, ?)', (bucket, client_ip, now))
        cursor.execute('COMMIT')
    finally:""").substitute().split("\n"),
            Template(r"""        conn.close()
""").substitute(),

            *Template(r"""@app.post('/register', tags=['Authentication'])
def register(req: RegisterRequest, request: Request):
    _check_rate_limit('register', _client_ip(request))
    if req.actor not in VALID_ACTORS:
        raise HTTPException(status_code=400, detail=f"Invalid actor. Valid actors: {VALID_ACTORS}")
    if req.actor not in SELF_REGISTER_ACTORS:
        raise HTTPException(status_code=403, detail=(
            f"The role '{req.actor}' is not open to self-registration. "
            'Accounts with this role are created offline: python3 manage.py adduser.'
        ))
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail='The password must contain at least 8 characters.')
    if len(req.password) > 256:
        raise HTTPException(status_code=400, detail='Password too long (256 characters maximum).')
    _identifiant = _normalize_identifier(req.username)
    _check_identifier(_identifiant)
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT id FROM _monl_users WHERE username = ?', (_identifiant,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail=_conflit_identifiant())
    salt_hex = os.urandom(16).hex()
    pwd_hash = _hash_password(req.password, salt_hex)
    anon_handle = None
    for _ in range(10):
        _candidate = f'Anon#{secrets.randbelow(9000) + 1000}'
        cursor.execute('SELECT 1 FROM _monl_users WHERE anon_handle = ?', (_candidate,))
        if not cursor.fetchone():
            anon_handle = _candidate
            break
    if anon_handle is None:
        conn.close()
        raise HTTPException(status_code=500, detail='Unable to generate a unique pseudonym, try again.')
    cursor.execute('INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) VALUES (?, ?, ?, ?, ?) RETURNING id',
                   (_identifiant, pwd_hash, salt_hex, req.actor, anon_handle))
    new_user_id = cursor.fetchone()[0]""").substitute().split("\n"),
            *self._verification_register_lines(),
            Template(r"""    conn.commit(); conn.close()""").substitute(),
            *self._verification_register_return_lines(),

            *Template(r"""class LoginRequest(BaseModel):
    username: str""").substitute().split("\n"),
            Template(r"""    password: str
""").substitute(),
            *login_request_extra,
            *( [Template(r"""
""").substitute()] if login_request_extra else [] ),

            *Template(r"""@app.post('/login', tags=['Authentication'])
def login(req: LoginRequest, request: Request):
    _check_rate_limit('login', _client_ip(request))
    _identifiant = _normalize_identifier(req.username)
    conn = _connect(); cursor = conn.cursor()""").substitute().split("\n"),
            *lookup_lines,
            *Template(r"""    payload = {
        'sub': _identifiant,
        'actor': actor,
        'user_id': db_user_id,
        'anon_handle': anon_handle,
        'jti': secrets.token_hex(16),""").substitute().split("\n"),
            ("        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)"
             if self.auth_features.get('refresh_tokens') else
             "        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS)"),
            Template(r"""    }""").substitute(),
            *self._ligne_version_du_jeton(),
            Template(r"""    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)""").substitute(),
            *success_lines,
            *login_return_lines,

            # ADDED (roadmap, token revocation): /logout records the current
            # token's jti in a persistent blocklist — any later presentation of
            # that same token is then rejected, even if it has not yet reached
            # its natural expiry date.
            *Template(r"""@app.post('/logout', tags=['Authentication'])
def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    payload = _decode_and_verify_token(credentials)
    jti = payload.get('jti')
    if not jti:
        raise HTTPException(status_code=400, detail='This token does not support revocation (missing jti).')
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('INSERT INTO _monl_revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING',
                   (jti, datetime.datetime.now(datetime.timezone.utc).isoformat(), payload.get('exp')))
    _purge_revoked_tokens(cursor)""").substitute().split("\n"),
            *([Template(r"""    cursor.execute('UPDATE _monl_refresh_tokens SET revoked_at = ? WHERE user_id = ?', (datetime.datetime.now(datetime.timezone.utc).timestamp(), payload.get('user_id')))""").substitute() ] if self.auth_features.get("refresh_tokens") else []),
            Template(r"""    conn.commit(); conn.close()""").substitute(),
            Template(r"""    return {'status': 'success', 'detail': 'Token revoked.'}
""").substitute(),
            *self._generate_auth_feature_routes(),
            Template(r"""# --- STRICT CRUD DATA VALIDATION (PYDANTIC) ---""").substitute()
        ])
        return self._verification_registration_flow(api_lines)

    # BRICK B4 (D3–D5): the account's token version travels in the JWT; without
    # a B4 option, none of these lines is emitted (historical output
    # byte-identical).
    def _colonne_version(self):
        return ", token_version" if self.auth_features else ""

    def _lookup_avec_version(self, lookup_lines, auth_checks):
        if not self.auth_features or auth_checks:
            return lookup_lines
        return [line.replace('anon_handle FROM', 'anon_handle, token_version FROM')
                .replace('anon_handle = row', 'anon_handle, token_version = row')
                for line in lookup_lines]

    def _ligne_version_du_jeton(self):
        return [Template(r"""    payload['token_version'] = token_version""").substitute()] if self.auth_features else []
