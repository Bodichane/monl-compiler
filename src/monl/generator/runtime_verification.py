"""Confirmation de l'adresse à l'inscription en ligne, opt-in (point 209).

Le transport reste celui de password_reset : même configuration, même thread
après commit, une panne n'est jamais une erreur de la route.
"""


class VerificationRuntimeMixin:
    """Émission conditionnelle ; aucun changement pour les specs historiques."""

    def _verification_sender_lines(self, lines):
        replacements = {
            'def _send_password_reset(user_id, raw_token):':
                "def _send_password_reset(user_id, raw_token, purpose='password_reset'):",
            "        body = 'Voici votre jeton de réinitialisation : ' + raw_token":
                "        body = ('Confirmez votre adresse e-mail avec ce jeton : ' if purpose == 'verify_email' else 'Voici votre jeton de réinitialisation : ') + raw_token",
            "        message['Subject'] = 'Réinitialisation de votre mot de passe'":
                "        message['Subject'] = 'Confirmation de votre adresse e-mail' if purpose == 'verify_email' else 'Réinitialisation de votre mot de passe'",
        }
        return [replacements.get(line, line) for line in lines]

    def _verification_sql_lines(self):
        if not self.auth_features.get('verify_email'):
            return []
        return '''CREATE TABLE IF NOT EXISTS _monl_verify_email_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL,
    used_at DOUBLE PRECISION,
    FOREIGN KEY (user_id) REFERENCES _monl_users(id)
);
CREATE INDEX IF NOT EXISTS idx_verify_email_user ON _monl_verify_email_tokens (user_id);

CREATE TABLE IF NOT EXISTS _monl_verify_email_resends (
    identifier_hash VARCHAR(64) NOT NULL,
    attempted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verify_resend ON _monl_verify_email_resends (identifier_hash, attempted_at);
'''.splitlines()

    def _verification_migration_lines(self):
        if not self.auth_features.get('verify_email'):
            return []
        return ['            ' + line for line in '''if 'email_verified' not in _table_columns(_sys_cur, '_monl_users'):
    _historical = conn.execute('SELECT COUNT(*) FROM _monl_users').fetchone()[0]
    _sys_cur.execute('ALTER TABLE _monl_users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1')
    conn.commit()
    print(f'ℹ️ {_historical} compte(s) antérieurs restent confirmés : aucune conversion des comptes existants.')
'''.splitlines()]

    def _lookup_avec_verification(self, lines):
        if not self.auth_features.get('verify_email'):
            return lines
        guard = self._verification_login_lines()
        result = []
        for line in lines:
            if line.startswith('    if totp_enabled'):
                result += guard
                guard = []
            result.append(line.replace(
                'if not hmac.compare_digest(_candidate_hash, stored_hash):',
                'if not row or not hmac.compare_digest(_candidate_hash, stored_hash):'))
        return result + guard

    def _verification_login_lines(self):
        if not self.auth_features.get('verify_email'):
            return []
        return '''    _verify_conn = _connect()
    try:
        _confirmed = _verify_conn.execute('SELECT email_verified FROM _monl_users WHERE id = ?', (db_user_id,)).fetchone()[0]
    finally:
        _verify_conn.close()
    if not _confirmed:
        raise HTTPException(status_code=403, detail={'code': 'email_not_verified', 'message': 'Confirmez votre adresse e-mail avant de vous connecter.'})
'''.splitlines()

    def _verification_register_lines(self):
        if not self.auth_features.get('verify_email'):
            return []
        return '''    cursor.execute('UPDATE _monl_users SET email_verified = 0 WHERE id = ?', (new_user_id,))
    verification_token = _issue_verification_token(cursor, new_user_id)
'''.splitlines()

    def _verification_register_return_lines(self):
        if not self.auth_features.get('verify_email'):
            return ["    return {'status': 'success', 'user_id': new_user_id}\n"]
        return '''    _dispatch_verification(new_user_id, verification_token)
    return {'status': 'pending', 'user_id': new_user_id, 'detail': 'Confirmez votre adresse e-mail avant de vous connecter.'}
'''.splitlines() + ['']

    def _generate_verification_helpers(self):
        features = self.auth_features
        return [
            f"VERIFY_EMAIL_TTL_SECONDS = {features['verify_email']}",
            f"VERIFY_RESEND_MAX = {features['verify_resend']['max_attempts']}",
            f"VERIFY_RESEND_WINDOW = {features['verify_resend']['window_seconds']}",
        ] + '''
def _issue_verification_token(cursor, user_id):
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    cursor.execute('UPDATE _monl_verify_email_tokens SET used_at = COALESCE(used_at, ?) WHERE user_id = ?', (now, user_id))
    cursor.execute('INSERT INTO _monl_verify_email_tokens (token_hash, user_id, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, NULL)', (token_hash, user_id, now, now + VERIFY_EMAIL_TTL_SECONDS))
    return raw_token

def _dispatch_verification(user_id, raw_token):
    threading.Thread(target=_send_password_reset, args=(user_id, raw_token, 'verify_email'), daemon=True, name='monl-password-reset').start()

def _verification_resend(identifier):
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    identifier_hash = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    conn = _connect(); conn.isolation_level = None; cursor = conn.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('DELETE FROM _monl_verify_email_resends WHERE attempted_at <= ?', (now - VERIFY_RESEND_WINDOW,))
        cursor.execute('SELECT COUNT(*) FROM _monl_verify_email_resends WHERE identifier_hash = ?', (identifier_hash,))
        recent = cursor.fetchone()[0]
        if recent >= VERIFY_RESEND_MAX:
            cursor.execute('COMMIT')
            return None
        cursor.execute('INSERT INTO _monl_verify_email_resends (identifier_hash, attempted_at) VALUES (?, ?)', (identifier_hash, now))
        cursor.execute('SELECT id FROM _monl_users WHERE username = ? AND email_verified = 0', (identifier,))
        row = cursor.fetchone()
        delivery = (row[0], _issue_verification_token(cursor, row[0])) if row else None
        cursor.execute('COMMIT')
        return delivery
    except Exception:
        cursor.execute('ROLLBACK')
        raise
    finally:
        conn.close()

'''.splitlines()

    def _generate_verification_routes(self):
        if not self.auth_features.get('verify_email'):
            return []
        return '''class VerifyEmailRequest(BaseModel):
    username: str
    token: str

class VerifyEmailResendRequest(BaseModel):
    username: str

@app.post('/verify-email/resend', tags=['Authentication'])
def verify_email_resend(req: VerifyEmailResendRequest):
    started = time.perf_counter()
    delivery = _verification_resend(_normalize_identifier(req.username))
    elapsed = time.perf_counter() - started
    if elapsed < PASSWORD_RESET_RESPONSE_FLOOR:
        time.sleep(PASSWORD_RESET_RESPONSE_FLOOR - elapsed)
    if delivery:
        _dispatch_verification(*delivery)
    return {'status': 'accepted', 'detail': 'Si le compte existe, un message a été envoyé.'}

@app.post('/verify-email', tags=['Authentication'])
def verify_email(req: VerifyEmailRequest):
    identifier = _normalize_identifier(req.username)
    token_hash = hashlib.sha256(req.token.encode('utf-8')).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    conn = _connect(); conn.isolation_level = None; cursor = conn.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('SELECT t.token_hash, t.user_id, u.username FROM _monl_verify_email_tokens t JOIN _monl_users u ON u.id = t.user_id WHERE t.token_hash = ?', (token_hash,))
        row = cursor.fetchone()
        fingerprint_ok = hmac.compare_digest(row[0], token_hash) if row else hmac.compare_digest(_DUMMY_RESET_HASH, token_hash)
        if not row or not fingerprint_ok or not hmac.compare_digest(row[2].encode('utf-8'), identifier.encode('utf-8')):
            raise HTTPException(status_code=400, detail='Jeton de confirmation invalide ou expiré.')
        cursor.execute('UPDATE _monl_verify_email_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?', (now, token_hash, now))
        if cursor.rowcount != 1:
            raise HTTPException(status_code=400, detail='Jeton de confirmation invalide ou expiré.')
        cursor.execute('UPDATE _monl_users SET email_verified = 1 WHERE id = ?', (row[1],))
        cursor.execute('COMMIT')
        return {'status': 'success', 'detail': 'Adresse e-mail confirmée.'}
    except Exception:
        cursor.execute('ROLLBACK')
        raise
    finally:
        conn.close()

'''.splitlines()
