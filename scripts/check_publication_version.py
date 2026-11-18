"""Refuses a publication when the tag and the declared version diverge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from packaging.version import InvalidVersion, Version


class PublicationVersionError(ValueError):
    """The tag does not describe the version the package is about to publish."""


def read_declared_version(pyproject: Path = Path("pyproject.toml")) -> str:
    """Reads the distribution version from the metadata file."""
    with pyproject.open("rb") as fichier:
        project = tomllib.load(fichier)["project"]
    return project["version"]


def validate_tag_version(tag: str, declared_version: str) -> None:
    """Raises if *tag* and *declared_version* are not equivalent.

    ``Version`` is Packaging's official normalization: it recognizes, for
    example, ``0.9.0-beta.8`` and ``0.9.0b8`` as one and the same Python
    version. String equality would wrongly refuse this correct publication.
    """
    if not tag.startswith("v") or tag == "v":
        raise PublicationVersionError(
            f"Publication refused: tag {tag!r} must start with v and carry a version"
        )

    tag_text = tag[1:]
    try:
        tag_version = Version(tag_text)
        project_version = Version(declared_version)
    except InvalidVersion as error:
        raise PublicationVersionError(
            f"Publication refused: tag {tag!r} and pyproject.toml {declared_version!r} "
            "do not carry valid Python versions"
        ) from error

    if tag_version != project_version:
        raise PublicationVersionError(
            f"Publication refused: tag {tag!r} (version {tag_text!r}) and "
            f"pyproject.toml {declared_version!r} diverge"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="GitHub tag name, for example v0.9.0b8")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="pyproject.toml file to check",
    )
    args = parser.parse_args(argv)

    declared_version = read_declared_version(args.pyproject)
    try:
        validate_tag_version(args.tag, declared_version)
    except PublicationVersionError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(
        f"Version validated: tag {args.tag!r} and pyproject.toml {declared_version!r} "
        "designate the same Python version"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
