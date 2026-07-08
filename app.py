# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Any
import sqlite3
import jwt
import datetime
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='ModerationApp - Secure Core')
DB_FILE = 'app.db'
JWT_SECRET = 'SUPER_SECRET_KEY_MONLANG_INDUSTRIAL_SAFETY_2026'
JWT_ALGORITHM = 'HS256'

security_bearer = HTTPBearer()

def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('actor')
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail='Token invalide ou expiré')

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

from fastapi.responses import RedirectResponse

@app.get('/', include_in_schema=False)
async def root():
    return RedirectResponse(url='/docs')

class LoginRequest(BaseModel):
    username: str
    actor: str

@app.post('/login', tags=['Authentication'])
async def login(req: LoginRequest):
    payload = {
        'sub': req.username,
        'actor': req.actor,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}

# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---
class PostSchema(BaseModel):
    title: str
    content: str


# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---
# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/post', tags=['AdminModeration'])
async def create_post(data: PostSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Admin": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Admin requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'INSERT INTO post (title, content) VALUES (?, ?)'
    cursor.execute(query, (data.title, data.content,))
    conn.commit(); row_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'id': row_id}

@app.delete('/post/{id}', tags=['AdminModeration'])
async def delete_post(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor not in {"Admin", "Moderator"}: raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle parmi [Admin, Moderator] requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('DELETE FROM post WHERE id = ?', (id,))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}
