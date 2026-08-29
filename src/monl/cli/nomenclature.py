"""Les noms de fichiers d'un projet, en un seul endroit.

Feuille du paquet : ces constantes sont lues par l'emplacement ET par le
conteneur, qui se liraient l'un l'autre si elles restaient chez l'un des
deux."""

from ..design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
)
from ..frontend_contract import CONTRACT_FILENAME, PROMPT_FILENAME

STATE_FILENAME = "monl.json"

# Ce que la spec produit et que personne ne doit retoucher à la main
# (manage.py et sandbox_ai.py compris : ils portent des droits).
SCELLE_ARTEFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py",
                    "serve.py")

# Artefacts de déploiement éditables par l'auteur. Ils sont publiés avec la
# compilation, mais ne sont ni scellés ni inclus dans les empreintes backend :
# une adaptation locale du conteneur doit survivre à `monl compile`.
CONTAINER_ARTEFACTS = ("Dockerfile", ".dockerignore", "requirements.txt")

PROJECT_ARTEFACTS = (
    *SCELLE_ARTEFACTS,
    *CONTAINER_ARTEFACTS,
    ".jwt_secret",
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    DESIGN_SPEC_FILENAME,
    ASSET_MANIFEST_FILENAME,
    "CLAUDE.md",
    STATE_FILENAME,
)

# Le Dockerfile installe depuis requirements.txt et n'énumère AUCUNE
# dépendance : deux listes à tenir d'accord finissent par diverger, et la
# divergence portait déjà — le gabarit n'ajoutait 'python-multipart' que si la
# spec déclare un Upload, quand requirements.txt le listait toujours. Une
# seule liste, et c'est celle que l'archive documente.
#
# MONL_ENV=production rend MONL_JWT_SECRET OBLIGATOIRE (aucun secret n'est
# généré ni lu sur le disque en production) : le conteneur REFUSE de démarrer
# sans lui, et c'est voulu — un secret fabriqué au démarrage changerait à
# chaque redémarrage, invalidant toutes les sessions, et un secret cuit dans
# l'image serait pire. Le dire ICI est le point du correctif : le message
# d'erreur du serveur nomme déjà la variable, mais il faut avoir lancé le
# conteneur et lu ses journaux pour le découvrir.
DEFAULT_DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    MONL_ENV=production

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# OBLIGATOIRE au démarrage : le conteneur s'arrête sans lui.
#   docker run -e MONL_JWT_SECRET="$(openssl rand -hex 32)" -p 8000:8000 <image>
# Le garder hors de l'image est délibéré : un secret cuit dans une image se
# diffuse avec elle.
EXPOSE 8000
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
"""

DEFAULT_DOCKERIGNORE = """.jwt_secret
*.db
__pycache__
frontend.precedent/
"""

# LA liste de dépendances du projet : le Dockerfile l'installe, l'archive la
# documente, et 'pip install -r requirements.txt' fonctionne sur une machine
# nue. 'python-multipart' n'y entre que si la spec déclare un Upload —
# l'ajouter d'office ferait installer, à tout projet, une bibliothèque qu'il
# n'emploie pas.
DEFAULT_REQUIREMENTS = """fastapi>=0.110,<1.0
uvicorn>=0.29,<1.0
PyJWT>=2.8,<3.0
"""

REQUIREMENTS_UPLOAD = DEFAULT_REQUIREMENTS + "python-multipart>=0.0.9,<1.0\n"

# GABARITS HÉRITÉS — un Dockerfile RESTÉ IDENTIQUE à l'un d'eux n'a jamais été
# touché par personne : le rafraîchir est un service, pas une intrusion. Un
# fichier réellement personnalisé reste, lui, sous la responsabilité de son
# auteur.
#
# ILS SONT ÉCRITS EN TOUTES LETTRES, jamais dérivés de DEFAULT_DOCKERFILE.
# Ils l'étaient — par `.replace()` sur le gabarit courant — et la première
# évolution de ce gabarit les a fait désigner des formes qui n'ont jamais été
# émises : la détection cessait de reconnaître les vrais fichiers hérités,
# donc tout projet existant voyait son Dockerfile traité comme personnalisé et
# gelé pour toujours. Silencieusement. Un « hérité » décrit le PASSÉ : il ne
# peut pas se déduire du présent.
_HERITE_ENTETE = """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    MONL_ENV=production

COPY . .
RUN pip install --no-cache-dir \\
    'fastapi>=0.110,<1.0' \\
    'uvicorn>=0.29,<1.0' \\
    'PyJWT>=2.8,<3.0'"""

_HERITE_ENTETE_UPLOAD = _HERITE_ENTETE + """ \\
    'python-multipart>=0.0.9,<1.0'"""

_HERITE_PIED = """

EXPOSE 8000
CMD ["uvicorn", "{cible}", "--host", "0.0.0.0", "--port", "8000"]
"""

# Quatre formes réellement émises : `app:app` avant le point 133, `serve:app`
# depuis — chacune avec et sans la dépendance d'Upload.
DOCKERFILES_HERITES = tuple(
    entete + _HERITE_PIED.format(cible=cible)
    for entete in (_HERITE_ENTETE, _HERITE_ENTETE_UPLOAD)
    for cible in ("app:app", "serve:app")
)
