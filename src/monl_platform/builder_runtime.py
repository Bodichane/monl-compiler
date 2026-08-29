"""Runtime dependencies and project helpers for the builder."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, status

from monl.app_templates import TEMPLATES

from .downloads import default_directory
from .hosting import SiteManager
from .paths import ProjectPathError, project_directory
from .store import PlatformStore


def _http_error(message, code):
    raise HTTPException(status_code=code, detail=message)


def _require_user(request: Request, identities):
    user = identities.session_user(request.cookies.get("monl_session"))
    if not user:
        raise HTTPException(status_code=401, detail="Connectez-vous pour continuer.")
    return user


def _slug(name, project_id):
    """Déduit une adresse stable pour un projet créé par le socle."""
    value = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return value[:80] or f"projet-{project_id[:12]}"


def _identity_project(identities, user_id, project_id):
    for project in identities.projects(user_id):
        if project["project_id"] == project_id:
            return project
    return None


def _ensure_builder_project(runtime, user, project_id):
    """Rattache paresseusement un projet compilé au constructeur.

    ``/api/compile`` est la création de projet du socle.  Le constructeur ne
    crée donc jamais une seconde ligne métier : à la première route de build,
    il ajoute seulement ses métadonnées dans ``builder_projects`` et recopie
    la spec déjà publiée vers le dossier privé du compte.
    """
    identity_project = _identity_project(runtime.identities, user["id"], project_id)
    if identity_project is None:
        _http_error("Projet introuvable.", status.HTTP_404_NOT_FOUND)

    project = runtime.store.get_project_for_user(user["id"], project_id)
    if project is None:
        try:
            runtime.store.create_project(
                user["id"], project_id, _slug(identity_project["name"], project_id)
            )
        except (OSError, ValueError):
            _http_error("Le projet ne peut pas être préparé pour une construction.", 422)
        project = runtime.store.get_project_for_user(user["id"], project_id)

    try:
        private_dir = project_directory(
            runtime.workspace_root, user["id"], project_id, create=True
        )
    except ProjectPathError as exc:
        _http_error(str(exc), 422)

    spec_path = private_dir / "spec.ml"
    if not spec_path.is_file():
        source = Path(runtime.service.workspace) / project_id / "spec.ml"
        if not source.is_file():
            _http_error("La spécification du projet est introuvable.", 404)
        spec_path.write_bytes(source.read_bytes())
    return project


def _provider_catalogue():
    return [
        {
            "name": template["name"],
            "hint": template["hint"],
            "actors": list(template.get("actors", [])),
            "entities": sorted(template.get("entities", {})),
        }
        for template in TEMPLATES
    ]


def _set_session_cookie(response, token):
    response.set_cookie(
        "monl_session", token, max_age=30 * 24 * 3600, path="/",
        httponly=True, samesite="strict",
        secure=os.environ.get("MONL_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
    )


@dataclass
class BuilderRuntime:
    """Les dépendances des routes de projet, sans une seule d'IA (point 161)."""

    service: object
    identities: object
    store: PlatformStore
    sites: SiteManager
    workspace_root: Path
    downloads_dir: str | None

    def start(self):
        """Rien à démarrer : la compilation est synchrone et sans file."""

    def stop(self):
        self.sites.stop_all()

    def remove_project(self, user_id, project_id):
        """Retire le dossier privé d'un projet précis, s'il existe."""
        try:
            directory = project_directory(
                self.workspace_root, user_id, project_id, create=False
            )
        except (ProjectPathError, FileNotFoundError):
            return
        if directory.is_dir():
            shutil.rmtree(directory)


def create_runtime(service, identities, *, domain=None, downloads_dir=None):
    """Construit les dépendances des routes de projet, sans monter de route.

    POINT 161 : plus de fournisseur IA, plus de quota, plus de worker. Ce qui
    reste — le magasin, l'hébergement local — est déterministe, donc rien
    n'est plus à injecter pour rendre la plateforme éprouvable hors ligne.
    """
    store = PlatformStore(service.workspace)
    sites = SiteManager(
        store, service.workspace, domain or os.environ.get("MONL_PLATFORM_DOMAIN", "localhost")
    )
    return BuilderRuntime(
        service=service,
        identities=identities,
        store=store,
        sites=sites,
        workspace_root=Path(service.workspace),
        downloads_dir=downloads_dir if downloads_dir is not None else default_directory(),
    )
