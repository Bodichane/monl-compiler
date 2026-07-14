# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Any
import sqlite3
import jwt
import datetime
import hashlib
import os
import secrets
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='AnonForum - Secure Core')
DB_FILE = 'app.db'
try:
    with open('.jwt_secret', 'r', encoding='utf-8') as _f:
        JWT_SECRET = _f.read().strip()
    if not JWT_SECRET:
        raise ValueError('.jwt_secret est vide')
except (FileNotFoundError, ValueError) as _e:
    raise RuntimeError(
        "Fichier '.jwt_secret' introuvable ou vide. Il est généré automatiquement "
        "par le compilateur MonLang — relancez 'python3 src/main.py <spec.yaml>' "
        "depuis la racine du projet avant de démarrer le serveur."
    ) from _e
JWT_ALGORITHM = 'HS256'
VALID_ACTORS = ["Member"]

security_bearer = HTTPBearer()

def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='Token invalide ou expiré')
    jti = payload.get('jti')
    if jti:
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM _monlang_revoked_tokens WHERE jti = ?', (jti,))
        revoked = cursor.fetchone(); conn.close()
        if revoked:
            raise HTTPException(status_code=401, detail='Ce token a été révoqué (déconnexion effectuée).')
    return payload

def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:
    return _decode_and_verify_token(credentials).get('actor')

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:
    return _decode_and_verify_token(credentials).get('user_id', 0)

@app.on_event('startup')
def init_db():
    conn = sqlite3.connect(DB_FILE)
    try:
        with open('schema.sql', 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
    except Exception as e:
        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')
    finally:
        conn.close()

from fastapi.responses import RedirectResponse, HTMLResponse

@app.get('/', include_in_schema=False, response_class=HTMLResponse)
async def root():
    try:
        with open('landing.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return RedirectResponse(url='/docs')

@app.get('/app', include_in_schema=False, response_class=HTMLResponse)
async def app_dashboard():
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return RedirectResponse(url='/')

class RegisterRequest(BaseModel):
    username: str
    password: str
    actor: str

def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()

_RATE_LIMIT_ATTEMPTS = {}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_ATTEMPTS = 5

def _check_rate_limit(bucket: str, client_ip: str):
    now = datetime.datetime.utcnow().timestamp()
    key = f'{bucket}:{client_ip}'
    attempts = _RATE_LIMIT_ATTEMPTS.setdefault(key, [])
    attempts[:] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail=f'Trop de tentatives ({bucket}). Réessayez dans {RATE_LIMIT_WINDOW_SECONDS} secondes.')
    attempts.append(now)

@app.post('/register', tags=['Authentication'])
async def register(req: RegisterRequest, request: Request):
    _check_rate_limit('register', request.client.host if request.client else 'unknown')
    if req.actor not in VALID_ACTORS:
        raise HTTPException(status_code=400, detail=f"Acteur invalide. Acteurs valides : {VALID_ACTORS}")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail='Le mot de passe doit contenir au moins 8 caractères.')
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT id FROM _monlang_users WHERE username = ?', (req.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà.")
    salt_hex = os.urandom(16).hex()
    pwd_hash = _hash_password(req.password, salt_hex)
    cursor.execute('INSERT INTO _monlang_users (username, password_hash, salt, actor) VALUES (?, ?, ?, ?)',
                   (req.username, pwd_hash, salt_hex, req.actor))
    conn.commit(); new_user_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'user_id': new_user_id}

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post('/login', tags=['Authentication'])
async def login(req: LoginRequest, request: Request):
    _check_rate_limit('login', request.client.host if request.client else 'unknown')
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, salt, actor FROM _monlang_users WHERE username = ?', (req.username,))
    row = cursor.fetchone(); conn.close()
    if not row:
        raise HTTPException(status_code=401, detail='Identifiants invalides.')
    db_user_id, stored_hash, salt_hex, actor = row
    if _hash_password(req.password, salt_hex) != stored_hash:
        raise HTTPException(status_code=401, detail='Identifiants invalides.')
    payload = {
        'sub': req.username,
        'actor': actor,
        'user_id': db_user_id,
        'jti': secrets.token_hex(16),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}

@app.post('/logout', tags=['Authentication'])
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    payload = _decode_and_verify_token(credentials)
    jti = payload.get('jti')
    if not jti:
        raise HTTPException(status_code=400, detail='Ce token ne supporte pas la révocation (jti manquant).')
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO _monlang_revoked_tokens (jti, revoked_at) VALUES (?, ?)',
                   (jti, datetime.datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {'status': 'success', 'detail': 'Token révoqué.'}

# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---
class PostSchema(BaseModel):
    content: str
    author: str


# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---
# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/post', tags=['PublishPost'])
async def create_post(data: PostSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Member": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Member requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'INSERT INTO "post" ("content", "author") VALUES (?, ?)'
    cursor.execute(query, (data.content, data.author,))
    conn.commit(); row_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'id': row_id}

@app.get('/post', tags=['PublishPost'])
async def list_post(limit: int = 50, offset: int = 0):
    pass  # Route publique (règle 'public') : aucune authentification requise
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM "post"')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT * FROM "post" LIMIT ? OFFSET ?', (limit, offset))
    rows = cursor.fetchall(); conn.close()
    _columns = ["id", "content", "author"]
    named_rows = [dict(zip(_columns, row)) for row in rows]
    for _r in named_rows:
        for _f in ['author']: _r.pop(_f, None)
    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}

@app.get('/post/{id}', tags=['PublishPost'])
async def read_post(id: int):
    pass  # Route publique (règle 'public') : aucune authentification requise
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT * FROM "post" WHERE id = ?', (id,))
    row = cursor.fetchone(); conn.close()
    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    named_row = dict(zip(["id", "content", "author"], row))
    for _f in ['author']: named_row.pop(_f, None)
    return {'status': 'success', 'data': named_row}
