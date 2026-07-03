#, # API générée automatiquement par MonLang
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title='TechBlog API')

# --- MODÈLES DE DONNÉES DE LA COMPILATION ---
class UserSchema(BaseModel):
    username: str
    email: str
    role: str
    class Config:
        from_attributes = True

class PostSchema(BaseModel):
    title: str
    slug: str
    content: str
    publishedAt: str
    class Config:
        from_attributes = True

class CommentSchema(BaseModel):
    content: str
    createdAt: str
    class Config:
        from_attributes = True

# --- ROUTES SÉCURISÉES PAR WORKFLOW ---
@app.post('/post', tags=['Workflow: AuthorManagePost (Author)'])
async def create_post(data: PostSchema):
    return {'message': 'Post créé avec succès via le workflow AuthorManagePost par Author', 'data': data}

@app.put('/post/{id}', tags=['Workflow: AuthorManagePost (Author)'])
async def update_post(id: int, data: PostSchema):
    return {'message': 'Post mis à jour', 'id': id, 'data': data}

@app.delete('/post/{id}', tags=['Workflow: AuthorManagePost (Author)'])
async def delete_post(id: int):
    return {'message': 'Post supprimé', 'id': id}

@app.post('/comment', tags=['Workflow: ReaderComment (Reader)'])
async def create_comment(data: CommentSchema):
    return {'message': 'Comment créé avec succès via le workflow ReaderComment par Reader', 'data': data}
