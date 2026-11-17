"""Les six étapes du smoke test, dans l'ordre où elles s'exécutent.

« Existe » n'est pas « servi » (point 83) : les deux étapes du milieu posent
la même question — le serveur rend-il ce fichier à l'URL annoncée ? — l'une
sur les assets DÉCLARÉS, l'autre sur ce que l'IA a inventé en écrivant la
page. Un fichier absent ne lève AUCUNE exception : jsdom reçoit le 404 et
continue, comme un vrai navigateur."""

import json
import os
import shutil
import subprocess

from . import fichiers_reclames, fondations, sondes, verification_email


def _compte_de_test(base, contract, errors, warnings):
    """Inscrire puis connecter un compte réel, et rendre son jeton."""
    # --- 2a. compte réel : register → login → jeton ---
    # CORRECTIF (bêta 3) : le compte de test était créé avec le premier
    # rôle par ordre alphabétique, qui est souvent un rôle privilégié
    # — désormais refusé à l'inscription (403). On prend un rôle
    # ouvert à l'inscription libre ; si la spec n'en déclare aucun,
    # l'application n'a pas de parcours d'inscription à éprouver.
    self_register = contract.get("self_register_actors") or []
    actor, token = None, None
    if self_register:
        actor = self_register[0]
        # POINT 95 : l'identifiant du compte de test doit respecter la
        # forme que l'application EXIGE. Codé en dur, 'smoke' recevait un
        # 422 sur toute app déclarant 'identifier: email' — et le smoke
        # test, censé prouver que l'app fonctionne, échouait sur sa
        # propre inscription. Le vérificateur ne peut pas ignorer une
        # règle qu'il fait par ailleurs appliquer.
        identifiant = fondations._identifiant_smoke(contract)
        status, _b = fondations._http("POST", base + "/register",
                           {"username": identifiant, "password": "smokepass123",
                            "actor": actor})
        if status != 200:
            errors.append(f"/register returned {status} (expected 200)")
        status, body = fondations._http("POST", base + "/login",
                             {"username": identifiant, "password": "smokepass123"})
        token = verification_email.verifier_connexion(
            base, contract, status, body, errors, warnings)
        # Un rôle NON ouvert à l'inscription ne doit jamais pouvoir être
        # obtenu par un simple appel HTTP : c'est la faille corrigée en
        # bêta 3, éprouvée ici à chaque lancement.
        for rang, provisioned in enumerate(
                [a for a in contract["actors"] if a not in self_register], start=1):
            status, _b = fondations._http("POST", base + "/register",
                               {"username": fondations._identifiant_smoke(contract, rang),
                                "password": "smokepass123", "actor": provisioned})
            if status == 200:
                errors.append(f"/register accepted provisioned role '{provisioned}' "
                              f"(privilege escalation: expected a 403 refusal)")
    else:
        warnings.append("No 'selfRegister' role: registration flow not tested "
                        "(accounts are provisioned by manage.py).")
    return verification_email.acteur_connecte(actor, contract), token

