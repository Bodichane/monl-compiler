"""`monl run --check`: does the delivered site keep the contract's promise.

Detecting stale artifacts compares against a REGENERATION, never a version
number — `__version__` had not moved during points 74 to 81, a stamp would
have seen nothing."""

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
from . import coverage, location, nomenclature


# ----------------------------------------------------------- consistency ----
def _fingerprints_regenerated(spec_path):
    """Fingerprints of the artifacts a recompilation would produce NOW, or None
    if the spec no longer compiles (the check must not turn into a failure:
    the modified spec is already reported by its own check).

    The recompilation happens in a temporary folder — the project is never
    touched — and its output is captured: a consistency check has no business
    replaying the security audit on screen."""

    fingerprints = {}
    with tempfile.TemporaryDirectory() as temporary:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # base_dir = the SPEC's folder, not the temporary folder: that
                # is where the assets to check live (brick 13).
                normalized = MonlAST(
                    parse_monl_file(spec_path),
                    base_dir=os.path.dirname(os.path.abspath(spec_path)),
                ).validate_and_audit()
                generator = MonlSecureGenerator(normalized, output_dir=temporary)
                generator.generate_all()
                generate_frontend_contract(normalized, generator, temporary)
        except Exception:
            return None
        for name in ("app.py", "schema.sql", "sandbox_ai.py", CONTRACT_FILENAME):
            path = os.path.join(temporary, name)
            if os.path.exists(path):
                fingerprints[name] = location._sha256_file(path)
    return fingerprints

def check_coherence(project_dir):
    """Checks that spec, backend, contract and frontend form a consistent whole.
    Returns (ok, errors, warnings)."""
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
    """Resolves the project, its state and the path of its spec."""
    issue = location._error_of_path(project_dir)
    if issue:
        return None, None, [issue.replace(" ❌ ", "").strip()]
    state = location._load_state(project_dir)
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
    if location._sha256_file(spec_path) != state["spec_sha256"]:
        errors.append("The spec has changed since the last compilation — run 'monl update' "
                      "to resynchronize the backend and contract.")
    return state, spec_path, errors


def _missing_artifacts(project_dir):
    return [
        f"Missing artifact: {artifact}"
        for artifact in ("app.py", "schema.sql", CONTRACT_FILENAME)
        if not os.path.exists(os.path.join(project_dir, artifact))
    ]


def _backend_integrity(project_dir, state):
    """Checks the backend's recorded seal."""
    fingerprints = state.get("backend_sha256")
    if not fingerprints:
        return [], ["State predates the backend seal: recompile ('monl update') so that "
                    "app.py and schema.sql are actually verified."]
    errors = []
    for name, expected in sorted(fingerprints.items()):
        path = os.path.join(project_dir, name)
        if not os.path.exists(path):
            errors.append(
                f"{name} is recorded in {nomenclature.STATE_FILENAME} but missing "
                "from the project — it is generated from the spec: recompile "
                "('monl update').")
        elif location._sha256_file(path) != expected:
            errors.append(
                f"{name} was modified manually — the backend is generated "
                "from the spec. Modify the spec, then run 'monl update'; "
                "any direct edits will be overwritten.")
    return errors, []


def _outdated_artifact_warnings(project_dir, state, spec_path):
    fees = _fingerprints_regenerated(spec_path)
    if fees is None:
        return ["Unable to recompile the spec to compare artifacts with the current "
                "compiler — check not performed."]
    stale = sorted(
        name for name, fingerprint in fees.items()
        if os.path.exists(os.path.join(project_dir, name))
        and location._sha256_file(os.path.join(project_dir, name)) != fingerprint
    )
    if not stale:
        return []
    from .. import __version__
    built_with = state.get("compiler_version")
    from_ = (f" (built with monl {built_with}, current "
              f"{__version__})" if built_with else "")
    return [
        f"Artifacts produced by an earlier compiler: {', '.join(stale)}"
        f"{from_}. The spec has not changed, but monl has — run 'monl update' to "
        f"resynchronize (a security fix reaches a project only after recompilation)."
    ]


def _frontend_references(frontend_dir, known_prefixes):
    routes_client, referenced = set(), set()
    for root, _dirs, files in os.walk(frontend_dir):
        for name in files:
            if not name.endswith((".html", ".js")):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            routes_client |= set(re.findall(r"#/([a-z_]+)", content))
            for match in re.finditer(r"""(['"`])(/[^'"`\n]*)\1""", content):
                path = match.group(2)
                if any(c in path for c in "<> "):
                    continue
                segment = re.match(r"/([a-z_]+)(?:[/?#]|$)", path)
                if segment:
                    referenced.add(segment.group(1))
    return sorted(referenced - known_prefixes - routes_client)


def _frontend_coherence(project_dir, spec_path):
    frontend_dir = os.path.join(project_dir, "frontend")
    if not os.path.isdir(frontend_dir):
        # The frontend generated by monl was removed at point 41: without
        # frontend/, there is neither landing nor /app. Promising them sent the
        # user to a JSON 404 they took for a failure (issue #83).
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
    calls = coverage._frontend_fetch_calls(frontend_dir)
    errors = coverage._frontend_fetch_contract_errors(contract, calls)
    coverage_errors, coverage_warnings = coverage._frontend_route_coverage(
        project_dir, spec_path, contract, calls=calls)
    errors.extend(coverage_errors)
    warnings.extend(coverage_warnings)
    return errors, warnings
