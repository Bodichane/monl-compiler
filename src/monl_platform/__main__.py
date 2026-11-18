"""Point d'entrée : servir la plateforme, la sauvegarder, ou l'administrer."""

from __future__ import annotations

import argparse
import sys

import uvicorn


def _resume(fonction) -> str:
    """La première ligne de la docstring d'un verbe : c'est ce que `--help`
    en dit. Un verbe sans docstring fait échouer plutôt que d'afficher une
    ligne vide — une aide muette est le défaut de l'issue #84."""
    doc = (fonction.__doc__ or "").strip()
    if not doc:
        raise ValueError(f"verb {fonction.__name__} has no docstring")
    return doc.splitlines()[0]


def _aide_des_verbes() -> str:
    """L'épilogue de `monl-platform --help`, DÉRIVÉ de `VERBES`.

    Avant l'issue #84, l'aide de premier niveau ne décrivait que `--host` et
    `--port` : `admin` et `sauvegarde` n'étaient découvrables que par
    `docs/EXPLOITATION.md`, qui ne voyage pas dans la roue. Lire la table du
    dispatch (point 190) garantit qu'un verbe servi est un verbe annoncé.
    """
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
    """Gestes d'exploitation sur les comptes et les projets.

    Import PARESSEUX : l'administration tire la base, servir n'en a pas besoin.
    """
    from .administration import main as administrer

    return administrer(argv)


def _sauvegarder(argv: list[str]) -> int:
    """Copie cohérente de la base de comptes, serveur en marche.

    `monl-platform sauvegarde <destination>`.
    Passe par l'API de sauvegarde en ligne de SQLite plutôt que par une copie
    de fichier : la plateforme écrit en WAL, donc copier le `.sqlite3` d'un
    serveur en marche peut rendre une base amputée des dernières transactions.
    """
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


#: Les verbes de ``monl-platform``, et ce qu'ils appellent. C'est une TABLE et
#: non une suite de ``if`` parce que le dispatch la LIT : un verbe ajouté ici
#: est servi, et un verbe servi est forcément ici. La documentation est
#: confrontée à cette table (`tests/test_documentation.py`), ce qui n'aurait
#: aucune valeur si le témoin lisait une liste écrite pour lui — c'est
#: exactement le défaut du point 164, où la page `/mcp` annonçait quatre outils
#: inexistants parce que sa liste était recopiée à la main.
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
