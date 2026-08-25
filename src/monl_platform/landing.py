"""Public product page for the compiler platform."""

from __future__ import annotations

from . import examples
from .theme import icon, page

EXTRA_CSS = """
.landing-hero { padding: 80px 0 72px; display:grid; grid-template-columns:1.05fr .95fr;
  gap:var(--space-7); align-items:center; }
.landing-hero h1 { max-width: 760px; margin: 0 0 var(--space-5);
  font-size: clamp(42px, 6vw, 70px); line-height: .98; letter-spacing: -.055em; }
.landing-hero .lede { max-width: 650px; margin: 0 0 var(--space-6);
  color: var(--muted); font-size: clamp(18px, 2.2vw, 21px); }
.hero-actions { display:flex; flex-wrap:wrap; gap:var(--space-3); }
.trust { display:flex; flex-wrap:wrap; gap:var(--space-5);
  margin-top:var(--space-6); color:var(--muted); font-size:14px; }
.trust span { display:inline-flex; gap:7px; align-items:center; }
.trust .icon { color:var(--brand); }
.start-card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius-lg);
  padding:var(--space-5); box-shadow:var(--shadow); }
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
.cases { display:grid; grid-template-columns:repeat(4,1fr); gap:var(--space-3); }
.case { display:flex; flex-direction:column; min-height:260px; text-decoration:none; }
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
.bento article:first-child p { color:#9db4aa; }
.bento article:first-child .feature-icon { background:#1f352d; color:var(--code-accent); }
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
  .output-flow { grid-template-columns:1fr; }.flow-arrow{transform:rotate(90deg);margin:auto}
  .pipeline article:not(:last-child)::after { display:none; }
  .bento article:first-child { grid-column:auto; }
}
@media(max-width:520px){.cases{grid-template-columns:1fr}}
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
<div><span class="eyebrow" data-reveal>Créez le backend de votre application</span>
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
<aside class="start-card" data-reveal style="--reveal-delay:120ms" aria-label="Comment commencer">
<div class="start-head"><b>Ce que vous allez faire</b><span>≈ 3 minutes</span></div>
<ol class="start-steps">
<li><div><b>Choisir une application proche de la vôtre</b><span>Vitrine, rendez-vous, boutique ou communauté.</span></div></li>
<li><div><b>Adapter les données et les droits</b><span>Modifiez la spec proposée, ou importez votre fichier .ml.</span></div></li>
<li><div><b>Vérifier puis compiler</b><span>Téléchargez le backend, le schéma SQL et le contrat frontend.</span></div></li>
</ol>
<a class="primary" href="/console">Commencer avec un exemple {icon('arrow')}</a>
<p class="start-note">Rien n’est installé sur votre machine.</p></aside>
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
