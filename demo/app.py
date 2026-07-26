# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Any
import sqlite3
import jwt
import datetime
import hashlib
import hmac
import os
import secrets
import sandbox_ai  # Fonctions 'custom' écrites à la main (module isolé)

from contextlib import asynccontextmanager

DB_FILE = 'app.db'

def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 10000')
    return conn

JWT_SECRET = (os.environ.get('MONL_JWT_SECRET') or '').strip()
if not JWT_SECRET:
    try:
        with open('.jwt_secret', 'r', encoding='utf-8') as _f:
            JWT_SECRET = _f.read().strip()
        if not JWT_SECRET:
            raise ValueError('.jwt_secret est vide')
    except (FileNotFoundError, ValueError) as _e:
        raise RuntimeError(
            "Aucun secret JWT : définissez la variable d'environnement "
            "MONL_JWT_SECRET, ou laissez le compilateur monl générer "
            "'.jwt_secret' (relancez 'python3 src/main.py <spec.ml>' depuis la "
            "racine du projet avant de démarrer le serveur)."
        ) from _e
JWT_ALGORITHM = 'HS256'
VALID_ACTORS = ["Admin", "Customer"]
SELF_REGISTER_ACTORS = ["Customer"]
TOKEN_TTL_HOURS = int(os.environ.get('MONL_TOKEN_TTL_HOURS', '2'))

# AJOUT (roadmap long terme, migrations sans perte de données) :
# schéma de colonnes attendu par table (hors 'id'), consommé par
# init_db() pour appliquer les ALTER TABLE ADD COLUMN manquants au
# démarrage. Injecté via repr() pour un littéral Python toujours
# valide, quel que soit le nom des colonnes.
_EXPECTED_COLUMNS = {'product': [('name', 'VARCHAR(255)'), ('price', 'NUMERIC(10, 2)'), ('description', 'TEXT'), ('imageUrl', 'VARCHAR(255)'), ('category', 'VARCHAR(255)'), ('stock', 'INTEGER')], 'order': [('total', 'NUMERIC(10, 2)'), ('status', 'VARCHAR(255)'), ('note', 'TEXT'), ('customer_id', 'INTEGER')], 'customer': [('displayName', 'VARCHAR(255)')]}

# AJOUT (roadmap frontend, bloc 'seed') : données de démonstration
# regroupées par table, injectées via repr() pour un littéral toujours
# valide. Consommées par init_db() (insertion idempotente si vide).
_SEED_DATA = {'product': [{'name': 'Casque urbain Vent', 'price': 74.0, 'description': 'Coque in-mold, aération 18 canaux, taille réglable 54-60 cm.', 'imageUrl': 'diagrammes/casque.svg', 'category': 'Sécurité', 'stock': 12}, {'name': 'Éclairage Nuit 600', 'price': 45.0, 'description': 'Phare avant 600 lumens, autonomie 12 h, fixation sans outil.', 'imageUrl': 'diagrammes/eclairage.svg', 'category': 'Sécurité', 'stock': 26}, {'name': 'Chaîne 11 vitesses', 'price': 32.5, 'description': '116 maillons, traitement anticorrosion, attache rapide fournie.', 'imageUrl': 'diagrammes/chaine.svg', 'category': 'Transmission', 'stock': 40}, {'name': 'Plateau 50 dents', 'price': 58.0, 'description': 'Aluminium usiné, entraxe 110 mm, compatible double plateau.', 'imageUrl': 'diagrammes/plateau.svg', 'category': 'Transmission', 'stock': 7}, {'name': 'Pneu Pavé 700x32', 'price': 39.9, 'description': 'Gomme renforcée, bande antiperforation, flancs réfléchissants.', 'imageUrl': 'diagrammes/pneu.svg', 'category': 'Roues', 'stock': 34}, {'name': 'Sacoche Atelier 14 L', 'price': 89.0, 'description': 'Toile enduite, fixation porte-bagages, poche à outils intérieure.', 'imageUrl': 'diagrammes/sacoche.svg', 'category': 'Bagagerie', 'stock': 9}, {'name': 'Kit outils Multi-8', 'price': 24.0, 'description': "Huit embouts, corps acier, étui coton — l'essentiel en poche.", 'imageUrl': 'diagrammes/outils.svg', 'category': 'Atelier', 'stock': 55}, {'name': 'Révision complète', 'price': 95.0, 'description': 'Prestation atelier : transmission, freins, roues, réglages, 48 h.', 'imageUrl': 'diagrammes/revision.svg', 'category': 'Atelier', 'stock': 20}]}

