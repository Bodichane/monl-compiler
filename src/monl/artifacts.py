"""Publication transactionnelle des artefacts produits par MONL.

La génération écrit d'abord dans un dossier temporaire situé sur le même
filesystem que le projet. ``publish_files`` remplace ensuite les fichiers
avec sauvegarde et restauration en cas d'échec. Cela ne prétend pas rendre
plusieurs fichiers atomiques au niveau POSIX ; cela garantit en revanche qu'une
erreur de publication ne laisse pas un mélange backend/contrat/état issu de
deux compilations différentes.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .errors import ProjectStateError


class ArtifactPublicationError(ProjectStateError):
    """Erreur de publication, après tentative de restauration du projet."""


def staging_directory(target_dir: str | os.PathLike[str]) -> tempfile.TemporaryDirectory:
    """Retourne un dossier de staging voisin de ``target_dir``.

    Le voisinage est important : ``os.replace`` reste ainsi sur le même
    filesystem et conserve son comportement de remplacement sans copie
    partielle.
    """
    target = Path(target_dir).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=f".{target.name}.monl-stage-",
                                        dir=target.parent)


def copy_preserved_files(source_dir: str | os.PathLike[str],
                         staging_dir: str | os.PathLike[str],
                         names: Iterable[str]) -> None:
    """Copie dans le staging les fichiers que la compilation doit préserver."""
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
    """Indirection testable autour de ``os.replace``."""
    os.replace(source, destination)


#: Le module des blocs `custom`. Nommé ici parce que DEUX couches décident de
#: le publier ou non — la génération et la ligne de commande — et que deux
#: mises en œuvre d'une même règle finissent toujours par diverger.
SANDBOX_FILENAME = "sandbox_ai.py"


def sans_sandbox(noms):
    """Retire le module `custom` d'une liste d'artefacts.

    Un projet sans bloc `custom` n'en reçoit pas : le fichier ne contenait
    qu'un commentaire, `app.py` l'importait sans jamais l'appeler, et le
    supprimer faisait échouer le démarrage. Un fichier qui ne fait rien et
    qu'on ne peut pas enlever n'a pas sa place dans une archive livrée.
    """
    return tuple(nom for nom in noms if nom != SANDBOX_FILENAME)


def publish_files(staging_dir: str | os.PathLike[str],
                  target_dir: str | os.PathLike[str],
                  names: Iterable[str]) -> None:
    """Publie ``names`` avec rollback complet si un remplacement échoue.

    Les sources doivent toutes exister avant le premier remplacement. Les
    fichiers non listés, notamment ``frontend/`` et les assets utilisateur,
    ne sont jamais touchés.
    """
    staging = Path(staging_dir).absolute()
    target = Path(target_dir).absolute()
    selected = tuple(dict.fromkeys(names))
    missing = [name for name in selected if not (staging / name).is_file()]
    if missing:
        raise ArtifactPublicationError(
            "Artefacts manquants dans le staging : " + ", ".join(missing))

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
            # Un artefact peut vivre dans un sous-dossier (`docs/…`) : sans ce
            # `mkdir`, `os.replace` lève `FileNotFoundError` sur un dossier
            # absent — et la publication entière serait annulée pour un dossier
            # qu'il suffisait de créer. `copy_preserved_files` le faisait déjà
            # de son côté ; les deux couches se répondent maintenant.
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                _replace(destination, backup)
                backups.append(name)
            _replace(source, destination)
            installed.append(name)
    except Exception as exc:
        # Retirer les nouveaux fichiers, y compris ceux dont l'ancien contenu
        # n'existait pas.
        for name in reversed(installed):
            destination = target / name
            if destination.exists():
                destination.unlink()
        # Restaurer chaque ancien fichier déplacé dans le backup.
        for name in reversed(backups):
            backup = backup_dir / name
            destination = target / name
            if backup.exists():
                _replace(backup, destination)
        raise ArtifactPublicationError(
            "Publication interrompue : les artefacts précédents ont été restaurés."
        ) from exc
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


#: Les documents qui se LISENT vivent dans `docs/` ; la racine garde ce qui
#: s'EXÉCUTE. Une archive dont les quinze fichiers sont à plat ne se lit pas :
#: on ne distingue pas ce qu'on lance de ce qu'on consulte.
DOCS_DIR = "docs"


def chemin_pret(base, nom):
    """Le chemin d'un artefact, son dossier créé si besoin.

    Un artefact peut vivre dans `docs/` : l'ouvrir en écriture sans avoir créé
    le dossier lève `FileNotFoundError`, et le staging est toujours neuf, donc
    le dossier n'y existe jamais la première fois.
    """
    cible = Path(base) / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    return cible


def deplacer_vers_docs(project_dir, chemins):
    """Range une seule fois les documents restés à la racine.

    Les projets compilés AVANT ce rangement portent ces fichiers à la racine.
    Écrire simplement au nouvel emplacement les laisserait sur place, périmés
    et sans un mot — c'est exactement le reproche fait à `sandbox_ai.py`, et
    le défaut serait pire ici : un `DESIGN_SPEC.md` retouché à la main est du
    travail humain, et la copie préservée irait le chercher où il n'est plus.

    On DÉPLACE donc, ce qui garde la personnalisation et n'orpheline rien. Un
    fichier déjà présent au nouvel emplacement gagne : c'est lui que la
    compilation vient de produire ou que l'auteur tient à jour.
    """
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
