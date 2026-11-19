"""What the delivered site CLAIMS, and which must be served."""

import json
import os
import posixpath
import re
from html import unescape

# A reference built at runtime (JS template, template engine) is not a file
# path: `src="${esc(p.imageUrl)}"` designates an image the API will return, not
# a file to find on disk.
_REFERENCE_DYNAMIQUE = re.compile(r"\$\{|\{\{|<%")

_BALISE_RESSOURCE = re.compile(
    r"<(?:img|script|link|source|video|audio|object)\b[^>]*?"
    r"\b(?:src|href|data)=['\"]([^'\"]+)['\"]",
    re.IGNORECASE | re.DOTALL,
)

# Only explicit resource assignments. Do not confuse a fetch('/booking') or a
# navigation link with a static file.
_RESSOURCE_JS = re.compile(
    r"\.(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]|"
    r"setAttribute\(\s*['\"](?:src|href)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_URL_CSS = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.IGNORECASE)

def _sans_corps_de_script(html):
    """Removes the BODY of <script>s, keeping the tags themselves.

    A <script>'s content is not markup: reading it as such makes a render
    function's `<img src="${...}">` template pass for a real tag. The opening
    tag is kept, otherwise the legitimate `<script src="app.js">` would
    disappear from the check."""
    return re.sub(r"(<script\b[^>]*>)(.*?)(</script\s*>)",
                  lambda m: m.group(1) + m.group(3), html,
                  flags=re.IGNORECASE | re.DOTALL)

def _declared_link_errors(project_dir, rendered_source):
    """A link declared in the spec must be found in the delivered site.

    It is the exact counterpart of the asset check (point 83): monl does not
    check that an address RESPONDS — it makes no network call — but it does
    check that it is PRESENT. Without this, the author declares their
    Instagram, the AI forgets it, and nobody notices before looking for the
    link on the live site.

    The comparison is on the address and not on the label: a label can
    legitimately be reworded by the interface, an address never."""
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if not os.path.exists(contract_path):
        return []
    try:
        with open(contract_path, encoding="utf-8") as fh:
            liens = json.load(fh).get("links") or []
    except (OSError, json.JSONDecodeError):
        return []
    source = unescape(rendered_source)
    return [
        f"declared link missing from the site: “{lien['label']}” → {lien['url']}"
        for lien in liens if lien["url"] not in source
    ]

def _dossier_assets_du_contrat(project_dir):
    """The assets folder declared by the contract, or None if it is unreadable.
    Extracted from `_frontend_local_reference_errors` (complexity ceiling)."""
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if not os.path.exists(contract_path):
        return None
    try:
        with open(contract_path, encoding="utf-8") as fh:
            return (json.load(fh).get("assets") or {}).get("dir")
    except (OSError, json.JSONDecodeError):
        return None


def _frontend_local_reference_errors(project_dir):
    """Checks the local resources actually referenced by the site.

    The smoke test runs the JavaScript and the API routes, but does not
    download images or load stylesheets like a browser. This check therefore
    complements the smoke test: it refuses CDNs, paths served by no mount,
    and every missing local file. External navigation links stay legitimate.

    Resolution follows the REAL map of ``serve.py`` (see serving.py), not an
    intuition about ``frontend/``: ``frontend/`` is mounted on ``/site`` and
    the assets folder declared by the spec on ``/site/<assets_dir>``. Each
    reference is therefore computed as a URL the way the browser would, then
    brought back to disk through these two mounts. An absolute path is not
    faulty in itself — ``/site/assets/photo.png`` is exactly what the wrapper
    serves; it is ``/assets/photo.png``, served by nobody, that is."""
    frontend_dir = os.path.join(project_dir, "frontend")
    errors = []
    prefixe_assets = (_dossier_assets_du_contrat(project_dir) or "").strip("/")
    # The wrapper mounts the assets folder only `if os.path.isdir(...)`:
    # declared in the spec does not mean present on disk. When it is missing,
    # no route is registered and Starlette lets the request fall through to
    # /site, so `assets/x.webp` is served from `frontend/assets/x.webp`.
    # Checked against a real server: taking the contract at its word made three
    # KoraMaison images that answer 200 get refused.
    monte_assets = bool(prefixe_assets) and os.path.isdir(
        os.path.join(project_dir, prefixe_assets))

    def fichier_servi(url):
        """The disk file served for a URL, or None if nothing serves it."""
        if url != "/site" and not url.startswith("/site/"):
            return None
        reste = url[len("/site"):].lstrip("/")
        if monte_assets and (reste == prefixe_assets
                             or reste.startswith(prefixe_assets + "/")):
            # Mounted BEFORE /site by the wrapper: this folder lives outside
            # frontend/, at the project root (brick 13, point 83).
            chemin = os.path.join(project_dir, reste)
        else:
            chemin = os.path.join(frontend_dir, reste)
        # StaticFiles(html=True) serves a folder's index.
        if os.path.isdir(chemin):
            chemin = os.path.join(chemin, "index.html")
        return chemin

    def check(origin, reference):
        ref = reference.strip()
        if not ref or ref.startswith(("#", "data:", "blob:", "mailto:", "tel:")):
            return
        if re.match(r"^(?:https?:)?//", ref, re.IGNORECASE):
            errors.append(f"forbidden external resource (CDN or remote URL): {origin} → {ref}")
            return
        # monl can assert nothing about a reference built at runtime: it stays
        # quiet rather than guessing a file (same trade-off as the asset
        # existence check, point 83).
        if _REFERENCE_DYNAMIQUE.search(ref):
            return
        clean = ref.split("#", 1)[0].split("?", 1)[0].strip()
        if not clean:
            return
        if clean.startswith("/"):
            url = posixpath.normpath(clean)
        else:
            url = posixpath.normpath(
                posixpath.join("/site", posixpath.dirname(origin), clean))
        candidat = fichier_servi(url)
        if candidat is None:
            errors.append(
                f"ressource jamais servie (hors de /site) : {origin} → {ref}")
            return
        if not os.path.isfile(candidat):
            relatif = os.path.relpath(candidat, project_dir).replace(os.sep, "/")
            errors.append(f"local resource missing: {relatif} (referenced by {origin})")

    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith((".html", ".css", ".js")):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fichier:
                    content = fichier.read()
            except OSError as exc:
                errors.append(f"frontend illisible : {path} — {exc}")
                continue
            origin = os.path.relpath(path, frontend_dir).replace(os.sep, "/")
            if name.endswith(".html"):
                for ref in _BALISE_RESSOURCE.findall(_sans_corps_de_script(content)):
                    check(origin, ref)
            elif name.endswith(".js"):
                for match in _RESSOURCE_JS.finditer(content):
                    check(origin, match.group(1) or match.group(2))
            elif name.endswith(".css"):
                for ref in _URL_CSS.findall(content):
                    check(origin, ref)
    return list(dict.fromkeys(errors))

def _frontend_behavioral_quality_errors(project_dir):
    """Spots a frequent trap of generated interfaces: DOM IDs.

    ``dataset`` always provides strings while JSON IDs are usually numeric. A
    strict, non-normalized lookup makes the Edit/Delete actions visually
    present but inoperative. This check stays deliberately narrow so as not to
    pretend to parse JavaScript; it only blocks the proven, fixable pattern."""
    frontend_dir = os.path.join(project_dir, "frontend")
    errors = []
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith(".js"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fichier:
                    content = fichier.read()
            except OSError:
                continue
            for match in re.finditer(
                    r"\b(?:const|let|var)\s+(\w+)\s*=\s*[^;\n]*\.dataset\.\w+",
                    content):
                variable = match.group(1)
                suffix = content[match.start():match.end()]
                if re.search(r"\b(?:Number|parseInt|parseFloat)\s*\(", suffix):
                    continue
                if re.search(rf"\.id\s*===\s*{re.escape(variable)}\b", content):
                    origin = os.path.relpath(path, frontend_dir).replace(os.sep, "/")
                    errors.append(
                        f"unnormalized DOM identifier in frontend/{origin}: "
                        f"{variable} comes from dataset and is compared with an API ID; "
                        "convert it with Number() or parseInt() before Edit/Delete.")
    return list(dict.fromkeys(errors))
