"""What the frontend CLAIMS: the files cited by the HTML and the CSS.

The limit is STATED (point 137): only references carrying a known
extension are kept, so a file is never confused with a route (`/item`) or
a navigation (`#/panier`). A rooted reference (`/photo.svg`) is NOT
rewritten to `/site/`: it is a real defect, and rewriting it would hide
it."""

import os
import posixpath
import re

# ---- the frontend's local references (brick 29, point 137) ---------------- A
# file the page CLAIMS but nobody delivered breaks no script: the browser shows
# a hole, jsdom does not flinch, and the smoke test declared green. That is
# what happened to AtelierNaya — six SVGs referenced, none delivered, `monl run
# --check` green.
#
# Only references carrying a known file EXTENSION are kept. The limit is STATED
# rather than guessed: `<img src="/photos/hero">` (without an extension) is not
# checked. It is the price for NEVER reporting a contract route or a `#/x`
# navigation link — a warning that is wrong about a correct site teaches people
# to stop reading warnings (points 57 and 92).
EXTENSIONS_REFERENCEES = (
    ".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".gif", ".avif", ".ico", ".bmp", ".woff", ".woff2", ".ttf",
    ".otf", ".eot", ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".pdf",
)

_REF_ATTRIBUT = re.compile(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', re.I)

_REF_SRCSET = re.compile(r'srcset\s*=\s*["\']([^"\']+)["\']', re.I)

_REF_CSS_URL = re.compile(r'url\(\s*["\']?([^)"\']+?)["\']?\s*\)', re.I)

_SCHEMA_URL = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:')

def _est_reference_locale(ref):
    """True if the reference designates a file of THIS site.

    Excluded: anchors and fragment navigation (`#`, `#/panier`), absolute and
    protocol-relative URLs (`//cdn…`), and anything carrying a scheme
    (`data:`, `mailto:`, `tel:`, `javascript:`, `http:`…)."""
    ref = ref.strip()
    if not ref or ref.startswith(("#", "//")):
        return False
    return not _SCHEMA_URL.match(ref)

def _references_locales(frontend_dir):
    """The local files claimed by the frontend, as (page, path) pairs.

    Reads only the HTML and the CSS: a URL built in JavaScript is only known
    at runtime, and guessing it would produce false positives — the jsdom
    layer already exercises the `fetch()` calls."""
    trouvees, vues = [], set()
    for racine, _dirs, fichiers in os.walk(frontend_dir):
        for nom in sorted(fichiers):
            if not nom.lower().endswith((".html", ".htm", ".css")):
                continue
            plein = os.path.join(racine, nom)
            page = os.path.relpath(plein, frontend_dir).replace(os.sep, "/")
            with open(plein, encoding="utf-8", errors="ignore") as fh:
                contenu = fh.read()
            brutes = _REF_ATTRIBUT.findall(contenu) + _REF_CSS_URL.findall(contenu)
            for jeu in _REF_SRCSET.findall(contenu):
                brutes += [part.strip().split()[0]
                           for part in jeu.split(",") if part.strip()]
            for ref in brutes:
                if not _est_reference_locale(ref):
                    continue
                chemin = ref.strip().split("#", 1)[0].split("?", 1)[0]
                if not chemin.lower().endswith(EXTENSIONS_REFERENCEES):
                    continue
                if (page, chemin) not in vues:
                    vues.add((page, chemin))
                    trouvees.append((page, chemin))
    return trouvees

def _url_de_reference(page, chemin):
    """The URL the BROWSER would request, the page being served under /site/.

    A rooted reference (`/photo.svg`) goes to the server root, not into
    /site/: it is a real defect, and the 404 will say so. It is not rewritten
    — rewriting means hiding."""
    if chemin.startswith("/"):
        return chemin
    resolu = posixpath.normpath(posixpath.join(posixpath.dirname(page), chemin))
    if resolu.startswith(".."):
        return None
    return "/site/" + resolu
