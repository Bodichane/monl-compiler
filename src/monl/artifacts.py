"""Transactional publication of the artifacts MONL produces.

Generation first writes into a temporary folder on the same filesystem as
the project. ``publish_files`` then replaces the files with backup and
restore on failure. This does not claim to make several files atomic at
the POSIX level; it does guarantee, however, that a publication error
does not leave a mix of backend/contract/state coming from two different
compilations."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .errors import ProjectStateError


class ArtifactPublicationError(ProjectStateError):
    """Publication error, after an attempt to restore the project."""


def staging_directory(target_dir: str | os.PathLike[str]) -> tempfile.TemporaryDirectory:
    """Returns a staging folder next to ``target_dir``.

    Being next to it matters: ``os.replace`` thus stays on the same filesystem
    and keeps its replace-without-partial-copy behavior."""
    target = Path(target_dir).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=f".{target.name}.monl-stage-",
                                        dir=target.parent)


def copy_preserved_files(source_dir: str | os.PathLike[str],
                         staging_dir: str | os.PathLike[str],
                         names: Iterable[str]) -> None:
    """Copies into staging the files the compilation must preserve."""
    source = Path(source_dir)
    staging = Path(staging_dir)
    for name in names:
        original = source / name
        if not original.is_file():
            continue
        destination = staging / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)


def _replace(source: Path, destination: Path) -> None:
    """Testable indirection around ``os.replace``."""
    os.replace(source, destination)


#: The `custom` blocks module. Named here because TWO layers decide whether to
#: publish it — generation and the command line — and two implementations of
#: the same rule always end up diverging.
SANDBOX_FILENAME = "sandbox_ai.py"


def sans_sandbox(noms):
    """Removes the `custom` module from a list of artifacts.

    A project without a `custom` block gets none: the file only contained a
    comment, `app.py` imported it without ever calling it, and deleting it
    made startup fail. A file that does nothing and cannot be removed has no
    place in a delivered archive."""
    return tuple(nom for nom in noms if nom != SANDBOX_FILENAME)


def publish_files(staging_dir: str | os.PathLike[str],
                  target_dir: str | os.PathLike[str],
                  names: Iterable[str]) -> None:
    """Publishes ``names`` with full rollback if a replacement fails.

    The sources must all exist before the first replacement. Unlisted files,
    notably ``frontend/`` and the user's assets, are never touched."""
    staging = Path(staging_dir).absolute()
    target = Path(target_dir).absolute()
    selected = tuple(dict.fromkeys(names))
    missing = [name for name in selected if not (staging / name).is_file()]
    if missing:
        raise ArtifactPublicationError(
            "Artifacts missing from staging: " + ", ".join(missing))

    target.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix=f".{target.name}.monl-backup-",
                                        dir=target.parent))
    installed: list[str] = []
    backups: list[str] = []
    try:
        for name in selected:
            source = staging / name
            destination = target / name
            backup = backup_dir / name
            # An artifact can live in a subfolder (`docs/…`): without this
            # `mkdir`, `os.replace` raises `FileNotFoundError` on a missing
            # folder — and the whole publication would be cancelled for a
            # folder that only needed to be created. `copy_preserved_files`
            # already did it on its side; the two layers now match.
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                _replace(destination, backup)
                backups.append(name)
            _replace(source, destination)
            installed.append(name)
    except Exception as exc:
        # Remove the new files, including those whose old content did not
        # exist.
        for name in reversed(installed):
            destination = target / name
            if destination.exists():
                destination.unlink()
        # Restore each old file moved into the backup.
        for name in reversed(backups):
            backup = backup_dir / name
            destination = target / name
            if backup.exists():
                _replace(backup, destination)
        raise ArtifactPublicationError(
            "Publication interrupted: previous artifacts have been restored."
        ) from exc
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


#: Documents that are READ live in `docs/`; the root keeps what is EXECUTED. An
#: archive whose fifteen files are flat cannot be read: one cannot tell what is
#: run from what is consulted.
DOCS_DIR = "docs"


def chemin_pret(base, nom):
    """The path of an artifact, its folder created if needed.

    An artifact can live in `docs/`: opening it for writing without having
    created the folder raises `FileNotFoundError`, and the staging is always
    fresh, so the folder never exists there the first time."""
    cible = Path(base) / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    return cible


def deplacer_vers_docs(project_dir, chemins):
    """Tidies up, only once, the documents left at the root.

    Projects compiled BEFORE this tidy-up carry these files at the root.
    Simply writing to the new location would leave them in place, stale and
    without a word — exactly the reproach made to `sandbox_ai.py`, and the
    defect would be worse here: a hand-edited `DESIGN_SPEC.md` is human work,
    and the preserved copy would look for it where it no longer is.

    We therefore MOVE, which keeps the customization and orphans nothing. A
    file already present at the new location wins: it is the one the
    compilation just produced or the author keeps up to date."""
    racine = Path(project_dir)
    deplaces = []
    for chemin in chemins:
        cible = racine / chemin
        ancien = racine / Path(chemin).name
        if cible.exists() or not ancien.is_file() or ancien == cible:
            continue
        cible.parent.mkdir(parents=True, exist_ok=True)
        _replace(ancien, cible)
        deplaces.append(chemin)
    return deplaces
