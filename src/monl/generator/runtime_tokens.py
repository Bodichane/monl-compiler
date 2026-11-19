"""The token, and the form of the account identifier.

POINT 95: the substance is not validation, it is NORMALIZATION — without a
canonical form, uniqueness can be bypassed by changing a capital letter.
It applies in THREE places: `/register`, `/login` and `manage.py`, the
third being the one people forget. The field stays named `username` ON THE
WIRE: it is the CONTRACT that says what it must contain."""

from string import Template


class JetonsRuntimeMixin:
    """The token, and the form of the account identifier."""

    def _socle_jetons(self):
        """Expected schema, demo dataset, uniqueness, and token reading."""
        return [
            *Template(r"""# ADDED (long-term roadmap, lossless migrations): expected column
# schema per table (excluding 'id'), consumed by init_db() to apply the
# missing ALTER TABLE ADD COLUMN at startup. Injected through repr()
# for a Python literal that is always valid, whatever the column names.""").substitute().split("\n"),
            Template(r"""_EXPECTED_COLUMNS = ${expected_columns}
""").substitute(expected_columns=repr(self._compute_expected_columns())),
            Template(r"""_MIGRATIONS = ${migrations}
""").substitute(migrations=repr(self._compute_migrations())),
            *Template(r"""# ADDED (frontend roadmap, 'seed' block): demo data grouped by table,
# injected through repr() for an always-valid literal. Consumed by
# init_db() (idempotent insertion when empty).""").substitute().split("\n"),
            Template(r"""_SEED_DATA = ${seed_data}
""").substitute(seed_data=repr(self._compute_seed_data())),
            # POINT 85: 'rule Entity.field unique' produced NOTHING — two rows
            # with the same value were accepted (checked against a real
            # server). An INDEX rather than a column constraint, for a decisive
            # reason: SQLite cannot add UNIQUE to an existing column, whereas
            # CREATE UNIQUE INDEX IF NOT EXISTS applies to an already populated
            # table and stays idempotent. The additive migration promise (point
            # 32) is therefore kept.
            Template(r"""_UNIQUE_INDEXES = ${unique_indexes}
""").substitute(unique_indexes=repr(self._compute_unique_indexes())),
            Template(r"""# Lookup indexes for foreign keys and filterable fields,
""").substitute(),
            Template(r"""# created at startup so databases already in service catch up too.
""").substitute(),
            Template(r"""_LOOKUP_INDEXES = ${lookup_indexes}
""").substitute(lookup_indexes=repr(self._compute_lookup_indexes())),
            Template(r"""# Multi-column business uniqueness (e.g. one vote per account and entry).
""").substitute(),
            Template(r"""_ONCE_PER_INDEXES = ${once_per_indexes}
""").substitute(once_per_indexes=repr(self._compute_once_per_indexes())),
            # POINT 89: the timestamped columns, so that startup can SAY how
            # many records will never have a date. See the migration block: it
            # is the only case in the compiler where an added column cannot be
            # caught up.
            Template(r"""_TIMESTAMP_COLUMNS = ${timestamp_columns}
""").substitute(timestamp_columns=repr(self._compute_timestamp_columns())),
            Template(r"""_POSTPAYMENT_ENUM_COLUMNS = ${postpayment_enumerated_columns}
""").substitute(postpayment_enumerated_columns=repr(self._compute_postpayment_enumerated_columns())),
            Template(r"""_NUMBERED_COLUMNS = ${numbered_columns}
""").substitute(numbered_columns=repr(self._compute_numbered_columns())),
            Template(r"""security_bearer = HTTPBearer()
""").substitute(),
            # FIX (roadmap, token revocation): token verification is
            # centralized in a single function, called by the two dependencies
            # below — before, each decoded the token on its own, which could
            # have let a future change forget the revocation check in one of
            # the two.
            *Template(r"""# FIX (beta 3): purge revoked tokens that have already expired — their
# signature is no longer accepted anyway, keeping them only bloated the
# table read on every authenticated request.
def _purge_revoked_tokens(cursor):
    cursor.execute('DELETE FROM _monl_revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?',""").substitute().split("\n"),
            Template(r"""                   (datetime.datetime.now(datetime.timezone.utc).timestamp(),))
""").substitute(),
            *Template(r"""def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    jti = payload.get('jti')
    if jti:
        conn = _connect(); cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM _monl_revoked_tokens WHERE jti = ?', (jti,))
        revoked = cursor.fetchone(); conn.close()
        if revoked:
            raise HTTPException(status_code=401, detail='This token has been revoked (signed out).')""").substitute().split("\n"),
            *([
                *Template(r"""    conn = _connect()
    try:
        row = conn.execute('SELECT token_version FROM _monl_users WHERE id = ?', (payload.get('user_id'),)).fetchone()
    finally:
        conn.close()
    if not row or payload.get('token_version', 0) != row[0]:
        raise HTTPException(status_code=401, detail='Session invalidated: sign in again.')""").substitute().split("\n"),
            ] if self.auth_features else []),
            Template(r"""    return payload
""").substitute(),

            # A single strict FastAPI dependency carries decoding and the
            # revocation check. The three consumers share its callable
            # identity, so FastAPI caches it once per request.
            # `get_optional_identity`, emitted separately for public routes,
            # stays deliberately distinct: it returns `{}` instead of 401 for a
            # missing, invalid or revoked token.
            Template(r"""def _identite_du_jeton(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> dict:""").substitute(),
            Template(r"""    return _decode_and_verify_token(credentials)
""").substitute(),

            Template(r"""def verify_jwt_and_get_actor(payload: dict = Depends(_identite_du_jeton)) -> str:""").substitute(),
            Template(r"""    return payload.get('actor')
""").substitute(),

            # ADDED (post-v6, roadmap): a separate dependency to fetch the
            # numeric identity (user_id) carried by the token, used by
            # ownership access control ('ownedBy') and by automatically filling
            # foreign key columns when a record is created.
            Template(r"""def get_current_user_id(payload: dict = Depends(_identite_du_jeton)) -> int:""").substitute(),
            Template(r"""    return payload.get('user_id', 0)
""").substitute(),

            # ADDED (roadmap, capability ecosystem -- follow-up to brick 1): a
            # separate dependency to fetch the current account's stable
            # anonymous pseudonym, used by 'generated' fields -- already
            # carried by the JWT since /login (see below), so no extra DB query
            # on every call.
            Template(r"""def get_current_anon_handle(payload: dict = Depends(_identite_du_jeton)) -> str:""").substitute(),
            Template(r"""    return payload.get('anon_handle', '')
""").substitute(),
        ]

    def _generate_identifier_helpers(self):
        """Normalization + form check of the account identifier (95).

        Emitted EVEN without a declaration: the function then exists and returns
        the value unchanged. One code path in the generated app.py is better than
        two, one of which is never exercised — and `/register`, `/login` and
        `manage.py` MUST agree, otherwise we create accounts nobody can log into."""
        formes = self.auth_identifier or []
        return [
            Template(r"""AUTH_IDENTIFIER_FORMS = ${formes}""").substitute(formes=repr(formes)),
            Template(r"""AUTH_PHONE_PREFIX = ${auth_phone_prefix}""").substitute(auth_phone_prefix=repr(self.auth_phone_prefix)),
            # A NATIONAL number ('06 12 34 56 78') designates the same line as
            # its international form — but only if we know which country.
            # Declared, we canonicalize; otherwise we leave it as is, and the
            # two notations remain two accounts (a stated limit, not a guess).
            #
            # POINT 138: the leading `0` is NOT universal. The original rule
            # only canonicalized a number starting with zero — a European trunk
            # prefix ('06…' → '+336…'). In Benin, where the local number is
            # written without a leading zero, `phone_prefix: "+229"` produced
            # NOTHING: the person registered as '97…' was not recognized as
            # '+22997…', exactly the two accounts the calling code exists to
            # prevent. A declared rule that produces nothing is what point 85
            # refuses.
            #
            # A number already international but typed without the '+':
            # prefixing it a second time ('+229' + '229…') would make a third
            # account.
            #
            # Email pattern identical to the `Email` type's (point 91): two
            # different patterns for the same thing would eventually diverge.
            # Deliberately broad: optional calling code, usual separators, 6 to
            # 15 digits (E.164 caps at 15). monl checks the FORM; it cannot
            # attest that a line exists — that would need an outgoing call,
            # which the compiler forbids itself everywhere except at the
            # payment provider (same limit as point 91 for email).
            *Template(r'''
def _normalize_identifier(valeur: str) -> str:
    """Canonical form of the identifier: it is what gets STORED and
    what uniqueness applies to."""
    valeur = (valeur or '').strip()
    if not AUTH_IDENTIFIER_FORMS:
        return valeur
    if '@' in valeur:
        # Only the domain is officially case-insensitive, but no real
        # provider distinguishes the local part: not lowering it would
        # allow two accounts for one mailbox, which uniqueness is meant
        # to prevent.
        return valeur.lower()
    if _RE_PHONE.match(valeur):
        # A number is typed with spaces, dots, dashes or parentheses —
        # never the same way twice.
        chiffres = ''.join(c for c in valeur if c.isdigit())
        if valeur.lstrip().startswith('+'):
            return '+' + chiffres
        if AUTH_PHONE_PREFIX:
            if chiffres.startswith('0'):
                return AUTH_PHONE_PREFIX + chiffres[1:]
            if chiffres.startswith(AUTH_PHONE_PREFIX.lstrip('+')):
                return '+' + chiffres
            return AUTH_PHONE_PREFIX + chiffres
        return chiffres
    return valeur

_RE_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$$')
_RE_PHONE = re.compile(r'^\+?[0-9][0-9 .\-()]{4,20}$$')

def _forme_valide(valeur: str) -> bool:
    """Pure predicate: used by the '/register' refusal AND by the startup
    count of older accounts. Two implementations of "is this an address?"
    would end up saying different things."""
    if not AUTH_IDENTIFIER_FORMS or 'libre' in AUTH_IDENTIFIER_FORMS:
        return True
    if 'email' in AUTH_IDENTIFIER_FORMS and _RE_EMAIL.match(valeur):
        return True
    if 'phone' in AUTH_IDENTIFIER_FORMS and _RE_PHONE.match(valeur):
        return 6 <= sum(c.isdigit() for c in valeur) <= 15
    return False

def _conflit_identifiant() -> str:
    if AUTH_IDENTIFIER_FORMS == ['email']:
        return 'This email address is already in use.'
    if AUTH_IDENTIFIER_FORMS == ['phone']:
        return 'This phone number is already in use.'
    if AUTH_IDENTIFIER_FORMS and 'libre' not in AUTH_IDENTIFIER_FORMS:
        return 'This identifier is already in use.'
    return "This username already exists."

def _check_identifier(valeur: str) -> None:
    if not _forme_valide(valeur):
        _attendu = {'email': 'an email address',
                    'phone': 'a phone number'}
        _libelle = ' or '.join(_attendu[f] for f in AUTH_IDENTIFIER_FORMS
                               if f in _attendu)
        raise HTTPException(status_code=422, detail=(
            f"The account identifier must be {_libelle}."))
''').substitute().split("\n"),
        ]
