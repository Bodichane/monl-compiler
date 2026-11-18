"""`monl run --check` : le site livré tient-il la promesse du contrat.

La détection d'artefacts périmés compare à une RÉGÉNÉRATION, jamais à un
numéro de version — `__version__` n'avait pas bougé pendant les points 74
à 81, un tampon n'aurait rien vu."""

import contextlib
import io
import json
import os
import re
import tempfile

from ..ast_validator import MonlAST
from ..frontend_contract import (
    CONTRACT_FILENAME,
    contract_sha256,
    generate_frontend_contract,
)
from ..generator import MonlSecureGenerator
from ..parser import parse_monl_file
from . import couverture, emplacement, nomenclature


# ------------------------------------------------------------ cohérence ----
def _empreintes_regenerees(spec_path):
    """Empreintes des artefacts qu'une recompilation produirait MAINTENANT,
    ou None si la spec ne compile plus (le contrôle ne doit pas devenir une
    panne : la spec modifiée est déjà signalée par son propre contrôle).

    La recompilation a lieu dans un dossier temporaire — le projet n'est jamais
    touché — et sa sortie est capturée : un contrôle de cohérence n'a pas à
    rejouer l'audit de sécurité à l'écran."""

    empreintes = {}
    with tempfile.TemporaryDirectory() as temporaire:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # base_dir = le dossier de la SPEC, pas le dossier temporaire :
                # c'est là que vivent les assets à vérifier (brique 13).
                normalized = MonlAST(
                    parse_monl_file(spec_path),
                    base_dir=os.path.dirname(os.path.abspath(spec_path)),
                ).validate_and_audit()
                generator = MonlSecureGenerator(normalized, output_dir=temporaire)
                generator.generate_all()
                generate_frontend_contract(normalized, generator, temporaire)
        except Exception:
            return None
        for nom in ("app.py", "schema.sql", "sandbox_ai.py", CONTRACT_FILENAME):
            chemin = os.path.join(temporaire, nom)
            if os.path.exists(chemin):
                empreintes[nom] = emplacement._sha256_file(chemin)
    return empreintes

def check_coherence(project_dir):
    """Vérifie que spec, backend, contrat et frontend forment un ensemble
    cohérent. Retourne (ok, erreurs, avertissements)."""
    project_dir = os.path.abspath(project_dir)
    state, spec_path, errors = _project_state(project_dir)
    warnings = []
    if state is None:
        return False, errors, warnings

    errors.extend(_missing_artifacts(project_dir))
    if errors:
        return False, errors, warnings

    backend_errors, backend_warnings = _backend_integrity(project_dir, state)
    errors.extend(backend_errors)
    warnings.extend(backend_warnings)
    if errors:
        return False, errors, warnings

    if contract_sha256(project_dir) != state["contract_sha256"]:
        errors.append(f"{CONTRACT_FILENAME} was modified manually — the contract is "
                      "derived from the spec and can only be changed via 'monl update'.")
        return False, errors, warnings

    warnings.extend(_outdated_artifact_warnings(project_dir, state, spec_path))
    frontend_errors, frontend_warnings = _frontend_coherence(
        project_dir, spec_path)
    errors.extend(frontend_errors)
    warnings.extend(frontend_warnings)
    return not errors, errors, warnings


def _project_state(project_dir):
    """Résout le projet, son état et le chemin de sa spec."""
    souci = emplacement._erreur_de_chemin(project_dir)
    if souci:
        return None, None, [souci.replace(" ❌ ", "").strip()]
    state = emplacement._load_state(project_dir)
    if state is None:
        return None, None, [
            f"{nomenclature.STATE_FILENAME} not found — this directory is not a compiled "
            "monl project (run 'monl' or 'monl compile')."
        ]
    spec_path = (state["spec"] if os.path.isabs(state["spec"])
                 else os.path.join(project_dir, state["spec"]))
    if not os.path.exists(spec_path):
        return None, None, [f"Spec not found: {spec_path}"]
    errors = []
    if emplacement._sha256_file(spec_path) != state["spec_sha256"]:
        errors.append("The spec has changed since the last compilation — run 'monl update' "
                      "to resynchronize the backend and contract.")
    return state, spec_path, errors


def _missing_artifacts(project_dir):
    return [
        f"Missing artifact: {artefact}"
        for artefact in ("app.py", "schema.sql", CONTRACT_FILENAME)
        if not os.path.exists(os.path.join(project_dir, artefact))
    ]