security_bearer = HTTPBearer()

# CORRECTIF (bêta 3) : purge des jetons révoqués déjà expirés — leur
# signature n'est plus acceptée de toute façon, les garder ne faisait
# que gonfler la table consultée à chaque requête authentifiée.
def _purge_revoked_tokens(cursor):
    cursor.execute('DELETE FROM _monl_revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?',
                   (datetime.datetime.now(datetime.timezone.utc).timestamp(),))

def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='Token invalide ou expiré')
    jti = payload.get('jti')
    if jti:
        conn = _connect(); cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM _monl_revoked_tokens WHERE jti = ?', (jti,))
        revoked = cursor.fetchone(); conn.close()
        if revoked:
            raise HTTPException(status_code=401, detail='Ce token a été révoqué (déconnexion effectuée).')
    return payload

def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:
    return _decode_and_verify_token(credentials).get('actor')

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:
    return _decode_and_verify_token(credentials).get('user_id', 0)

def get_current_anon_handle(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:
    return _decode_and_verify_token(credentials).get('anon_handle', '')

def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.execute('PRAGMA journal_mode = WAL')
    try:
        with open('schema.sql', 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
    except Exception as e:
        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')
    # AJOUT (roadmap long terme, migrations sans perte de données) :
    # après le CREATE TABLE IF NOT EXISTS (qui ne modifie jamais une
    # table déjà présente), on rattrape les colonnes ajoutées à la
    # spec depuis la dernière compilation. Pour chaque table, on
    # compare les colonnes attendues aux colonnes réelles
    # (PRAGMA table_info) et on ajoute les manquantes par ALTER TABLE
    # ADD COLUMN — opération purement additive : aucune donnée
    # existante n'est lue, déplacée ou supprimée. Les colonnes
    # retirées de la spec sont laissées en place (SQLite ne supporte
    # pas DROP COLUMN sans reconstruction, et les supprimer
    # détruirait des données — voir docs/MIGRATIONS.md).
    try:
        _cur = conn.cursor()
        for _table, _cols in _EXPECTED_COLUMNS.items():
            _cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?', (_table,))
            if _cur.fetchone() is None:
                continue  # table absente : le CREATE l'a déjà couverte, ou spec sans données
            _cur.execute(f'PRAGMA table_info("{_table}")')
            _existing = {_row[1] for _row in _cur.fetchall()}
            for _col, _sql_type in _cols:
                if _col not in _existing:
                    _cur.execute(f'ALTER TABLE "{_table}" ADD COLUMN "{_col}" {_sql_type}')
                    print(f'🔧 Migration : colonne "{_col}" ajoutée à "{_table}" ({_sql_type}).')
        conn.commit()
    except Exception as e:
        print(f'⚠️ Migration additive ignorée : {e}')
    # AJOUT (roadmap frontend, bloc 'seed') : insertion des données de
    # démonstration si (et seulement si) la table est VIDE — idempotent,
    # donc un redémarrage n'empile pas les doublons, et des données
    # réelles créées par l'utilisateur ne sont jamais écrasées.
    try:
        _scur = conn.cursor()
        for _table, _rows in _SEED_DATA.items():
            _scur.execute(f'SELECT COUNT(*) FROM "{_table}"')
            if _scur.fetchone()[0] > 0:
                continue  # déjà des données : on ne touche à rien
            for _row in _rows:
                _cols = list(_row.keys())
                _placeholders = ', '.join(['?'] * len(_cols))
                _colnames = ', '.join(f'"{_c}"' for _c in _cols)
                _scur.execute(f'INSERT INTO "{_table}" ({_colnames}) VALUES ({_placeholders})', tuple(_row.values()))
            if _rows:
                print(f'🌱 Données de démonstration insérées dans "{_table}" ({len(_rows)}).')
        conn.commit()
    except Exception as e:
        print(f'⚠️ Données de démonstration ignorées : {e}')
    # CORRECTIF (bêta 3) : migration de la table système des jetons
    # révoqués (colonne 'expires_at' ajoutée en bêta 3), pour qu'une
    # base créée par une version antérieure continue de fonctionner.
    try:
        _sys_cur = conn.cursor()
        _sys_cur.execute('PRAGMA table_info(_monl_revoked_tokens)')
        if 'expires_at' not in {_r[1] for _r in _sys_cur.fetchall()}:
            _sys_cur.execute('ALTER TABLE _monl_revoked_tokens ADD COLUMN expires_at REAL')
        _purge_revoked_tokens(_sys_cur)
        conn.commit()
    except Exception as e:
        print(f'⚠️ Migration système ignorée : {e}')
    finally:
        conn.close()

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield

_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'
app = FastAPI(title='AtelierVelo - Secure Core', lifespan=_lifespan,
               docs_url='/docs' if _docs_actives else None,
               redoc_url='/redoc' if _docs_actives else None,
               openapi_url='/openapi.json' if _docs_actives else None)

from fastapi.responses import RedirectResponse

@app.get('/', include_in_schema=False)
async def root():
    return RedirectResponse(url='/docs')

class RegisterRequest(BaseModel):
    username: str
    password: str
    actor: str

def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()

# CORRECTIF (bêta 3, énumération de comptes par canal temporel) :
# '/login' renvoyait 401 immédiatement quand le compte n'existait pas,
# sans dérouler les 100 000 itérations PBKDF2 — l'écart de temps de
# réponse (~100 ms) révélait quels noms d'utilisateur existent.
# On hache donc toujours, contre ce sel factice fixe le cas échéant.
_DUMMY_SALT_HEX = '6d6f6e6c2d64756d6d792d73616c742d'
_DUMMY_HASH = _hash_password('monl-dummy-password', _DUMMY_SALT_HEX)

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_ATTEMPTS = 5

# AJOUT (bêta, déploiement derrière un proxy) : par défaut on utilise
# l'IP de la connexion directe (request.client.host). Si l'application
# tourne derrière un reverse proxy de confiance (nginx, Traefik...),
# activer MONL_TRUST_PROXY=1 fait lire la première IP de l'en-tête
# X-Forwarded-For — sinon un client direct pourrait usurper cet en-tête
# pour contourner la limitation de débit. On ne fait donc confiance à
# l'en-tête QUE si l'opérateur l'a explicitement autorisé.
_TRUST_PROXY = os.environ.get('MONL_TRUST_PROXY', '').lower() in ('1', 'true', 'yes')
def _client_ip(request: Request) -> str:
    if _TRUST_PROXY:
        fwd = request.headers.get('x-forwarded-for')
        if fwd:
            return fwd.split(',')[0].strip() or 'unknown'
    return request.client.host if request.client else 'unknown'

# AJOUT (roadmap long terme, rate limiting multi-workers) : compteur
# de tentatives persisté en base plutôt qu'en mémoire de processus,
# pour que le quota soit partagé par tous les workers uvicorn/gunicorn
# (voir _monl_rate_limit dans schema.sql). Fenêtre glissante :
# on compte les tentatives récentes, on purge les anciennes, puis on
# enregistre la tentative courante.
# CORRECTIF (bêta 3, TOCTOU) : le comptage et l'enregistrement de la
# tentative se faisaient en deux exécutions autocommit distinctes —
# N requêtes parallèles lisaient toutes le même compteur avant que
# l'une d'elles ne l'incrémente, et passaient donc toutes le quota.
# Le tout est désormais dans une transaction en écriture immédiate :
# SQLite sérialise les writers, le quota redevient exact, y compris
# entre workers puisqu'il est persisté en base.
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
            raise HTTPException(status_code=429, detail=f'Trop de tentatives ({bucket}). Réessayez dans {RATE_LIMIT_WINDOW_SECONDS} secondes.')
        cursor.execute('INSERT INTO _monl_rate_limit (bucket, client_ip, attempted_at) VALUES (?, ?, ?)', (bucket, client_ip, now))
        cursor.execute('COMMIT')
    finally:
        conn.close()

@app.post('/register', tags=['Authentication'])
def register(req: RegisterRequest, request: Request):
    _check_rate_limit('register', _client_ip(request))
    if req.actor not in VALID_ACTORS:
        raise HTTPException(status_code=400, detail=f"Acteur invalide. Acteurs valides : {VALID_ACTORS}")
    if req.actor not in SELF_REGISTER_ACTORS:
        raise HTTPException(status_code=403, detail=(
            f"Le rôle '{req.actor}' n'est pas ouvert à l'inscription libre. "
            'Les comptes de ce rôle sont créés hors ligne : python3 manage.py adduser.'
        ))
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail='Le mot de passe doit contenir au moins 8 caractères.')
    if len(req.password) > 256:
        raise HTTPException(status_code=400, detail='Mot de passe trop long (256 caractères maximum).')
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT id FROM _monl_users WHERE username = ?', (req.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà.")
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
        raise HTTPException(status_code=500, detail='Impossible de générer un pseudonyme unique, réessayez.')
    cursor.execute('INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle) VALUES (?, ?, ?, ?, ?)',
                   (req.username, pwd_hash, salt_hex, req.actor, anon_handle))
    conn.commit(); new_user_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'user_id': new_user_id}

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post('/login', tags=['Authentication'])
def login(req: LoginRequest, request: Request):
    _check_rate_limit('login', _client_ip(request))
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, salt, actor, anon_handle FROM _monl_users WHERE username = ?', (req.username,))
    row = cursor.fetchone(); conn.close()
    if not row:
        hmac.compare_digest(_hash_password(req.password[:256], _DUMMY_SALT_HEX), _DUMMY_HASH)
        raise HTTPException(status_code=401, detail='Identifiants invalides.')
    db_user_id, stored_hash, salt_hex, actor, anon_handle = row
    if not hmac.compare_digest(_hash_password(req.password, salt_hex), stored_hash):
        raise HTTPException(status_code=401, detail='Identifiants invalides.')
    payload = {
        'sub': req.username,
        'actor': actor,
        'user_id': db_user_id,
        'anon_handle': anon_handle,
        'jti': secrets.token_hex(16),
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=TOKEN_TTL_HOURS)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}

