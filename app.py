# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Any
import sqlite3
import jwt
import datetime
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='TodoApp - Secure Core')
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
class UserSchema(BaseModel):
    name: str
    email: str


class TodoSchema(BaseModel):
    title: str
    completed: bool


# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---
class autoArchiveTodoInputSchema(BaseModel):
    title: str


# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---
@app.post('/todo', tags=['ManageTodo'])
async def create_todo(data: TodoSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'INSERT INTO todo (title, completed) VALUES (?, ?)'
    cursor.execute(query, (data.title, data.completed,))
    conn.commit(); row_id = cursor.lastrowid; conn.close()
    return {'status': 'success', 'id': row_id}

@app.put('/todo/{id}', tags=['ManageTodo'])
async def update_todo(id: int, data: TodoSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    query = 'UPDATE todo SET title = ?, completed = ? WHERE id = ?'
    cursor.execute(query, (data.title, data.completed, id))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}

@app.post('/workflow/managetodo/autoarchivetodo', tags=['ManageTodo'])
async def execute_autoarchivetodo(payload: autoArchiveTodoInputSchema, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    result = sandbox_ai.autoArchiveTodo(payload.dict())
    return {'status': 'executed', 'sandbox_result': result}

@app.delete('/todo/{id}', tags=['AdminTodo'])
async def delete_todo(id: int, current_actor: str = Depends(verify_jwt_and_get_actor)):
    if current_actor != "Admin": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle Admin requis")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('DELETE FROM todo WHERE id = ?', (id,))
    conn.commit(); conn.close()
    return {'status': 'success', 'id': id}
