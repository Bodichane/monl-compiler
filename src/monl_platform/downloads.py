"""Downloadable monl artifacts, served by the platform.

A page that offers a download must offer a file that EXISTS: this module
reads a real folder, measures what it finds there and publishes its
fingerprint. Nothing is announced that is not on disk.

The requested name is compared to the list of files REALLY present, never
assembled from what the client sends: it is the only way to make path
traversal impossible rather than merely unlikely."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

#: Publishable extensions. A distribution folder can contain other things
#: (temporary folders, RECORD, build logs): only what installs is published.
PUBLISHABLE_SUFFIXES = (".whl", ".tar.gz")

#: A Python artifact name is already very constrained; checking it before even
#: looking at the disk avoids turning a hostile input into a file access.
ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9._+-]{1,120}$")

_CHUNK = 1024 * 1024


class DownloadError(RuntimeError):
    """The download folder is unusable."""


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
    """Describes a folder's publishable artifacts, from newest to oldest.

    A missing folder is not an error: the platform can run without a built
    distribution, and the page will then say how to start from the sources."""
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
    # The wheel first: it is what installs. The source archive is a fallback,
    # offering it first would make people choose the longer path.
    artifacts.sort(key=lambda item: (
        0 if item["kind"] == "wheel" else 1,
        -item["modified_at"],
        item["name"],
    ))
    return artifacts


def resolve_artifact(directory, name):
    """Returns the path of a publishable artifact, or ``None``.

    The comparison is made on the names of the files found, without ever
    concatenating the client's input to a path."""
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
    """Distribution folder, declared by the environment only."""
    environ = os.environ if environ is None else environ
    value = environ.get("MONL_PLATFORM_DOWNLOADS")
    if value is None:
        return None
    value = str(value).strip()
    return value or None
