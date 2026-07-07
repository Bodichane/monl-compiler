# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import jwt
import datetime
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='TodoApp - Cryptographically Secure Core')

DB_FILE = 'app.db'
JWT_SECRET = 'SUPER_SECRET_KEY_MONLANG_2026'  # En production, charger depuis l'environnement
JWT_ALGORITHM = 'HS256'

security_bearer = HTTPBearer()

def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:
    """Middleware de vérification cryptographique stricte du Token JWT."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('actor')
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expiré')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Token invalide')

class LoginRequest(BaseModel):
    username: str
    actor: str

@app.post('/login', tags=['Authentication'])
async def login(req: LoginRequest):
    """Génère un jeton JWT signé cryptographiquement pour l'acteur demandé."""
    payload = {
        'sub': req.username,
        'actor': req.actor,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}

# --- VALIDATION STRICTE DES DONNÉES (PYDANTIC) ---
class UserSchema(BaseModel):
    name: str
    email: str


class TodoSchema(BaseModel):
    title: str
    completed: bool


# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/todo', tags=['ManageTodo'])
async def create_todo(data: TodoSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis par la spécification MonLang")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'INSERT INTO todo (title, completed) VALUES (?, ?)'
    cursor.execute(query, (data.title, data.completed,))
    conn.commit(); row_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'action': 'create', 'id': row_id}

@app.put('/todo/{id}', tags=['ManageTodo'])
async def update_todo(id: int, data: TodoSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis par la spécification MonLang")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'UPDATE todo SET title = ?, completed = ? WHERE id = ?'
    cursor.execute(query, (data.title, data.completed, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'action': 'update', 'id': id}

@app.delete('/todo/{id}', tags=['ManageTodo'])
async def delete_todo(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis par la spécification MonLang")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('DELETE FROM todo WHERE id = ?', (id,))
    conn.commit(); conn.close()
    return {'status': 'success', 'action': 'delete', 'id': id}

@app.post('/workflow/managetodo/autoarchivetodo', tags=['ManageTodo'])
async def execute_autoarchivetodo(payload: dict, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis par la spécification MonLang")
    result = sandbox_ai.autoArchiveTodo(payload)
    return {'status': 'executed', 'sandbox_result': result}
