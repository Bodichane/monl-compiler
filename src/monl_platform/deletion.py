"""Deletion shared by the routes, the administration and the purge."""

import contextlib

from .service import PlatformNotFoundError


def delete_project(runtime, user_id, project_id):
    """Stops the site before removing its data and its ownership."""
    runtime.sites.stop_project(project_id)
    with contextlib.suppress(PlatformNotFoundError):
        runtime.service.delete(project_id)
    runtime.remove_project(user_id, project_id)
    runtime.identities.delete_project(user_id, project_id)


def delete_account(runtime, user_id):
    """Keeps the owners until the end of the disk cleanup."""
    projects = runtime.identities.projects(user_id)
    for project in projects:
        delete_project(runtime, user_id, project["project_id"])
    runtime.identities.delete_user(user_id)
    return [project["project_id"] for project in projects]
