"""The harness: the jsdom driver, the port, the HTTP call, the identifier.

THE VERIFIER IS A CLIENT LIKE ANY OTHER (points 95, 96, 100): any brick
that constrains an INPUT also constrains the smoke test, which hard-codes
its values and has no way of knowing. Twice in a row it declared a healthy
application broken. `_identifiant_smoke` therefore derives the identifier
from the CONTRACT, it does not invent it.

jsdom's fetch MUST be injected through `beforeParse`: assigned after
construction, it is never seen by the page's scripts."""

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
            report.js_errors.push('non-self-contained CDN script (the contract requires a frontend without external dependencies): ' + src);
            return '';
        }
        const rel = src.replace(/^\.?\//, '').replace(/^site\//, '');
        const p = path.join(frontendDir, rel);
        if (!fs.existsSync(p)) {
            report.js_errors.push('local script not found: ' + src);
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
                const msg = "Absolute URL forbidden — the contract requires a"
                    + " relative path (/entity): the frontend is served under /site"
                    + " by the API server; a hard-coded port breaks when it changes";
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
    report.js_errors.push('unhandled rejected promise: ' + msg);
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
    """Test account identifier matching what the app REQUIRES (point 95).

    `rang` distinguishes the accounts of a single pass: the
    privilege-escalation loop tries one per provisioned role, and two
    registrations under the same identifier would give a 409 that would be
    wrongly read as a role refusal. The `.test` domain is reserved by RFC 2606
    — never routable, hence never a real recipient by accident."""
    formes = (contract.get("api", {}).get("auth", {}).get("register", {})
              .get("identifier_forms") or [])
    suffixe = f"-{rang}" if rang else ""
    if "email" in formes:
        return f"smoke{suffixe}@monl.test"
    if "phone" in formes:
        # Range 06 99 00 00 xx: the length of a real number, without being one.
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
                # /docs and the like return HTML, and since brick 13 BINARY
                # assets (png, jpg) are fetched too — only the status matters.
                # `UnicodeDecodeError` is NOT a `JSONDecodeError`: catching it
                # only for JSON surfaced the full traceback at the first
                # non-UTF-8 byte. A latent defect until now because nothing
                # binary was ever requested.
                return resp.status, {}
    except urllib.error.HTTPError as e:
        # An HTTPError IS the response: reading it is not enough, it must be
        # closed. Without this close, every expected 401 (and the smoke test
        # causes some on purpose, to check that protected routes are protected)
        # left a descriptor behind.
        with e:
            try:
                payload = json.loads(e.read() or b"{}")
            except Exception:
                payload = {}
        return e.code, payload  # non-JSON error body tolerated too
    except urllib.error.URLError:
        return 0, {}

# jsdom is installed ONCE in a user cache (~/.monl/jsdom), never in the
# project: large, outside the repository, reusable across projects.
def _jsdom_cache_dir():
    return os.path.join(os.path.expanduser("~"), ".monl", "jsdom")

def _jsdom_node_path():
    return os.path.join(_jsdom_cache_dir(), "node_modules")

def _ensure_jsdom(workdir, say):
    if os.path.isdir(os.path.join(_jsdom_node_path(), "jsdom")):
        return True
    cache = _jsdom_cache_dir()
    os.makedirs(cache, exist_ok=True)
    say(" -> Installing jsdom once (cache ~/.monl/jsdom)…")
    proc = subprocess.run(["npm", "install", "--prefix", cache, "jsdom", "--silent"],
                          capture_output=True, text=True, timeout=300)
    return proc.returncode == 0 and os.path.isdir(os.path.join(_jsdom_node_path(), "jsdom"))
