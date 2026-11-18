"""Does the frontend really call the contract's routes.

POINT 150: an UNDETERMINED measurement is not a NULL measurement. The
check follows the parameter's FLOW (direct, template, local variable) —
counting zero on a site that calls five routes means accusing a correct
site."""

import os
import re

from ..parser import parse_monl_file
from . import couverture_fetch


def _frontend_fetch_calls(frontend_dir):
    """Returns the statically identifiable ``fetch`` calls."""
    return couverture_fetch.frontend_fetch_calls(frontend_dir)

def _frontend_contract_paths(contract):
    """Returns the paths exposed to the frontend by the contract.

    Business routes live in ``routes``. Authentication is a historical
    exception: ``/register``, ``/login`` and ``/logout`` are described in
    ``api.auth`` but are not part of that list. They are added here from the
    contract, never hard-coded in the check."""
    chemins = []
    for route in contract.get("routes", []):
        chemin = route.get("path")
        if isinstance(chemin, str):
            chemins.append(chemin)

    auth = (contract.get("api") or {}).get("auth") or {}
    chemins_auth = []
    for nom in ("register", "login", "logout"):
        endpoint = auth.get(nom) or {}
        chemin = endpoint.get("path")
        if isinstance(chemin, str):
            chemins.append(chemin)
            chemins_auth.append(chemin)
    return list(dict.fromkeys(chemins)), list(dict.fromkeys(chemins_auth))

def _frontend_contract_path_matches(appele, declare):
    """Tells whether a normalized path matches a contract path."""
    motif = re.escape(declare)
    motif = re.sub(r"\\\{[^{}]+\\\}", r"[^/?#]+", motif)
    return re.fullmatch(motif, appele) is not None

def _frontend_fetch_path_label(chemin):
    """Reduces a call path to its certain part, for the message.

    ``/auth/{id}`` comes from a template the analysis can reduce enough to
    notice the error, but ``{id}`` is not a path the user really wrote. The
    useful name of the defect is therefore ``/auth``."""
    certains = []
    for segment in chemin.split("/"):
        if not segment:
            continue
        if re.fullmatch(r"\{[^}]+\}", segment):
            break
        certains.append(segment)
    return "/" + "/".join(certains) if certains else chemin

def _frontend_fetch_path_suggestions(chemin, chemins, chemins_auth):
    """Suggests contract paths without pretending to understand the JS."""
    label = _frontend_fetch_path_label(chemin)
    if label == "/auth" and chemins_auth:
        return sorted(chemins_auth)
    dernier = label.rstrip("/").rsplit("/", 1)[-1]
    if not dernier:
        return []
    return sorted({
        candidat for candidat in chemins
        if candidat.rstrip("/").rsplit("/", 1)[-1] == dernier
    })

def _frontend_fetch_contract_errors(contract, appels):
    """Refuses the ``fetch`` calls whose path is not in the contract.

    ``appels`` comes exclusively from ``_frontend_fetch_calls``. A dynamic form
    this analysis cannot reduce therefore never enters here and triggers
    nothing, in line with the journey's conservative trade-off."""
    chemins, chemins_auth = _frontend_contract_paths(contract)
    errors = []
    for _methode, appele in sorted(appels, key=lambda appel: (appel[1], appel[0] or "")):
        if any(_frontend_contract_path_matches(appele, declare)
               for declare in chemins):
            continue
        label = _frontend_fetch_path_label(appele)
        message = (f"REJECTED: fetch calls path {label}, which is absent from "
                   "the contract")
        if label != appele:
            message += f" (reduced form: {appele})"
        suggestions = _frontend_fetch_path_suggestions(
            appele, chemins, chemins_auth)
        if suggestions:
            message += "; possible existing paths: " + ", ".join(suggestions)
        errors.append(message + ".")
    return list(dict.fromkeys(errors))

def _route_est_appelee(route, appels):
    """Tests a contract route against the frontend's normalized calls."""
    chemin = route["path"]
    motif = re.escape(chemin).replace(r"\{id\}", r"[^/?#]+")
    return any(methode == route["method"] and re.fullmatch(motif, appele)
               for methode, appele in appels)

