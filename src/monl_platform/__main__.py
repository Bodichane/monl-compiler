"""Entry point: serve the platform, back it up, or administer it."""

from __future__ import annotations

import argparse
import sys

import uvicorn


def _resume(fonction) -> str:
    """The first line of a verb's docstring: it is what `--help` says about it.
    A verb without a docstring fails rather than displaying an empty line — a
    mute help is the defect of issue #84."""
    doc = (fonction.__doc__ or "").strip()
    if not doc:
        raise ValueError(f"verb {fonction.__name__} has no docstring")
    return doc.splitlines()[0]


def _aide_des_verbes() -> str:
    """The epilog of `monl-platform --help`, DERIVED from `VERBES`.

    Before issue #84, the top-level help only described `--host` and
    `--port`: `admin` and `sauvegarde` could only be discovered through
    `docs/EXPLOITATION.md`, which does not travel in the wheel. Reading the
    dispatch table (point 190) guarantees that a served verb is an announced
    verb."""
    largeur = max(len(nom) for nom in VERBES)
    lignes = [f"  {nom.ljust(largeur)}  {_resume(fonction)}"
              for nom, fonction in VERBES.items()]
    return ("commands (no command: serve the platform):\n"
            + "\n".join(lignes)
            + "\n\nHelp for a command: monl-platform <command> --help")


def _build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monl-platform",
        description="Plateforme web Monl",
        epilog=_aide_des_verbes(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8022)
    return parser


def _administrer(argv: list[str]) -> int:
    """Operational actions on accounts and projects.

    LAZY import: administration pulls in the database, serving does not need
    it."""
    from .administration import main as administrer

    return administrer(argv)


def _sauvegarder(argv: list[str]) -> int:
    """Consistent copy of the accounts database, with the server running.

    `monl-platform sauvegarde <destination>`.
    Goes through SQLite's online backup API rather than a file copy: the
    platform writes in WAL, so copying the `.sqlite3` of a running server can
    yield a database missing its latest transactions."""
    from .identity import IdentityStore
    from .service import CompilationService

    parser = argparse.ArgumentParser(
        prog="monl-platform sauvegarde",
        description="Consistent copy of the accounts database, with the server running.")
    parser.add_argument("destination", help="Path of the backup file to write.")
    parser.add_argument("--workspace", default=None,
                        help="Workspace (default: MONL_PLATFORM_WORKSPACE).")
    parser.add_argument("--garder", type=int, default=0, metavar="N",
                        help="Keep only the N most recent backups "
                             "in the same folder. 0 (default) deletes nothing.")
    args = parser.parse_args(argv)

    magasin = IdentityStore(CompilationService(args.workspace).workspace)
    cible = magasin.sauvegarder(args.destination)
    print(f"Database backed up: {cible} ({cible.stat().st_size} bytes)")
    for perimee in _rotation(cible, args.garder):
        print(f"Backup removed: {perimee}")
    print("Project folders are NOT included: they are temporary "
          "and can be regenerated from the specs.")
    return 0


def _rotation(cible, garder: int) -> list:
    """Removes the extra backups, and returns the list of what went.

    A periodic backup without rotation fills the disk, and a full disk stops
    the service it was meant to protect — the backup then becomes the outage.
    Rotation lives HERE rather than in an operator's script: it is the same
    command that writes and tidies, so the two cannot diverge.

    Sorting is done on the modification date, never on the NAME: a name
    pattern is the operator's choice, and an alphabetical sort of
    `base-2026-8-9` against `base-2026-12-1` would erase the wrong one.

    Only touches files in the same folder carrying the same suffix as the
    target: a backup folder shared with something else must not be emptied by
    accident."""
    if garder <= 0:
        return []
    voisines = sorted(
        (f for f in cible.parent.iterdir()
         if f.is_file() and f.suffix == cible.suffix),
        key=lambda f: f.stat().st_mtime, reverse=True)
    retirees = []
    for perimee in voisines[garder:]:
        perimee.unlink()
        retirees.append(perimee)
    return retirees


#: The verbs of ``monl-platform``, and what they call. It is a TABLE and not a
#: series of ``if``s because the dispatch READS it: a verb added here is
#: served, and a served verb is necessarily here. The documentation is compared
#: to this table (`tests/test_documentation.py`), which would have no value if
#: the witness read a list written for it — it is exactly the defect of point
#: 164, where the `/mcp` page announced four nonexistent tools because its list
#: was copied by hand.
VERBES = {
    "sauvegarde": _sauvegarder,
    "admin": _administrer,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in VERBES:
        return VERBES[argv[0]](argv[1:])

    parser = _build_serve_parser()
    args = parser.parse_args(argv)
    uvicorn.run("monl_platform.app:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
