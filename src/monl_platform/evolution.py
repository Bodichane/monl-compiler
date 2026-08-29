"""Ce qui a changé entre deux compilations d'un même projet.

POINT 162. Un agent pouvait compiler par MCP, jamais RECOMPILER : il fallait
repartir d'un projet neuf, donc d'une adresse neuve, sans jamais savoir ce que
le changement de spec impliquait pour l'interface déjà écrite. Or c'est TOUT le
geste après la première compilation — et le journal montre dix fois (points 88
à 119) qu'un delta incomplet laisse un écran entier à réécrire sans que rien ne
le dise.

**Le delta n'est pas recalculé ici.** ``_contract_signature`` (monl.cli) est la
source unique des dix ensembles que le contrat promet ; deux calculs de delta
divergeraient, et c'est le calcul que dix points ont eu du mal à tenir juste.
Ce module se borne à le lire pour DEUX contrats et à nommer l'écart.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from monl.cli.signature import _contract_signature

from .service import PlatformInputError, compiler_dans, contract_summary

#: Le nom de chaque ensemble rendu par ``_contract_signature``, dans l'ordre.
#: Les neuf premiers sont comparés comme des ensembles ; les deux
#: DICTIONNAIRES (contenus, sections obligatoires) portent une empreinte par
#: clé — une valeur qui change sans que la clé bouge est un vrai changement
#: d'interface (leçon des points 89, 94 et 96), donc « modifié » existe.
RUBRIQUES = (
    ("routes", "ensemble"),
    ("champs", "ensemble"),
    ("acces", "ensemble"),
    ("lecture_seule", "ensemble"),
    ("prealables", "ensemble"),
    ("verrous", "ensemble"),
    ("contenus", "dictionnaire"),
    ("rattachements", "ensemble"),
    ("types_de_champs", "dictionnaire"),
    ("sections_obligatoires", "dictionnaire"),
)


def _ecart(ancienne, nouvelle, forme):
    ajoutes = sorted(set(nouvelle) - set(ancienne))
    retires = sorted(set(ancienne) - set(nouvelle))
    rubrique = {"ajoutes": ajoutes, "retires": retires}
    if forme == "dictionnaire":
        rubrique["modifies"] = sorted(
            cle for cle in set(ancienne) & set(nouvelle)
            if ancienne[cle] != nouvelle[cle]
        )
    return rubrique


def delta_de_contrat(ancien, nouveau):
    """Nomme tout ce qui a changé entre deux contrats frontend.

    Rend un dictionnaire par rubrique, plus ``interface_inchangee`` — le seul
    verdict qui compte pour qui a déjà écrit son interface.
    """
    avant = _contract_signature(ancien)
    apres = _contract_signature(nouveau)
    rapport = {
        nom: _ecart(avant[index], apres[index], forme)
        for index, (nom, forme) in enumerate(RUBRIQUES)
    }
    rapport["interface_inchangee"] = not any(
        any(valeurs) for rubrique in rapport.values() if isinstance(rubrique, dict)
        for valeurs in rubrique.values()
    )
    return rapport


def contrat_dune_spec(service, spec):
    """Compile une spec DANS UN DOSSIER JETABLE et rend son contrat.

    Rien n'est écrit dans l'espace du compte : c'est la discipline de
    ``monl diff`` (point 103), qui pose la question de ``monl update`` sans
    rien modifier.
    """
    validation = service.validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])
    with tempfile.TemporaryDirectory(prefix="monl-diff-") as dossier:
        chemin = Path(dossier)
        spec_path = chemin / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        compiler_dans(spec_path, chemin)
        contrat = chemin / "frontend_contract.json"
        if not contrat.is_file():
            raise PlatformInputError("La compilation n'a produit aucun contrat.")
        return json.loads(contrat.read_text(encoding="utf-8"))


def recompiler(service, project_id, spec):
    """Remplace les artefacts d'un projet par ceux d'une spec nouvelle.

    Le nouveau dossier est produit EN ENTIER dans un dossier jetable avant que
    l'ancien ne soit touché : une compilation qui échoue laisse le projet
    exactement comme il était. Le delta est calculé AVANT le remplacement —
    après, l'ancien contrat n'existe plus, et c'est lui qui dit ce qu'il reste
    à écrire.

    L'identité du projet SURVIT (``id``, ``created_at``) : c'est tout l'intérêt
    de recompiler plutôt que de repartir d'un projet neuf — l'adresse de
    téléchargement ne change pas. Le résumé, lui, est refait depuis le NOUVEAU
    contrat : le garder ferait mentir ``/api/projects/{id}``.
    """
    ancien_contrat = service.contract(project_id)
    directory = service._project_dir(project_id)
    validation = service.validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])

    with tempfile.TemporaryDirectory(prefix="monl-update-") as dossier:
        neuf = Path(dossier) / "projet"
        neuf.mkdir()
        spec_path = neuf / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        compiler_dans(spec_path, neuf)
        contrat_path = neuf / "frontend_contract.json"
        if not contrat_path.is_file():
            raise PlatformInputError("La compilation n'a produit aucun contrat.")
        nouveau_contrat = json.loads(contrat_path.read_text(encoding="utf-8"))
        rapport = delta_de_contrat(ancien_contrat, nouveau_contrat)

        manifeste_path = directory / "platform-manifest.json"
        manifeste = json.loads(manifeste_path.read_text(encoding="utf-8"))
        for entree in directory.iterdir():
            if entree.is_dir():
                shutil.rmtree(entree)
            else:
                entree.unlink()
        for entree in neuf.iterdir():
            cible = directory / entree.name
            if entree.is_dir():
                shutil.copytree(entree, cible)
            else:
                shutil.copy2(entree, cible)

    manifeste["summary"] = contract_summary(nouveau_contrat)
    manifeste["files"] = sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and path.name != ".jwt_secret"
    )
    manifeste_path.write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")
    return rapport
