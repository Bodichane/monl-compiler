"""Wrapper généré par 'monl run' — ne pas éditer.
Monte le frontend produit par l'IA (frontend/) sur /site, sans modifier
app.py (le backend reste un artefact scellé du compilateur)."""
from fastapi.staticfiles import StaticFiles
from app import app

app.mount("/site", StaticFiles(directory="frontend", html=True), name="site")