@app.post('/logout', tags=['Authentication'])
def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    payload = _decode_and_verify_token(credentials)
    jti = payload.get('jti')
    if not jti:
        raise HTTPException(status_code=400, detail='Ce token ne supporte pas la révocation (jti manquant).')
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO _monl_revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)',
                   (jti, datetime.datetime.now(datetime.timezone.utc).isoformat(), payload.get('exp')))
    _purge_revoked_tokens(cursor)
    conn.commit(); conn.close()
    return {'status': 'success', 'detail': 'Token révoqué.'}

# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---
class ProductSchema(BaseModel):
    name: str = Field(..., max_length=255)
    price: float
    description: str = Field(..., max_length=20000)
    imageUrl: str = Field(..., max_length=255)
    category: str = Field(..., max_length=255)
    stock: int


class OrderSchema(BaseModel):
    total: float
    status: str = Field(..., max_length=255)
    note: str = Field(..., max_length=20000)


class CustomerSchema(BaseModel):
    displayName: str = Field(..., max_length=255)


# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---
# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/product', tags=['ManageProduct'])
def create_product(data: ProductSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Admin": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Admin requis")
    conn = _connect(); cursor = conn.cursor()
    query = 'INSERT INTO "product" ("name", "price", "description", "imageUrl", "category", "stock") VALUES (?, ?, ?, ?, ?, ?)'
    try:
        cursor.execute(query, (data.name, data.price, data.description, data.imageUrl, data.category, data.stock,))
        row_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            'Référence invalide : un identifiant lié fourni ne correspond à aucun '
            'enregistrement existant.'
        ))
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'status': 'success', 'id': row_id}

