# API Déterministe Sécurisée par défaut - Ne pas modifier à la main
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
import sandbox_ai  # Importation de l'échappatoire IA isolé

app = FastAPI(title='TodoApp - Secure Core')

# --- VALIDATION STRICTE DES DONNÉES (PYDANTIC) ---
class UserSchema(BaseModel):
    name: str
    email: str


class TodoSchema(BaseModel):
    title: str
    completed: bool


# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR WORKFLOW ---
@app.post('/todo', tags=['ManageTodo'])
async def create_todo(data: TodoSchema, x_actor: str = Header(...)):
    if x_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    return {'status': 'success', 'action': 'create', 'target': 'Todo'}

@app.post('/workflow/managetodo/autoarchivetodo', tags=['ManageTodo'])
async def execute_autoarchivetodo(payload: dict, x_actor: str = Header(...)):
    if x_actor != "User": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle User requis")
    # Appel sécurisé à l'échappatoire IA
    result = sandbox_ai.autoArchiveTodo(payload)
    return {'status': 'executed', 'sandbox_result': result}
