"""Public product page for the compiler platform."""

from __future__ import annotations

from . import examples
from .theme import icon, page

EXTRA_CSS = """
.landing-hero { position:relative; padding: 88px 0 80px; display:grid; grid-template-columns:1.08fr .92fr;
  gap:clamp(32px,6vw,76px); align-items:center; }
.landing-hero::before { content:""; position:absolute; width:520px; height:520px; right:-180px; top:-170px;
  border-radius:50%; pointer-events:none; filter:blur(4px);
  background:radial-gradient(circle,color-mix(in srgb,var(--brand) 12%,transparent),transparent 68%); }
.landing-hero h1 { max-width: 760px; margin: 0 0 var(--space-5);
  font-size: clamp(42px, 6vw, 70px); line-height: .98; letter-spacing: -.055em; }
.landing-hero .lede { max-width: 650px; margin: 0 0 var(--space-6);
  color: var(--muted); font-size: clamp(18px, 2.2vw, 21px); }
.hero-actions { display:flex; flex-wrap:wrap; gap:var(--space-3); }
.trust { display:flex; flex-wrap:wrap; gap:var(--space-5);
  margin-top:var(--space-6); color:var(--muted); font-size:14px; }
.trust span { display:inline-flex; gap:7px; align-items:center; }
.trust .icon { color:var(--brand); }
.proof-rail { display:grid;grid-template-columns:repeat(4,1fr);border-block:1px solid var(--line);background:var(--surface);
  padding-inline:max(20px,calc((100vw - var(--shell))/2)); }
.proof-rail div { padding:20px clamp(16px,3vw,34px);border-right:1px solid var(--line); }
.proof-rail div:last-child{border-right:0}.proof-rail b{display:block;font:700 clamp(18px,2vw,24px) var(--mono);letter-spacing:-.04em}
.proof-rail span{color:var(--muted);font-size:12px}.proof-rail .proof-word{color:var(--brand)}
.start-card { position:relative; background:var(--code-bg); color:var(--code-ink); border:1px solid var(--line);
  border-radius:calc(var(--radius-lg) + 4px); padding:var(--space-3); box-shadow:0 28px 70px rgba(0,0,0,.22);
  transform:rotate(1deg); }
.start-card::before { content:""; position:absolute; inset:18px -16px -16px 18px; border:1px solid var(--line);
  border-radius:inherit; z-index:-1; background:var(--surface-2); transform:rotate(-2deg); }
.demo-window { border:1px solid color-mix(in srgb,var(--code-ink) 15%,transparent);border-radius:14px;overflow:hidden;background:#100d10; }
.demo-bar { display:flex;align-items:center;gap:7px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.1);font:11px var(--mono);color:#9f949c; }
.demo-bar i { width:7px;height:7px;border-radius:50%;background:#4b4248; }.demo-bar i:first-child{background:var(--code-accent)}
.demo-bar span { margin-left:auto;display:inline-flex;align-items:center;gap:6px;color:#ffb09f; }
.demo-bar span::before { content:"";width:6px;height:6px;border-radius:50%;background:var(--code-accent);box-shadow:0 0 0 4px rgba(255,107,74,.16); }
.demo-code { padding:22px 20px 18px;font:12px/1.85 var(--mono);color:#a399a1; }
.demo-code b { color:var(--code-accent);font-weight:500 }.demo-code strong{color:#f5eee8;font-weight:500}
.scan-line { height:1px;background:linear-gradient(90deg,transparent,var(--code-accent),transparent);animation:scan 3.2s ease-in-out infinite; }
.demo-result { display:grid;grid-template-columns:1.25fr repeat(3,.6fr);gap:1px;background:rgba(255,255,255,.1);border-top:1px solid rgba(255,255,255,.1); }
.demo-result div { padding:14px;background:#151116; }.demo-result b{display:block;color:#f8f1eb;font:600 16px var(--mono)}
.demo-result span{font:10px var(--mono);color:#988d95}.demo-result .verified b{color:var(--code-accent);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
@keyframes scan { 0%,100%{transform:translateY(-8px);opacity:.25} 50%{transform:translateY(8px);opacity:1} }
.start-head { display:flex; justify-content:space-between; align-items:center; gap:var(--space-3);
  padding-bottom:var(--space-4); border-bottom:1px solid var(--line); }
.start-head b { font-size:17px; }.start-head span { color:var(--muted); font:12px var(--mono); }
.start-steps { list-style:none; padding:0; margin:var(--space-4) 0; counter-reset:start; }
.start-steps li { counter-increment:start; display:grid; grid-template-columns:32px 1fr; gap:var(--space-3);
  padding:var(--space-3) 0; border-bottom:1px solid var(--line); }
.start-steps li::before { content:counter(start); width:28px; height:28px; display:grid; place-items:center;
  border-radius:9px; background:var(--soft); color:var(--brand); font:700 12px var(--mono); }
.start-steps b { display:block; margin-bottom:2px; }.start-steps span { color:var(--muted); font-size:14px; }
.start-card .primary { width:100%; }
.start-note { text-align:center; color:var(--muted); font-size:12px; margin:var(--space-3) 0 0; }
.cases { display:grid; grid-template-columns:repeat(12,1fr); gap:var(--space-3); }
.case { display:flex; flex-direction:column; min-height:260px; text-decoration:none; }
.case:nth-child(6n+1),.case:nth-child(6n+4){grid-column:span 5;min-height:300px}
.case:nth-child(6n+2),.case:nth-child(6n+5){grid-column:span 3}
.case:nth-child(6n+3),.case:nth-child(6n+6){grid-column:span 4}
.case-top { display:flex; align-items:start; justify-content:space-between; gap:var(--space-3); }
.case h3 { margin:var(--space-4) 0 var(--space-2); font-size:18px; }
.case p { color:var(--muted); font-size:14px; flex:1; }
.case-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--space-2);
  border-top:1px solid var(--line); padding-top:var(--space-4); }
.case-metrics b { display:block; font:700 17px var(--mono); color:var(--ink); }
.case-metrics span { color:var(--muted); font-size:11px; }
.case-cta { display:inline-flex; align-items:center; gap:6px; color:var(--brand); font-weight:600; font-size:14px;
  margin-top:var(--space-4); }
.output-flow { display:grid; grid-template-columns:.8fr auto 1.2fr; gap:var(--space-4); align-items:center; }
.mini-spec { margin:0; min-height:300px; }
.flow-arrow { width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:var(--brand);color:var(--on-brand); }
.artifact { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius-lg); overflow:hidden; }
.artifact-head { padding:var(--space-4); border-bottom:1px solid var(--line); display:flex;justify-content:space-between;gap:var(--space-3); }
.artifact-body { padding:var(--space-5); }
.artifact-stats { display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-2);margin-bottom:var(--space-5); }
.artifact-stats div { background:var(--surface-2);border-radius:10px;padding:var(--space-3); }
.artifact-stats b { display:block;font:700 20px var(--mono); }.artifact-stats span{color:var(--muted);font-size:12px}
.tree { font:13px/1.8 var(--mono); color:var(--muted); }.tree b{color:var(--ink)}
.layers { display:grid;grid-template-columns:1fr 1.15fr 1fr;gap:var(--space-3);align-items:stretch; }
.layer { position:relative;min-height:260px;display:flex;flex-direction:column;justify-content:space-between; }
.layer:nth-child(2){background:var(--code-bg);color:var(--code-ink);border-color:color-mix(in srgb,var(--brand) 55%,var(--line));transform:translateY(-12px);box-shadow:var(--shadow)}
.layer:nth-child(2) p{color:#b6a9b1}.layer:nth-child(2) .layer-label{color:var(--code-accent)}
.layer-label{font:600 11px var(--mono);color:var(--brand);letter-spacing:.1em;text-transform:uppercase}
.layer h3{font-size:clamp(22px,3vw,29px);margin:var(--space-5) 0 var(--space-3)}.layer p{color:var(--muted);margin:0}
.layer-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:var(--space-5)}.layer-tags span{border:1px solid currentColor;border-radius:999px;padding:4px 9px;font:10px var(--mono);opacity:.72}
.layer-arrow{position:absolute;right:-23px;top:50%;z-index:3;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:var(--brand);color:var(--on-brand)}
.pipeline { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--space-3);
  max-width:960px; margin:0 auto; text-align:left; }
.pipeline article { position:relative; min-height:190px; }
.pipeline article:not(:last-child)::after { content:"→"; position:absolute; right:-20px; top:45%;
  z-index:2; width:28px; height:28px; display:grid; place-items:center; border-radius:50%;
  background:var(--brand); color:var(--on-brand); font-family:var(--mono); }
.feature-icon { width:42px; height:42px; display:grid; place-items:center; border-radius:12px;
  background:var(--soft); color:var(--brand); margin-bottom:var(--space-5); }
.feature-icon .icon { width:21px; height:21px; }
.pipeline h3,.bento h3 { margin-bottom:var(--space-2); font-size:19px; }
.pipeline p,.bento p { color:var(--muted); margin:0; font-size:15px; }
.band { border-block:1px solid var(--line); background:var(--surface-2); }
.bento { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--space-3); }
.bento article { min-height:220px; }
.bento article:first-child { grid-column:span 2; display:flex; flex-direction:column; justify-content:flex-end;
  background:var(--code-bg); color:var(--code-ink); }
.bento article:first-child p { color:#b6a9b1; }
.bento article:first-child .feature-icon { background:#2b1718; color:var(--code-accent); }
.step-list { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--space-5); counter-reset:step; }
.step-list article { counter-increment:step; border-top:1px solid var(--line); padding-top:var(--space-5); }
.step-list article::before { content:"0" counter(step); color:var(--brand); font:600 12px var(--mono); }
.step-list h3 { margin:var(--space-4) 0 var(--space-2); }
.step-list p { color:var(--muted); }
.final { margin:var(--space-8) auto; padding:clamp(32px,6vw,64px); text-align:center;
  background:var(--brand); color:var(--on-brand); border-radius:var(--radius-lg); }
.final h2 { max-width:700px; margin:0 auto var(--space-4); font-size:clamp(30px,5vw,48px); }
.final p { max-width:620px; margin:0 auto var(--space-6); opacity:.86; }
.final .secondary { background:var(--surface); color:var(--ink); border:0; }
@media(max-width:760px){
  .landing-hero { padding-top:56px; grid-template-columns:1fr; }
  .pipeline,.bento,.step-list { grid-template-columns:1fr; }
  .cases { grid-template-columns:1fr 1fr; }
  .case:nth-child(n){grid-column:auto;min-height:260px}
  .proof-rail{grid-template-columns:1fr 1fr}.proof-rail div:nth-child(2){border-right:0}.proof-rail div:nth-child(-n+2){border-bottom:1px solid var(--line)}
  .layers{grid-template-columns:1fr}.layer:nth-child(2){transform:none}.layer-arrow{display:none}
  .output-flow { grid-template-columns:1fr; }.flow-arrow{transform:rotate(90deg);margin:auto}
  .pipeline article:not(:last-child)::after { display:none; }
  .bento article:first-child { grid-column:auto; }
}
@media(max-width:520px){.cases{grid-template-columns:1fr}.start-card{transform:none}.start-card::before{display:none}.demo-result{grid-template-columns:1fr 1fr}}
@media(prefers-reduced-motion:reduce){.scan-line{animation:none}}
"""


