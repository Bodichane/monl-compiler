"""Le socle visuel partagé par les pages de la plateforme.

Une seule feuille, un seul gabarit : la console et le guide ne peuvent pas
diverger d'aspect, et un correctif de contraste se fait une fois.

Trois contraintes, toutes tenues ici plutôt que rappelées page par page.

**Aucune ressource externe.** Pas de CDN, pas de police distante, pas
d'icône téléchargée. La plateforme se sert elle-même : elle doit s'ouvrir
derrière un pare-feu, et le dépôt exige déjà cette autonomie des frontends
qu'il fait produire. Les icônes sont donc des SVG en ligne, et les polices
celles du système.

**Les deux thèmes, pas un.** Le thème suit `prefers-color-scheme` par
défaut, et la bascule écrit `data-theme` sur `<html>` — ce qui doit gagner
dans les DEUX sens, sinon un visiteur en mode sombre ne peut plus revenir au
clair. Le choix est mémorisé, et appliqué AVANT le rendu (script en tête de
page) : appliqué après, la page clignote en clair une fraction de seconde.

**Le contraste est vérifié, pas espéré.** Les couples encre/fond des deux
thèmes tiennent le 4.5:1 de WCAG AA ; `tests/test_platform_apparence.py` le
mesure plutôt que de le croire.
"""

from __future__ import annotations