def _eprouver_les_routes(actor, base, contract, errors, token):
    """Chaque route du contrat, appelée pour de vrai."""
    # --- 2b. chaque route du contrat, en conditions réelles ---
    for route in contract["routes"]:
        path, method = route["path"], route["method"]
        concrete = path.replace("{id}", "1")
        if route.get("auth_mode") == "refresh_token":
            # BRIQUE B4 : /refresh est authentifiée par un jeton
            # opaque dédié, jamais par le JWT d'accès. Une requête
            # vide doit être refusée, sans exiger un Bearer qui n'a
            # précisément rien à faire ici.
            status, _b = fondations._http(method, base + concrete,
                               body={} if method in ("POST", "PUT") else None)
            if status < 400:
                errors.append(f"{method} {path} accepted an empty refresh "
                              f"(response {status})")
        elif route["auth_required"] and route["allowed_actors"]:
            status, _b = fondations._http(method, base + concrete,
                               body={} if method in ("POST", "PUT") else None)
            if status not in (401, 403):
                errors.append(f"{method} {path} without a token returned {status} "
                              f"(expected a 401/403 refusal)")
        elif route["auth_required"]:
            # POINT 74 : une route protégée AUTREMENT que par un JWT —
            # le webhook de paiement, authentifié par la signature du
            # prestataire. Aucun acteur ne l'ouvre, donc exiger 401/403
            # n'a pas de sens : sans clé configurée elle répond 503, et
            # avec clé 400 (signature absente). Ce qui doit être vrai
            # dans tous les cas, c'est qu'une requête nue est REFUSÉE.
            status, _b = fondations._http(method, base + concrete,
                               body={} if method in ("POST", "PUT") else None)
            if status < 400:
                errors.append(f"{method} {path} accepted a request without "
                              f"any authentication (response {status})")
        if method == "GET" and not route["auth_required"]:
            status, _b = fondations._http("GET", base + concrete)
            if route["action"] == "List" and status != 200:
                errors.append(f"GET {path} (public) returned {status} (expected 200)")
            if route["action"] == "Read" and status not in (200, 404):
                errors.append(f"GET {path} (public) returned {status} (expected 200/404)")
        if method == "GET" and route["auth_required"] and token \
                and actor in route["allowed_actors"] and route["action"] == "List":
            status, _b = fondations._http("GET", base + concrete, token=token)
            if status != 200:
                errors.append(f"GET {path} with {actor} token returned {status} "
                              f"(expected 200)")
            if status == 200 and route.get("list_query"):
                probe = sondes._list_query_probe(route, contract)
                status, _b = fondations._http("GET", base + concrete + probe,
                                   token=token)
                if status != 200:
                    errors.append(f"GET {path}{probe} with the contract's list "
                                  f"capabilities returned {status} (expected 200)")
        if method == "GET" and not route["auth_required"] \
                and route["action"] == "List" and route.get("list_query"):
            probe = sondes._list_query_probe(route, contract)
            status, _b = fondations._http("GET", base + concrete + probe)
            if status != 200:
                errors.append(f"GET {path}{probe} (public) returned {status} "
                              f"(expected 200)")

def _eprouver_une_creation(actor, base, contract, errors, token, warnings):
    """Une création réelle, pour éprouver le corps de requête de bout en bout."""
    # Une création réelle sur la première entité créable par l'acteur,
    # pour éprouver le corps de requête du contrat de bout en bout.
    for route in contract["routes"]:
        if route["action"] != "Create" or actor not in route["allowed_actors"]:
            continue
        entite = contract["entities"][route["entity"]]
        fields = {f["name"]: f for f in entite["fields"]}
        # Le corps se construit depuis request_fields DU CONTRAT, pas
        # depuis la liste des champs de l'entité : les colonnes de
        # rattachement (l'article d'un commentaire) n'en font pas
        # partie, et le probe se disait « conforme au contrat » tout
        # en omettant ce que le contrat exige (point 57).
        references = {fk["column"]: fk["references"]
                      for fk in entite["foreign_keys"]}
        payload, parent_absent = {}, None
        for nom in route.get("request_fields") or []:
            spec = fields.get(nom)
            if spec:
                payload[nom] = sondes._sample_value(spec["type"], nom, spec)
                continue
            # Les clés étrangères sont CONTRAINTES en base : inventer
            # un identifiant ferait échouer l'insertion pour une
            # raison qui n'a rien à voir avec le contrat.
            parent = references.get(nom)
            identifiant = sondes._premier_id(base, parent, token) if parent else None
            if identifiant is None:
                parent_absent = (nom, parent)
                break
            payload[nom] = identifiant
        if parent_absent:
            nom, parent = parent_absent
            warnings.append(
                f"creation of {route['entity']} not tested: '{nom}' "
                f"requires an existing {parent}, and none is readable "
                f"(adding a 'seed {parent}' block would make this path "
                f"verifiable)")
            break
        status, _b = fondations._http("POST", base + route["path"], payload,
                           token=None if not route["auth_required"] else token)
        if status != 200:
            errors.append(f"POST {route['path']} with a contract-compliant body "
                          f"returned {status} (expected 200)")
        break

def _assets_reellement_servis(assets_dir, assets_src, base, contract, errors, has_assets):
    """Les assets DÉCLARÉS répondent-ils à l'URL que le contrat annonce ?"""
    # --- 2c. assets déclarés : réellement servis ? (brique 13) ---
    # Le validateur a déjà vérifié que chaque fichier EXISTE sur disque.
    # Ce contrôle-ci répond à l'autre moitié de la question, la seule
    # qui compte pour un navigateur : le serveur le rend-il, à l'URL que
    # le contrat annonce ? Un montage placé après celui de /site
    # existerait sans jamais répondre, et rien ne l'aurait dit.
    if has_assets:
        assets = contract.get("assets") or {}
        for cle in ("logo", "favicon"):
            if not assets.get(cle):
                continue
            url = f"{base}/site/{assets[cle]}"
            status, _b = fondations._http("GET", url)
            if status != 200:
                errors.append(
                    f"declared asset '{cle}' ({assets[cle]}) returned {status} at "
                    f"/site/{assets[cle]}: the file exists but is not SERVED.")
        # Un dossier d'assets déclaré mais monté nulle part est un piège
        # silencieux : on l'éprouve sur un fichier réel du dossier.
        temoin = next((n for n in sorted(os.listdir(assets_src))
                       if os.path.isfile(os.path.join(assets_src, n))), None)
        if temoin:
            status, _b = fondations._http("GET", f"{base}/site/{assets_dir}/{temoin}")
            if status != 200:
                errors.append(
                    f"assets directory '{assets_dir}/' is not served: "
                    f"/site/{assets_dir}/{temoin} returned {status}.")

