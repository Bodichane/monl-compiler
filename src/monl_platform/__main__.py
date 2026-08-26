"""Point d'entrée : servir la plateforme, ou sauvegarder sa base."""

from __future__ import annotations

import argparse
import sys

import uvicorn


def _sauvegarder(argv: list[str]) -> int:
    """`monl-platform sauvegarde <destination>`.

    Passe par l'API de sauvegarde en ligne de SQLite plutôt que par une copie
    de fichier : la plateforme écrit en WAL, donc copier le `.sqlite3` d'un
    serveur en marche peut rendre une base amputée des dernières transactions.
    """
    from .identity import IdentityStore
    from .service import CompilationService

    parser = argparse.ArgumentParser(
        prog="monl-platform sauvegarde",
        description="Copie cohérente de la base de comptes, serveur en marche.")
    parser.add_argument("destination", help="Chemin du fichier de sauvegarde à écrire.")
    parser.add_argument("--workspace", default=None,
                        help="Espace de travail (par défaut MONL_PLATFORM_WORKSPACE).")
    args = parser.parse_args(argv)

    magasin = IdentityStore(CompilationService(args.workspace).workspace)
    cible = magasin.sauvegarder(args.destination)
    print(f"Base sauvegardée : {cible} ({cible.stat().st_size} octets)")
    print("Les dossiers de projets ne sont PAS inclus : ils sont temporaires "
          "et régénérables depuis les specs.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "sauvegarde":
        return _sauvegarder(argv[1:])

    parser = argparse.ArgumentParser(description="Plateforme web Monl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8022)
    args = parser.parse_args(argv)
    uvicorn.run("monl_platform.app:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
