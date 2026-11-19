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

from .service import PlatformInputError, compiler_in, contract_summary

#: The name of each set returned by ``_contract_signature``, in order. The
#: first nine are compared as sets; the two DICTIONARIES (contents, mandatory
#: sections) carry one fingerprint per key — a value that changes without the
#: key moving is a real interface change (lesson of points 89, 94 and 96), so
#: "modified" exists.
SECTIONS = (
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


def _gap(previous, nouvelle, forme):
    added = sorted(set(nouvelle) - set(previous))
    retires = sorted(set(previous) - set(nouvelle))
    section = {"ajoutes": added, "retires": retires}
    if forme == "dictionnaire":
        section["modifies"] = sorted(
            key for key in set(previous) & set(nouvelle)
            if previous[key] != nouvelle[key]
        )
    return section


def delta_of_contract(old, new):
    """Names everything that changed between two frontend contracts.

    Returns one dictionary per heading, plus ``interface_inchangee`` — the
    only verdict that matters for someone who has already written their
    interface."""
    before = _contract_signature(old)
    apres = _contract_signature(new)
    rapport = {
        name: _gap(before[index], apres[index], forme)
        for index, (name, forme) in enumerate(SECTIONS)
    }
    rapport["interface_inchangee"] = not any(
        any(values) for section in rapport.values() if isinstance(section, dict)
        for values in section.values()
    )
    return rapport


def contract_dune_spec(service, spec):
    """Compiles a spec IN A THROWAWAY FOLDER and returns its contract.

    Nothing is written in the account's space: it is the discipline of
    ``monl diff`` (point 103), which asks the question of ``monl update``
    without modifying anything."""
    validation = service.validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])
    with tempfile.TemporaryDirectory(prefix="monl-diff-") as folder:
        path = Path(folder)
        spec_path = path / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        compiler_in(spec_path, path)
        contract = path / "frontend_contract.json"
        if not contract.is_file():
            raise PlatformInputError("The compilation produced no contract.")
        return json.loads(contract.read_text(encoding="utf-8"))


def recompile(service, project_id, spec):
    """Replaces a project's artifacts with those of a new spec.

    The new folder is produced IN FULL in a throwaway folder before the old
    one is touched: a failing compilation leaves the project exactly as it
    was. The delta is computed BEFORE the replacement — afterwards, the old
    contract no longer exists, and it is what says what remains to be written.

    The project's identity SURVIVES (``id``, ``created_at``): that is the
    whole point of recompiling rather than starting from a new project — the
    download address does not change. The summary, however, is rebuilt from
    the NEW contract: keeping it would make ``/api/projects/{id}`` lie."""
    old_contract = service.contract(project_id)
    directory = service._project_dir(project_id)
    validation = service.validate(spec)
    if not validation.valid:
        raise PlatformInputError(validation.errors[0])

    with tempfile.TemporaryDirectory(prefix="monl-update-") as folder:
        fresh = Path(folder) / "projet"
        fresh.mkdir()
        spec_path = fresh / "spec.ml"
        spec_path.write_text(spec, encoding="utf-8")
        compiler_in(spec_path, fresh)
        contract_path = fresh / "frontend_contract.json"
        if not contract_path.is_file():
            raise PlatformInputError("The compilation produced no contract.")
        new_contract = json.loads(contract_path.read_text(encoding="utf-8"))
        rapport = delta_of_contract(old_contract, new_contract)

        manifest_path = directory / "platform-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in directory.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        for entry in fresh.iterdir():
            target = directory / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)

    manifest["summary"] = contract_summary(new_contract)
    manifest["files"] = sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and path.name != ".jwt_secret"
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return rapport