def _fichiers_reclames_servis(base, errors, has_frontend, workdir):
    """Les fichiers que l'IA a RÉCLAMÉS sont-ils livrés ? (brique 29)"""
    # --- 2d. fichiers RÉCLAMÉS par le frontend : réellement servis ?
    # (brique 29, point 137) — même question que 2c, posée sur ce que
    # l'IA a écrit et non sur ce que la spec déclare. Le point 83
    # éprouvait les assets DÉCLARÉS ; ceux-là, personne ne les avait
    # déclarés : l'IA les a inventés en écrivant la page.
    if has_frontend:
        front_dir = os.path.join(workdir, "frontend")
        for page, chemin in fichiers_reclames._references_locales(front_dir):
            url = fichiers_reclames._url_de_reference(page, chemin)
            if url is None:
                errors.append(
                    f"frontend/{page} references '{chemin}', which escapes the site.")
                continue
            status, _b = fondations._http("GET", base + url)
            if status == 200:
                continue
            detail = (f"frontend/{page} references '{chemin}': "
                      f"{url} returned {status}.")
            if chemin.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")):
                # Cause fréquente et silencieuse : `monl import` ne
                # RETIENT que la liste blanche, donc une photo présente
                # dans l'archive est écartée sans un mot, et la page qui
                # la réclame reste. Sa place est le dossier d'assets
                # (brique 13), qui est versionné et vérifié.
                detail += (" An image delivered with the frontend is not "
                           "retained: declare it in the spec's 'assets'.")
            else:
                detail += " This file was not delivered."
            errors.append(detail)

def _frontend_dans_jsdom(base, contract, errors, has_frontend, say, warnings, workdir):
    """Le frontend, chargé dans un vrai navigateur sans écran."""
    # --- 3. frontend réel dans jsdom (si Node disponible) ---
    if has_frontend:
        node = shutil.which("node")
        if not node:
            warnings.append("Node.js not found — the frontend was not executed "
                            "(static check only). Install node for a complete "
                            "smoke test.")
        else:
            jsdom_ok = fondations._ensure_jsdom(workdir, say)
            if not jsdom_ok:
                warnings.append("jsdom unavailable (npm installation failed) — "
                                "the frontend was not executed.")
            else:
                runner = os.path.join(workdir, "_smoke_runner.js")
                with open(runner, "w", encoding="utf-8") as fh:
                    fh.write(fondations.JSDOM_RUNNER)
                proc = subprocess.run(
                    [node, runner, os.path.join(workdir, "frontend"), base],
                    cwd=workdir, capture_output=True, text=True, timeout=60,
                    env={**os.environ, "NODE_PATH": fondations._jsdom_node_path()})
                report = None
                for line in proc.stdout.splitlines():
                    try:
                        report = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
                if report is None:
                    errors.append("the jsdom runner produced no report: "
                                  + (proc.stderr or proc.stdout)[-300:])
                else:
                    for err in dict.fromkeys(report["js_errors"]):  # dédoublonné (onerror + listener)
                        errors.append(f"JavaScript exception in frontend: {err}")
                    known = {r["path"].split("/")[1] for r in contract["routes"]}
                    known |= {"register", "login", "logout", "docs", "site"}
                    for f in report["fetches"]:
                        first = f["url"].lstrip("/").split("/")[0].split("?")[0]
                        if f["url"].startswith("/") and first not in known:
                            errors.append(f"frontend calls a path outside the "
                                          f"contract: {f['url']}")
                        elif f["status"] in (0, 404, 422, 500):
                            errors.append(f"frontend call {f['url']} → "
                                          f"{f['status'] or f.get('error', '?')}")
                    if not report["fetches"]:
                        warnings.append("the frontend made no API calls on "
                                        "load — nothing to check over the network.")
