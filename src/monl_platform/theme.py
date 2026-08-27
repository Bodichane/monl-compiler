"""Public theme façade and page template.

The shared page skeleton, brand assets and icons stay together here; the
large CSS and browser fragments are kept in a dedicated static module.
"""

from __future__ import annotations

import os

from .brand import BANNIERE, LETTRES, MARQUE_M
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

# Le « m » du logo, VECTORISÉ depuis l'artwork (voir brand.py). Un tracé, pas
# du texte : le dessin ne dépend d'aucune police installée.
LOGO_MARK = (
    f'<svg viewBox="0 0 48 48" role="img" aria-label="Monl">'
    f'<path d="{MARQUE_M}" fill="currentColor"/>'
    '</svg>'
)

# Le favicon, lui, ne peut PAS être en currentColor : il vit dans un onglet,
# hors de toute page, sans couleur héritée. Il porte donc sa pastille en dur —
# c'est la seule place où un fond est justifié, et l'onglet d'un navigateur en
# attend un.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" '
    'aria-label="Monl">'
    '<rect width="48" height="48" rx="11" fill="#2e2b25"/>'
    f'<path d="{MARQUE_M}" fill="#f9f4ed"/>'
    '</svg>'
)
FAVICON = LOGO_SVG

# Le wordmark est INLINE, et c'est un correctif, pas une préférence : en
# `<img>`, la bannière garde son fond #2e2b25 quel que soit le thème — soit
# 1,29:1 contre le fond sombre, un logo qui disparaît de l'en-tête (mesuré).
# En SVG dans la page, les deux tons suivent les variables et s'inversent.
WORDMARK = (
    '<svg class="brand-wordmark" xmlns="http://www.w3.org/2000/svg" '
    'viewBox="0 0 256 100" role="img" aria-label="monl">'
    f'<path d="{BANNIERE}" fill="currentColor"/>'
    f'<path d="{LETTRES}" fill="var(--bg)" fill-rule="evenodd"/>'
    '</svg>'
)


def _brand() -> str:
    return WORDMARK


def _lien(href: str, libelle: str, actif: str, cle: str) -> str:
    courant = ' aria-current="page"' if actif == cle else ""
    return f'<a href="{href}"{courant}>{libelle}</a>'


def _social(title: str, description: str) -> str:
    """Les balises de partage.

    Sans elles, une adresse collée dans Slack, X ou WhatsApp n'affiche qu'un
    lien nu. L'image doit être ABSOLUE pour qu'un robot la récupère : elle
    n'est donc émise que si `MONL_PLATFORM_PUBLIC_URL` est déclarée — jamais
    devinée depuis l'en-tête `Host`, qu'un tiers contrôle (même frontière
    qu'au point 145 pour l'adresse de retour OAuth)."""
    base = (os.environ.get("MONL_PLATFORM_PUBLIC_URL") or "").rstrip("/")
    commun = (
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="monl compiler">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<meta property="og:locale" content="fr_FR">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{description}">'
    )
    if not base:
        return commun + '<meta name="twitter:card" content="summary">'
    return (commun
            + f'<meta property="og:url" content="{base}/">'
            + f'<meta property="og:image" content="{base}/brand/monl-social.png">'
            + '<meta property="og:image:width" content="1200">'
            + '<meta property="og:image:height" content="630">'
            + '<meta property="og:image:alt" content="monl — le backend est '
              'compilé, pas improvisé">'
            + '<meta name="twitter:card" content="summary_large_image">'
            + f'<meta name="twitter:image" content="{base}/brand/monl-social.png">')


def page(*, title: str, description: str, body: str, active: str = "",
         scripts: str = "", extra_css: str = "") -> str:
    """Le gabarit commun. `body` est inséré tel quel dans `<main>`."""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{description}">
<meta name="theme-color" content="#171512" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f9f4ed" media="(prefers-color-scheme: light)">
{_social(title, description)}
<title>{title}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script>{THEME_BOOT}</script>
<style>{CSS}{extra_css}</style>
</head>
<body>
<div class="scroll-progress" aria-hidden="true"></div>
<a class="skip" href="#contenu">Aller au contenu</a>
<header class="topbar"><nav class="shell nav" aria-label="Navigation principale">
<a class="brand" href="/" aria-label="Monl compiler">{_brand()}</a>
<div class="navlinks">
{_lien("/", icon("home") + "Accueil", active, "home")}
{_lien("/guide", icon("book") + "Guide", active, "guide")}
{_lien("/mcp", icon("mcp") + "MCP", active, "mcp")}
{_lien("/docs", icon("docs") + "Docs API", active, "docs")}
{_lien("/account", icon("user") + "Compte", active, "account")}
<button class="icon-btn" id="theme-toggle" type="button" aria-label="Basculer le thème">{ICON_THEME}</button>
<a class="nav-cta" href="/console">{icon("compiler")} Ouvrir la console</a>
</div>
</nav></header>
<main id="contenu">
{body}
</main>
<div class="footer-wrap"><footer class="shell footer">
<div class="footer-grid">
<div class="footer-brand"><a class="brand" href="/" aria-label="Monl compiler">{_brand()}</a>
<p>Le métier est compilé, l’interface reste libre. Un backend déterministe et son contrat à partir d’une seule spécification.</p></div>
<div><h2>Produit</h2><nav aria-label="Produit"><a href="/console">Console</a><a href="/guide#frontiere">Pourquoi Monl</a><a href="/guide#limites">Limites actuelles</a></nav></div>
<div><h2>Développeurs</h2><nav aria-label="Développeurs"><a href="/guide#dsl">Référence DSL</a><a href="/guide#api">API HTTP</a><a href="/docs">Documentation développeur</a><a href="/api-docs">Explorateur OpenAPI</a><a href="/mcp">Serveur MCP</a></nav></div>
<div><h2>Ressources</h2><nav aria-label="Ressources"><a href="/guide">Guide de démarrage</a><a href="/security">Sécurité et garanties</a><a href="/api/version">Versions</a><a href="/health">État du service</a></nav></div>
</div>
<div class="footer-bottom"><span>© monl compiler</span><nav class="footer-legal" aria-label="Informations légales"><a href="/mentions-legales">Mentions légales</a><a href="/conditions">Conditions d’utilisation</a><a href="/confidentialite">Confidentialité</a></nav><a class="service-status" href="/health">Service opérationnel</a></div>
</footer></div>
<script>{THEME_TOGGLE}</script>
{scripts}
</body>
</html>"""
