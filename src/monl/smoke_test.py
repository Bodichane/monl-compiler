# ─────────────────────────────────────────────────────────────────────
# SMOKE TEST — pivot orchestrateur, point 1 : "cohérent" ne suffit pas,
# il faut que ça FONCTIONNE. Avant de lancer l'application pour de vrai,
# 'monl run' exécute ici un test de fumée comportemental :
#
#   1. Un serveur uvicorn ÉPHÉMÈRE est démarré dans un dossier temporaire
#      (copie des artefacts) : base de données neuve, port libre — le smoke
#      test ne touche JAMAIS aux données réelles du projet.
#   2. Chaque route du contrat est éprouvée en HTTP réel : les GET publics
#      doivent répondre 200, les routes protégées doivent REFUSER sans
#      jeton (401/403), et un compte réel est créé (register → login) pour
#      vérifier qu'un jeton valide ouvre bien les routes protégées.
#   3. Si Node.js est disponible, frontend/index.html est chargé dans
#      jsdom (scripts exécutés), ses fetch() routés vers le serveur
#      éphémère : toute exception JavaScript ou tout appel à un chemin
#      hors contrat fait échouer le test. Sans Node, cette étape est
#      sautée avec un avertissement explicite — jamais silencieusement.
#
# Tout est piloté par frontend_contract.json : si le contrat et l'API
# divergeaient, c'est ici que ça se verrait en conditions réelles.
# ─────────────────────────────────────────────────────────────────────
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .frontend_contract import CONTRACT_FILENAME
from .serving import rendre_wrapper

JSDOM_RUNNER = r"""
// Runner jsdom généré par monl (smoke test) — charge index.html, exécute
// ses scripts, route fetch() vers le serveur éphémère, rapporte erreurs JS
// et statuts des appels. Sortie : une ligne JSON sur stdout.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const [frontendDir, baseUrl] = process.argv.slice(2);
let html = fs.readFileSync(path.join(frontendDir, 'index.html'), 'utf-8');
const report = { js_errors: [], fetches: [] };

// fetch : jsdom n'en fournit pas, et les scripts s'exécutent PENDANT la
// construction du DOM -> le branchement doit se faire dans beforeParse,
// jamais après coup (bug réel trouvé par exécution : un fetch assigné
// après 'new JSDOM' n'est jamais vu par les scripts de la page).
// Les <script src> LOCAUX sont inlinés dans le HTML avant construction :
// jsdom ne charge pas les ressources externes par défaut (et son API de
// chargement a changé entre versions — ResourceLoader n'existe plus en
// v29), donc sans cette étape un fetch vivant dans app.js n'est jamais
// exécuté et le smoke test devient un faux positif silencieux (bug réel
// trouvé en éprouvant 'monl import' avec un zip multi-fichiers).
// Les scripts https:// (CDN) ne sont PAS chargés — le contrat exige un
// frontend autonome, précisément pour rester vérifiable ici.
html = html.replace(/<script([^>]*?)\ssrc=["']([^"']+)["']([^>]*)>\s*<\/script>/gi,
    (m, pre, src, post) => {
        if (/^https?:/i.test(src)) {
            report.js_errors.push('script CDN non autonome (le contrat exige un frontend sans dépendance externe) : ' + src);
            return '';
        }
        const rel = src.replace(/^\.?\//, '').replace(/^site\//, '');
        const p = path.join(frontendDir, rel);
        if (!fs.existsSync(p)) {
            report.js_errors.push('script local introuvable : ' + src);
            return '';
        }
        return '<script>\n' + fs.readFileSync(p, 'utf-8') + '\n</script>';
    });

const dom = new JSDOM(html, {
    url: baseUrl + '/site/',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    beforeParse(window) {
        window.fetch = async (input, init) => {
            let target = String(input);
            if (target.startsWith('/')) target = baseUrl + target;
            else if (/^https?:/i.test(target)) {
                // Le contrat impose des chemins relatifs (même origine). Une
                // URL absolue vise un port codé en dur, jamais celui du
                // serveur éphémère -> 'TypeError: fetch failed', message qui
                // ne désigne pas la cause et que la correction automatique ne
                // pouvait pas exploiter. On nomme le défaut, sans réécrire
                // l'URL : la faute est réelle ('monl run --port' casserait
                // pareil), la masquer ici serait un faux positif.
                const msg = "URL absolue interdite — le contrat exige un chemin"
                    + " relatif (/entite) : le frontend est servi sur /site par"
                    + " le serveur de l'API, un port codé en dur casse dès qu'il"
                    + " change";
                // Consigné comme appel (et non comme erreur JS) : la tentative
                // a bien eu lieu, sinon le rapport conclut à tort « aucun appel
                // API au chargement ».
                report.fetches.push({ url: target, status: 0, error: msg });
                throw new TypeError(msg);
            }
            try {
                const res = await fetch(target, init);
                report.fetches.push({ url: String(input), status: res.status });
                return res;
            } catch (err) {
                report.fetches.push({ url: String(input), status: 0, error: String(err) });
                throw err;
            }
        };
        window.onerror = (msg) => { report.js_errors.push(String(msg)); };
        window.addEventListener('error', (e) => {
            if (e.error) report.js_errors.push(String(e.error && e.error.message || e.message));
        });
    },
});

// Un fetch en échec dont la page n'attrape pas le rejet tue le process Node
// avant l'échéance ci-dessous : le smoke test ne rapportait alors que « le
// runner jsdom n'a rendu aucun rapport », en perdant la vraie cause. On la
// consigne comme erreur JS — c'en est une du point de vue de la page — sans
// doublonner ce que le shim fetch a déjà nommé.
process.on('unhandledRejection', (err) => {
    const msg = String((err && err.message) || err);
    if (report.fetches.some((f) => f.error === msg)) return;
    report.js_errors.push('promesse rejetée sans gestion : ' + msg);
});

// Laisser les scripts + leurs fetch initiaux se dérouler, puis rapporter.
setTimeout(() => { console.log(JSON.stringify(report)); process.exit(0); }, 2500);
"""


