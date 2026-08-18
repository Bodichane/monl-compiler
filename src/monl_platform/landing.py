"""Page de présentation de monl, servie à la racine de la plateforme.

La console est un OUTIL : elle suppose qu'on sait déjà ce que monl fait. Cette
page-ci s'adresse à quelqu'un qui l'ignore, propose une version à installer,
puis conduit à la console.

Registre assumé : un terminal, en thème sombre unique. Le produit est une
ligne de commande, la page ne prétend donc pas être autre chose — et un thème
à moitié tenu serait pire qu'un thème assumé.

Comme la console, la page est ENTIÈREMENT autonome : aucune police web, aucune
image distante, aucun script tiers, et pas même un lien sortant. C'est ce que
vérifie ``tests/test_platform_landing.py``.
"""

from fastapi.responses import HTMLResponse

LANDING_HTML = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>monl — le compilateur d'intention logicielle</title>
<meta name="description" content="Un dialogue guidé, sans IA, produit une spécification. Le compilateur en tire un backend FastAPI scellé, son schéma SQL et le contrat que l'interface doit respecter.">
<style>
/* ════════════════════════════════════════════════════════════════════
   monl — page de présentation.
   Registre assumé : un terminal. Le produit EST une ligne de commande,
   la page ne prétend donc pas être autre chose. Un seul thème, sombre,
   peint explicitement — pas de bascule claire à moitié tenue.
   Aucune ressource distante : ni police web, ni image, ni script tiers.
   Tout ce qui bouge s'arrête sous prefers-reduced-motion.
   ════════════════════════════════════════════════════════════════════ */
:root {
  --bg:        #100e0c;
  --bg-1:      #17140f;
  --bg-2:      #1e1a15;
  --bg-3:      #262119;
  --fg:        #ece6dd;
  --fg-2:      #a89f93;
  --fg-3:      #847a6d;   /* 4,57:1 sur le fond — AA tenu, y compris pour les mentions */
  --line:      #2c2620;
  --line-2:    #3d352c;

  --clay:      #d97757;
  --clay-hi:   #e89275;
  --clay-dim:  #3a241a;
  --green:     #74c187;
  --green-dim: #16301d;
  --blue:      #7fa8dd;
  --amber:     #d9a441;
  --red:       #e0736f;

  --s1: .25rem; --s2: .5rem;  --s3: .75rem; --s4: 1rem;
  --s5: 1.5rem; --s6: 2.5rem; --s7: 4rem;   --s8: 6rem;
  --r1: .3rem;  --r2: .55rem; --r3: .9rem;

  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
          "DejaVu Sans Mono", "Liberation Mono", monospace;

  --page: min(1080px, calc(100% - 2.5rem));
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 400 15px/1.65 var(--mono);
  -webkit-font-smoothing: antialiased;
  overflow-x: hidden;
}
a { color: var(--clay); text-decoration: none; }
a:hover { color: var(--clay-hi); }
:where(a, button):focus-visible {
  outline: 2px solid var(--clay);
  outline-offset: 3px;
  border-radius: var(--r1);
}
h1, h2, h3, p, ul, ol { margin: 0; }
ul { padding: 0; list-style: none; }
code, pre { font-family: var(--mono); }

/* Halo d'ambiance : une seule source, très diffuse, jamais animée en
   continu — un fond qui bouge tout le temps fatigue et coûte du GPU. */
body::before {
  content: "";
  position: fixed;
  inset: -30vh -10vw auto;
  height: 70vh;
  background: radial-gradient(60% 60% at 50% 0%,
    rgba(217, 119, 87, .13), transparent 70%);
  pointer-events: none;
  z-index: 0;
}
.wrap { position: relative; z-index: 1; width: var(--page); margin-inline: auto; }

/* ───────────────────────────────────────────────────────── navigation ── */
.nav {
  position: sticky; top: 0; z-index: 20;
  background: rgba(16, 14, 12, .82);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(10px);
}
.nav-in {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--s4); min-height: 3.4rem; padding-block: var(--s2);
}
.logo { display: inline-flex; align-items: center; gap: var(--s2); color: var(--fg); font-weight: 700; }
.logo-mark {
  display: grid; place-items: center;
  width: 1.6rem; height: 1.6rem;
  border-radius: var(--r1);
  background: var(--clay); color: #1c0d05;
  font-size: .8rem; font-weight: 700;
}
.logo b { font-weight: 700; letter-spacing: -.01em; }
.logo span { color: var(--fg-3); font-weight: 400; }
.nav-links { display: flex; align-items: center; gap: var(--s5); }
.nav-links a { color: var(--fg-2); font-size: .84rem; }
.nav-links a:hover { color: var(--fg); }
/* `.nav-links a` est plus spécifique que `.btn` : sans cette reprise, le
   bouton d'appel à l'action sortait en gris sur argile — 2,1:1, illisible. */