def feature(symbol: str, title: str, text: str, delay: int = 0) -> str:
    return f"""<article class="card lift" data-reveal style="--reveal-delay:{delay}ms">
<span class="feature-icon">{icon(symbol)}</span><h3>{title}</h3><p>{text}</p></article>"""


def case_card(item: dict, delay: int) -> str:
    result = item["result"]
    return f"""<a class="card case lift" href="/console?example={item['id']}" data-reveal
style="--reveal-delay:{delay}ms"><div class="case-top"><span class="feature-icon">{icon('package')}</span>
<span class="case-cta">Ouvrir {icon('arrow')}</span></div><h3>{item['name']}</h3><p>{item['summary']}</p>
<div class="case-metrics"><span><b>{result['entities']}</b>entités</span><span><b>{result['routes']}</b>routes</span>
<span><b>{result['files']}</b>fichiers</span></div></a>"""


CASES = "".join(case_card(item, index * 50) for index, item in enumerate(examples.catalogue()))


BODY = f"""
<section class="shell landing-hero">
<div><span class="eyebrow" data-reveal>Le backend est compilé, pas improvisé</span>
<h1 data-reveal style="--reveal-delay:60ms">Décrivez vos règles.<br>Téléchargez votre backend.</h1>
<p class="lede" data-reveal style="--reveal-delay:120ms">Partez d’un exemple, indiquez vos données,
vos utilisateurs et leurs droits. Monl vérifie votre spécification puis génère une API FastAPI, sa base SQL
et le contrat destiné à votre interface.</p>
<div class="hero-actions" data-reveal style="--reveal-delay:180ms">
<a class="primary" href="/console">{icon('terminal')} Créer un backend</a>
<a class="secondary" href="/docs">{icon('book')} Voir comment écrire la spec</a></div>
<div class="trust" data-reveal style="--reveal-delay:220ms">
<span>{icon('check')} Compte gratuit</span><span>{icon('check')} Exemples inclus</span>
<span>{icon('check')} Backend autonome</span></div></div>
<aside class="start-card" data-reveal style="--reveal-delay:120ms" aria-label="Ce que vous allez faire">
<div class="demo-window"><div class="demo-bar"><i></i><i></i><i></i><span>compilation vérifiée</span></div>
<div class="demo-code"><b>app</b> <strong>PetiteBoutique</strong><br><br><b>entity</b> Produit<br>&nbsp;&nbsp;prix: Money<br>&nbsp;&nbsp;stock: Integer<br><br><b>rule</b> Produit.stock min 0<br><b>rule</b> Produit.Read public</div>
<div class="scan-line"></div><div class="demo-result"><div class="verified"><b>{icon('check')} valide</b><span>audit métier</span></div>
<div><b>3</b><span>entités</span></div><div><b>17</b><span>routes</span></div><div><b>12</b><span>fichiers</span></div></div></div></aside>
</section>

<section class="proof-rail" aria-label="Preuves du compilateur">
<div><b>10</b><span>spécifications complètes incluses</span></div><div><b>0</b><span>appel réseau pour compiler</span></div>
<div><b class="proof-word">Refus</b><span>si une règle est incohérente</span></div><div><b class="proof-word">Export</b><span>backend autonome, sans verrouillage</span></div>
</section>

<section class="band"><div class="shell section">
<div class="section-head" data-reveal><span class="eyebrow">Voyez le résultat</span>
<h2>Une spec entre. Un backend complet sort.</h2>
<p>Exemple réel de boutique : les métriques ci-dessous sont vérifiées en recompilant la spec dans les tests.</p></div>
<div class="output-flow" data-reveal><pre class="codeblock mini-spec"><code><span class="kw">entity</span> Produit
    nom: String
    prix: Money
    stock: Integer

<span class="kw">rule</span> Produit.prix min 0
<span class="kw">rule</span> Produit.stock min 0
<span class="kw">rule</span> Produit.Read public</code></pre>
<span class="flow-arrow">{icon('arrow')}</span><div class="artifact"><div class="artifact-head"><b>PetiteBoutique</b><span class="muted">archive autonome</span></div>
<div class="artifact-body"><div class="artifact-stats"><div><b>3</b><span>entités</span></div><div><b>17</b><span>routes API</span></div><div><b>12</b><span>fichiers</span></div></div>
<div class="tree"><b>backend/</b><br>├── app.py <span>API FastAPI</span><br>├── schema.sql <span>base de données</span><br>
├── frontend_contract.json <span>droits et routes</span><br>├── manage.py <span>administration</span><br>└── README.md <span>démarrage</span></div></div></div></div>
</div></section>

<section class="shell section" aria-labelledby="position-title">
<div class="section-head" data-reveal><span class="eyebrow">Une couche différente</span>
<h2 id="position-title">L’infrastructure héberge. Monl compile le métier.</h2>
<p>Une base managée fournit le stockage et le calcul. Monl intervient avant : il transforme vos règles en API,
schéma SQL et contrat vérifiés, puis vous laisse choisir où les exécuter.</p></div>
<div class="layers">
<article class="card layer" data-reveal><div><span class="layer-label">01 · Infrastructure</span><h3>Les fondations techniques</h3>
<p>Postgres, stockage, calcul et réseau peuvent venir de votre cloud, d’un service managé ou de votre propre serveur.</p></div>
<div class="layer-tags"><span>database</span><span>storage</span><span>compute</span></div><span class="layer-arrow">{icon('arrow')}</span></article>
<article class="card layer" data-reveal style="--reveal-delay:60ms"><div><span class="layer-label">02 · Monl compiler</span><h3>Les règles qui ne doivent pas varier</h3>
<p>Acteurs, permissions, propriété, stock, paiements et invariants passent par le parseur et l’audit avant de devenir du code.</p></div>
<div class="layer-tags"><span>spec.ml</span><span>audit</span><span>contrat</span></div><span class="layer-arrow">{icon('arrow')}</span></article>
<article class="card layer" data-reveal style="--reveal-delay:120ms"><div><span class="layer-label">03 · Interfaces</span><h3>Tout ce que vos utilisateurs voient</h3>
<p>Web, mobile et agents consomment le même contrat sans avoir à deviner les routes ou les autorisations.</p></div>
<div class="layer-tags"><span>web</span><span>mobile</span><span>MCP</span></div></article>
</div></section>

<section class="shell section" aria-labelledby="pipeline-title">
<div class="section-head" data-reveal><span class="eyebrow">Une chaîne vérifiable</span>
<h2 id="pipeline-title">De la règle métier au backend, sans zone grise.</h2>
<p>L’IA peut aider à écrire une spécification. Seul le compilateur décide de ce qui est valide.</p></div>
<div class="pipeline">
{feature('code', '1. Décrivez', 'Entités, acteurs, permissions et invariants restent lisibles dans un fichier texte.', 0)}
{feature('shield', '2. Vérifiez', 'Le parseur refuse les incohérences avant qu’elles ne deviennent du code.', 60)}
{feature('package', '3. Livrez', 'Recevez l’API, le schéma SQL, le contrat frontend et les instructions.', 120)}
</div></section>

<section class="band"><div class="shell section">
<div class="section-head" data-reveal><span class="eyebrow">Ce que Monl garantit</span>
<h2>Des garanties observables, pas seulement du code plausible.</h2>
<p>Chaque règle est vérifiée avant émission, puis traduite de la même façon dans l’API, la base et le contrat.</p></div>
<div class="bento">
{feature('shield', 'La sécurité vient de la spécification', 'Authentification, propriété des enregistrements et permissions par acteur sont compilées dans chaque route. Une action interdite n’est pas laissée à l’interprétation du frontend.', 0)}
{feature('check', 'Les incohérences sont refusées', 'Types, relations, invariants et workflows traversent un parseur et un audit statique avant la génération.', 40)}
{feature('code', 'Le contrat décrit les droits', 'Web, mobile ou agent connaissent les routes publiques, authentifiées et autorisées sans les deviner.', 80)}
{feature('shield', 'Les secrets restent chez vous', 'Le secret JWT n’entre jamais dans l’archive : il est créé sur la machine qui exécute le backend.', 120)}
{feature('package', 'Une livraison reproductible', 'API FastAPI, schéma SQL, contrat et instructions proviennent de la même source versionnable.', 160)}
{feature('plug', 'Le même moteur par MCP', 'Les agents valident et compilent via le pipeline officiel, sans générateur parallèle moins strict.', 200)}
</div><div style="margin-top:var(--space-5)" data-reveal><a class="secondary" href="/security">Voir les garanties et leurs limites {icon('arrow')}</a></div></div></section>

<section class="shell section"><div class="section-head" data-reveal><span class="eyebrow">Cas métier compilables</span>
<h2>Partez d’une application proche de la vôtre.</h2><p>Chaque carte ouvre sa spécification complète dans la console.</p></div>
<div class="cases">{CASES}</div></section>

<section class="shell section">
<div class="section-head" data-reveal><span class="eyebrow">Un parcours pour tous</span>
<h2>Commencez sans connaître le compilateur.</h2></div>
<div class="step-list">
<article data-reveal><h3>Choisissez un exemple</h3><p>La console propose plusieurs applications complètes et réellement compilables.</p></article>
<article data-reveal style="--reveal-delay:60ms"><h3>Adaptez vos règles</h3><p>Le retour de validation explique précisément ce qui doit être corrigé.</p></article>
<article data-reveal style="--reveal-delay:120ms"><h3>Téléchargez le résultat</h3><p>Votre backend et son contrat arrivent dans une archive reproductible.</p></article>
</div></section>

<section class="shell final" data-reveal>
<h2>Compilez une règle métier réelle.</h2>
<p>Vos projets restent disponibles dans votre compte et chaque archive demeure autonome.</p>
<a class="secondary" href="/console">Ouvrir la console {icon('arrow')}</a>
</section>
"""

LANDING_HTML = page(
    title="monl compiler — le métier est compilé",
    description="Monl compile vos règles métier en backend autonome et contrat frontend vérifiable.",
    body=BODY,
    active="home",
    extra_css=EXTRA_CSS,
)
