"""Shared CSS and browser fragments for platform pages."""

from __future__ import annotations

CSS = """
:root {
  color-scheme: light dark;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SFMono-Regular", "JetBrains Mono", "IBM Plex Mono", Consolas, monospace;

  --bg: #eee7dc;
  --surface: #f5eee4;
  --surface-2: #e4dbcf;
  --ink: #2e2b25;
  --muted: #665f55;
  --line: #ddd4c8;
  --line-strong: #8b8175;
  --brand: #2e2b25;
  --brand-strong: #171512;
  --on-brand: #f9f4ed;
  --accent: #924821;
  --soft: #e4dbcf;
  --danger: #b3123c;
  --danger-bg: #fdecef;
  --danger-line: #f0b9c6;
  --code-bg: #2e2b25;
  --code-ink: #f9f4ed;
  --code-accent: #e7b875;
  --code-muted: #b9b0a5;
  --code-line: #514b42;

  --radius: 12px;
  --radius-lg: 18px;
  --motion-fast: 160ms;
  --motion-ui: 240ms;
  --motion-reveal: 520ms;
  --ease-out: cubic-bezier(.16, 1, .3, 1);
  --shell: 1180px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
  --shadow: 0 1px 2px rgba(46, 43, 37, .08), 0 18px 44px rgba(46, 43, 37, .09);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
  --bg: #171512;
  --surface: #211e1a;
  --surface-2: #2e2b25;
  --ink: #f9f4ed;
  --muted: #b9b0a5;
  --line: #403b34;
  --line-strong: #786f64;
  --brand: #f9f4ed;
  --brand-strong: #fffdf9;
  --on-brand: #2e2b25;
  --accent: #e5a45f;
  --soft: #2e2b25;
  --danger: #ff90a6;
  --danger-bg: #2a1220;
  --danger-line: #56283a;
  --code-bg: #0f0e0c;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 12px 32px rgba(0, 0, 0, .3);
  }
}
:root[data-theme="dark"] {
  --bg: #171512;
  --surface: #211e1a;
  --surface-2: #2e2b25;
  --ink: #f9f4ed;
  --muted: #b9b0a5;
  --line: #403b34;
  --line-strong: #786f64;
  --brand: #f9f4ed;
  --brand-strong: #fffdf9;
  --on-brand: #2e2b25;
  --accent: #e5a45f;
  --soft: #2e2b25;
  --danger: #ff90a6;
  --danger-bg: #2a1220;
  --danger-line: #56283a;
  --code-bg: #0f0e0c;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 12px 32px rgba(0, 0, 0, .3);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 88px; overflow-x: clip; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--sans); font-size: 16px; line-height: 1.6;
  -webkit-text-size-adjust: 100%; overflow-x: clip; isolation:isolate;
}
body::selection { background: var(--brand); color: var(--on-brand); }
button, input, textarea, select { font: inherit; color: inherit; }
a { color: inherit; }
img, svg { max-width: 100%; }
h1, h2, h3, h4 { line-height: 1.12; letter-spacing: -.035em; margin: 0; font-weight: 750; }
p { margin: 0 0 var(--space-4); }
code { font-family: var(--mono); font-size: .92em; }
main,.footer-wrap { position:relative; z-index:1; }
.shell { width: min(var(--shell), calc(100% - 40px)); margin-inline: auto; }
.skip {
  position: absolute; left: -9999px; top: 0; z-index: 60;
  background: var(--brand); color: var(--on-brand);
  padding: var(--space-3) var(--space-4); border-radius: 0 0 var(--radius) 0;
}
.skip:focus { left: 0; }
/* ---------- barre de navigation ---------- */
/* OPAQUE background, not 92 %: at 92 % the text scrolling underneath shows
   through and reads like a line cut in two — measured on /console. The
   `backdrop-filter` goes with it: it no longer blurs anything behind an
   opaque background. This comment lives OUTSIDE the rule, a CSS comment
   being page CONTENT (point 156) — inside, it made its own witness fail. */
.topbar {
  position: sticky; top: 0; z-index: 30;
  background: var(--bg);
  border-bottom: 1px solid var(--line);
}
.scroll-progress {
  position:fixed; inset:0 0 auto; height:2px; z-index:50; pointer-events:none;
  background:var(--brand); transform:scaleX(0); transform-origin:left;
}
.nav { height: 68px; display: flex; align-items: center; gap: var(--space-5); }
.brand {
  display: inline-flex; align-items: center; min-height: 44px;
  color:var(--ink); font-weight: 700; letter-spacing: -.02em; text-decoration: none;
}
/* The compact lockup keeps only MONL: at 112 px it is 32 px high, readable
   enough without taking over the navigation. */
.brand-wordmark { width:112px; height:auto; display:block; flex:none; }
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
  position:relative; text-decoration: none; padding: 8px 10px; border-radius: 0;
  min-height: 44px; display: inline-flex; align-items: center; gap: 7px;
  transition: color .18s ease;
}
.navlinks a::after { content:""; position:absolute; left:10px; right:10px; bottom:3px; height:1px;
  background:currentColor; transform:scaleX(0); transform-origin:center; transition:transform .18s ease; }
.navlinks a:hover { color: var(--ink); }.navlinks a:hover::after { transform:scaleX(.45); }
.navlinks a[aria-current="page"] { color: var(--ink); font-weight: 600; }
.navlinks a[aria-current="page"]::after { transform:scaleX(1); }
.navlinks .nav-cta { border-radius:11px; padding-inline:18px; }
.navlinks .nav-cta::after { display:none; }

/* ---------- controls ---------- */
.primary, .secondary, .ghost, .nav-cta {
  min-height: 44px; border-radius: 11px; padding: 0 18px;
  border: 1px solid transparent; cursor: pointer; text-decoration: none;
  display: inline-flex; align-items: center; justify-content: center; gap: 9px;
  font-weight: 600;
  touch-action: manipulation;
  transition: background var(--motion-fast) ease, border-color var(--motion-fast) ease,
              color var(--motion-fast) ease, transform var(--motion-fast) var(--ease-out),
              box-shadow var(--motion-ui) ease;
}
.primary, .nav-cta { background: var(--brand); color: var(--on-brand); }
.primary:hover, .nav-cta:hover { background: var(--brand-strong); box-shadow:0 10px 28px color-mix(in srgb,var(--brand) 18%,transparent); }
.primary:active,.secondary:active,.ghost:active,.nav-cta:active { transform:translateY(1px) scale(.985); }
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
  color: var(--accent); margin-bottom: var(--space-3);
}
.eyebrow::before { content: ""; width: 18px; height: 2px; background: currentColor; }
.card {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius); padding: var(--space-5);
}
.lift { position:relative; overflow:hidden; transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease; }
.lift:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--brand) 45%, var(--line)); box-shadow: var(--shadow); }
.motion-ready [data-reveal] { opacity: 0; transform: translateY(16px) scale(.992); }
.motion-ready [data-reveal].is-visible {
  opacity: 1; transform: none;
  transition: opacity var(--motion-reveal) ease,
              transform var(--motion-reveal) var(--ease-out);
  transition-delay: var(--reveal-delay, 0ms);
}
.muted { color: var(--muted); }
.codeblock {
  position: relative; background: var(--code-bg); color: var(--code-ink);
  border-radius: var(--radius); padding: var(--space-5);
  overflow-x: auto; font: 13px/1.7 var(--mono); white-space: pre;
}
/* Syntax highlighting. ONE palette for both themes: the code background is
   dark on both sides (#2E2B25 in light, #0F0E0C in dark), so a variant per
   theme would be a second truth to maintain for nothing.
   The seven values are measured on the LIGHTER of the two backgrounds — the
   harder one — and all hold 4.5:1, the TEXT threshold and not the graphics
   one: code is read.
   Gold (--s-act) now has only ONE use, the CRUD actions. Before, `.kw` gave
   it to every keyword of every spec: that is what made it come back
   everywhere on the site.
   Contrast BETWEEN two tokens is not the right measure: WCAG talks about the
   background, and two colors of the same lightness separated by hue are told
   apart very well. The rule held here — and VERIFIED by a test — is that no
   pair of SATURATED tokens is close in both hue (< 35°) and lightness
   (< 1.35:1). It cost three values: declared names were cream, so 1.06:1
   from the block's ink — a class that distinguished nothing; the keywords'
   pink and the strings' olive each fell 32° from gold. */
:root {
  --s-kw: #e88ba6;    /* entity, rule, relation, workflow…  5.83:1 */
  --s-act: #e7b875;   /* Create, Read, Update, Delete       7.73:1 */
  --s-type: #9ec8a8;  /* String, Money, DateTime…           7.58:1 */
  --s-nom: #c4b0dd;   /* declared names                     7.12:1 */
  --s-str: #b9d489;   /* "strings"                          8.63:1 */
  --s-num: #9fbeda;   /* numbers                            7.29:1 */
  --s-cm: #9d9488;    /* # comments                         4.72:1 */
}
.s-kw { color: var(--s-kw); }
.s-act { color: var(--s-act); }
.s-type { color: var(--s-type); }
.s-nom { color: var(--s-nom); }
.s-str { color: var(--s-str); }
.s-num { color: var(--s-num); }
.s-cm { color: var(--s-cm); }
/* `.kw` and `.cm` remain for what is NOT a monl spec — the guide's shell
   blocks carry hand-marked comments. */
.codeblock .kw { color: var(--s-kw); }
.codeblock .cm { color: var(--s-cm); }
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

.footer-wrap { border-top:1px solid var(--line); }
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
.footer-legal { display:flex; gap:var(--space-4); flex-wrap:wrap; }
.footer-legal a { min-height:44px; display:inline-flex; align-items:center; }
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

/* Theme switch as a circular reveal. The API's default fade is removed: both
   layers stay opaque and the new one's clip-path uncovers the page. The
   @media (prefers-reduced-motion) block does NOT apply to these
   pseudo-elements (none is reached by `*`) — so refusing motion is handled
   in JavaScript, before the transition is even opened. */
::view-transition-old(root), ::view-transition-new(root) {
  animation: none; mix-blend-mode: normal;
}
::view-transition-old(root) { z-index: 0; }
::view-transition-new(root) { z-index: 1; }
"""