# Identité Monl : charbon, lin et ambre — le monde du terminal, sans le vert
# que tout outil d'infrastructure emploie. L'ambre change de valeur selon le
# fond (brûlé le jour, vif la nuit) : c'est la même couleur, pas deux accents.
CSS = """
:root {
  color-scheme: light dark;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace;

  --bg: #f6f4f0;
  --surface: #fffdfa;
  --surface-2: #ede9e2;
  --ink: #171512;
  --muted: #615b51;
  --line: #d3cabb;
  --line-strong: #8f8060;
  --brand: #96520a;
  --brand-strong: #7a4108;
  --on-brand: #ffffff;
  --soft: #fbeed5;
  --danger: #a32448;
  --danger-bg: #fcecf1;
  --danger-line: #e0b3c1;
  --code-bg: #0f0e0c;
  --code-ink: #f0e9dd;
  --code-accent: #ffb020;
  --code-muted: #a79e90;
  --code-line: #2b2721;

  --radius: 12px;
  --radius-lg: 18px;
  --shell: 1180px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
  --shadow: 0 1px 2px rgba(23, 20, 26, .07), 0 18px 44px rgba(23, 20, 26, .08);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
  --bg: #0b0a09;
  --surface: #141210;
  --surface-2: #1d1a16;
  --ink: #f3ece0;
  --muted: #a79e90;
  --line: #3d372e;
  --line-strong: #6f6555;
  --brand: #ffb020;
  --brand-strong: #ffc559;
  --on-brand: #241800;
  --soft: #2e2213;
  --danger: #ff8fa8;
  --danger-bg: #2a1219;
  --danger-line: #5c2a38;
  --code-bg: #060505;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 12px 32px rgba(0, 0, 0, .3);
  }
}

:root[data-theme="dark"] {
  --bg: #0b0a09;
  --surface: #141210;
  --surface-2: #1d1a16;
  --ink: #f3ece0;
  --muted: #a79e90;
  --line: #3d372e;
  --line-strong: #6f6555;
  --brand: #ffb020;
  --brand-strong: #ffc559;
  --on-brand: #241800;
  --soft: #2e2213;
  --danger: #ff8fa8;
  --danger-bg: #2a1219;
  --danger-line: #5c2a38;
  --code-bg: #060505;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 12px 32px rgba(0, 0, 0, .3);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 88px; overflow-x: clip; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--sans); font-size: 16px; line-height: 1.6;
  -webkit-text-size-adjust: 100%; overflow-x: clip;
}
body::selection { background: var(--brand); color: var(--on-brand); }
button, input, textarea, select { font: inherit; color: inherit; }
a { color: inherit; }
img, svg { max-width: 100%; }
h1, h2, h3, h4 { line-height: 1.12; letter-spacing: -.035em; margin: 0; font-weight: 750; }
p { margin: 0 0 var(--space-4); }
code { font-family: var(--mono); font-size: .92em; }

.shell { width: min(var(--shell), calc(100% - 40px)); margin-inline: auto; }
.skip {
  position: absolute; left: -9999px; top: 0; z-index: 60;
  background: var(--brand); color: var(--on-brand);
  padding: var(--space-3) var(--space-4); border-radius: 0 0 var(--radius) 0;
}
.skip:focus { left: 0; }

/* ---------- barre de navigation ---------- */
.topbar {
  position: sticky; top: 0; z-index: 30;
  background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line);
}
.scroll-progress {
  position:fixed; inset:0 0 auto; height:2px; z-index:50; pointer-events:none;
  background:var(--brand); transform:scaleX(0); transform-origin:left;
}
.nav { height: 68px; display: flex; align-items: center; gap: var(--space-5); }
.brand {
  display: inline-flex; align-items: center; gap: 10px; min-height: 44px;
  color:var(--ink); font-weight: 700; letter-spacing: -.02em; text-decoration: none;
}
.mark {
  width: 34px; height: 34px; border-radius: 10px; flex: none;
  display: grid; place-items: center; overflow:hidden;
}
.mark svg { width:100%; height:100%; display:block; }
.brand-copy { display:flex; align-items:baseline; gap:7px; white-space:nowrap; }
.brand-copy strong { font-size:16px; letter-spacing:-.035em; }
.brand-copy small { color:var(--muted); font:600 9px var(--mono); letter-spacing:.13em; text-transform:uppercase; }
.navlinks {
  display: flex; align-items: center; gap: var(--space-2);
  margin-left: auto; color: var(--muted); font-size: 15px;
}
.navlinks a {
  text-decoration: none; padding: 8px 12px; border-radius: 10px;
  min-height: 44px; display: inline-flex; align-items: center; gap: 7px;
  transition: background .18s ease, color .18s ease;
}
.navlinks a:hover { background: var(--surface-2); color: var(--ink); }
.navlinks a[aria-current="page"] { color: var(--ink); font-weight: 600; background: var(--soft); }

/* ---------- contrôles ---------- */
.primary, .secondary, .ghost, .nav-cta {
  min-height: 44px; border-radius: 11px; padding: 0 18px;
  border: 1px solid transparent; cursor: pointer; text-decoration: none;
  display: inline-flex; align-items: center; justify-content: center; gap: 9px;
  font-weight: 600;
  transition: background .18s ease, border-color .18s ease, color .18s ease;
}
.primary, .nav-cta { background: var(--brand); color: var(--on-brand); }
.primary:hover, .nav-cta:hover { background: var(--brand-strong); }
.primary[disabled] { opacity: .6; cursor: not-allowed; }
.secondary { background: var(--surface); border-color: var(--line-strong); }
.secondary:hover { border-color: var(--muted); }
.ghost { background: transparent; color: var(--muted); }
.ghost:hover { background: var(--surface-2); color: var(--ink); }
.icon-btn {
  width: 44px; height: 44px; border-radius: 11px; flex: none;
  display: inline-grid; place-items: center; cursor: pointer;
  background: transparent; border: 1px solid var(--line-strong); color: var(--muted);
  transition: background .18s ease, color .18s ease;
}
.icon-btn:hover { background: var(--surface-2); color: var(--ink); }
.icon { width: 18px; height: 18px; flex: none; }
:focus-visible { outline: 3px solid color-mix(in srgb, var(--brand) 55%, transparent); outline-offset: 2px; }

/* ---------- blocs de contenu ---------- */
.section { padding: var(--space-8) 0; }
.section-head { max-width: 720px; margin-bottom: var(--space-6); }
.section-head h2 { font-size: clamp(28px, 4vw, 40px); margin-bottom: var(--space-3); }
.section-head p { color: var(--muted); font-size: 18px; margin: 0; }
.eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  font: 600 12px var(--mono); letter-spacing: .12em; text-transform: uppercase;
  color: var(--brand); margin-bottom: var(--space-3);
}
.eyebrow::before { content: ""; width: 18px; height: 2px; background: currentColor; }
.card {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius); padding: var(--space-5);
}
.lift { transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease; }
.lift { position:relative; overflow:hidden; }
.lift::after { content:""; position:absolute; inset:0; pointer-events:none; opacity:0;
  background:linear-gradient(120deg,transparent 30%,color-mix(in srgb,var(--brand) 8%,transparent),transparent 70%);
  transform:translateX(-55%); transition:opacity .25s ease,transform .5s ease; }
.lift:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--brand) 45%, var(--line)); box-shadow: var(--shadow); }
.lift:hover::after { opacity:1; transform:translateX(55%); }
.motion-ready [data-reveal] { opacity: 0; transform: translateY(14px); }
.motion-ready [data-reveal].is-visible {
  opacity: 1; transform: none;
  transition: opacity .42s ease, transform .42s cubic-bezier(.2,.75,.25,1);
  transition-delay: var(--reveal-delay, 0ms);
}
.muted { color: var(--muted); }
.codeblock {
  position: relative; background: var(--code-bg); color: var(--code-ink);
  border-radius: var(--radius); padding: var(--space-5);
  overflow-x: auto; font: 13px/1.7 var(--mono); white-space: pre;
}
.codeblock .kw { color: var(--code-accent); }
.codeblock .cm { color: var(--code-muted); }
.copy {
  position: absolute; top: 8px; right: 8px; min-height: 44px;
  padding: 0 12px; border-radius: 8px; cursor: pointer; font-size: 13px;
  background: rgba(255, 255, 255, .1); color: var(--code-ink);
  border: 1px solid rgba(255, 255, 255, .18);
}
.copy:hover { background: rgba(255, 255, 255, .18); }
table.grid { width: 100%; border-collapse: collapse; font-size: 15px; }
table.grid th, table.grid td {
  text-align: left; padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line); vertical-align: top;
}
table.grid th { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
table.grid td code { background: var(--surface-2); padding: 2px 6px; border-radius: 6px; }
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }

.footer-wrap { border-top:1px solid var(--line); background:var(--surface); }
.footer { padding:var(--space-7) 0 var(--space-5); color:var(--muted); font-size:14px; }
.footer-grid { display:grid; grid-template-columns:1.35fr repeat(3,1fr); gap:var(--space-7); }
.footer-brand { max-width:330px; }
.footer-brand .brand { color:var(--ink); margin-bottom:var(--space-4); }
.footer-brand p { margin:0; }
.footer h2 { color:var(--ink); font:600 13px var(--sans); margin-bottom:var(--space-3); }
.footer nav { display:flex; flex-direction:column; align-items:flex-start; gap:0; }
.footer a { text-decoration:none; }
.footer nav a { min-height:44px; display:inline-flex; align-items:center; }
.footer nav a:hover { color:var(--ink); text-decoration:underline; }
.footer-bottom { display:flex; justify-content:space-between; gap:var(--space-4); flex-wrap:wrap;
  margin-top:var(--space-7); padding-top:var(--space-4); border-top:1px solid var(--line); }
.service-status { min-height:44px; display:inline-flex; align-items:center; gap:7px; }
.service-status::before { content:""; width:8px; height:8px; border-radius:50%; background:var(--brand);
  box-shadow:0 0 0 4px color-mix(in srgb,var(--brand) 16%,transparent); }

@media (max-width: 780px) {
  .navlinks a:not(.nav-cta):not(.icon-btn) { display: none; }
  .section { padding: var(--space-7) 0; }
  .footer-grid { grid-template-columns:1fr 1fr; gap:var(--space-6); }
  .footer-brand { grid-column:1/-1; }
}
@media (max-width: 480px) { .footer-grid { grid-template-columns:1fr; } .footer-brand { grid-column:auto; } .brand-copy small { display:none; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important; transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
"""