class SmokeFailure(Exception):
    pass


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _identifiant_smoke(contract, rang=0):
    """Identifiant de compte de test conforme à ce que l'app EXIGE (point 95).

    `rang` distingue les comptes d'un même passage : la boucle d'élévation de
    privilège en essaie un par rôle provisionné, et deux inscriptions sous le
    même identifiant donneraient un 409 qu'on lirait à tort comme un refus de
    rôle. Le domaine `.test` est réservé par la RFC 2606 — jamais routable,
    donc jamais un vrai destinataire par accident."""
    formes = (contract.get("api", {}).get("auth", {}).get("register", {})
              .get("identifier_forms") or [])
    suffixe = f"-{rang}" if rang else ""
    if "email" in formes:
        return f"smoke{suffixe}@monl.test"
    if "phone" in formes:
        # Plage 06 99 00 00 xx : de la longueur d'un vrai numéro, sans en être un.
        return f"+3369900{rang:04d}"
    return f"smoke{suffixe}"


def _http(method, url, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                # /docs et consorts renvoient du HTML, et depuis la brique 13 on
                # récupère aussi des assets BINAIRES (png, jpg) — seul le statut
                # compte. `UnicodeDecodeError` n'est PAS un `JSONDecodeError` :
                # ne l'attraper qu'en JSON faisait remonter la trace complète
                # dès le premier octet non-UTF-8. Défaut latent jusqu'ici parce
                # que rien de binaire n'était jamais demandé.
                return resp.status, {}
    except urllib.error.HTTPError as e:
        # Un HTTPError EST la réponse : le lire ne suffit pas, il faut le
        # fermer. Sans ce close, chaque 401 attendu (et le smoke test en
        # provoque à dessein, pour vérifier que les routes protégées le sont)
        # laissait un descripteur derrière lui.
        with e:
            try:
                payload = json.loads(e.read() or b"{}")
            except Exception:
                payload = {}
        return e.code, payload  # corps d'erreur non-JSON toléré aussi
    except urllib.error.URLError:
        return 0, {}


def _premier_id(base, entite, token):
    """Identifiant d'un enregistrement RÉEL de l'entité parente, ou None si
    la liste est vide ou hors de portée de cet acteur. Sert à rattacher une
    création à une cible qui existe : les clés étrangères sont contraintes
    (PRAGMA foreign_keys = ON dans le backend généré)."""
    if not entite:
        return None
    status, corps = _http("GET", f"{base}/{entite.lower()}?limit=1", token=token)
    if status != 200:
        return None
    donnees = (corps or {}).get("data") or []
    return donnees[0].get("id") if donnees else None


def _sample_value(ftype, fname, spec=None):
    # POINT 96 : un champ `oneOf` n'accepte QUE ses valeurs — 'smoke-status'
    # récolterait un 422, et le smoke test déclarerait cassée une application
    # saine. Deuxième occurrence de la leçon du point 95 : le vérificateur est
    # un client comme un autre, et toute brique qui contraint une ENTRÉE le
    # contraint aussi. La première valeur déclarée fait l'affaire — sur un
    # statut, c'est l'état initial.
    choix = (spec or {}).get("allowed_values")
    if choix:
        return choix[0]
    low = fname.lower()
    if ftype == "Integer":
        return 1
    if ftype in ("Float", "Money"):
        return 1.5
    if ftype == "Boolean":
        return True
    if ftype == "Email":
        return "smoke@exemple.fr"
    if any(k in low for k in ("image", "photo", "url")):
        return "https://picsum.photos/seed/smoke/400/300"
    return f"smoke-{fname}"


def run_smoke_test(project_dir, say=print):
    """Retourne (ok, erreurs, avertissements). Lève seulement sur bug interne."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)
    with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
        contract = json.load(fh)

    workdir = tempfile.mkdtemp(prefix="monl_smoke_")
    try:
        # Copie des artefacts : base neuve, données réelles intouchées.
        for name in ("app.py", "schema.sql", "sandbox_ai.py", ".jwt_secret"):
            src = os.path.join(project_dir, name)
            if os.path.exists(src):
                shutil.copy2(src, workdir)
        frontend_src = os.path.join(project_dir, "frontend")
        has_frontend = os.path.isdir(frontend_src)
        if has_frontend:
            shutil.copytree(frontend_src, os.path.join(workdir, "frontend"))
        # AJOUT (brique 13, point 83) : les assets déclarés sont copiés et
        # SERVIS, via le même wrapper que 'monl run'. Jusqu'ici le smoke test
        # lançait `app:app` : ni /site ni les assets ne passaient par HTTP,
        # donc « servi » n'était vérifié nulle part — seul l'œil, sur la page,
        # aurait vu un montage mal placé.
        assets_dir = (contract.get("assets") or {}).get("dir")
        assets_src = os.path.join(project_dir, assets_dir) if assets_dir else None
        has_assets = bool(assets_src and os.path.isdir(assets_src))
        if has_assets:
            shutil.copytree(assets_src, os.path.join(workdir, assets_dir))
        module = "app:app"
        if has_frontend:
            with open(os.path.join(workdir, "serve.py"), "w", encoding="utf-8") as fh:
                fh.write(rendre_wrapper(assets_dir if has_assets else None))
            module = "serve:app"

        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(50):
                status, _b = _http("GET", base + "/docs")
                if status == 200:
                    break
                if server.poll() is not None:
                    raise SmokeFailure("le serveur éphémère s'est arrêté au démarrage : "
                                       + server.stderr.read().decode(errors="replace")[-400:])
                time.sleep(0.2)
            else:
                raise SmokeFailure("le serveur éphémère n'a jamais répondu sur /docs")

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
                identifiant = _identifiant_smoke(contract)
                status, _b = _http("POST", base + "/register",
                                   {"username": identifiant, "password": "smokepass123",
                                    "actor": actor})
                if status != 200:
                    errors.append(f"/register a répondu {status} (attendu 200)")
                status, body = _http("POST", base + "/login",
                                     {"username": identifiant, "password": "smokepass123"})
                token = body.get("token") or body.get("access_token")
                if status != 200 or not token:
                    errors.append(f"/login a répondu {status} sans jeton exploitable")
                    token = None
                # Un rôle NON ouvert à l'inscription ne doit jamais pouvoir être
                # obtenu par un simple appel HTTP : c'est la faille corrigée en
                # bêta 3, éprouvée ici à chaque lancement.
                for rang, provisioned in enumerate(
                        [a for a in contract["actors"] if a not in self_register], start=1):
                    status, _b = _http("POST", base + "/register",
                                       {"username": _identifiant_smoke(contract, rang),
                                        "password": "smokepass123", "actor": provisioned})
                    if status == 200:
                        errors.append(f"/register a accepté le rôle provisionné '{provisioned}' "
                                      f"(élévation de privilège : un refus 403 était attendu)")
            else:
                warnings.append("Aucun rôle 'selfRegister' : parcours d'inscription non éprouvé "
                                "(comptes provisionnés par manage.py).")

            # --- 2b. chaque route du contrat, en conditions réelles ---
            for route in contract["routes"]:
                path, method = route["path"], route["method"]
                concrete = path.replace("{id}", "1")
                if route["auth_required"] and route["allowed_actors"]:
                    status, _b = _http(method, base + concrete,
                                       body={} if method in ("POST", "PUT") else None)
                    if status not in (401, 403):
                        errors.append(f"{method} {path} sans jeton a répondu {status} "
                                      f"(un refus 401/403 était attendu)")
                elif route["auth_required"]:
                    # POINT 74 : une route protégée AUTREMENT que par un JWT —
                    # le webhook de paiement, authentifié par la signature du
                    # prestataire. Aucun acteur ne l'ouvre, donc exiger 401/403
                    # n'a pas de sens : sans clé configurée elle répond 503, et
                    # avec clé 400 (signature absente). Ce qui doit être vrai
                    # dans tous les cas, c'est qu'une requête nue est REFUSÉE.
                    status, _b = _http(method, base + concrete,
                                       body={} if method in ("POST", "PUT") else None)
                    if status < 400:
                        errors.append(f"{method} {path} a accepté une requête sans "
                                      f"aucune authentification (réponse {status})")
                if method == "GET" and not route["auth_required"]:
                    status, _b = _http("GET", base + concrete)
                    if route["action"] == "List" and status != 200:
                        errors.append(f"GET {path} (public) a répondu {status} (attendu 200)")
                    if route["action"] == "Read" and status not in (200, 404):
                        errors.append(f"GET {path} (public) a répondu {status} (attendu 200/404)")
                if method == "GET" and route["auth_required"] and token \
                        and actor in route["allowed_actors"] and route["action"] == "List":
                    status, _b = _http("GET", base + concrete, token=token)
                    if status != 200:
                        errors.append(f"GET {path} avec jeton {actor} a répondu {status} "
                                      f"(attendu 200)")

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
                        payload[nom] = _sample_value(spec["type"], nom, spec)
                        continue
                    # Les clés étrangères sont CONTRAINTES en base : inventer
                    # un identifiant ferait échouer l'insertion pour une
                    # raison qui n'a rien à voir avec le contrat.
                    parent = references.get(nom)
                    identifiant = _premier_id(base, parent, token) if parent else None
                    if identifiant is None:
                        parent_absent = (nom, parent)
                        break
                    payload[nom] = identifiant
                if parent_absent:
                    nom, parent = parent_absent
                    warnings.append(
                        f"création de {route['entity']} non éprouvée : « {nom} » "
                        f"exige un {parent} existant, et aucun n'est lisible "
                        f"(ajouter un bloc 'seed {parent}' rendrait ce chemin "
                        f"vérifiable)")
                    break
                status, _b = _http("POST", base + route["path"], payload,
                                   token=None if not route["auth_required"] else token)
                if status != 200:
                    errors.append(f"POST {route['path']} avec un corps conforme au contrat "
                                  f"a répondu {status} (attendu 200)")
                break

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
                    status, _b = _http("GET", url)
                    if status != 200:
                        errors.append(
                            f"l'asset déclaré '{cle}' ({assets[cle]}) a répondu {status} sur "
                            f"/site/{assets[cle]} : le fichier existe mais n'est pas SERVI.")
                # Un dossier d'assets déclaré mais monté nulle part est un piège
                # silencieux : on l'éprouve sur un fichier réel du dossier.
                temoin = next((n for n in sorted(os.listdir(assets_src))
                               if os.path.isfile(os.path.join(assets_src, n))), None)
                if temoin:
                    status, _b = _http("GET", f"{base}/site/{assets_dir}/{temoin}")
                    if status != 200:
                        errors.append(
                            f"le dossier d'assets '{assets_dir}/' n'est pas servi : "
                            f"/site/{assets_dir}/{temoin} a répondu {status}.")

            # --- 3. frontend réel dans jsdom (si Node disponible) ---
            if has_frontend:
                node = shutil.which("node")
                if not node:
                    warnings.append("Node.js introuvable — le frontend n'a pas été exécuté "
                                    "(vérification statique seule). Installer node pour un "
                                    "smoke test complet.")
                else:
                    jsdom_ok = _ensure_jsdom(workdir, say)
                    if not jsdom_ok:
                        warnings.append("jsdom indisponible (installation npm échouée) — "
                                        "le frontend n'a pas été exécuté.")
                    else:
                        runner = os.path.join(workdir, "_smoke_runner.js")
                        with open(runner, "w", encoding="utf-8") as fh:
                            fh.write(JSDOM_RUNNER)
                        proc = subprocess.run(
                            [node, runner, os.path.join(workdir, "frontend"), base],
                            cwd=workdir, capture_output=True, text=True, timeout=60,
                            env={**os.environ, "NODE_PATH": _jsdom_node_path()})
                        report = None
                        for line in proc.stdout.splitlines():
                            try:
                                report = json.loads(line)
                                break
                            except json.JSONDecodeError:
                                continue
                        if report is None:
                            errors.append("le runner jsdom n'a rendu aucun rapport : "
                                          + (proc.stderr or proc.stdout)[-300:])
                        else:
                            for err in dict.fromkeys(report["js_errors"]):  # dédoublonné (onerror + listener)
                                errors.append(f"exception JavaScript dans le frontend : {err}")
                            known = {r["path"].split("/")[1] for r in contract["routes"]}
                            known |= {"register", "login", "logout", "docs", "site"}
                            for f in report["fetches"]:
                                first = f["url"].lstrip("/").split("/")[0].split("?")[0]
                                if f["url"].startswith("/") and first not in known:
                                    errors.append(f"le frontend appelle un chemin hors "
                                                  f"contrat : {f['url']}")
                                elif f["status"] in (0, 404, 422, 500):
                                    errors.append(f"appel frontend {f['url']} → "
                                                  f"{f['status'] or f.get('error', '?')}")
                            if not report["fetches"]:
                                warnings.append("le frontend n'a émis aucun appel API au "
                                                "chargement — rien à éprouver côté réseau.")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            # `stderr=PIPE` ouvre un descripteur que ni terminate() ni wait()
            # ne referment. Sans ce close, chaque smoke test en laisse un
            # derrière lui — et le smoke test tourne à chaque `monl run`.
            if server.stderr:
                server.stderr.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return (not errors), errors, warnings


# jsdom est installé UNE FOIS dans un cache utilisateur (~/.monl/jsdom),
# jamais dans le projet : volumineux, hors dépôt, réutilisable entre projets.
def _jsdom_cache_dir():
    return os.path.join(os.path.expanduser("~"), ".monl", "jsdom")


def _jsdom_node_path():
    return os.path.join(_jsdom_cache_dir(), "node_modules")


def _ensure_jsdom(workdir, say):
    if os.path.isdir(os.path.join(_jsdom_node_path(), "jsdom")):
        return True
    cache = _jsdom_cache_dir()
    os.makedirs(cache, exist_ok=True)
    say(" -> Installation unique de jsdom (cache ~/.monl/jsdom)…")
    proc = subprocess.run(["npm", "install", "--prefix", cache, "jsdom", "--silent"],
                          capture_output=True, text=True, timeout=300)
    return proc.returncode == 0 and os.path.isdir(os.path.join(_jsdom_node_path(), "jsdom"))
