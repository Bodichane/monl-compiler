"""What changed between two compilations of the same project.

POINT 162. An agent could compile through MCP, never RECOMPILE: it had to
start again from a new project, hence a new address, without ever knowing
what the spec change implied for the already written interface. Yet that
is THE WHOLE action after the first compilation — and the journal shows
ten times (points 88 to 119) that an incomplete delta leaves an entire
screen to rewrite with nothing saying so.

**The delta is not recomputed here.** ``_contract_signature`` (monl.cli)
is the single source of the ten sets the contract promises; two delta
calculations would diverge, and it is the calculation ten points struggled
to keep right. This module only reads it for TWO contracts and names the
gap."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from monl.cli.signature import _contract_signature

from .service import PlatformInputError, compiler_dans, contract_summary

#: The name of each set returned by ``_contract_signature``, in order. The
#: first nine are compared as sets; the two DICTIONARIES (contents, mandatory
#: sections) carry one fingerprint per key — a value that changes without the
#: key moving is a real interface change (lesson of points 89, 94 and 96), so
#: "modified" exists.
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
    """Names everything that changed between two frontend contracts.

    Returns one dictionary per heading, plus ``interface_inchangee`` — the
    only verdict that matters for someone who has already written their
    interface."""
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
    """Compiles a spec IN A THROWAWAY FOLDER and returns its contract.

    Nothing is written in the account's space: it is the discipline of
    ``monl diff`` (point 103), which asks the question of ``monl update``
    without modifying anything."""
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
            raise PlatformInputError("The compilation produced no contract.")
        return json.loads(contrat.read_text(encoding="utf-8"))


def recompiler(service, project_id, spec):
    """Replaces a project's artifacts with those of a new spec.

    The new folder is produced IN FULL in a throwaway folder before the old
    one is touched: a failing compilation leaves the project exactly as it
    was. The delta is computed BEFORE the replacement — afterwards, the old
    contract no longer exists, and it is what says what remains to be written.

    The project's identity SURVIVES (``id``, ``created_at``): that is the
    whole point of recompiling rather than starting from a new project — the
    download address does not change. The summary, however, is rebuilt from
    the NEW contract: keeping it would make ``/api/projects/{id}`` lie."""
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
            raise PlatformInputError("The compilation produced no contract.")
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
