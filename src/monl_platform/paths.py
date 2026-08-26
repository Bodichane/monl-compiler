"""Chemins de projets, confinés à un espace de travail de plateforme."""

import os
from pathlib import Path


class ProjectPathError(ValueError):
    """Un chemin fourni pour un projet ne respecte pas la frontière."""


def _safe_component(value, label):
    text = str(value)
    if not text or text in {".", ".."} or "\x00" in text:
        raise ProjectPathError(f"{label} invalide : remontée de chemin refusée")
    if "/" in text or "\\" in text:
        raise ProjectPathError(f"{label} invalide : séparateur de chemin refusé")
    return text


def project_directory(workspace_root, account_id, project_id, *, create=True):
    """Retourne le dossier privé d'un projet et vérifie ses symlinks.

    Les identifiants opaques texte issus de l'identité sont les seuls
    composants du chemin. Le slug reste une donnée de catalogue, jamais un
    chemin fourni par l'utilisateur. Un lien symbolique existant est refusé :
    sinon un dossier du compte A pourrait pointer vers les fichiers du compte B.
    """
    account = _safe_component(account_id, "identifiant de compte")
    project = _safe_component(project_id, "identifiant de projet")
    root = Path(workspace_root).absolute()
    if root.exists() and root.is_symlink():
        raise ProjectPathError("l'espace de travail ne peut pas être un lien symbolique")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()

    account_root = root / "accounts"
    account_dir = account_root / account
    projects_dir = account_dir / "projects"
    candidate = projects_dir / project
    for path in (account_root, account_dir, projects_dir, candidate):
        if path.is_symlink():
            raise ProjectPathError(f"chemin de projet non sûr : lien symbolique {path}")

    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    resolved = candidate.resolve(strict=False)
    lexical = candidate.absolute()
    if resolved != lexical:
        raise ProjectPathError("chemin de projet hors de son dossier privé")
    try:
        if os.path.commonpath((str(root), str(resolved))) != str(root):
            raise ProjectPathError("chemin de projet hors de l'espace de travail")
    except ValueError as exc:
        raise ProjectPathError("chemin de projet sur un volume différent") from exc
    return resolved
