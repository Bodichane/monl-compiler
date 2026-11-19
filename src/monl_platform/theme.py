"""Public theme façade and page template.

The shared page skeleton, brand assets and icons stay together here; the
large CSS and browser fragments are kept in a dedicated static module.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .brand import (
    MARK_PATH,
    NAV_MARK_PATH,
    NAV_TEXT_OFFSET_Y,
    NAV_TEXT_PATH,
    NAV_VIEW,
    VIEW,
    WORDMARK_PATH,
)
from .theme_ambiance import CSS as AMBIANCE_CSS
from .theme_fragments import CSS, THEME_BOOT, THEME_TOGGLE

ICON_THEME = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" aria-hidden="true">'
    '<path d="M12 3v1.5M12 19.5V21M4.2 4.2l1.1 1.1M18.7 18.7l1.1 1.1M3 12h1.5M19.5 12H21'
    'M4.2 19.8l1.1-1.1M18.7 5.3l1.1-1.1"/><circle cx="12" cy="12" r="4"/></svg>'
)

_ICONS = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10M9.5 20v-6h5v6"/>',
    "terminal": '<path d="m5 7 4 4-4 4M11 17h8"/><rect x="3" y="3" width="18" height="18" rx="3"/>',
    "book": '<path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22z"/><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z"/>',
    "docs": '<path d="M6 2h9l4 4v16H6z"/><path d="M14 2v5h5M9 12h7M9 16h7"/>',
    "mcp": '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h5m0 0 5-6m-5 6 5 6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>',
    "compiler": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m7 10 3 2-3 2m6 0h4"/>',
    "key": '<circle cx="8" cy="12" r="4"/><path d="M12 12h9m-3 0v3m-3-3v2"/>',
    "shield": '<path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10Z"/><path d="m9 12 2 2 4-5"/>',
    "code": '<path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/>',
    "package": '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 7 9 5 9-5M3 12l9 5 9-5M3 17l9 5 9-5"/>',
    "upload": '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 15v5h16v-5"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
}


def icon(name: str) -> str:
    """Return a decorative, dependency-free outline icon."""
    path = _ICONS[name]
    return (f'<svg class="icon" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{path}</svg>')

# The compiler's core, vectorized from the artwork. Monochrome and without a
# background, it inherits the page's ink and so stays readable in both themes.
LOGO_MARK = (
    f'<svg viewBox="0 0 48 48" role="img" aria-label="Monl">'
    f'<path d="{MARK_PATH}" fill="currentColor" fill-rule="evenodd"/>'
    '</svg>'
)

# The favicon, however, CANNOT be in currentColor: it lives in a tab, outside
# any page, with no inherited color. It therefore carries its badge hard-coded
# — it is the only place where a background is justified, and a browser tab
# expects one.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" '
    'aria-label="Monl">'
    '<rect width="48" height="48" rx="11" fill="#2e2b25"/>'
    f'<path d="{MARK_PATH}" fill="#f9f4ed" fill-rule="evenodd"/>'
    '</svg>'
)
FAVICON = LOGO_SVG

ICON_ICO = Path(__file__).with_name("static") / "favicon.ico"


def _fingerprint(donnees: bytes) -> str:
    """Eight characters DERIVED from the icon's content.

    They travel in the URL declared by the page. Without them, `/favicon.ico`
    is an address that NEVER changes: the browser keeps the icon it already
    has, and the old one "reappears" through no fault of the server — the
    defect reported on the logo change. A hand-written version number would
    have the same effect the day someone forgets to increment it; a
    fingerprint of the content changes exactly when the image changes, never
    before, never after."""
    return hashlib.sha256(donnees).hexdigest()[:8]


VERSION_ICO = _fingerprint(ICON_ICO.read_bytes())
VERSION_SVG = _fingerprint(FAVICON.encode())


def cache_icon(requested: str, expected: str) -> dict:
    """An icon's cache header, depending on whether the URL carries its
    fingerprint.

    A versioned URL can be kept for a year: its content will not change, since
    different content would carry another address. A BARE URL, however, is
    the one the browser requests by default without reading the page — it
    cannot be versioned, so it is kept briefly, so that a stale icon expires
    by itself instead of surviving a day."""
    if requested == expected:
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    return {"Cache-Control": "public, max-age=300"}

# The wordmark is INLINE, and it is a fix, not a preference: served as an
# `<img>`, it would carry the artwork's dark background whatever the theme —
# that is, a logo that disappears from the light header (measured 1.29:1 on the
# old one). As SVG in the page, the whole lockup follows the ink and its
# background stays transparent.
WORDMARK = (
    '<svg class="brand-wordmark brand-wordmark-full" xmlns="http://www.w3.org/2000/svg" '
    f'viewBox="0 0 {VIEW[0]} {VIEW[1]}" role="img" aria-label="monl">'
    f'<path d="{WORDMARK_PATH}" fill="currentColor" fill-rule="evenodd"/>'
    '</svg>'
)

NAV_WORDMARK = (
    '<svg class="brand-wordmark" xmlns="http://www.w3.org/2000/svg" '
    f'viewBox="0 0 {NAV_VIEW[0]} {NAV_VIEW[1]}" role="img" aria-label="Monl">'
    f'<path d="{NAV_MARK_PATH}" fill="currentColor" fill-rule="evenodd"/>'
    f'<path d="{NAV_TEXT_PATH}" fill="currentColor" fill-rule="evenodd" '
    f'transform="translate(0 {NAV_TEXT_OFFSET_Y})"/>'
    '</svg>'
)


def _brand() -> str:
    return NAV_WORDMARK


def _link(href: str, label: str, active: str, key: str) -> str:
    current = ' aria-current="page"' if active == key else ""
    return f'<a href="{href}"{current}>{label}</a>'


def _social(title: str, description: str) -> str:
    """The share tags.

    Without them, an address pasted into Slack, X or WhatsApp only shows a
    bare link. The image must be ABSOLUTE for a bot to fetch it: it is
    therefore emitted only if `MONL_PLATFORM_PUBLIC_URL` is declared — never
    guessed from the `Host` header, which a third party controls (the same
    boundary as point 145 for the OAuth return address)."""
    base = (os.environ.get("MONL_PLATFORM_PUBLIC_URL") or "").rstrip("/")
    common = (
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="MONL">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<meta property="og:locale" content="fr_FR">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{description}">'
    )
    if not base:
        return common + '<meta name="twitter:card" content="summary">'
    return (common
            + f'<meta property="og:url" content="{base}/">'
            + f'<meta property="og:image" content="{base}/brand/monl-social.png">'
            + '<meta property="og:image:width" content="1200">'
            + '<meta property="og:image:height" content="630">'
            + '<meta property="og:image:alt" content="monl — the backend is '
              'compiled, not improvised">'
            + '<meta name="twitter:card" content="summary_large_image">'
            + f'<meta name="twitter:image" content="{base}/brand/monl-social.png">')


def page(*, title: str, description: str, body: str, active: str = "",
         scripts: str = "", extra_css: str = "") -> str:
    """The shared template. `body` is inserted as is into `<main>`."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{description}">
