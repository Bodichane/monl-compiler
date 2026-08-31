"""Refuse une publication quand le tag et la version déclarée divergent."""

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
    """Le tag ne décrit pas la version que le paquet va publier."""


def read_declared_version(pyproject: Path = Path("pyproject.toml")) -> str:
    """Lit la version de distribution dans le fichier de métadonnées."""
    with pyproject.open("rb") as fichier:
        project = tomllib.load(fichier)["project"]
    return project["version"]


def validate_tag_version(tag: str, declared_version: str) -> None:
    """Lève une erreur si *tag* et *declared_version* ne sont pas équivalents.

    ``Version`` est la normalisation officielle de Packaging : elle reconnaît
    par exemple ``0.9.0-beta.8`` et ``0.9.0b8`` comme une même version Python.
    Une égalité de chaînes refuserait à tort cette publication correcte.
    """
    if not tag.startswith("v") or tag == "v":
        raise PublicationVersionError(
            f"Publication refusée : le tag {tag!r} doit commencer par v et porter une version"
        )

    tag_text = tag[1:]
    try:
        tag_version = Version(tag_text)
        project_version = Version(declared_version)
    except InvalidVersion as error:
        raise PublicationVersionError(
            f"Publication refusée : tag {tag!r} et pyproject.toml {declared_version!r} "
            "ne portent pas des versions Python valides"
        ) from error

    if tag_version != project_version:
        raise PublicationVersionError(
            f"Publication refusée : tag {tag!r} (version {tag_text!r}) et "
            f"pyproject.toml {declared_version!r} divergent"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="nom du tag GitHub, par exemple v0.9.0b8")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="fichier pyproject.toml à vérifier",
    )
    args = parser.parse_args(argv)

    declared_version = read_declared_version(args.pyproject)
    try:
        validate_tag_version(args.tag, declared_version)
    except PublicationVersionError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(
        f"Version validée : tag {args.tag!r} et pyproject.toml {declared_version!r} "
        "désignent la même version Python"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