@app.get('/product', tags=['ManageProduct'])
def list_product(limit: int = 50, offset: int = 0):
    pass  # Route publique (règle 'public') : aucune authentification requise
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM "product"')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT * FROM "product" LIMIT ? OFFSET ?', (limit, offset))
    rows = cursor.fetchall()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    named_rows = [dict(zip(_columns, row)) for row in rows]
    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}

@app.get('/product/{id}', tags=['ManageProduct'])
def read_product(id: int):
    pass  # Route publique (règle 'public') : aucune authentification requise
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT * FROM "product" WHERE id = ?', (id,))
    row = cursor.fetchone()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    named_row = dict(zip(_columns, row))
    return {'status': 'success', 'data': named_row}

@app.put('/product/{id}', tags=['ManageProduct'])
def update_product(id: int, data: ProductSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Admin": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Admin requis")
    conn = _connect(); cursor = conn.cursor()
    query = 'UPDATE "product" SET "name" = ?, "price" = ?, "description" = ?, "imageUrl" = ?, "category" = ?, "stock" = ? WHERE id = ?'
    cursor.execute(query, (data.name, data.price, data.description, data.imageUrl, data.category, data.stock, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}

@app.delete('/product/{id}', tags=['ManageProduct'])
def delete_product(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Admin": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Admin requis")
    conn = _connect(); cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM "product" WHERE id = ?', (id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            "Suppression impossible : cet enregistrement est encore référencé "
            'par des données liées. Supprimez-les d\'abord.'
        ))
    conn.close()
    return {'status': 'success', 'id': id}

