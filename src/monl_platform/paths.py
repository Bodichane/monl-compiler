"""Project paths, confined to a platform workspace."""

import os
from pathlib import Path


class ProjectPathError(ValueError):
    """A path supplied for a project does not respect the boundary."""


def _safe_component(value, label):
    text = str(value)
    if not text or text in {".", ".."} or "\x00" in text:
        raise ProjectPathError(f"invalid {label}: path traversal refused")
    if "/" in text or "\\" in text:
        raise ProjectPathError(f"invalid {label}: path separator refused")
    return text


def project_directory(workspace_root, account_id, project_id, *, create=True):
    """Returns a project's private folder and checks its symlinks.

    The opaque text identifiers coming from identity are the only components
    of the path. The slug stays catalog data, never a user-supplied path. An
    existing symbolic link is refused: otherwise a folder of account A could
    point to the files of account B."""
    account = _safe_component(account_id, "account identifier")
    project = _safe_component(project_id, "project identifier")
    root = Path(workspace_root).absolute()
    if root.exists() and root.is_symlink():
        raise ProjectPathError("the workspace cannot be a symbolic link")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()

    account_root = root / "accounts"
    account_dir = account_root / account
    projects_dir = account_dir / "projects"
    candidate = projects_dir / project
    for path in (account_root, account_dir, projects_dir, candidate):
        if path.is_symlink():
            raise ProjectPathError(f"unsafe project path: symbolic link {path}")

    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    resolved = candidate.resolve(strict=False)
    lexical = candidate.absolute()
    if resolved != lexical:
        raise ProjectPathError("project path outside its private folder")
    try:
        if os.path.commonpath((str(root), str(resolved))) != str(root):
            raise ProjectPathError("project path outside the workspace")
    except ValueError as exc:
        raise ProjectPathError("project path on a different volume") from exc
    return resolved