def _route_correspond_aux_action(route, action):
    """Maps a workflow action to the routes it really produces."""
    type_action = action["type"]
    cible = action["target"]
    entite = cible.split(".", 1)[0]
    if type_action == "Read":
        return route["entity"] == entite and route["action"] in ("List", "Read")
    return route["entity"] == entite and route["action"] == type_action

def _route_label(route):
    return f"{route['method']} {route['path']}"

# The next two functions are extracted from `_frontend_route_coverage`
# (complexity ceiling): same walk, same lists, same messages.
def _parcours_des_workflows(workflows, routes, couverts):
    """({route id: [workflow names]}, [(workflow, missing actions)]).

    A workflow counts as covered as soon as ONE of its actions has a called
    route; only an entirely uncovered workflow is reported."""
    route_workflows = {id(route): [] for route in routes}
    parcours_manquants = []
    for workflow in workflows:
        actions_manquantes = []
        workflow_couvert = False
        for action in workflow.get("actions", []):
            candidates = [route for route in routes
                          if _route_correspond_aux_action(route, action)]
            if any(id(route) in couverts for route in candidates):
                workflow_couvert = True
                for route in candidates:
                    route_workflows[id(route)].append(workflow["name"])
                continue
            for route in candidates:
                route_workflows[id(route)].append(workflow["name"])
            actions_manquantes.append(f"{action['type']} {action['target']}")
        if not workflow_couvert and actions_manquantes:
            parcours_manquants.append((workflow, actions_manquantes))
    return route_workflows, parcours_manquants


def _libelles_manquants(missing_routes, route_workflows):
    """Each never-called route, with the workflows it belongs to."""
    missing_labels = []
    for route in missing_routes:
        workflows_noms = sorted(set(route_workflows[id(route)]))
        suffix = (f" (workflows: {', '.join(workflows_noms)})"
                  if workflows_noms else " (auxiliary contract route)")
        missing_labels.append(_route_label(route) + suffix)
    return missing_labels


def _frontend_route_coverage(project_dir, spec_path, contract, appels=None):
    """Checks the coverage of the delivered frontend, without running an
    intention.

    The routes are read from the contract on disk and matched against the
    ``fetch`` calls present in the delivered files. The workflows come from
    the spec, the source of their name and actor. The webhook is the only case
    explicitly off screen: the contract already forbids the browser from
    calling it."""
    frontend_dir = os.path.join(project_dir, "frontend")
    if appels is None:
        appels = _frontend_fetch_calls(frontend_dir)
    routes = [r for r in contract.get("routes", [])
              if r["path"] != "/paiement/webhook"]
    couverts = {id(route) for route in routes if _route_est_appelee(route, appels)}

    try:
        workflows = parse_monl_file(spec_path).get("workflows", [])
    except Exception as exc:  # pragma: no cover - artifact already validated upstream
        return [], ["Frontend workflow coverage cannot be determined: "
                    f"reading workflows failed ({exc})."]

    self_register = set(contract.get("self_register_actors") or [])
    route_workflows, parcours_manquants = _parcours_des_workflows(
        workflows, routes, couverts)

    missing_routes = [route for route in routes if id(route) not in couverts]
    missing_labels = _libelles_manquants(missing_routes, route_workflows)

    errors, warnings = [], []
    if missing_routes:
        message = (
            f"Frontend coverage: {len(couverts)}/{len(routes)} contract routes "
            "are referenced by frontend/. Routes never called: "
            + "; ".join(missing_labels)
        )
        # A single route is not necessarily a screen: a detail can be rendered
        # from the list, and a service write can be absent from a storefront.
        # The refusal therefore applies to the measurable floor (a user
        # workflow with no entry at all), while this exhaustive list stays an
        # actionable warning.
        warnings.append(message)

    for workflow, actions in parcours_manquants:
        message = (
            f"Missing frontend workflow: workflow '{workflow['name']}' "
            f"for actor '{workflow['actor']}' — no entry calls "
            "a route from this workflow (declared actions: "
            + ", ".join(actions)
            + ")"
        )
        if workflow["actor"] in self_register:
            errors.append(message)
        else:
            warnings.append(message)

    return errors, warnings
