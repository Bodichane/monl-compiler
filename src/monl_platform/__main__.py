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
    parser.add_argument("--garder", type=int, default=0, metavar="N",
                        help="Ne conserver que les N sauvegardes les plus récentes "
                             "du même dossier. 0 (défaut) n'efface rien.")
    args = parser.parse_args(argv)

    magasin = IdentityStore(CompilationService(args.workspace).workspace)
    cible = magasin.sauvegarder(args.destination)
    print(f"Base sauvegardée : {cible} ({cible.stat().st_size} octets)")
    for perimee in _rotation(cible, args.garder):
        print(f"Sauvegarde retirée : {perimee}")
    print("Les dossiers de projets ne sont PAS inclus : ils sont temporaires "
          "et régénérables depuis les specs.")
    return 0


def _rotation(cible, garder: int) -> list:
    """Retire les sauvegardes en trop, et rend la liste de ce qui est parti.

    Une sauvegarde périodique sans rotation remplit le disque, et un disque
    plein arrête le service qu'elle était censée protéger — la sauvegarde
    devient alors la panne. La rotation vit ICI plutôt que dans un script de
    l'exploitant : c'est la même commande qui écrit et qui range, donc les
    deux ne peuvent pas diverger.

    Le tri se fait sur la date de modification, jamais sur le NOM : un gabarit
    de nom est au choix de l'exploitant, et un tri alphabétique sur
    `base-2026-8-9` contre `base-2026-12-1` effacerait la mauvaise.

    Ne touche qu'aux fichiers du même dossier portant le même suffixe que la
    cible : un dossier de sauvegardes partagé avec autre chose ne doit pas
    être vidé par inadvertance.
    """
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