.nav-links a.btn { color: #1c0d05; }
.nav-links a.btn:hover { color: #1c0d05; }

.btn {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .5rem .9rem;
  border: 1px solid var(--clay);
  border-radius: var(--r1);
  background: var(--clay); color: #1c0d05;
  font: 600 .84rem/1 var(--mono);
  white-space: nowrap;
  cursor: pointer;
  transition: background-color .16s ease, border-color .16s ease, transform .16s ease;
}
.btn:hover { background: var(--clay-hi); border-color: var(--clay-hi); color: #1c0d05; transform: translateY(-1px); }
.btn.ghost { background: transparent; color: var(--fg); border-color: var(--line-2); }
.btn.ghost:hover { background: var(--bg-2); border-color: var(--fg-3); color: var(--fg); transform: translateY(-1px); }
.btn.lg { padding: .72rem 1.2rem; font-size: .92rem; }

/* ────────────────────────────────────────────────────────────── héros ── */
.hero { padding: var(--s8) 0 var(--s7); }
.tag {
  display: inline-flex; align-items: center; gap: var(--s2);
  margin-bottom: var(--s5);
  padding: .3rem .7rem;
  border: 1px solid var(--line-2);
  border-radius: 99px;
  background: var(--bg-2);
  color: var(--fg-2);
  font-size: .76rem;
}
.tag i { color: var(--green); font-style: normal; }
h1 {
  max-width: 20ch;
  font-size: clamp(2.1rem, 5.6vw, 3.6rem);
  font-weight: 700; line-height: 1.08; letter-spacing: -.03em;
}
h1 em { color: var(--clay); font-style: normal; }
.sub {
  max-width: 62ch; margin-top: var(--s5);
  color: var(--fg-2); font-size: 1.02rem; line-height: 1.7;
}
.sub b { color: var(--fg); font-weight: 600; }
.hero-cta { display: flex; flex-wrap: wrap; gap: var(--s3); margin-top: var(--s6); }
.hero-note { margin-top: var(--s4); color: var(--fg-3); font-size: .8rem; }

/* ─────────────────────────────────────────────────────────── terminal ── */
.term {
  margin-top: var(--s7);
  border: 1px solid var(--line-2);
  border-radius: var(--r3);
  background: var(--bg-1);
  box-shadow: 0 30px 80px -40px rgba(0, 0, 0, .9);
  overflow: hidden;
}
.term-bar {
  display: flex; align-items: center; gap: var(--s3);
  padding: .6rem var(--s4);
  border-bottom: 1px solid var(--line);
  background: var(--bg-2);
}
.dots { display: flex; gap: .35rem; }
.dots i { width: .62rem; height: .62rem; border-radius: 50%; background: var(--line-2); }
.dots i:nth-child(1) { background: #4a3430; }
.dots i:nth-child(2) { background: #4a4130; }
.dots i:nth-child(3) { background: #30462f; }
.term-title { color: var(--fg-3); font-size: .78rem; }
.term-body {
  min-height: 22rem;
  padding: var(--s5);
  font-size: .86rem; line-height: 1.85;
  white-space: pre-wrap; overflow-wrap: anywhere;
}
.term-body .l { display: block; }
.c-dim { color: var(--fg-3); }
.c-fg  { color: var(--fg); }
.c-q   { color: var(--blue); }
.c-a   { color: var(--fg); }
.c-ok  { color: var(--green); }
.c-cl  { color: var(--clay); }
.c-am  { color: var(--amber); }
.caret {
  display: inline-block; width: .55em; height: 1.05em;
  vertical-align: text-bottom; background: var(--clay);
  animation: blink 1.05s steps(1) infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* ──────────────────────────────────────────────────────────── sections ── */
section { padding: var(--s8) 0; }
.eyebrow {
  display: block; margin-bottom: var(--s3);
  color: var(--clay); font-size: .74rem; font-weight: 700; letter-spacing: .16em;
  text-transform: uppercase;
}
h2 {
  max-width: 24ch;
  font-size: clamp(1.5rem, 3.4vw, 2.15rem);
  font-weight: 700; line-height: 1.18; letter-spacing: -.02em;
}
.lede { max-width: 66ch; margin-top: var(--s4); color: var(--fg-2); line-height: 1.75; }
.sep { height: 1px; background: linear-gradient(90deg, var(--line-2), transparent); }

.grid { display: grid; gap: var(--s4); margin-top: var(--s6); }
.g3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.g2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.card {
  padding: var(--s5);
  border: 1px solid var(--line);
  border-radius: var(--r2);
  background: var(--bg-1);
  transition: border-color .18s ease, transform .18s ease, background-color .18s ease;
}
.card:hover { border-color: var(--line-2); background: var(--bg-2); transform: translateY(-2px); }
.card h3 { margin-bottom: var(--s2); font-size: .98rem; font-weight: 700; }
.card p { color: var(--fg-2); font-size: .875rem; line-height: 1.7; }
.card .k {
  display: inline-block; margin-bottom: var(--s3);
  padding: .18rem .5rem;
  border-radius: var(--r1);
  background: var(--clay-dim); color: var(--clay);
  font-size: .72rem; font-weight: 700;
}

/* ───────────────────────────────────────────────────────────── pipeline ── */
.pipe { display: grid; gap: var(--s2); margin-top: var(--s6); }
.step {
  display: grid;
  grid-template-columns: 2.2rem 1fr;
  gap: var(--s4);
  padding: var(--s4) var(--s4) var(--s4) var(--s3);
  border: 1px solid var(--line);
  border-left: 2px solid var(--clay);
  border-radius: var(--r2);
  background: var(--bg-1);
}
.step .n {
  display: grid; place-items: start center;
  color: var(--clay); font-size: .8rem; font-weight: 700;
  padding-top: .15rem;
}
.step h3 { font-size: .95rem; font-weight: 700; margin-bottom: var(--s1); }
.step p { color: var(--fg-2); font-size: .875rem; line-height: 1.7; }
.step p code { color: var(--fg); background: var(--bg-3); padding: .08em .38em; border-radius: var(--r1); }

pre.code {
  margin-top: var(--s5);
  padding: var(--s5);
  border: 1px solid var(--line);
  border-radius: var(--r2);
  background: var(--bg-1);
  overflow-x: auto;
  font-size: .82rem; line-height: 1.75;
}
pre.code .kw { color: var(--clay); }
pre.code .ty { color: var(--blue); }
pre.code .st { color: var(--green); }
pre.code .cm { color: var(--fg-3); }

/* ───────────────────────────────────────────────────────────── refus ── */
.refus { display: grid; gap: var(--s2); margin-top: var(--s6); }
.refus li {
  display: grid; grid-template-columns: 1.4rem 1fr; gap: var(--s3);
  padding: var(--s3) var(--s4);
  border: 1px solid var(--line);
  border-radius: var(--r2);
  background: var(--bg-1);
  font-size: .875rem; line-height: 1.7;
}
.refus li b { color: var(--fg); font-weight: 600; }
.refus li span:first-child { color: var(--red); font-weight: 700; }
.refus li em { color: var(--fg-2); font-style: normal; }

/* ───────────────────────────────────────────────────────────── chiffres ── */
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--s4); margin-top: var(--s6); }
.stat { padding: var(--s5) var(--s4); border: 1px solid var(--line); border-radius: var(--r2); background: var(--bg-1); }
.stat b { display: block; font-size: clamp(1.4rem, 3vw, 1.9rem); font-weight: 700; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.stat span { display: block; margin-top: var(--s1); color: var(--fg-3); font-size: .78rem; }

/* ─────────────────────────────────────────────────────── téléchargement ── */
.dl { display: grid; gap: var(--s4); margin-top: var(--s6); }
.dl-item {
  display: grid; grid-template-columns: 1fr auto; align-items: center; gap: var(--s4);
  padding: var(--s5);
  border: 1px solid var(--line-2);
  border-radius: var(--r2);
  background: var(--bg-1);
}
.dl-item h3 { font-size: .95rem; font-weight: 700; }
.dl-meta { margin-top: var(--s2); color: var(--fg-3); font-size: .78rem; }
.dl-sha { display: block; margin-top: var(--s1); color: var(--fg-3); font-size: .72rem; overflow-wrap: anywhere; }
.dl-empty { padding: var(--s5); border: 1px dashed var(--line-2); border-radius: var(--r2); color: var(--fg-2); font-size: .875rem; }
.install { margin-top: var(--s4); }
.install-line {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s3);
  padding: var(--s3) var(--s4);
  border: 1px solid var(--line);
  border-radius: var(--r2);
  background: var(--bg-2);
  font-size: .84rem;
}
.install-line code { color: var(--fg); overflow-wrap: anywhere; }
.install-line .p { color: var(--green); user-select: none; }
.copy {
  padding: .3rem .6rem; border: 1px solid var(--line-2); border-radius: var(--r1);
  background: transparent; color: var(--fg-2); font: 600 .74rem/1 var(--mono); cursor: pointer;
  transition: color .15s ease, border-color .15s ease;
}
.copy:hover { color: var(--fg); border-color: var(--fg-3); }
.copy[data-done="1"] { color: var(--green); border-color: var(--green); }

/* ───────────────────────────────────────────────────────────── clôture ── */
.close {
  margin: var(--s7) 0 var(--s8);
  padding: var(--s7) var(--s6);
  border: 1px solid var(--line-2);
  border-radius: var(--r3);
  background:
    radial-gradient(80% 140% at 50% 0%, rgba(217, 119, 87, .10), transparent 70%),
    var(--bg-1);
  text-align: center;
}
.close h2 { max-width: none; margin-inline: auto; }
.close .lede { margin-inline: auto; }
.close .hero-cta { justify-content: center; }

footer { padding: var(--s6) 0 var(--s7); border-top: 1px solid var(--line); }
.foot { display: flex; flex-wrap: wrap; gap: var(--s4); justify-content: space-between; color: var(--fg-3); font-size: .78rem; }

/* ─────────────────────────────────────────────────────────── apparition ── */
.rise { opacity: 0; transform: translateY(14px); }
.rise.seen { opacity: 1; transform: none; transition: opacity .5s ease, transform .5s cubic-bezier(.16, 1, .3, 1); }

/* ───────────────────────────────────────────────────────────── largeurs ── */
@media (max-width: 900px) {
  .g3, .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .nav-links a:not(.btn) { display: none; }
}
@media (max-width: 620px) {
  :root { --page: calc(100% - 1.6rem); }
  /* En étroit, « / compilateur » cassait la marque sur deux lignes et
     poussait le bouton hors de la barre. */
  .logo span:not(.logo-mark) { display: none; }
  .nav-links { gap: var(--s3); }
  .g3, .g2, .stats { grid-template-columns: 1fr; }
  .dl-item { grid-template-columns: 1fr; }
  .term-body { min-height: 26rem; padding: var(--s4); font-size: .78rem; }
  section, .hero { padding: var(--s7) 0; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
  .rise { opacity: 1; transform: none; }
}
</style>
</head>
<body>

<header class="nav">
  <div class="wrap nav-in">
    <a class="logo" href="#top"><span class="logo-mark">m</span><b>monl</b><span>/ compilateur</span></a>
    <nav class="nav-links">
      <a href="#quoi">Ce que c'est</a>
      <a href="#comment">Comment</a>
      <a href="#refus">Ce qu'il refuse</a>
      <a href="#telecharger">Télécharger</a>
      <a class="btn" href="/console">Ouvrir la console</a>
    </nav>
  </div>
</header>

<main id="top">

  <div class="wrap hero">
    <span class="tag"><i>●</i> version <span id="version">0.9.0-beta.7</span> — bêta publique</span>
    <h1>Décrivez votre site. <em>Le compilateur écrit le serveur.</em></h1>
    <p class="sub">
      monl mène un <b>dialogue guidé, sans aucune IA et sans le moindre appel réseau</b>.
      De vos réponses il tire une spécification, puis compile un backend FastAPI complet —
      base SQLite, authentification, contrôle d'accès — et le <b>scelle</b>. L'interface est
      écrite ensuite, contre un contrat que le serveur a lui-même publié.
    </p>
    <div class="hero-cta">
      <a class="btn lg" href="#telecharger">Télécharger monl</a>
      <a class="btn ghost lg" href="/console">Essayer dans le navigateur</a>
    </div>
    <p class="hero-note">Python 3.10+ · licence FSL-1.1-ALv2 · aucune télémétrie</p>

    <div class="term" aria-label="Démonstration du dialogue guidé monl">
      <div class="term-bar">
        <span class="dots"><i></i><i></i><i></i></span>
        <span class="term-title">~/projets/atelier-horizon — monl</span>
      </div>
      <div class="term-body" id="term"></div>
    </div>
  </div>

  <section id="quoi">
    <div class="wrap">
      <span class="eyebrow">Ce que c'est</span>
      <h2>Un compilateur, pas un assistant.</h2>
      <p class="lede">
        Une IA qui écrit du code produit un résultat différent à chaque tirage. Un compilateur,
        non : la même spécification rend le même serveur, à l'octet près. monl place donc l'IA
        là où l'imprévisible est acceptable — l'apparence — et nulle part ailleurs.
      </p>
      <div class="grid g3">
        <article class="card">
          <span class="k">déterministe</span>
          <h3>Le dialogue n'invente rien</h3>
          <p>Questions fermées, saisie stricte, aucun appel réseau. La spécification produite est
             relue par le vrai analyseur avant d'être écrite sur le disque.</p>
        </article>
        <article class="card">
          <span class="k">scellé</span>
          <h3>Le backend n'est pas modifiable</h3>
          <p><code>app.py</code>, <code>schema.sql</code> et leurs voisins portent une empreinte.
             Aucun agent, aucune IA, aucune commande ne les réécrit — la vérification refuse.</p>
        </article>
        <article class="card">
          <span class="k">vérifié</span>
          <h3>Rien n'est « fait » sans preuve</h3>
          <p>Chaque construction démarre un vrai serveur éphémère, appelle de vraies routes et
             charge la page dans un vrai moteur. Un échec est un échec, pas un avertissement.</p>
        </article>
      </div>
    </div>
  </section>

  <div class="wrap"><div class="sep"></div></div>

  <section id="comment">
    <div class="wrap">
      <span class="eyebrow">Comment ça marche</span>
      <h2>Six étapes, dont une seule fait appel à une IA.</h2>
      <div class="pipe">
        <div class="step"><span class="n">01</span><div>
          <h3>Le dialogue</h3>
          <p><code>monl init</code> pose ses questions. Dix modèles d'applications servent de point
             de départ — boutique, blog, réservation, petites annonces… — et chacun est testé
             compilable, en répondant tout&nbsp;oui comme tout&nbsp;non.</p></div></div>
        <div class="step"><span class="n">02</span><div>
          <h3>La spécification</h3>
          <p>Un fichier <code>.ml</code> lisible : entités, champs, acteurs, règles, parcours.
             C'est le seul document que vous modifiez à la main, et il est fait pour ça.</p></div></div>
        <div class="step"><span class="n">03</span><div>
          <h3>La compilation</h3>
          <p>Grammaire, validation, audit de sécurité, puis génération. Sortent
             <code>app.py</code>, <code>schema.sql</code>, un <code>manage.py</code> d'administration
             et un <code>Dockerfile</code>.</p></div></div>
        <div class="step"><span class="n">04</span><div>
          <h3>Le contrat d'interface</h3>
          <p>Le serveur publie ce qu'il fait <em>vraiment</em> : routes, champs, ce qui est en
             lecture seule, qui a le droit d'écrire, les verrous. Pas ce que la spec déclarait —
             ce que le code fait.</p></div></div>
        <div class="step"><span class="n">05</span><div>
          <h3>L'interface</h3>
          <p>Une IA écrit le HTML, la CSS et le JavaScript en obéissant au contrat. Par clé d'API
             ou par un agent en ligne de commande, au choix. C'est la seule étape non
             déterministe — et la seule où l'apparence se joue.</p></div></div>
        <div class="step"><span class="n">06</span><div>
          <h3>La mise en service</h3>
          <p><code>monl run</code> vérifie la cohérence, joue le test de fumée, puis sert le site.
             <code>monl update</code> recompile et rapporte, écran par écran, ce que votre
             changement de spec vient de casser.</p></div></div>
      </div>

      <pre class="code" aria-label="Extrait d'une spécification monl"><span class="cm"># atelier-horizon.ml — extrait</span>
<span class="kw">entity</span> Product
    name: <span class="ty">String</span>
    price: <span class="ty">Money</span>
    stock: <span class="ty">Integer</span>

<span class="kw">actor</span> Customer selfRegister

<span class="kw">rule</span> Product.Read public
<span class="kw">rule</span> Product.stock min <span class="ty">0</span>
<span class="kw">rule</span> Order.total sumOf OrderLine.amount
<span class="kw">rule</span> OrderLine.amount derivedFrom Product.price by quantity
<span class="kw">rule</span> Order.total payable
<span class="kw">rule</span> OrderLine.Create decrements Product.stock by quantity</pre>
      <p class="lede">
        Six lignes de règles, et le serveur généré calcule le total côté serveur, refuse un panier
        qui dépasse le stock, décompte à la commande, restitue à l'annulation, encaisse le montant
        qu'il a lui-même calculé, et fige la commande une fois réglée.
      </p>
    </div>
  </section>

  <div class="wrap"><div class="sep"></div></div>

  <section id="refus">
    <div class="wrap">
      <span class="eyebrow">Ce qu'il refuse</span>
      <h2>Un compilateur utile est un compilateur qui dit non.</h2>
      <p class="lede">
        Chacun de ces refus vient d'une faille qui a réellement été exploitée sur un projet, puis
        fermée à la racine. Ils font échouer la compilation, en nommant la ligne fautive.
      </p>
      <ul class="refus">
        <li><span>✗</span><span><b>Un montant que le client peut écrire.</b>
          <em>Une commande était postée à 0,01 € et le serveur l'encaissait. Un champ encaissable
          doit être calculé par le serveur, sans exception — pas même pour un administrateur.</em></span></li>
        <li><span>✗</span><span><b>Une propriété qui ne remonte à aucun compte.</b>
          <em>La règle compilait en silence et rattachait les enregistrements au mauvais
          propriétaire.</em></span></li>
        <li><span>✗</span><span><b>Une règle qui ne produit rien.</b>
          <em>Quatre règles de contrainte n'avaient aucun effet sur la sortie ; un prix négatif
          partait chez le prestataire de paiement. Un test compare désormais la sortie avec et
          sans.</em></span></li>
        <li><span>✗</span><span><b>Un fichier déclaré mais absent.</b>
          <em>Trois chemins d'image fautifs compilaient sans un mot. Une image cassée ne se voit
          qu'à l'œil, une fois en ligne.</em></span></li>
        <li><span>✗</span><span><b>Une valeur client collée dans une requête SQL.</b>
          <em>Il n'existe aucune interface pour le faire : tout le contrôle d'accès passe par une
          couche d'émission typée, et un garde-fou relit le code produit pour l'interdire.</em></span></li>
        <li><span>✗</span><span><b>Une interface qui ment sur le serveur.</b>
          <em>Un appel vers une route absente du contrat fait échouer la construction. Un site
          « réussi » dont la connexion visait une route inexistante avait été livré une fois.</em></span></li>
      </ul>
    </div>
  </section>

  <div class="wrap"><div class="sep"></div></div>

  <section>
    <div class="wrap">
      <span class="eyebrow">L'état du projet</span>
      <h2>Bêta publique, mesurée.</h2>
      <div class="stats">
        <div class="stat"><b>1&nbsp;068</b><span>tests, joués à chaque changement</span></div>
        <div class="stat"><b>28</b><span>briques de langage éprouvées</span></div>
        <div class="stat"><b>10</b><span>modèles d'applications</span></div>
        <div class="stat"><b>139</b><span>décisions documentées</span></div>
      </div>
      <p class="lede">
        Chaque brique arrive avec son épreuve contre un vrai serveur : la couverture de
        compilation seule a laissé passer cinq briques pendant toute la vie du projet. Ce qui
        n'est pas prouvé par exécution n'est pas considéré comme fait.
      </p>
    </div>
  </section>

  <div class="wrap"><div class="sep"></div></div>

  <section id="telecharger">
    <div class="wrap">
      <span class="eyebrow">Télécharger</span>
      <h2>Une version, sur votre machine.</h2>
      <p class="lede">
        monl s'installe et tourne entièrement en local. La compilation ne fait aucun appel réseau ;
        seule l'écriture de l'interface en fait, et uniquement si vous le demandez.
      </p>

      <div class="dl" id="dl"><div class="dl-empty">Lecture des artefacts…</div></div>

      <div class="install">
        <div class="install-line">
          <span><span class="p">$</span> <code id="cmd-pip">pip install ./monl_compiler-0.9.0b7-py3-none-any.whl</code></span>
          <button class="copy" type="button" data-copy="cmd-pip">copier</button>
        </div>
      </div>
      <div class="install">
        <div class="install-line">
          <span><span class="p">$</span> <code id="cmd-run">monl init</code></span>
          <button class="copy" type="button" data-copy="cmd-run">copier</button>
        </div>
      </div>
      <p class="hero-note">Python 3.10 ou plus récent. Les dépendances (FastAPI, Lark, PyJWT) sont
        installées automatiquement.</p>
    </div>
  </section>

  <div class="wrap">
    <div class="close">
      <span class="eyebrow">Sans rien installer</span>
      <h2>La console fait le même travail, dans le navigateur.</h2>
      <p class="lede">Le même dialogue, une question à la fois. La construction se suit en direct :
        étapes, jetons consommés, coût réel. Le site produit est ensuite servi sous sa propre
        adresse.</p>
      <div class="hero-cta"><a class="btn lg" href="/console">Ouvrir la console</a></div>
    </div>
  </div>

</main>

<footer>
  <div class="wrap foot">
    <span>monl — compilateur d'intention logicielle · <span id="foot-version">0.9.0-beta.7</span></span>
    <span>Licence FSL-1.1-ALv2 · aucune ressource distante sur cette page</span>
  </div>
</footer>

<script>
(function () {
  "use strict";
  var reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Terminal du héros ──────────────────────────────────────────────
     Rejoue un vrai échange du dialogue guidé. Les durées sont courtes :
     une démonstration qui se regarde plus de vingt secondes n'est plus
     une démonstration. Sous prefers-reduced-motion, tout est posé d'un
     coup — le contenu reste lisible, seul le déroulé disparaît. */
  var SCENE = [
    { t: "$ monl init", c: "c-fg", d: 60 },
    { t: "", d: 10 },
    { t: "✻ monl 0.9.0-beta.7 — dialogue guidé", c: "c-cl", d: 30 },
    { t: "  aucune IA, aucun appel réseau", c: "c-dim", d: 20 },
    { t: "", d: 10 },
    { t: "? Que voulez-vous construire ?", c: "c-q", d: 30 },
    { t: "  › 3. Boutique en ligne", c: "c-a", d: 40, pause: 380 },
    { t: "", d: 10 },
    { t: "? Comment s'appelle le site ?", c: "c-q", d: 30 },
    { t: "  › Atelier Horizon", c: "c-a", d: 40, pause: 380 },
    { t: "", d: 10 },
    { t: "? Les clients peuvent-ils payer en ligne ?", c: "c-q", d: 26 },
    { t: "  › oui", c: "c-a", d: 40, pause: 420 },
    { t: "", d: 10 },
    { t: "spin", spin: "Compilation de la spécification", ms: 1100 },
    { t: "✓ spec.ml                  6 entités, 14 règles", c: "c-ok", d: 16 },
    { t: "✓ app.py                   scellé · 61 536 o", c: "c-ok", d: 16 },
    { t: "✓ schema.sql               8 tables, 3 index", c: "c-ok", d: 16 },
    { t: "✓ frontend_contract.json   15 routes", c: "c-ok", d: 16 },
    { t: "", d: 10 },
    { t: "spin", spin: "Test de fumée sur un serveur réel", ms: 1000 },
    { t: "✓ POST /register           201", c: "c-ok", d: 16 },
    { t: "✓ GET  /product            200 · 3 articles", c: "c-ok", d: 16 },
    { t: "✓ POST /order/1/paiement   402 · montant relu en base", c: "c-ok", d: 16 },
    { t: "", d: 10 },
    { t: "Prêt. → monl run", c: "c-cl", d: 40 }
  ];
  var SPIN = ["✻", "✽", "✳", "✢", "·", "✢", "✳", "✽"];

  var term = document.getElementById("term");
  if (term) {
    if (reduit) {
      SCENE.forEach(function (etape) {
        var l = document.createElement("span");
        l.className = "l " + (etape.c || "");
        l.textContent = etape.spin ? "✓ " + etape.spin : etape.t;
        term.appendChild(l);
      });
    } else {
      jouer();
    }
  }

  function jouer() {
    term.textContent = "";
    var i = 0;
    suite();

    function suite() {
      if (i >= SCENE.length) {
        setTimeout(function () { jouer(); }, 4200);
        return;
      }
      var etape = SCENE[i++];
      if (etape.spin) { tourner(etape, suite); return; }
      ecrire(etape, suite);
    }

    function ecrire(etape, fini) {
      var ligne = document.createElement("span");
      ligne.className = "l " + (etape.c || "");
      term.appendChild(ligne);
      var texte = etape.t || "";
      if (!texte) { setTimeout(fini, etape.d || 20); return; }
      var k = 0;
      var curseur = document.createElement("span");
      curseur.className = "caret";
      ligne.appendChild(curseur);
      (function frappe() {
        if (k >= texte.length) {
          curseur.remove();
          setTimeout(fini, etape.pause || 90);
          return;
        }
        curseur.before(document.createTextNode(texte.charAt(k++)));
        setTimeout(frappe, etape.d || 26);
      })();
    }

    function tourner(etape, fini) {
      var ligne = document.createElement("span");
      ligne.className = "l c-am";
      term.appendChild(ligne);
      var debut = Date.now();
      var n = 0;
      (function tick() {
        var passe = Date.now() - debut;
        if (passe >= etape.ms) {
          ligne.className = "l c-dim";
          ligne.textContent = "✓ " + etape.spin + " — " + (etape.ms / 1000).toFixed(1) + " s";
          setTimeout(fini, 140);
          return;
        }
        ligne.textContent = SPIN[n++ % SPIN.length] + " " + etape.spin + "… "
          + (passe / 1000).toFixed(1) + " s";
        setTimeout(tick, 110);
      })();
    }
  }

  /* ── Apparition à l'entrée dans le cadre ────────────────────────────── */
  var cibles = document.querySelectorAll(".card, .step, .stat, .refus li, .dl-item, .close");
  if (!reduit && "IntersectionObserver" in window) {
    Array.prototype.forEach.call(cibles, function (el, n) {
      el.classList.add("rise");
      el.style.transitionDelay = (n % 6) * 45 + "ms";
    });
    var oeil = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("seen"); oeil.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    Array.prototype.forEach.call(cibles, function (el) { oeil.observe(el); });
  }

  /* ── Copier une commande ───────────────────────────────────────────── */
  document.addEventListener("click", function (e) {
    var bouton = e.target.closest ? e.target.closest(".copy") : null;
    if (!bouton) return;
    var source = document.getElementById(bouton.getAttribute("data-copy"));
    if (!source) return;
    var texte = source.textContent;
    var fini = function () {
      bouton.textContent = "copié";
      bouton.setAttribute("data-done", "1");
      setTimeout(function () {
        bouton.textContent = "copier";
        bouton.removeAttribute("data-done");
      }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texte).then(fini, function () {});
    }
  });

  /* ── Artefacts réellement présents sur le serveur ───────────────────── */
  var poids = function (n) {
    if (n >= 1048576) return (n / 1048576).toFixed(1).replace(".", ",") + " Mo";
    if (n >= 1024) return Math.round(n / 1024) + " Ko";
    return n + " o";
  };
  var zone = document.getElementById("dl");
  fetch("/telechargements").then(function (r) {
    return r.ok ? r.json() : { artifacts: [] };
  }).then(function (data) {
    var liste = (data && data.artifacts) || [];
    zone.textContent = "";
    if (!liste.length) {
      var vide = document.createElement("div");
      vide.className = "dl-empty";
      vide.textContent = "Aucune distribution construite sur ce serveur. "
        + "Depuis les sources : pip install -e .";
      zone.appendChild(vide);
      return;
    }
    liste.forEach(function (a) {
      var item = document.createElement("div");
      item.className = "dl-item";
      var gauche = document.createElement("div");
      var titre = document.createElement("h3");
      titre.textContent = a.kind === "wheel"
        ? "Paquet installable (.whl)" : "Archive des sources (.tar.gz)";
      var meta = document.createElement("p");
      meta.className = "dl-meta";
      meta.textContent = a.name + " · " + poids(a.bytes);
      var sha = document.createElement("code");
      sha.className = "dl-sha";
      sha.textContent = "sha256 " + a.sha256;
      gauche.appendChild(titre); gauche.appendChild(meta); gauche.appendChild(sha);
      var lien = document.createElement("a");
      lien.className = "btn";
      lien.setAttribute("href", "/telechargements/" + encodeURIComponent(a.name));
      lien.textContent = "Télécharger";
      item.appendChild(gauche); item.appendChild(lien);
      zone.appendChild(item);
      if (a.kind === "wheel") {
        var cmd = document.getElementById("cmd-pip");
        if (cmd) cmd.textContent = "pip install ./" + a.name;
      }
    });
  }).catch(function () {
    zone.textContent = "";
    var vide = document.createElement("div");
    vide.className = "dl-empty";
    vide.textContent = "Les artefacts n'ont pas pu être lus sur ce serveur.";
    zone.appendChild(vide);
  });
})();
</script>
</body>
</html>
'''


def landing_response():
    """Rend la page de présentation."""
    return HTMLResponse(content=LANDING_HTML)
