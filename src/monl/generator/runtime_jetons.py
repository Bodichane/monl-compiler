"""Le jeton, et la forme de l'identifiant de compte.

POINT 95 : la substance n'est pas la validation, c'est la NORMALISATION —
sans forme canonique, l'unicité se contourne en changeant une majuscule.
Elle s'applique aux TROIS endroits : `/register`, `/login` et `manage.py`,
le troisième étant celui qu'on oublie. Le champ reste nommé `username` SUR
LE FIL : c'est le CONTRAT qui dit ce qu'il doit contenir."""

from string import Template


class JetonsRuntimeMixin:
    """Le jeton, et la forme de l'identifiant de compte."""

    def _socle_jetons(self):
        """Schéma attendu, jeu de démonstration, unicités, et lecture du jeton."""
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
            # POINT 85 : 'rule Entite.champ unique' ne produisait RIEN — deux
            # lignes de même valeur étaient acceptées (vérifié contre un vrai
            # serveur). Un INDEX plutôt qu'une contrainte de colonne, pour une
            # raison qui commande : SQLite ne sait pas ajouter UNIQUE à une
            # colonne existante, alors que CREATE UNIQUE INDEX IF NOT EXISTS
            # s'applique à une table déjà peuplée et reste idempotent. La
            # promesse de migration additive (point 32) est donc tenue.
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
            # POINT 89 : les colonnes horodatées, pour que le démarrage puisse
            # DIRE combien d'enregistrements n'auront jamais de date. Voir le
            # bloc de migration : c'est le seul cas du compilateur où une
            # colonne ajoutée ne peut pas être rattrapée.
            Template(r"""_TIMESTAMP_COLUMNS = ${timestamp_columns}
""").substitute(timestamp_columns=repr(self._compute_timestamp_columns())),
            Template(r"""_POSTPAYMENT_ENUM_COLUMNS = ${postpayment_enumerated_columns}
""").substitute(postpayment_enumerated_columns=repr(self._compute_postpayment_enumerated_columns())),
            Template(r"""_NUMBERED_COLUMNS = ${numbered_columns}
""").substitute(numbered_columns=repr(self._compute_numbered_columns())),
            Template(r"""security_bearer = HTTPBearer()
""").substitute(),
            # CORRECTIF (roadmap, révocation de token) : la vérification du
            # token est centralisée dans une seule fonction, appelée par les
            # deux dépendances ci-dessous — avant, chacune redécodait le token
            # indépendamment, ce qui aurait pu faire oublier la vérification
            # de révocation dans l'une des deux lors d'une future modification.
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

            # Une seule dépendance FastAPI stricte porte le décodage et le
            # contrôle de révocation. Les trois consommateurs partagent son
            # identité de callable, donc FastAPI la met en cache une fois par
            # requête. `get_optional_identity`, émise séparément pour les
            # routes publiques, reste volontairement distincte : elle rend
            # `{}` au lieu de 401 pour un jeton absent, invalide ou révoqué.
            Template(r"""def _identite_du_jeton(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> dict:""").substitute(),
            Template(r"""    return _decode_and_verify_token(credentials)
""").substitute(),

            Template(r"""def verify_jwt_and_get_actor(payload: dict = Depends(_identite_du_jeton)) -> str:""").substitute(),
            Template(r"""    return payload.get('actor')
""").substitute(),

            # AJOUT (post-v6, roadmap) : dépendance séparée pour récupérer l'identité
            # numérique (user_id) portée par le token, utilisée par le contrôle
            # d'accès par propriété ('ownedBy') et par le peuplement automatique
            # des colonnes de clé étrangère à la création d'un enregistrement.
            Template(r"""def get_current_user_id(payload: dict = Depends(_identite_du_jeton)) -> int:""").substitute(),
            Template(r"""    return payload.get('user_id', 0)
""").substitute(),

            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # dépendance séparée pour récupérer le pseudonyme anonyme stable
            # du compte courant, utilisée par les champs 'generated' -- déjà
            # porté par le JWT depuis /login (voir plus bas), pas besoin
            # d'une requête DB supplémentaire à chaque appel.
            Template(r"""def get_current_anon_handle(payload: dict = Depends(_identite_du_jeton)) -> str:""").substitute(),
            Template(r"""    return payload.get('anon_handle', '')
""").substitute(),
        ]

    def _generate_identifier_helpers(self):
        """Normalisation + contrôle de forme de l'identifiant de compte (95).

        Émis MÊME sans déclaration : la fonction existe alors et rend la valeur
        inchangée. Un seul chemin de code dans le app.py généré vaut mieux que
        deux, dont un jamais exercé — et `/register`, `/login` et `manage.py`
        DOIVENT s'accorder, sinon on crée des comptes auxquels on ne peut pas
        se connecter."""
        formes = self.auth_identifier or []
        return [
            Template(r"""AUTH_IDENTIFIER_FORMS = ${formes}""").substitute(formes=repr(formes)),
            Template(r"""AUTH_PHONE_PREFIX = ${auth_phone_prefix}""").substitute(auth_phone_prefix=repr(self.auth_phone_prefix)),
            # Un numéro NATIONAL ('06 12 34 56 78') désigne la même ligne que sa
            # forme internationale — mais seulement si l'on sait de quel pays.
            # Déclaré, on canonicalise ; sinon on laisse tel quel, et les deux
            # notations restent deux comptes (limite énoncée, pas devinée).
            # POINT 138 : le `0` initial n'est PAS universel. La règle d'origine
            # ne canonicalisait qu'un numéro commençant par zéro — un préfixe
            # interurbain européen ('06…' → '+336…'). Au Bénin, où le numéro
            # local s'écrit sans zéro de tête, `phone_prefix: "+229"` ne
            # produisait RIEN : la personne inscrite en '97…' ne se
            # reconnaissait pas en '+22997…', soit exactement les deux comptes
            # que l'indicatif existe pour empêcher. Une règle déclarée qui ne
            # produit rien est ce que le point 85 refuse.
            # Numéro déjà international mais tapé sans le '+' : le préfixer une
            # seconde fois ('+229' + '229…') fabriquerait un troisième compte.
            # Motif d'e-mail identique à celui du type `Email` (point 91) : deux
            # motifs différents pour la même chose finiraient par diverger.
            # Volontairement large : indicatif optionnel, séparateurs usuels,
            # 6 à 15 chiffres (E.164 plafonne à 15). monl vérifie la FORME ; il
            # ne peut pas attester qu'une ligne existe — cela demanderait un
            # appel sortant, que le compilateur s'interdit partout ailleurs que
            # chez le prestataire de paiement (même limite qu'au point 91 pour
            # l'e-mail).
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
