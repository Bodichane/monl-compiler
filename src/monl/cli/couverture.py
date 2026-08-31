"""Le frontend appelle-t-il vraiment les routes du contrat.

POINT 150 : une mesure INDÉTERMINÉE n'est pas une mesure NULLE. Le
contrôle suit le FLUX du paramètre (direct, gabarit, variable locale) —
compter zéro sur un site qui appelle cinq routes, c'est accuser un site
correct."""

import os
import re

from ..parser import parse_monl_file
from . import couverture_fetch


def _frontend_fetch_calls(frontend_dir):
    """Retourne les appels ``fetch`` statiquement identifiables."""
    return couverture_fetch.frontend_fetch_calls(frontend_dir)

def _frontend_contract_paths(contract):
    """Retourne les chemins exposés au frontend par le contrat.

    Les routes métier vivent dans ``routes``. L'authentification est une
    exception historique : ``/register``, ``/login`` et ``/logout`` sont
    décrits dans ``api.auth`` mais ne font pas partie de cette liste. Ils sont
    ajoutés ici depuis le contrat, jamais recopiés en dur dans le contrôle.
    """
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
    """Indique si un chemin normalisé correspond à un chemin du contrat."""
    motif = re.escape(declare)
    motif = re.sub(r"\\\{[^{}]+\\\}", r"[^/?#]+", motif)
    return re.fullmatch(motif, appele) is not None

def _frontend_fetch_path_label(chemin):
    """Réduit un chemin d'appel à sa partie certaine pour le message.

    ``/auth/{id}`` vient d'un gabarit que l'analyse sait assez réduire pour
    constater l'erreur, mais ``{id}`` n'est pas un chemin que l'utilisateur a
    réellement écrit. Le nom utile du défaut est donc ``/auth``.
    """
    certains = []
    for segment in chemin.split("/"):
        if not segment:
            continue
        if re.fullmatch(r"\{[^}]+\}", segment):
            break
        certains.append(segment)
    return "/" + "/".join(certains) if certains else chemin

def _frontend_fetch_path_suggestions(chemin, chemins, chemins_auth):
    """Suggère des chemins contractuels sans prétendre comprendre le JS."""
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
    """Refuse les appels ``fetch`` dont le chemin n'est pas contractuel.

    ``appels`` vient exclusivement de ``_frontend_fetch_calls``. Une forme
    dynamique que cette analyse ne sait pas réduire n'entre donc pas ici et
    ne déclenche rien, conformément à l'arbitrage conservateur du parcours.
    """
    chemins, chemins_auth = _frontend_contract_paths(contract)
    errors = []
    for _methode, appele in sorted(appels, key=lambda appel: (appel[1], appel[0] or "")):
        if any(_frontend_contract_path_matches(appele, declare)
               for declare in chemins):
            continue
        label = _frontend_fetch_path_label(appele)
        message = f"REFUSÉ : fetch appelle le chemin {label}, absent du contrat"
        if label != appele:
            message += f" (forme réduite : {appele})"
        suggestions = _frontend_fetch_path_suggestions(
            appele, chemins, chemins_auth)
        if suggestions:
            message += "; chemins existants possibles : " + ", ".join(suggestions)
        errors.append(message + ".")
    return list(dict.fromkeys(errors))

def _route_est_appelee(route, appels):
    """Teste une route contractuelle contre les appels normalisés du frontend."""
    chemin = route["path"]
    motif = re.escape(chemin).replace(r"\{id\}", r"[^/?#]+")
    return any(methode == route["method"] and re.fullmatch(motif, appele)
               for methode, appele in appels)

def _route_correspond_aux_action(route, action):
    """Associe une action de workflow aux routes qu'elle produit réellement."""
    type_action = action["type"]
    cible = action["target"]
    entite = cible.split(".", 1)[0]
    if type_action == "Read":
        return route["entity"] == entite and route["action"] in ("List", "Read")
    return route["entity"] == entite and route["action"] == type_action

def _route_label(route):
    return f"{route['method']} {route['path']}"

def _frontend_route_coverage(project_dir, spec_path, contract, appels=None):
    """Vérifie la couverture du frontend livré, sans exécuter une intention.

    Les routes sont lues dans le contrat sur disque et confrontées aux
    ``fetch`` présents dans les fichiers livrés. Les workflows viennent de la
    spec, source de leur nom et de leur acteur. Le webhook est le seul cas
    explicitement hors écran : le contrat interdit déjà au navigateur de
    l'appeler.
    """
    frontend_dir = os.path.join(project_dir, "frontend")
    if appels is None:
        appels = _frontend_fetch_calls(frontend_dir)
    routes = [r for r in contract.get("routes", [])
              if r["path"] != "/paiement/webhook"]
    couverts = {id(route) for route in routes if _route_est_appelee(route, appels)}

    try:
        workflows = parse_monl_file(spec_path).get("workflows", [])
    except Exception as exc:  # pragma: no cover - artefact déjà validé en amont
        return [], ["Couverture des parcours indéterminable : "
                    f"lecture des workflows impossible ({exc})."]

    self_register = set(contract.get("self_register_actors") or [])
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

    missing_routes = [route for route in routes if id(route) not in couverts]
    missing_labels = []
    for route in missing_routes:
        workflows_noms = sorted(set(route_workflows[id(route)]))
        suffix = (f" (workflows : {', '.join(workflows_noms)})"
                  if workflows_noms else " (route auxiliaire du contrat)")
        missing_labels.append(_route_label(route) + suffix)

    errors, warnings = [], []
    if missing_routes:
        message = (
            f"Couverture frontend : {len(couverts)}/{len(routes)} routes du contrat "
            "sont référencées par frontend/. Routes jamais appelées : "
            + "; ".join(missing_labels)
        )
        # Une route isolée n'est pas nécessairement un écran : un détail peut
        # être rendu depuis la liste, et une écriture de service peut être
        # absente d'une vitrine. Le refus porte donc sur le plancher mesurable
        # (un workflow utilisateur sans aucune entrée), tandis que cette
        # liste exhaustive reste un avertissement actionnable.
        warnings.append(message)

    for workflow, actions in parcours_manquants:
        message = (
            f"Parcours frontend manquant : workflow '{workflow['name']}' "
            f"pour l'acteur '{workflow['actor']}' — aucune entrée n'appelle "
            "une route de ce workflow (actions déclarées : "
            + ", ".join(actions)
            + ")"
        )
        if workflow["actor"] in self_register:
            errors.append(message)
        else:
            warnings.append(message)

    return errors, warnings