# Appliqué avant le rendu : après, la page clignote en clair chez qui a
# choisi le sombre.
THEME_BOOT = """
(function () {
  try {
    var saved = localStorage.getItem('monl-theme');
    if (saved === 'dark' || saved === 'light') {
      document.documentElement.setAttribute('data-theme', saved);
    }
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.documentElement.classList.add('motion-ready');
    }
  } catch (e) { /* stockage refusé : le thème système suffit */ }
})();
"""

THEME_TOGGLE = """
(function () {
  var button = document.getElementById('theme-toggle');
  if (!button) return;
  function courant() {
    var forced = document.documentElement.getAttribute('data-theme');
    if (forced) return forced;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function annoncer() {
    var vers = courant() === 'dark' ? 'clair' : 'sombre';
    button.setAttribute('aria-label', 'Basculer en thème ' + vers);
    button.setAttribute('title', 'Thème ' + vers);
  }
  annoncer();
  button.addEventListener('click', function () {
    var suivant = courant() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', suivant);
    try { localStorage.setItem('monl-theme', suivant); } catch (e) { /* ignoré */ }
    annoncer();
  });
})();

(function () {
  var bar = document.querySelector('.scroll-progress');
  if (!bar) return;
  var scheduled = false;
  function update() {
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var progress = max > 0 ? Math.min(1, window.scrollY / max) : 0;
    bar.style.transform = 'scaleX(' + progress + ')';
    scheduled = false;
  }
  window.addEventListener('scroll', function () {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(update);
  }, { passive: true });
  update();
})();

(function () {
  var items = document.querySelectorAll('[data-reveal]');
  if (!items.length) return;
  if (!('IntersectionObserver' in window)) {
    items.forEach(function (item) { item.classList.add('is-visible'); });
    return;
  }
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12 });
  items.forEach(function (item) { observer.observe(item); });
})();
"""

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
    "plug": '<path d="m8 12 8-8M14 3l7 7M3 14l7 7M4 20l4-4M16 8l4-4"/>',
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

