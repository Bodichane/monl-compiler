"""Does the frontend really call the contract's routes.

POINT 150: an UNDETERMINED measurement is not a NULL measurement. The
check follows the parameter's FLOW (direct, template, local variable) —
counting zero on a site that calls five routes means accusing a correct
site."""

import os
import re

from ..parser import parse_monl_file
from . import coverage_fetch


def _frontend_fetch_calls(frontend_dir):
    """Returns the statically identifiable ``fetch`` calls."""
    return coverage_fetch.frontend_fetch_calls(frontend_dir)

def _frontend_contract_paths(contract):
    """Returns the paths exposed to the frontend by the contract.

    Business routes live in ``routes``. Authentication is a historical
    exception: ``/register``, ``/login`` and ``/logout`` are described in
    ``api.auth`` but are not part of that list. They are added here from the
    contract, never hard-coded in the check."""
    paths = []
    for route in contract.get("routes", []):
        path = route.get("path")
        if isinstance(path, str):
            paths.append(path)

    auth = (contract.get("api") or {}).get("auth") or {}
    paths_auth = []
    for name in ("register", "login", "logout"):
        endpoint = auth.get(name) or {}
        path = endpoint.get("path")
        if isinstance(path, str):
            paths.append(path)
            paths_auth.append(path)
    return list(dict.fromkeys(paths)), list(dict.fromkeys(paths_auth))

def _frontend_contract_path_matches(called, declare):
    """Tells whether a normalized path matches a contract path."""
    motif = re.escape(declare)
    motif = re.sub(r"\\\{[^{}]+\\\}", r"[^/?#]+", motif)
    return re.fullmatch(motif, called) is not None

def _frontend_fetch_path_label(path):
    """Reduces a call path to its certain part, for the message.

    ``/auth/{id}`` comes from a template the analysis can reduce enough to
    notice the error, but ``{id}`` is not a path the user really wrote. The
    useful name of the defect is therefore ``/auth``."""
    some = []
    for segment in path.split("/"):
        if not segment:
            continue
        if re.fullmatch(r"\{[^}]+\}", segment):
            break
        some.append(segment)
    return "/" + "/".join(some) if some else path

def _frontend_fetch_path_suggestions(path, paths, paths_auth):
    """Suggests contract paths without pretending to understand the JS."""
    label = _frontend_fetch_path_label(path)
    if label == "/auth" and paths_auth:
        return sorted(paths_auth)
    last = label.rstrip("/").rsplit("/", 1)[-1]
    if not last:
        return []
    return sorted({
        candidate for candidate in paths
        if candidate.rstrip("/").rsplit("/", 1)[-1] == last
    })

def _frontend_fetch_contract_errors(contract, calls):
    """Refuses the ``fetch`` calls whose path is not in the contract.

    ``appels`` comes exclusively from ``_frontend_fetch_calls``. A dynamic form
    this analysis cannot reduce therefore never enters here and triggers
    nothing, in line with the journey's conservative trade-off."""
    paths, paths_auth = _frontend_contract_paths(contract)
    errors = []
    for _method, called in sorted(calls, key=lambda call: (call[1], call[0] or "")):
        if any(_frontend_contract_path_matches(called, declare)
               for declare in paths):
            continue
        label = _frontend_fetch_path_label(called)
        message = (f"REJECTED: fetch calls path {label}, which is absent from "
                   "the contract")
        if label != called:
            message += f" (reduced form: {called})"
        suggestions = _frontend_fetch_path_suggestions(
            called, paths, paths_auth)
        if suggestions:
            message += "; possible existing paths: " + ", ".join(suggestions)
        errors.append(message + ".")
    return list(dict.fromkeys(errors))

def _route_is_called(route, calls):
    """Tests a contract route against the frontend's normalized calls."""
    path = route["path"]
    motif = re.escape(path).replace(r"\{id\}", r"[^/?#]+")
    return any(method == route["method"] and re.fullmatch(motif, called)
               for method, called in calls)

def _route_correspond_aux_action(route, action):
    """Maps a workflow action to the routes it really produces."""
    type_action = action["type"]
    target = action["target"]
    entity = target.split(".", 1)[0]
    if type_action == "Read":
        return route["entity"] == entity and route["action"] in ("List", "Read")
    return route["entity"] == entity and route["action"] == type_action

def _route_label(route):
    return f"{route['method']} {route['path']}"

# The next two functions are extracted from `_frontend_route_coverage`
# (complexity ceiling): same walk, same lists, same messages.
def _walk_of_workflows(workflows, routes, covered):
    """({route id: [workflow names]}, [(workflow, missing actions)]).

    A workflow counts as covered as soon as ONE of its actions has a called
    route; only an entirely uncovered workflow is reported."""
    route_workflows = {id(route): [] for route in routes}
    walk_missing = []
    for workflow in workflows:
        actions_missing = []
        workflow_covered = False
        for action in workflow.get("actions", []):
            candidates = [route for route in routes
                          if _route_correspond_aux_action(route, action)]
            if any(id(route) in covered for route in candidates):
                workflow_covered = True
                for route in candidates:
                    route_workflows[id(route)].append(workflow["name"])
                continue
            for route in candidates:
                route_workflows[id(route)].append(workflow["name"])
            actions_missing.append(f"{action['type']} {action['target']}")
        if not workflow_covered and actions_missing:
            walk_missing.append((workflow, actions_missing))
    return route_workflows, walk_missing


def _labels_missing(missing_routes, route_workflows):
    """Each never-called route, with the workflows it belongs to."""
    missing_labels = []
    for route in missing_routes:
        workflows_names = sorted(set(route_workflows[id(route)]))
        suffix = (f" (workflows: {', '.join(workflows_names)})"
                  if workflows_names else " (auxiliary contract route)")
        missing_labels.append(_route_label(route) + suffix)
    return missing_labels


def _frontend_route_coverage(project_dir, spec_path, contract, calls=None):
    """Checks the coverage of the delivered frontend, without running an
    intention.

    The routes are read from the contract on disk and matched against the
    ``fetch`` calls present in the delivered files. The workflows come from
    the spec, the source of their name and actor. The webhook is the only case
    explicitly off screen: the contract already forbids the browser from
    calling it."""
    frontend_dir = os.path.join(project_dir, "frontend")
    if calls is None:
        calls = _frontend_fetch_calls(frontend_dir)
    routes = [r for r in contract.get("routes", [])
              if r["path"] != "/paiement/webhook"]
    covered = {id(route) for route in routes if _route_is_called(route, calls)}

    try:
        workflows = parse_monl_file(spec_path).get("workflows", [])
    except Exception as exc:  # pragma: no cover - artifact already validated upstream
        return [], ["Frontend workflow coverage cannot be determined: "
                    f"reading workflows failed ({exc})."]

    self_register = set(contract.get("self_register_actors") or [])
    route_workflows, walk_missing = _walk_of_workflows(
        workflows, routes, covered)

    missing_routes = [route for route in routes if id(route) not in covered]
    missing_labels = _labels_missing(missing_routes, route_workflows)

    errors, warnings = [], []
    if missing_routes:
        message = (
            f"Frontend coverage: {len(covered)}/{len(routes)} contract routes "
            "are referenced by frontend/. Routes never called: "
            + "; ".join(missing_labels)
        )
        # A single route is not necessarily a screen: a detail can be rendered
        # from the list, and a service write can be absent from a storefront.
        # The refusal therefore applies to the measurable floor (a user
        # workflow with no entry at all), while this exhaustive list stays an
        # actionable warning.
        warnings.append(message)

    for workflow, actions in walk_missing:
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
