#, # API générée automatiquement par MonLang
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title='TodoApp API')

# --- MODÈLES DE DONNÉES DE LA COMPILATION ---
class UserSchema(BaseModel):
    name: str
    email: str
    class Config:
        from_attributes = True

class TodoSchema(BaseModel):
    title: str
    completed: bool
    class Config:
        from_attributes = True

# --- ROUTES SÉCURISÉES PAR WORKFLOW ---
@app.post('/todo', tags=['Workflow: ManageTodo (User)'])
async def create_todo(data: TodoSchema):
    return {'message': 'Todo créé avec succès via le workflow ManageTodo par User', 'data': data}

@app.put('/todo/{id}', tags=['Workflow: ManageTodo (User)'])
async def update_todo(id: int, data: TodoSchema):
    return {'message': 'Todo mis à jour', 'id': id, 'data': data}

@app.delete('/todo/{id}', tags=['Workflow: ManageTodo (User)'])
async def delete_todo(id: int):
    return {'message': 'Todo supprimé', 'id': id}
