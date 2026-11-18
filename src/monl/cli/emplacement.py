"""Where a project lives, and what monl knows about it.

POINT 105: does the folder exist, THEN does it hold a project.
`_erreur_de_chemin` asks the FIRST question, shared by the four entry
points — without it, `monl frontend` advised "run 'monl compile'" for a
folder never found."""

import hashlib
import json
import os
import sys

from ..frontend_contract import CONTRACT_FILENAME, contract_sha256
from ..parser.version import LANGUAGE_VERSION
from . import nomenclature, signature


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()

def _load_state(project_dir):
    path = os.path.join(project_dir, nomenclature.STATE_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def _erreur_de_chemin(project_dir, *, fichier_requis=None):
    """Error message for a missing folder or frontend artifact.

    POINT 105: "monl.json not found — this folder is not a monl project" was
    also shown when the folder did not exist at all, and `monl frontend` went
    as far as advising "run 'monl compile'". The message thus sent people to
    fix a missing compilation when it was the PATH that was wrong — an
    assumption shown as a diagnosis, exactly what point 97 holds against the
    rephrasing advice.

    Two levels, in the order the questions arise: does the folder exist, THEN
    does it hold a project. The frontend brief is the next level for the
    command that must give it to an AI: naming it here avoids letting a file
    open answer in place of the CLI."""
    if os.path.isdir(project_dir):
        if fichier_requis and not os.path.isfile(
                os.path.join(project_dir, fichier_requis)):
            return (f" ❌ Incomplete frontend contract: {fichier_requis} missing — "
                    "run 'monl compile' first.")
        return None
    lignes = [f" ❌ Directory not found: {project_dir}"]
    # The most common mistake, and the one that motivated this point: a
    # RELATIVE path written with a leading slash. `/projets/X` is not
    # "projets/X here" — it is "X in the projets folder AT THE SYSTEM ROOT",
    # which obviously does not exist.
    if project_dir.startswith(os.sep):
        voisin = project_dir.lstrip(os.sep)
        if os.path.isdir(voisin):
            lignes.append(
                f"    The path starts with '{os.sep}': it is searched from the "
                f"system root, not from here.")
            lignes.append(f"    Did you mean: {voisin}")
    lignes.append("    (the directory contents have not been inspected yet: "
                  "the path is the problem, not the compilation)")
    return "\n".join(lignes)

def _save_state(project_dir, spec_relpath, spec_source_path=None):
    from .. import __version__
    spec_path = spec_source_path or os.path.join(project_dir, spec_relpath)
    state = {
        "spec": spec_relpath,
        # POINT 85: WHAT this project was built with. Purely informative —
        # detecting a stale artifact (point 81) stays based on a regeneration,
        # because a version number may not move when generation has changed.
        # That is exactly what happened from points 74 to 84. The number serves
        # to NAME the gap, not to find it.
        "compiler_version": __version__,
        "language_version": LANGUAGE_VERSION,
        "spec_sha256": _sha256_file(spec_path),
        "contract_sha256": contract_sha256(project_dir),
        # POINT 64: fingerprint of the generated backend. "app.py stays sealed"
        # was a promise NOTHING measured: the consistency check only verified
        # that these files existed, and a hand edit went by silently — while
        # 'monl run' announces "spec ↔ backend ↔ contract ↔ frontend" as
        # verified. Discovered while writing the first test of the command
        # journey, not by rereading the code.
        "backend_sha256": {
            nom: _sha256_file(os.path.join(project_dir, nom))
            for nom in nomenclature.SCELLE_ARTEFACTS
            if os.path.exists(os.path.join(project_dir, nom))
        },
    }
    with open(os.path.join(project_dir, nomenclature.STATE_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return state

def _situer_projet(project_dir, geste):
    """(absolute folder, spec path) — or exit with an error.

    Shared by 'update' and 'diff': both start from the same state, and only
    one of them knowing how to read it would be one more divergence."""
    project_dir = os.path.abspath(project_dir)
    souci = _erreur_de_chemin(project_dir)
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(project_dir)
    if state is None:
        print(f" ❌ {nomenclature.STATE_FILENAME} not found — nothing to {geste} here.")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    return project_dir, spec_path

def _signature_precedente(project_dir):
    """The signature of the contract ALREADY in place, or empty sets if there is
    none yet — in which case everything is "added", which is accurate."""
    contract_path = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(contract_path):
        return (set(), set(), set(), set(), set(), set(), {}, set(), {}, {})
    with open(contract_path, encoding="utf-8") as fh:
        return signature._contract_signature(json.load(fh))

# ----------------------------------------------------------------- assets --
def _spec_du_projet(project_dir):
    """Path of a compiled project's spec, according to monl.json.

    Pass the path to assets_tool rather than making it reread monl.json: the
    project state is the CLI's business, and a second reader of monl.json
    would be a second place to fix."""
    souci = _erreur_de_chemin(os.path.abspath(project_dir))
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(os.path.abspath(project_dir))
    if state is None:
        print(f" ❌ {nomenclature.STATE_FILENAME} not found — this directory is not a compiled "
              "monl project (run 'monl' or 'monl compile').")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(os.path.abspath(project_dir), state["spec"])
    if not os.path.exists(spec_path):
        print(f" ❌ Spec not found: {spec_path}")
        sys.exit(1)
    return spec_path

def _assets_dir_du_projet(project_dir):
    """Declared assets folder, read from the CONTRACT and not from the spec.

    The contract is already derived from the spec and checked consistent with
    it: rereading it here avoids a second parser to drift. Returns None if
    the project declares none — the wrapper then adds no mount."""
    chemin = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(chemin):
        return None
    try:
        with open(chemin, encoding="utf-8") as fh:
            return (json.load(fh).get("assets") or {}).get("dir") or None
    except (OSError, ValueError):
        return None
