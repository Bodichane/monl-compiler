# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Any
import sqlite3
import jwt
import datetime
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='ContactManager - Secure Core')
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

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('user_id', 0)
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

from fastapi.responses import RedirectResponse, HTMLResponse

@app.get('/', include_in_schema=False)
async def root():
    return RedirectResponse(url='/docs')

@app.get('/ui', include_in_schema=False, response_class=HTMLResponse)
async def ui():
    try:
        with open('frontend.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content='<h1>frontend.html introuvable</h1>', status_code=404)

class LoginRequest(BaseModel):
    username: str
    actor: str
    # AJOUT (post-v6, roadmap) : identifiant numérique auto-déclaré par le
    # client, utilisé pour le contrôle d'accès par propriété ('ownedBy').
    # LIMITE CONNUE (prototype) : comme pour 'actor', ce projet n'a pas de
    # registre d'utilisateurs réel — ce user_id est déclaré par le client,
    # pas vérifié contre une base d'authentification. Voir docs/design_decisions.md.
    user_id: int = 1

@app.post('/login', tags=['Authentication'])
async def login(req: LoginRequest):
    payload = {
        'sub': req.username,
        'actor': req.actor,
        'user_id': req.user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}

# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---
class ContactSchema(BaseModel):
    name: str
    email: str
    phone: str
    address: str


# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---
# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/contact', tags=['ManageContact'])
async def create_contact(data: ContactSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'INSERT INTO contact (name, email, phone, address) VALUES (?, ?, ?, ?)'
    cursor.execute(query, (data.name, data.email, data.phone, data.address,))
    conn.commit(); row_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'id': row_id}

@app.get('/contact/{id}', tags=['ManageContact'])
async def read_contact(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('SELECT * FROM contact WHERE id = ?', (id,))
    row = cursor.fetchone(); conn.close()
    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    return {'status': 'success', 'data': row}

@app.put('/contact/{id}', tags=['ManageContact'])
async def update_contact(id: int, data: ContactSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'UPDATE contact SET name = ?, email = ?, phone = ?, address = ? WHERE id = ?'
    cursor.execute(query, (data.name, data.email, data.phone, data.address, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}

@app.delete('/contact/{id}', tags=['ManageContact'])
async def delete_contact(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('DELETE FROM contact WHERE id = ?', (id,))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}
