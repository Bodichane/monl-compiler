"""A project's file names, in one place.

The package's leaf: these constants are read by the location module AND
by the container module, which would read each other if the constants
stayed in one of the two."""

from ..design_system import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
)
from ..frontend_contract import (
    AGENTS_FILENAME,
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    README_FILENAME,
)

STATE_FILENAME = "monl.json"

# What the spec produces and nobody must touch up by hand (manage.py and
# sandbox_ai.py included: they carry permissions).
SEALED_ARTIFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py",
                    "serve.py")

# Deployment artifacts the author can edit. They are published with the
# compilation, but are neither sealed nor included in the backend fingerprints:
# a local adaptation of the container must survive `monl compile`.
CONTAINER_ARTIFACTS = ("Dockerfile", ".dockerignore", "requirements.txt")

PROJECT_ARTIFACTS = (
    *SEALED_ARTIFACTS,
    *CONTAINER_ARTIFACTS,
    ".jwt_secret",
    CONTRACT_FILENAME,
    PROMPT_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    DESIGN_SPEC_FILENAME,
    ASSET_MANIFEST_FILENAME,
    AGENTS_FILENAME,
    README_FILENAME,
    STATE_FILENAME,
)

# The Dockerfile installs from requirements.txt and lists NO dependency: two
# lists to keep in agreement end up diverging, and the divergence already bit —
# the template added 'python-multipart' only if the spec declared an Upload,
# while requirements.txt always listed it. A single list, and it is the one the
# archive documents.
#
# MONL_ENV=production makes MONL_JWT_SECRET MANDATORY (no secret is generated
# or read from disk in production): the container REFUSES to start without it,
# on purpose — a secret made at startup would change on every restart,
# invalidating all sessions, and a secret baked into the image would be worse.
# Saying it HERE is the point of the fix: the server's error message already
# names the variable, but one has to start the container and read its logs to
# discover it.
DEFAULT_DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    MONL_ENV=production

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# REQUIRED at startup: the container stops without it.
#   docker run -e MONL_JWT_SECRET="$(openssl rand -hex 32)" -p 8000:8000 <image>
# Keeping it out of the image is deliberate: a secret baked into an image
# spreads with it.
EXPOSE 8000
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
"""

DEFAULT_DOCKERIGNORE = """.jwt_secret
*.db
__pycache__
frontend.precedent/
"""

# THE project's dependency list: the Dockerfile installs it, the archive
# documents it, and 'pip install -r requirements.txt' works on a bare machine.
# 'python-multipart' enters only if the spec declares an Upload — adding it by
# default would make every project install a library it does not use.
DEFAULT_REQUIREMENTS = """fastapi>=0.110,<1.0
uvicorn>=0.29,<1.0
PyJWT>=2.8,<3.0
"""

REQUIREMENTS_UPLOAD = DEFAULT_REQUIREMENTS + "python-multipart>=0.0.9,<1.0\n"

# INHERITED TEMPLATES — a Dockerfile that STAYED IDENTICAL to one of them was
# never touched by anyone: refreshing it is a service, not an intrusion. A
# really customized file stays its author's responsibility.
#
# THEY ARE WRITTEN OUT IN FULL, never derived from DEFAULT_DOCKERFILE. They
# used to be — through `.replace()` on the current template — and the first
# change to that template made them designate forms that were never emitted:
# detection stopped recognizing the real inherited files, so every existing
# project saw its Dockerfile treated as customized and frozen forever.
# Silently. "Inherited" describes the PAST: it cannot be deduced from the
# present.
_INHERITED_HEADER = """FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    MONL_ENV=production

COPY . .
RUN pip install --no-cache-dir \\
    'fastapi>=0.110,<1.0' \\
    'uvicorn>=0.29,<1.0' \\
    'PyJWT>=2.8,<3.0'"""

_INHERITED_HEADER_UPLOAD = _INHERITED_HEADER + """ \\
    'python-multipart>=0.0.9,<1.0'"""

_INHERITED_FOOTER = """

EXPOSE 8000
CMD ["uvicorn", "{cible}", "--host", "0.0.0.0", "--port", "8000"]
"""

# The fifth form: `-r requirements.txt` with the secret instructions still in
# French, emitted until the English migration of the generated comments.
_INHERITED_REQUIREMENTS_FR = """FROM python:3.12-slim

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

# Five forms really emitted: `app:app` before point 133, `serve:app` since —
# each with and without the Upload dependency — then the requirements.txt form
# with French comments.
DOCKERFILES_INHERITED = tuple(
    header + _INHERITED_FOOTER.format(cible=target)
    for header in (_INHERITED_HEADER, _INHERITED_HEADER_UPLOAD)
    for target in ("app:app", "serve:app")
) + (_INHERITED_REQUIREMENTS_FR,)