# Le signe assemble un « m » structurel et une barre de compilation. Les
# formes sont des tracés, pas du texte : le dessin ne dépend d'aucune police.
LOGO_MARK = (
    '<svg viewBox="0 0 48 48" role="img" aria-label="Monl">'
    '<path d="M6 14l7 7-7 7" fill="none" stroke="currentColor" stroke-width="3.4" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M20 34V19l6.5 8 6.5-8v15" fill="none" stroke="currentColor" '
    'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="38" y="17" width="4.5" height="17" rx="1.2" fill="currentColor"/>'
    '</svg>'
)

# Le favicon, lui, ne peut PAS être en currentColor : il vit dans un onglet,
# hors de toute page, sans couleur héritée. Il porte donc sa pastille et son
# ambre en dur — c'est la seule place où un fond est justifié, et l'onglet
# d'un navigateur en attend un.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" '
    'aria-label="Monl">'
    '<rect width="48" height="48" rx="11" fill="#0b0a09"/>'
    '<path d="M6 14l7 7-7 7" fill="none" stroke="#ffb020" stroke-width="3.4" '
    'stroke-linecap="round" stroke-linejoin="round" transform="translate(2)"/>'
    '<path d="M20 34V19l6.5 8 6.5-8v15" fill="none" stroke="#ffb020" '
    'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="37" y="17" width="4.5" height="17" rx="1.2" fill="#ffb020" opacity=".55"/>'
    '</svg>'
)
FAVICON = LOGO_SVG


def _brand() -> str:
    return (f'<span class="mark" aria-hidden="true">{LOGO_MARK}</span>'
            '<span class="brand-copy"><strong>monl</strong><small>compiler</small></span>')


def _lien(href: str, libelle: str, actif: str, cle: str) -> str:
    courant = ' aria-current="page"' if actif == cle else ""
    return f'<a href="{href}"{courant}>{libelle}</a>'


def page(*, title: str, description: str, body: str, active: str = "",
         scripts: str = "", extra_css: str = "") -> str:
    """Le gabarit commun. `body` est inséré tel quel dans `<main>`."""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{description}">
<meta name="theme-color" content="#0b0a09" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f6f4f0" media="(prefers-color-scheme: light)">
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
{_lien("/guide#mcp", icon("plug") + "MCP", active, "mcp")}
{_lien("/docs", icon("docs") + "Docs API", active, "docs")}
{_lien("/account", icon("shield") + "Compte", active, "account")}
<button class="icon-btn" id="theme-toggle" type="button" aria-label="Basculer le thème">{ICON_THEME}</button>
<a class="nav-cta" href="/console">{icon("terminal")} Ouvrir la console</a>
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
<div><h2>Développeurs</h2><nav aria-label="Développeurs"><a href="/guide#dsl">Référence DSL</a><a href="/guide#api">API HTTP</a><a href="/docs">Documentation développeur</a><a href="/api-docs">Explorateur OpenAPI</a><a href="/guide#mcp">Serveur MCP</a></nav></div>
<div><h2>Ressources</h2><nav aria-label="Ressources"><a href="/guide">Guide de démarrage</a><a href="/security">Sécurité et garanties</a><a href="/api/version">Versions</a><a href="/health">État du service</a></nav></div>
</div>
<div class="footer-bottom"><span>© monl compiler</span><a class="service-status" href="/health">Service opérationnel</a></div>
</footer></div>
<script>{THEME_TOGGLE}</script>
{scripts}
</body>
</html>"""
