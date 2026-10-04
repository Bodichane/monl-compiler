"""Suppression commune aux routes, à l'administration et à la purge."""

import contextlib

from .service import PlatformNotFoundError


def supprimer_projet(runtime, user_id, project_id):
    """Arrête le site avant de retirer ses données et sa propriété."""
    runtime.sites.stop_project(project_id)
    with contextlib.suppress(PlatformNotFoundError):
        runtime.service.delete(project_id)
    runtime.remove_project(user_id, project_id)
    runtime.identities.delete_project(user_id, project_id)


def supprimer_compte(runtime, user_id):
    """Conserve les propriétaires jusqu'à la fin du nettoyage disque."""
    projets = runtime.identities.projects(user_id)
    for projet in projets:
        supprimer_projet(runtime, user_id, projet["project_id"])
    runtime.identities.delete_user(user_id)
    return [projet["project_id"] for projet in projets]
