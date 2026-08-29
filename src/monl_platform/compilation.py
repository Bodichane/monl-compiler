"""Compiler un projet DANS son dossier privé, sans une once d'IA.

POINT 162. C'est ce qui reste de ``builder.py`` une fois le constructeur
frontend retiré. L'ancien ``build_project`` enchaînait cinq choses — quota,
écriture de la spec, compilation, ``generate_and_verify`` (l'IA), snapshot —
et facturait les quatre dernières à la plateforme. Le cap ayant changé, seule
la troisième subsiste : la plateforme compile, l'usager construit son
interface chez lui avec SON fournisseur.

Ce que ça retire, et qu'on ne remet pas : le quota (il n'y a plus rien à
facturer), la file de constructions (une compilation dure une seconde, elle
n'a pas besoin d'être mise en attente ni suivie à la trace), et le snapshot
(il datait d'un temps où le dossier servi pouvait différer du dossier
compilé — désormais c'est le même, voir ``hosting.py``).

L'isolation de la compilation est celle du socle : ``compiler_isole`` lance le
compilateur dans un sous-processus limité. La plateforme compile des specs
FOURNIES, elle ne les exécute jamais dans son propre interpréteur.
"""

from __future__ import annotations

import json

from .paths import ProjectPathError, project_directory
from .service import (
    CompilationService,
    PlatformExecutionError,
    PlatformInputError,
    compiler_dans,
)


class ProjectIsolationError(RuntimeError):
    """Le projet demandé n'appartient pas au compte, ou son chemin n'est pas sûr."""


def compiler_le_projet(project_id, *, account_id, store, workspace_root, service=None):
    """Compile ``spec.ml`` du dossier privé d'un projet et rend son contrat.

    ``service`` sert uniquement à valider la spec avant de lancer le worker :
    un refus du validateur est une faute d'entrée (message lisible), pas une
    panne d'exécution — la distinction porte le code HTTP de la route.
    """
    project = store.get_project_for_user(account_id, project_id)
    if project is None:
        raise ProjectIsolationError(
            f"projet {project_id} introuvable pour le compte {account_id}"
        )
    try:
        project_dir = project_directory(
            workspace_root, account_id, project["project_id"], create=True
        )
    except ProjectPathError as exc:
        raise ProjectIsolationError(str(exc)) from exc

    spec_path = project_dir / "spec.ml"
    if not spec_path.is_file():
        raise PlatformInputError("La spécification du projet est introuvable.")
    spec = spec_path.read_text(encoding="utf-8")

    validation = (service or CompilationService(workspace_root)).validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])

    sortie = compiler_dans(spec_path, project_dir)
    contrat_path = project_dir / "frontend_contract.json"
    if not contrat_path.is_file():
        raise PlatformExecutionError(
            "La compilation n'a produit aucun contrat frontend."
        )
    contrat = json.loads(contrat_path.read_text(encoding="utf-8"))
    return {
        "project_id": project["project_id"],
        "directory": str(project_dir),
        "contract": contrat,
        "compiler_output": sortie,
        "files": sorted(
            str(path.relative_to(project_dir))
            for path in project_dir.rglob("*")
            if path.is_file() and path.name != ".jwt_secret"
        ),
    }
