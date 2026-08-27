"""Le harnais : le pilote jsdom, le port, l'appel HTTP, l'identifiant.

LE VÉRIFICATEUR EST UN CLIENT COMME UN AUTRE (points 95, 96, 100) : toute
brique qui contraint une ENTRÉE contraint aussi le smoke test, qui code ses
valeurs en dur et n'a aucun moyen de le savoir. Deux fois de suite il a
déclaré cassée une application saine. `_identifiant_smoke` dérive donc
l'identifiant du CONTRAT, il ne l'invente pas.

Le fetch de jsdom DOIT être injecté via `beforeParse` : assigné après
construction, il n'est jamais vu par les scripts de la page."""

import json
import os
import socket
import subprocess
import urllib.request

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
