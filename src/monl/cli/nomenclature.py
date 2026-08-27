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
CONTAINER_ARTEFACTS = ("Dockerfile", ".dockerignore")

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

DEFAULT_DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    MONL_ENV=production

COPY . .
RUN pip install --no-cache-dir \\
    'fastapi>=0.110,<1.0' \\
    'uvicorn>=0.29,<1.0' \\
    'PyJWT>=2.8,<3.0'

EXPOSE 8000
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
"""

DEFAULT_DOCKERIGNORE = """.jwt_secret
*.db
__pycache__
frontend.precedent/
"""

# GABARITS HÉRITÉS — la version `app:app`, émise jusqu'à ce que le point 133
# la corrige. Un Dockerfile RESTÉ IDENTIQUE à l'un d'eux n'a jamais été touché
# par personne : le rafraîchir est un service, pas une intrusion. Un fichier
# réellement personnalisé, lui, reste sous la responsabilité de son auteur —
# c'est déjà l'arbitrage retenu pour le gabarit Upload, repris tel quel.
_DOCKERFILE_HERITE_BASE = DEFAULT_DOCKERFILE.replace(
    '"serve:app"', '"app:app"')

_DOCKERFILE_HERITE_UPLOAD = _DOCKERFILE_HERITE_BASE.replace(
    "    'PyJWT>=2.8,<3.0'\n",
    "    'PyJWT>=2.8,<3.0' " + "\\\n"
    "    'python-multipart>=0.0.9,<1.0'\n",
)

DOCKERFILES_HERITES = (_DOCKERFILE_HERITE_BASE, _DOCKERFILE_HERITE_UPLOAD)
