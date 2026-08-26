"""Artefacts téléchargeables de monl, servis par la plateforme.

Une page qui propose un téléchargement doit proposer un fichier qui EXISTE :
ce module lit un dossier réel, mesure ce qu'il y trouve et en publie
l'empreinte. Rien n'est annoncé qui ne soit pas sur le disque.

Le nom demandé est comparé à la liste des fichiers RÉELLEMENT présents, jamais
assemblé à partir de ce que le client envoie : c'est la seule façon de rendre
la remontée de chemin impossible plutôt que simplement improbable.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

#: Extensions publiables. Un dossier de distribution peut contenir autre chose
#: (dossiers temporaires, RECORD, journaux de construction) : on ne publie que
#: ce qui s'installe.
PUBLISHABLE_SUFFIXES = (".whl", ".tar.gz")

#: Un nom d'artefact Python est déjà très contraint ; le vérifier avant même de
#: regarder le disque évite de transformer une entrée hostile en accès fichier.
ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9._+-]{1,120}$")

_CHUNK = 1024 * 1024


class DownloadError(RuntimeError):
    """Le dossier de téléchargement est inexploitable."""


def _is_publishable(path: Path) -> bool:
    name = path.name
    return path.is_file() and not path.is_symlink() and name.endswith(PUBLISHABLE_SUFFIXES)


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _kind(name: str) -> str:
    return "wheel" if name.endswith(".whl") else "sources"


def list_artifacts(directory) -> list[dict]:
    """Décrit les artefacts publiables d'un dossier, du plus récent au plus ancien.

    Un dossier absent n'est pas une erreur : la plateforme peut tourner sans
    distribution construite, et la page dira alors comment partir des sources.
    """
    if not directory:
        return []
    root = Path(directory)
    if not root.is_dir():
        return []
    artifacts = []
    for path in sorted(root.iterdir()):
        if not _is_publishable(path):
            continue
        checksum, size = _digest(path)
        artifacts.append({
            "name": path.name,
            "kind": _kind(path.name),
            "bytes": size,
            "sha256": checksum,
            "modified_at": int(path.stat().st_mtime),
        })
    # La roue d'abord : c'est ce qui s'installe. L'archive des sources est un
    # repli, la proposer en tête ferait choisir le chemin le plus long.
    artifacts.sort(key=lambda item: (
        0 if item["kind"] == "wheel" else 1,
        -item["modified_at"],
        item["name"],
    ))
    return artifacts


def resolve_artifact(directory, name):
    """Rend le chemin d'un artefact publiable, ou ``None``.

    La comparaison se fait sur le nom des fichiers trouvés, sans jamais
    concaténer l'entrée du client à un chemin.
    """
    if not directory or not isinstance(name, str) or not ARTIFACT_NAME.match(name):
        return None
    root = Path(directory)
    if not root.is_dir():
        return None
    for path in root.iterdir():
        if path.name == name and _is_publishable(path):
            return path
    return None


def default_directory(environ=None) -> str | None:
    """Dossier de distribution, déclaré par l'environnement uniquement."""
    environ = os.environ if environ is None else environ
    value = environ.get("MONL_PLATFORM_DOWNLOADS")
    if value is None:
        return None
    value = str(value).strip()
    return value or None