<meta name="theme-color" content="#171512" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f9f4ed" media="(prefers-color-scheme: light)">
{_social(title, description)}
<title>{title}</title>
<link rel="icon" href="/favicon.ico?v={VERSION_ICO}" sizes="32x32"><link rel="icon" href="/favicon.svg?v={VERSION_SVG}" type="image/svg+xml">
<script>{THEME_BOOT}</script>
<style>{CSS}{AMBIANCE_CSS}{extra_css}</style>
</head>
<body>
<div class="scroll-progress" aria-hidden="true"></div>
<div class="site-ambient" aria-hidden="true"><div class="ambient-grid"></div><div class="ambient-orbit ambient-orbit-a"><i></i><i></i><i></i></div><div class="ambient-orbit ambient-orbit-b"><i></i><i></i><i></i></div><span class="ambient-beam"></span></div>
<a class="skip" href="#contenu">Skip to content</a>
<header class="topbar"><nav class="shell nav" aria-label="Main navigation">
<a class="brand" href="/" aria-label="MONL">{_brand()}</a>
<div class="navlinks">
{_link("/", icon("home") + "Home", active, "home")}
{_link("/guide", icon("book") + "Guide", active, "guide")}
{_link("/mcp", icon("mcp") + "MCP", active, "mcp")}
{_link("/docs", icon("docs") + "API docs", active, "docs")}
{_link("/account", icon("user") + "Account", active, "account")}
<button class="icon-btn" id="theme-toggle" type="button" aria-label="Toggle theme">{ICON_THEME}</button>
<a class="nav-cta" href="/console" target="_blank" rel="noopener">{icon("compiler")} Open the console</a>
</div>
</nav></header>
<main id="contenu">
{body}
</main>
<div class="footer-wrap"><footer class="shell footer">
<div class="footer-grid">
<div class="footer-brand"><a class="brand" href="/" aria-label="MONL">{_brand()}</a>
<p>The business logic is compiled, the interface stays free. A deterministic backend and its contract from a single specification.</p></div>
<div><h2>Product</h2><nav aria-label="Product"><a href="/console">Console</a><a href="/guide#frontiere">Why Monl</a><a href="/guide#limites">Current limits</a></nav></div>
<div><h2>Developers</h2><nav aria-label="Developers"><a href="/docs">DSL reference</a><a href="/guide#api">HTTP API</a><a href="/api-docs">OpenAPI explorer</a><a href="/mcp">MCP server</a></nav></div>
<div><h2>Resources</h2><nav aria-label="Resources"><a href="/guide">Getting started</a><a href="/security">Security and guarantees</a><a href="/api/version">Versions</a><a href="/health">Service status</a></nav></div>
</div>
<div class="footer-bottom"><span>© MONL</span><nav class="footer-legal" aria-label="Legal information"><a href="/mentions-legales">Legal notice</a><a href="/conditions">Terms of use</a><a href="/confidentialite">Privacy</a></nav><a class="service-status" href="/health">Service operational</a></div>
</footer></div>
<script>{THEME_TOGGLE}</script>
{scripts}
</body>
</html>"""
