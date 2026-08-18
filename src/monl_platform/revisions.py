"""Snapshots durables des constructions de plateforme.

Un projet possède toujours un dossier actif, mais ce dossier peut être
réécrit par la construction suivante. Ce module conserve donc une copie
identifiée par le numéro de build, dans le même espace de travail et sur le
même filesystem. La copie est préparée ailleurs puis publiée par un rename
de répertoire : un snapshot visible est toujours complet.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REVISION_DIRNAME = "revisions"
SNAPSHOT_METADATA = "SNAPSHOT.json"


class SnapshotError(RuntimeError):
    """Le snapshot ne peut pas être créé de manière sûre."""


def _validate_build_id(build_id):
    if isinstance(build_id, bool) or not isinstance(build_id, int) or build_id < 1:
        raise SnapshotError("identifiant de construction invalide")


def _ignore(_directory, names):
    ignored = set()
    for name in names:
        if name == REVISION_DIRNAME or name == "__pycache__":
            ignored.add(name)
        elif name.endswith(("-wal", "-shm")):
            # Ces fichiers SQLite sont des journaux vivants, pas des artefacts
            # de code. Les copier au milieu d'une transaction créerait une
            # sauvegarde incohérente.
            ignored.add(name)
        elif name.startswith((".monl-stage-", ".monl-backup-", ".monl-build-")):
            ignored.add(name)
    return ignored


def _reject_symlinks(root):
    for directory, directories, files in os.walk(root, followlinks=False):
        names = tuple(directories) + tuple(files)
        for name in names:
            path = Path(directory) / name
            if name == REVISION_DIRNAME:
                if path.is_symlink():
                    raise SnapshotError(f"snapshot refusé : lien symbolique dans {path}")
                continue
            if path.is_symlink():
                raise SnapshotError(f"snapshot refusé : lien symbolique dans {path}")
        directories[:] = [name for name in directories if name != REVISION_DIRNAME]


def _digest(root):
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name != SNAPSHOT_METADATA
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                total_bytes += len(chunk)
        file_count += 1
    return digest.hexdigest(), file_count, total_bytes


def create_snapshot(project_dir, build_id):
    """Copie un projet dans ``revisions/build-N`` et retourne ses métadonnées.

    Le dossier ``revisions`` est exclu de la copie afin que les versions ne
    s'imbriquent jamais. Les liens symboliques sont refusés plutôt que suivis,
    et les journaux SQLite vivants ne sont pas archivés.
    """
    _validate_build_id(build_id)
    source = Path(project_dir).absolute()
    if not source.is_dir() or source.is_symlink():
        raise SnapshotError(f"projet introuvable ou non sûr : {source}")
    _reject_symlinks(source)

    revisions = source / REVISION_DIRNAME
    revisions.mkdir(parents=True, exist_ok=True)
    relative = Path(REVISION_DIRNAME) / f"build-{build_id}"
    destination = source / relative
    if destination.exists() or destination.is_symlink():
        raise SnapshotError(f"snapshot déjà présent : {relative.as_posix()}")

    temporary_parent = Path(tempfile.mkdtemp(
        prefix=f".monl-snapshot-{build_id}-", dir=revisions
    ))
    payload = temporary_parent / "payload"
    try:
        shutil.copytree(source, payload, ignore=_ignore, symlinks=False)
        checksum, file_count, total_bytes = _digest(payload)
        metadata = {
            "schema_version": 1,
            "build_id": build_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifact_sha256": checksum,
            "file_count": file_count,
            "bytes": total_bytes,
        }
        (payload / SNAPSHOT_METADATA).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(payload, destination)
    except Exception as exc:
        raise SnapshotError(f"création du snapshot impossible : {exc}") from exc
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)

    return {
        "path": relative.as_posix(),
        "sha256": checksum,
        "bytes": total_bytes,
        "file_count": file_count,
    }