# Applied before rendering: afterwards, the page flashes light for whoever
# chose dark.
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
  } catch (e) { /* storage refused: the system theme is enough */ }
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
    var vers = courant() === 'dark' ? 'light' : 'dark';
    button.setAttribute('aria-label', 'Switch to ' + vers + ' theme');
    button.setAttribute('title', vers.charAt(0).toUpperCase() + vers.slice(1) + ' theme');
  }
  annoncer();
  function basculer() {
    var suivant = courant() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', suivant);
    try { localStorage.setItem('monl-theme', suivant); } catch (e) { /* ignored */ }
    annoncer();
  }
  var doux = window.matchMedia('(prefers-reduced-motion: reduce)');
  button.addEventListener('click', function () {
    if (!document.startViewTransition || doux.matches) { basculer(); return; }
    var boite = button.getBoundingClientRect();
    var x = boite.left + boite.width / 2;
    var y = boite.top + boite.height / 2;
    var rayon = Math.hypot(Math.max(x, window.innerWidth - x),
                           Math.max(y, window.innerHeight - y));
    document.startViewTransition(basculer).ready.then(function () {
      document.documentElement.animate(
        { clipPath: ['circle(0px at ' + x + 'px ' + y + 'px)',
                     'circle(' + rayon + 'px at ' + x + 'px ' + y + 'px)'] },
        { duration: 420, easing: 'cubic-bezier(.4, 0, .2, 1)',
          pseudoElement: '::view-transition-new(root)' });
    }, function () { /* transition refused: the theme has already switched */ });
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