def _backend_integrity(project_dir, state):
    """Vérifie le sceau enregistré du backend."""
    empreintes = state.get("backend_sha256")
    if not empreintes:
        return [], ["State predates the backend seal: recompile ('monl update') so that "
                    "app.py and schema.sql are actually verified."]
    errors = []
    for nom, attendu in sorted(empreintes.items()):
        chemin = os.path.join(project_dir, nom)
        if not os.path.exists(chemin):
            errors.append(
                f"{nom} is recorded in {nomenclature.STATE_FILENAME} but missing "
                "from the project — it is generated from the spec: recompile "
                "('monl update').")
        elif emplacement._sha256_file(chemin) != attendu:
            errors.append(
                f"{nom} was modified manually — the backend is generated "
                "from the spec. Modify the spec, then run 'monl update'; "
                "any direct edits will be overwritten.")
    return errors, []


def _outdated_artifact_warnings(project_dir, state, spec_path):
    frais = _empreintes_regenerees(spec_path)
    if frais is None:
        return ["Unable to recompile the spec to compare artifacts with the current "
                "compiler — check not performed."]
    perimes = sorted(
        nom for nom, empreinte in frais.items()
        if os.path.exists(os.path.join(project_dir, nom))
        and emplacement._sha256_file(os.path.join(project_dir, nom)) != empreinte
    )
    if not perimes:
        return []
    from .. import __version__
    construit_avec = state.get("compiler_version")
    depuis = (f" (built with monl {construit_avec}, current "
              f"{__version__})" if construit_avec else "")
    return [
        f"Artifacts produced by an earlier compiler: {', '.join(perimes)}"
        f"{depuis}. The spec has not changed, but monl has — run 'monl update' to "
        f"resynchronize (a security fix reaches a project only after recompilation)."
    ]


def _frontend_references(frontend_dir, known_prefixes):
    routes_client, referenced = set(), set()
    for root, _dirs, files in os.walk(frontend_dir):
        for name in files:
            if not name.endswith((".html", ".js")):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                contenu = fh.read()
            routes_client |= set(re.findall(r"#/([a-z_]+)", contenu))
            for match in re.finditer(r"""(['"`])(/[^'"`\n]*)\1""", contenu):
                chemin = match.group(2)
                if any(c in chemin for c in "<> "):
                    continue
                segment = re.match(r"/([a-z_]+)(?:[/?#]|$)", chemin)
                if segment:
                    referenced.add(segment.group(1))
    return sorted(referenced - known_prefixes - routes_client)


def _frontend_coherence(project_dir, spec_path):
    frontend_dir = os.path.join(project_dir, "frontend")
    if not os.path.isdir(frontend_dir):
        # Le frontend généré par monl a été retiré au point 41 : sans
        # frontend/, il n'y a ni landing ni /app. Les promettre envoyait
        # l'usager sur un 404 JSON qu'il prenait pour une panne (issue #83).
        return [], ["No frontend/ directory — only the API will be served: / redirects "
                    "to /docs, and /site/ will return 404 until 'monl frontend' "
                    "or 'monl import' has produced the interface."]
    if not os.path.exists(os.path.join(frontend_dir, "index.html")):
        return ["frontend/ exists but frontend/index.html is missing "
                "(entry point required by the contract)."], []
    from ..frontend_ai import _design_completeness_errors
    design_errors = _design_completeness_errors(project_dir)
    if design_errors:
        return design_errors, []
    with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
        contract = json.load(fh)
    known_prefixes = {r["path"].split("/")[1] for r in contract["routes"]}
    known_prefixes |= {"register", "login", "logout", "docs", "site", "workflow"}
    unknown = _frontend_references(frontend_dir, known_prefixes)
    warnings = []
    if unknown:
        warnings.append("The frontend references paths missing from the contract: "
                        + ", ".join(f"/{u}" for u in unknown))
    appels = couverture._frontend_fetch_calls(frontend_dir)
    errors = couverture._frontend_fetch_contract_errors(contract, appels)
    couverture_errors, couverture_warnings = couverture._frontend_route_coverage(
        project_dir, spec_path, contract, appels=appels)
    errors.extend(couverture_errors)
    warnings.extend(couverture_warnings)
    return errors, warnings