@app.post('/order', tags=['ManageOrder'])
def create_order(data: OrderSchema, current_actor: str = Depends(verify_jwt_and_get_actor), current_user_id: int = Depends(get_current_user_id)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    conn = _connect(); cursor = conn.cursor()
    query = 'INSERT INTO "order" ("total", "status", "note", "customer_id") VALUES (?, ?, ?, ?)'
    try:
        cursor.execute(query, (data.total, data.status, data.note, current_user_id,))
        row_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            'Référence invalide : un identifiant lié fourni ne correspond à aucun '
            'enregistrement existant.'
        ))
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'status': 'success', 'id': row_id}

@app.get('/order', tags=['ManageOrder'])
def list_order(limit: int = 50, offset: int = 0, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor not in {"Admin", "Customer"}: raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle parmi [Admin, Customer] requis")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM "order"')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT * FROM "order" LIMIT ? OFFSET ?', (limit, offset))
    rows = cursor.fetchall()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    named_rows = [dict(zip(_columns, row)) for row in rows]
    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}

@app.get('/order/{id}', tags=['ManageOrder'])
def read_order(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor not in {"Admin", "Customer"}: raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle parmi [Admin, Customer] requis")
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT * FROM "order" WHERE id = ?', (id,))
    row = cursor.fetchone()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    named_row = dict(zip(_columns, row))
    return {'status': 'success', 'data': named_row}

@app.put('/order/{id}', tags=['ManageOrder'])
def update_order(id: int, data: OrderSchema, current_actor: str = Depends(verify_jwt_and_get_actor), current_user_id: int = Depends(get_current_user_id)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    if current_actor == "Customer":
        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()
        _owner_cur.execute('SELECT "customer_id" FROM "order" WHERE id = ?', (id,))
        _owner_row = _owner_cur.fetchone(); _owner_conn.close()
        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, detail="Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action")
    conn = _connect(); cursor = conn.cursor()
    query = 'UPDATE "order" SET "total" = ?, "status" = ?, "note" = ? WHERE id = ?'
    cursor.execute(query, (data.total, data.status, data.note, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}

@app.delete('/order/{id}', tags=['ManageOrder'])
def delete_order(id: int, current_actor: str = Depends(verify_jwt_and_get_actor), current_user_id: int = Depends(get_current_user_id)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    if current_actor == "Customer":
        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()
        _owner_cur.execute('SELECT "customer_id" FROM "order" WHERE id = ?', (id,))
        _owner_row = _owner_cur.fetchone(); _owner_conn.close()
        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, detail="Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action")
    conn = _connect(); cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM "order" WHERE id = ?', (id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            "Suppression impossible : cet enregistrement est encore référencé "
            'par des données liées. Supprimez-les d\'abord.'
        ))
    conn.close()
    return {'status': 'success', 'id': id}

@app.post('/customer', tags=['ManageCustomer'])
def create_customer(data: CustomerSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    conn = _connect(); cursor = conn.cursor()
    query = 'INSERT INTO "customer" ("displayName") VALUES (?)'
    try:
        cursor.execute(query, (data.displayName,))
        row_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            'Référence invalide : un identifiant lié fourni ne correspond à aucun '
            'enregistrement existant.'
        ))
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'status': 'success', 'id': row_id}

@app.get('/customer', tags=['ManageCustomer'])
def list_customer(limit: int = 50, offset: int = 0, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM "customer"')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT * FROM "customer" LIMIT ? OFFSET ?', (limit, offset))
    rows = cursor.fetchall()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    named_rows = [dict(zip(_columns, row)) for row in rows]
    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}

@app.get('/customer/{id}', tags=['ManageCustomer'])
def read_customer(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    conn = _connect(); cursor = conn.cursor()
    cursor.execute('SELECT * FROM "customer" WHERE id = ?', (id,))
    row = cursor.fetchone()
    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)
    conn.close()
    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    named_row = dict(zip(_columns, row))
    return {'status': 'success', 'data': named_row}

@app.put('/customer/{id}', tags=['ManageCustomer'])
def update_customer(id: int, data: CustomerSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    conn = _connect(); cursor = conn.cursor()
    query = 'UPDATE "customer" SET "displayName" = ? WHERE id = ?'
    cursor.execute(query, (data.displayName, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}

@app.delete('/customer/{id}', tags=['ManageCustomer'])
def delete_customer(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Customer": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Customer requis")
    conn = _connect(); cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM "customer" WHERE id = ?', (id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback(); conn.close()
        raise HTTPException(status_code=409, detail=(
            "Suppression impossible : cet enregistrement est encore référencé "
            'par des données liées. Supprimez-les d\'abord.'
        ))
    conn.close()
    return {'status': 'success', 'id': id}
