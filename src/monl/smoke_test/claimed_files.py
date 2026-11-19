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
EXTENSIONS_REFERENCED = (
    ".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".gif", ".avif", ".ico", ".bmp", ".woff", ".woff2", ".ttf",
    ".otf", ".eot", ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".pdf",
)

_REF_ATTRIBUTE = re.compile(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', re.I)

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
    found, views = [], set()
    for racine, _dirs, files in os.walk(frontend_dir):
        for name in sorted(files):
            if not name.lower().endswith((".html", ".htm", ".css")):
                continue
            full = os.path.join(racine, name)
            page = os.path.relpath(full, frontend_dir).replace(os.sep, "/")
            with open(full, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            brutes = _REF_ATTRIBUTE.findall(content) + _REF_CSS_URL.findall(content)
            for jeu in _REF_SRCSET.findall(content):
                brutes += [part.strip().split()[0]
                           for part in jeu.split(",") if part.strip()]
            for ref in brutes:
                if not _est_reference_locale(ref):
                    continue
                path = ref.strip().split("#", 1)[0].split("?", 1)[0]
                if not path.lower().endswith(EXTENSIONS_REFERENCED):
                    continue
                if (page, path) not in views:
                    views.add((page, path))
                    found.append((page, path))
    return found

def _url_of_reference(page, path):
    """The URL the BROWSER would request, the page being served under /site/.

    A rooted reference (`/photo.svg`) goes to the server root, not into
    /site/: it is a real defect, and the 404 will say so. It is not rewritten
    — rewriting means hiding."""
    if path.startswith("/"):
        return path
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
    if resolved.startswith(".."):
        return None
    return "/site/" + resolved
