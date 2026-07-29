"""Socle runtime de l'application générée : imports, secret JWT,
init_db/migrations/seed, inscription, connexion, révocation de jeton,
limitation de débit.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class RuntimeMixin:
    def _generate_runtime_lines(self):
        """Lignes de app.py jusqu'aux schémas Pydantic (incluses)."""
        actors_literal = ", ".join(f'"{a}"' for a in self.actors)
        self_register_literal = ", ".join(f'"{a}"' for a in self.self_register_actors)
        api_lines = [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            "from fastapi import FastAPI, HTTPException, Header, Depends, Request",
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
            "from pydantic import BaseModel, Field",
            "from typing import List, Optional, Any",
            "import sqlite3",
            "import jwt",
            "import datetime",
            "import hashlib",
            "import hmac",
            "import os",
            "import secrets",
            # BRIQUE PAIEMENT (point 74) : premier appel SORTANT du backend
            # généré. json/urllib ne servaient à rien tant que monl restait
            # hors-ligne ; encaisser change cela, et il faut le dire.
            "import json",
            "import urllib.parse",
            "import urllib.request",
            "import urllib.error",
            "import sandbox_ai  # Fonctions 'custom' écrites à la main (module isolé)\n",
            "from contextlib import asynccontextmanager\n",
            "DB_FILE = 'app.db'\n",
            # CORRECTIF (bêta 3) : toutes les connexions de requête passent par
            # ce helper. Il active l'intégrité référentielle (SQLite la désactive
            # par défaut : les clés étrangères déclarées dans schema.sql
            # n'étaient jamais vérifiées) et un délai d'attente sur verrou, pour
            # que deux écritures concurrentes patientent au lieu d'échouer
            # immédiatement en 'database is locked'.
            "def _connect():",
            "    conn = sqlite3.connect(DB_FILE, timeout=10.0)",
            "    conn.execute('PRAGMA foreign_keys = ON')",
            "    conn.execute('PRAGMA busy_timeout = 10000')",
            "    return conn\n",
            # CORRECTIF (bêta, hygiène de secret) : le secret JWT est lu en
            # priorité depuis la variable d'environnement MONL_JWT_SECRET
            # (recommandé en production — le secret ne touche jamais le disque
            # ni un dépôt), et retombe sinon sur le fichier '.jwt_secret'
            # généré à la compilation. Un projet peut ainsi être livré SANS
            # secret embarqué et se le voir injecter au déploiement.
            "JWT_SECRET = (os.environ.get('MONL_JWT_SECRET') or '').strip()",
            "if not JWT_SECRET:",
            "    try:",
            "        with open('.jwt_secret', 'r', encoding='utf-8') as _f:",
            "            JWT_SECRET = _f.read().strip()",
            "        if not JWT_SECRET:",
            "            raise ValueError('.jwt_secret est vide')",
            "    except (FileNotFoundError, ValueError) as _e:",
            "        raise RuntimeError(",
            "            \"Aucun secret JWT : définissez la variable d'environnement \"",
            "            \"MONL_JWT_SECRET, ou laissez le compilateur monl générer \"",
            "            \"'.jwt_secret' (relancez 'python3 src/main.py <spec.ml>' depuis la \"",
            "            \"racine du projet avant de démarrer le serveur).\"",
            "        ) from _e",
            "JWT_ALGORITHM = 'HS256'",
            f"VALID_ACTORS = [{actors_literal}]",
            # CORRECTIF (bêta 3, faille critique d'élévation de privilège) :
            # '/register' acceptait n'importe quel rôle déclaré, envoyé par le
            # client. Le rôle porté par le jeton provenait bien du compte réel,
            # mais ce compte se choisissait lui-même son rôle : s'inscrire
            # comme administrateur suffisait. Seuls les rôles marqués
            # 'selfRegister' dans la spec sont désormais ouverts à
            # l'inscription ; les autres sont provisionnés hors ligne
            # (manage.py). Liste vide = aucune inscription libre.
            f"SELF_REGISTER_ACTORS = [{self_register_literal}]",
            # CORRECTIF (bêta 3) : la durée de vie était écrite en dur (2 h)
            # alors que le contrat remis à l'IA frontend annonçait 1 h. Valeur
            # unique, réglable au déploiement, et publiée telle quelle dans le
            # contrat — une promesse de sécurité invérifiable ne vaut rien.
            "TOKEN_TTL_HOURS = int(os.environ.get('MONL_TOKEN_TTL_HOURS', '2'))\n",
            "# AJOUT (roadmap long terme, migrations sans perte de données) :",
            "# schéma de colonnes attendu par table (hors 'id'), consommé par",
            "# init_db() pour appliquer les ALTER TABLE ADD COLUMN manquants au",
            "# démarrage. Injecté via repr() pour un littéral Python toujours",
            "# valide, quel que soit le nom des colonnes.",
            f"_EXPECTED_COLUMNS = {self._compute_expected_columns()!r}\n",
            "# AJOUT (roadmap frontend, bloc 'seed') : données de démonstration",
            "# regroupées par table, injectées via repr() pour un littéral toujours",
            "# valide. Consommées par init_db() (insertion idempotente si vide).",
            f"_SEED_DATA = {self._compute_seed_data()!r}\n",
            "security_bearer = HTTPBearer()\n",
            # CORRECTIF (roadmap, révocation de token) : la vérification du
            # token est centralisée dans une seule fonction, appelée par les
            # deux dépendances ci-dessous — avant, chacune redécodait le token
            # indépendamment, ce qui aurait pu faire oublier la vérification
            # de révocation dans l'une des deux lors d'une future modification.
            "# CORRECTIF (bêta 3) : purge des jetons révoqués déjà expirés — leur",
            "# signature n'est plus acceptée de toute façon, les garder ne faisait",
            "# que gonfler la table consultée à chaque requête authentifiée.",
            "def _purge_revoked_tokens(cursor):",
            "    cursor.execute('DELETE FROM _monl_revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?',",
            "                   (datetime.datetime.now(datetime.timezone.utc).timestamp(),))\n",
            "def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:",
            "    try:",
            "        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "    except jwt.PyJWTError:",
            "        raise HTTPException(status_code=401, detail='Token invalide ou expiré')",
            "    jti = payload.get('jti')",
            "    if jti:",
            "        conn = _connect(); cursor = conn.cursor()",
            "        cursor.execute('SELECT 1 FROM _monl_revoked_tokens WHERE jti = ?', (jti,))",
            "        revoked = cursor.fetchone(); conn.close()",
            "        if revoked:",
            "            raise HTTPException(status_code=401, detail='Ce token a été révoqué (déconnexion effectuée).')",
            "    return payload\n",

            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    return _decode_and_verify_token(credentials).get('actor')\n",

            # AJOUT (post-v6, roadmap) : dépendance séparée pour récupérer l'identité
            # numérique (user_id) portée par le token, utilisée par le contrôle
            # d'accès par propriété ('ownedBy') et par le peuplement automatique
            # des colonnes de clé étrangère à la création d'un enregistrement.
            "def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:",
            "    return _decode_and_verify_token(credentials).get('user_id', 0)\n",

            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # dépendance séparée pour récupérer le pseudonyme anonyme stable
            # du compte courant, utilisée par les champs 'generated' -- déjà
            # porté par le JWT depuis /login (voir plus bas), pas besoin
            # d'une requête DB supplémentaire à chaque appel.
            "def get_current_anon_handle(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    return _decode_and_verify_token(credentials).get('anon_handle', '')\n",

            # CORRECTIF (bêta 3) : '@app.on_event' est déprécié par Starlette et
            # disparaîtra ; le cycle de vie passe par un gestionnaire 'lifespan'.
            # init_db() ouvre volontairement une connexion SANS contrainte de clé
            # étrangère : création du schéma, migrations additives et données de
            # démonstration doivent pouvoir s'exécuter dans n'importe quel ordre.
            "def init_db():",
            "    conn = sqlite3.connect(DB_FILE, timeout=10.0)",
            "    conn.execute('PRAGMA journal_mode = WAL')",
            "    try:",
            "        with open('schema.sql', 'r', encoding='utf-8') as f:",
            "            conn.executescript(f.read())",
            "    except Exception as e:",
            "        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')",
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
            "            _cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=?', (_table,))",
            "            if _cur.fetchone() is None:",
            "                continue  # table absente : le CREATE l'a déjà couverte, ou spec sans données",
            "            _cur.execute(f'PRAGMA table_info(\"{_table}\")')",
            "            _existing = {_row[1] for _row in _cur.fetchall()}",
            "            for _col, _sql_type in _cols:",
            "                if _col not in _existing:",
            "                    _cur.execute(f'ALTER TABLE \"{_table}\" ADD COLUMN \"{_col}\" {_sql_type}')",
            "                    print(f'🔧 Migration : colonne \"{_col}\" ajoutée à \"{_table}\" ({_sql_type}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Migration additive ignorée : {e}')",
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
            "            for _row in _rows:",
            "                _cols = list(_row.keys())",
            "                _placeholders = ', '.join(['?'] * len(_cols))",
            "                _colnames = ', '.join(f'\"{_c}\"' for _c in _cols)",
            "                _scur.execute(f'INSERT INTO \"{_table}\" ({_colnames}) VALUES ({_placeholders})', tuple(_row.values()))",
            "            if _rows:",
            "                print(f'🌱 Données de démonstration insérées dans \"{_table}\" ({len(_rows)}).')",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Données de démonstration ignorées : {e}')",
            "    # CORRECTIF (bêta 3) : migration de la table système des jetons",
            "    # révoqués (colonne 'expires_at' ajoutée en bêta 3), pour qu'une",
            "    # base créée par une version antérieure continue de fonctionner.",
            "    try:",
            "        _sys_cur = conn.cursor()",
            "        _sys_cur.execute('PRAGMA table_info(_monl_revoked_tokens)')",
            "        if 'expires_at' not in {_r[1] for _r in _sys_cur.fetchall()}:",
            "            _sys_cur.execute('ALTER TABLE _monl_revoked_tokens ADD COLUMN expires_at REAL')",
            "        _purge_revoked_tokens(_sys_cur)",
            "        conn.commit()",
            "    except Exception as e:",
            "        print(f'⚠️ Migration système ignorée : {e}')",
            "    finally:",
            "        conn.close()\n",

            "@asynccontextmanager",
            "async def _lifespan(_app: FastAPI):",
            "    init_db()",
            "    yield\n",
            # CORRECTIF (bêta 3) : '/docs' et '/openapi.json' publiaient la
            # surface complète de l'API en toutes circonstances. Indispensable
            # en développement, rarement souhaitable en déploiement :
            # MONL_DOCS=off les désactive sans toucher au code généré.
            "_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'",
            f"app = FastAPI(title='{self.app_name} - Secure Core', lifespan=_lifespan,",
            "               docs_url='/docs' if _docs_actives else None,",
            "               redoc_url='/redoc' if _docs_actives else None,",
            "               openapi_url='/openapi.json' if _docs_actives else None)\n",

            # Redirection de la racine vers la documentation Swagger/OpenAPI
            # auto-générée par FastAPI — le seul front que monl fournit
            # encore (pivot, point 41) : l'interface réelle vient de l'IA
            # frontend, servie sur '/site' par 'monl run' (wrapper serve.py).
            "from fastapi.responses import RedirectResponse\n",
            "@app.get('/', include_in_schema=False)",
            "async def root():",
            "    return RedirectResponse(url='/docs')\n",
        ]

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
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('SELECT id FROM _monl_users WHERE username = ?', (req.username,))",
            "    if cursor.fetchone():",
            "        conn.close()",
            "        raise HTTPException(status_code=409, detail=\"Ce nom d'utilisateur existe déjà.\")",
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
            "    cursor.execute('INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) VALUES (?, ?, ?, ?, ?)',",
            "                   (req.username, pwd_hash, salt_hex, req.actor, anon_handle))",
            "    conn.commit(); new_user_id = cursor.lastrowid; conn.close()",
            "    return {'status': 'success', 'user_id': new_user_id}\n",

            "class LoginRequest(BaseModel):",
            "    username: str",
            "    password: str\n",

            "@app.post('/login', tags=['Authentication'])",
            "def login(req: LoginRequest, request: Request):",
            "    _check_rate_limit('login', _client_ip(request))",
            "    conn = _connect(); cursor = conn.cursor()",
            "    cursor.execute('SELECT id, password_hash, salt, actor, anon_handle FROM _monl_users WHERE username = ?', (req.username,))",
            "    row = cursor.fetchone(); conn.close()",
            "    if not row:",
            "        hmac.compare_digest(_hash_password(req.password[:256], _DUMMY_SALT_HEX), _DUMMY_HASH)",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    db_user_id, stored_hash, salt_hex, actor, anon_handle = row",
            "    if not hmac.compare_digest(_hash_password(req.password, salt_hex), stored_hash):",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    payload = {",
            "        'sub': req.username,",
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
            "        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS)",
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            "    return {'access_token': token, 'token_type': 'bearer'}\n",

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
            "    cursor.execute('INSERT OR IGNORE INTO _monl_revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)',",
            "                   (jti, datetime.datetime.now(datetime.timezone.utc).isoformat(), payload.get('exp')))",
            "    _purge_revoked_tokens(cursor)",
            "    conn.commit(); conn.close()",
            "    return {'status': 'success', 'detail': 'Token révoqué.'}\n",
            "# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---"
        ]
        return api_lines
