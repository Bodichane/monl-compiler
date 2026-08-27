"""Public product page for the compiler platform."""

from __future__ import annotations

from . import examples, landing_pourquoi
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
.trust .icon { color:var(--ink); }
.proof-rail { display:grid;grid-template-columns:repeat(4,1fr);border-block:1px solid var(--line);
  padding-inline:max(20px,calc((100vw - var(--shell))/2)); }
.proof-rail div { padding:20px clamp(16px,3vw,34px);border-right:1px solid var(--line); }
.proof-rail div:last-child{border-right:0}.proof-rail b{display:block;font:700 clamp(18px,2vw,24px) var(--mono);letter-spacing:-.04em}
.proof-rail span{color:var(--muted);font-size:12px}.proof-rail .proof-word{color:var(--ink)}
.start-card { position:relative; background:var(--code-bg); color:var(--code-ink); border:1px solid var(--line);
  border-radius:calc(var(--radius-lg) + 4px); padding:var(--space-3); box-shadow:0 28px 70px rgba(0,0,0,.22);
  transform:rotate(1deg); }
.start-card::before { content:""; position:absolute; inset:18px -16px -16px 18px; border:1px solid var(--line);
  border-radius:inherit; z-index:-1; background:var(--surface-2); transform:rotate(-2deg); }
.demo-window { border:1px solid color-mix(in srgb,var(--code-ink) 15%,transparent);border-radius:14px;overflow:hidden;background:var(--code-bg); }
.demo-bar { display:flex;align-items:center;gap:7px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.1);font:11px var(--mono);color:var(--code-muted); }
.demo-bar i { width:7px;height:7px;border-radius:50%;background:var(--code-line); }.demo-bar i:first-child{background:var(--code-accent)}
.demo-bar span { margin-left:auto;display:inline-flex;align-items:center;gap:6px;color:var(--code-accent); }
.demo-bar span::before { content:"";width:6px;height:6px;border-radius:50%;background:var(--code-accent);box-shadow:0 0 0 4px rgba(229,164,95,.16); }
.demo-code { padding:22px 20px 18px;font:12px/1.85 var(--mono);color:var(--code-muted); }
.demo-code b { color:var(--code-accent);font-weight:500 }.demo-code strong{color:var(--code-ink);font-weight:500}
.scan-line { height:1px;background:linear-gradient(90deg,transparent,var(--code-accent),transparent);animation:scan 3.2s ease-in-out infinite; }
.demo-result { display:grid;grid-template-columns:1.25fr repeat(3,.6fr);gap:1px;background:rgba(255,255,255,.1);border-top:1px solid rgba(255,255,255,.1); }
.demo-result div { padding:14px;background:var(--code-bg); }.demo-result b{display:block;color:var(--code-ink);font:600 16px var(--mono)}
.demo-result span{font:10px var(--mono);color:var(--code-muted)}.demo-result .verified b{color:var(--code-accent);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
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
.editorial { display:grid; grid-template-columns:minmax(240px,.78fr) minmax(0,1.35fr); gap:clamp(40px,8vw,110px); }
.editorial .section-head { margin:0; }
.platform-flow { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid var(--line); border-radius:var(--radius-lg); overflow:hidden; }
.flow-stage { min-height:280px; padding:clamp(24px,3vw,36px); border-right:1px solid var(--line); display:flex; flex-direction:column; }
.flow-stage:last-child { border-right:0; }
.flow-stage:nth-child(2) { background:var(--code-bg); color:var(--code-ink); }
.flow-stage .stage-no { font:600 11px var(--mono); letter-spacing:.1em; color:var(--muted); }
.flow-stage:nth-child(2) .stage-no,.flow-stage:nth-child(2) p { color:var(--code-muted); }
.flow-stage h3 { margin:auto 0 10px; font-size:clamp(22px,2.4vw,29px); }
.flow-stage p { color:var(--muted); margin:0; }
.flow-stage .stage-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:22px; }
.flow-stage .stage-tags span { font:10px var(--mono); border:1px solid currentColor; border-radius:999px; padding:3px 8px; opacity:.7; }
.capability-grid { display:grid; grid-template-columns:1fr 1fr; border:1px solid var(--line); border-radius:var(--radius-lg); overflow:hidden; }
.capability { min-height:230px; padding:clamp(24px,3vw,34px); border-right:1px solid var(--line); border-bottom:1px solid var(--line); }
.capability:nth-child(2n) { border-right:0; }.capability:nth-last-child(-n+2) { border-bottom:0; }
.capability .feature-icon { margin-bottom:clamp(32px,5vw,58px); background:transparent; border:1px solid var(--line); color:var(--ink); }
.capability h3 { font-size:19px; margin-bottom:8px; }.capability p { color:var(--muted); margin:0; }
.principles { border-top:1px solid var(--line); }
.principle { display:grid; grid-template-columns:44px 1fr; gap:var(--space-4); padding:26px 0; border-bottom:1px solid var(--line); }
.principle .feature-icon { margin:0; background:transparent; border:1px solid var(--line); color:var(--ink); }
.principle h3 { font-size:19px; margin-bottom:6px; }
.principle p { color:var(--muted); margin:0; }
.case-explorer { display:grid; grid-template-columns:minmax(230px,.7fr) minmax(0,1.55fr); border:1px solid var(--line);
  border-radius:var(--radius-lg); overflow:hidden; min-height:560px; }
.case-tabs { position:relative; background:var(--surface-2); border-right:1px solid var(--line); padding:12px; }
.case-tab { position:relative; z-index:1; width:100%; border:0; border-radius:10px; padding:16px; background:transparent; color:var(--muted); text-align:left;
  cursor:pointer; display:block; transition:background .18s,color .18s; }
.case-tab:hover { color:var(--ink); }.case-tab[aria-selected="true"] { background:var(--surface); color:var(--ink); }
/* Le fond de l'onglet actif devient un repère unique qui GLISSE d'un onglet à
   l'autre. Il n'est cédé que si le script a réellement posé le repère
   (classe `glisse`) : sans JavaScript, la règle `[aria-selected]` reste seule
   et l'onglet garde son fond. Sa spécificité est plus forte (0,3,1 contre 0,2,1),
   donc l'ordre des règles n'a pas à être défendu. */
.case-tabs.glisse .case-tab[aria-selected="true"] { background:transparent; }
/* Et le fond de l'onglet cesse d'être animé dès que le repère prend le relais :
   sans ça, l'onglet quitté s'éteint en .18s pendant que le repère met .34s à
   arriver, et les deux mouvements se contredisent. */
.case-tabs.glisse .case-tab { transition:color .18s; }
.case-repere {
  position:absolute; top:0; left:0; z-index:0; pointer-events:none;
  width:var(--repere-w,0); height:var(--repere-h,0);
  transform:translate(var(--repere-x,0), var(--repere-y,0));
  background:var(--surface); border-radius:10px;
  transition:transform .34s cubic-bezier(.4,0,.2,1), width .34s cubic-bezier(.4,0,.2,1),
             height .34s cubic-bezier(.4,0,.2,1);
}
.case-tab b { display:block; margin-bottom:4px; font-size:15px; }.case-tab span { font-size:12px; line-height:1.4; display:block; }
.case-panels { min-width:0; background:var(--surface); }
.case-panel { display:none; min-height:100%; padding:clamp(28px,5vw,58px); }
.case-panel.active { display:grid; grid-template-columns:1fr 1fr; gap:clamp(24px,5vw,56px); animation:case-in .25s ease-out; }
.case-panel h3 { font-size:clamp(27px,4vw,42px); margin:8px 0 16px; }.case-panel p { color:var(--muted); }
.case-spec { min-width:0; display:flex; flex-direction:column; }
.case-spec .codeblock { flex:1; min-height:0; white-space:pre-wrap; overflow:visible; overflow-wrap:anywhere; }
.case-rules { display:flex; flex-wrap:wrap; gap:6px; }
.case-rules span { border:1px solid var(--line); border-radius:999px; padding:3px 8px; color:var(--muted); font:10px var(--mono); }
.case-result { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.case-result b { display:block; color:var(--ink); font:700 18px var(--mono); }
.case-result span { color:var(--muted); font-size:10px; }
.case-open { display:inline-flex; align-items:center; gap:6px; margin-top:24px; color:var(--ink); font-size:13px; font-weight:650; }
@keyframes case-in { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
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
.layer:nth-child(2) p{color:var(--code-muted)}.layer:nth-child(2) .layer-label{color:var(--code-accent)}
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
/* UNE SEULE couleur de fond pour toute la page. Les bandes alternaient
   --surface-2, le rail --surface et le pied --surface : trois fonds en plus
   du --bg de la page, donc un changement de couleur presque à chaque section.
   Le filet reste : il marque la même césure que le fond marquait, sans
   repeindre. Les CARTES gardent --surface — une carte doit se détacher du
   fond, c'est ce qui la fait lire comme une carte, et le bloc final est une
   carte arrondie et non une bande. */
.band { border-block:1px solid var(--line); }
.bento { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--space-3); }
.bento article { min-height:220px; }
.bento article:first-child { grid-column:span 2; display:flex; flex-direction:column; justify-content:flex-end;
  background:var(--code-bg); color:var(--code-ink); }
.bento article:first-child p { color:var(--code-muted); }
.bento article:first-child .feature-icon { background:var(--soft); color:var(--code-accent); }
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
  .pipeline,.bento,.step-list,.editorial,.platform-flow,.case-explorer { grid-template-columns:1fr; }
  .flow-stage { min-height:220px; border-right:0; border-bottom:1px solid var(--line); }.flow-stage:last-child{border-bottom:0}
  .case-tabs { border-right:0; border-bottom:1px solid var(--line); display:flex; overflow-x:auto; }
  .case-tab { width:190px; flex:none; }.case-tab span { display:none; }
  .case-panel.active { grid-template-columns:1fr; }.case-explorer { min-height:0; }
  .proof-rail{grid-template-columns:1fr 1fr}.proof-rail div:nth-child(2){border-right:0}.proof-rail div:nth-child(-n+2){border-bottom:1px solid var(--line)}
  .layers{grid-template-columns:1fr}.layer:nth-child(2){transform:none}.layer-arrow{display:none}
  .output-flow { grid-template-columns:1fr; }.flow-arrow{transform:rotate(90deg);margin:auto}
  .pipeline article:not(:last-child)::after { display:none; }
  .bento article:first-child { grid-column:auto; }
}
@media(max-width:520px){.start-card{transform:none}.start-card::before{display:none}.demo-result{grid-template-columns:1fr 1fr}.capability-grid{grid-template-columns:1fr}.capability{border-right:0;border-bottom:1px solid var(--line)!important}.capability:last-child{border-bottom:0!important}}
@media(prefers-reduced-motion:reduce){.scan-line{animation:none}}
"""


def feature(symbol: str, title: str, text: str, delay: int = 0) -> str:
    return f"""<article class="card lift" data-reveal style="--reveal-delay:{delay}ms">
<span class="feature-icon">{icon(symbol)}</span><h3>{title}</h3><p>{text}</p></article>"""


CASE_OUTCOMES = {
    "vitrine": "Lecture publique, administration privée et catalogue initialisé dès le premier démarrage.",
    "rendez-vous": "Chaque client reste isolé ; le praticien retrouve toutes les demandes et maîtrise leurs statuts.",
    "boutique": "Prix calculés côté serveur, stock jamais négatif, commande numérotée et paiement verrouillé.",
    "communaute": "Pseudonymes générés, une réaction par compte, signalement et modération sans contournement.",
}

CASE_SNIPPETS = {
    "vitrine": """rule Realisation.Read public

workflow Gerer for Admin
    Create Realisation
    Update Realisation
    Delete Realisation""",
    "rendez-vous": """rule Demande.Read ownedBy Visiteur
rule Demande.Read sharedBy Praticien
rule Demande.Create requiresOwn Client
rule Demande.statut oneOf
    \"deposee\", \"confirmee\", \"honoree\"""",
    "boutique": """rule Ligne.sousTotal derivedFrom Produit.prix by quantite
rule Commande.total sumOf Ligne.sousTotal
rule Ligne.Create decrements Produit.stock by quantite
rule Commande.total payable""",
    "communaute": """rule Membre.pseudo generated \"MBR-{NNNN}\"
rule Jaime.Create oncePer Membre, Message
rule Jaime.Create increments Message.jaimes by 1
rule Message.Read publicWhen statut \"publie\"""",
}


def case_tab(item: dict, index: int) -> str:
    selected = ' aria-selected="true"' if index == 0 else ' aria-selected="false"'
    return (f'<button class="case-tab" id="tab-{item["id"]}" role="tab" '
            f'aria-controls="case-{item["id"]}"{selected} data-case="{item["id"]}">'
            f'<b>{item["name"]}</b><span>{item["summary"]}</span></button>')


def case_panel(item: dict, index: int) -> str:
    result = item["result"]
    rules = "".join(f"<span>{rule}</span>" for rule in item["teaches"])
    active = " active" if index == 0 else ""
    hidden = "" if index == 0 else " hidden"
    snippet = CASE_SNIPPETS[item["id"]]
    return f"""<section class="case-panel{active}" id="case-{item['id']}" role="tabpanel"
aria-labelledby="tab-{item['id']}"{hidden}><div><span class="eyebrow">0{index + 1} · Spec incluse</span>
<h3>{item['name']}</h3><p>{CASE_OUTCOMES[item['id']]}</p>
<div class="case-rules" aria-label="Règles démontrées">{rules}</div>
<div class="case-result" style="margin-top:28px"><span><b>{result['entities']}</b>entités</span>
<span><b>{result['routes']}</b>routes</span><span><b>{result['files']}</b>fichiers</span></div>
<a class="case-open" href="/console?example={item['id']}">Ouvrir dans la console {icon('arrow')}</a></div>
<div class="case-spec"><pre class="codeblock"><code>{snippet}</code></pre></div></section>"""


CATALOGUE = examples.catalogue()
CASE_TABS = "".join(case_tab(item, index) for index, item in enumerate(CATALOGUE))
CASE_PANELS = "".join(case_panel(item, index) for index, item in enumerate(CATALOGUE))


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
<div><b>4</b><span>spécifications complètes incluses</span></div><div><b>0</b><span>appel réseau pour compiler</span></div>
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
<div class="section-head" data-reveal><span class="eyebrow">La place de Monl</span>
<h2 id="position-title">Votre infrastructure exécute. Monl décide ce qui est valide.</h2>
<p>Postgres, votre cloud ou un service managé hébergent les données. Monl intervient avant eux et reste indépendant de l’interface.</p></div>
<div class="platform-flow" data-reveal>
<article class="flow-stage"><span class="stage-no">01 · INFRASTRUCTURE</span><h3>Les fondations</h3><p>Base de données, calcul, stockage et réseau restent chez le fournisseur que vous choisissez.</p><div class="stage-tags"><span>Postgres</span><span>cloud</span><span>self-hosted</span></div></article>
<article class="flow-stage"><span class="stage-no">02 · MONL COMPILER</span><h3>Le métier vérifié</h3><p>Acteurs, droits, propriété, paiements et invariants deviennent une API et un contrat cohérents. Le même moteur pour les agents MCP.</p><div class="stage-tags"><span>spec.ml</span><span>audit</span><span>contrat</span></div></article>
<article class="flow-stage"><span class="stage-no">03 · INTERFACES</span><h3>Chaque expérience</h3><p>Web, mobile et agents utilisent les mêmes routes et autorisations sans les deviner.</p><div class="stage-tags"><span>web</span><span>mobile</span><span>MCP</span></div></article>
</div></section>

{landing_pourquoi.SECTIONS}
<section class="band"><div class="shell section editorial">
<div class="section-head" data-reveal><span class="eyebrow">Garanties vérifiables</span>
<h2>La sécurité n’est pas une consigne donnée au frontend.</h2>
<p>Elle est dérivée de la spécification et répétée dans chaque couche produite. Les limites restent explicites.</p>
<a class="secondary" href="/security">Lire le modèle de sécurité {icon('arrow')}</a></div>
<div class="capability-grid">
<article class="capability" data-reveal><span class="feature-icon">{icon('shield')}</span><h3>Droits compilés par acteur</h3><p>Lecture publique, session, propriété et rôle privilégié sont distingués route par route.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('check')}</span><h3>Invariants côté serveur</h3><p>Stock, montants, unicité, états autorisés et gel après paiement ne dépendent jamais du navigateur.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('code')}</span><h3>Contrat frontend exact</h3><p>Chaque interface reçoit les routes, champs, actions et exigences d’authentification disponibles.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('key')}</span><h3>Secrets créés chez vous</h3><p>Le secret JWT ne voyage pas dans l’archive et reste sous le contrôle de l’exploitant.</p></article>
</div></div></section>

<section class="shell section"><div class="section-head" data-reveal><span class="eyebrow">Cas métier compilables</span>
<h2>Quatre applications, quatre familles de règles réellement testées.</h2>
<p>Chaque exemple est une spécification complète servie par la plateforme. Ouvrez-la dans la console, adaptez-la puis compilez son backend.</p></div>
<div class="case-explorer" data-reveal><div class="case-tabs" role="tablist" aria-label="Cas métier">{CASE_TABS}</div>
<div class="case-panels">{CASE_PANELS}</div></div></section>

<section class="shell final" data-reveal>
<h2>Compilez une règle métier réelle.</h2>
<p>Vos projets restent disponibles dans votre compte et chaque archive demeure autonome.</p>
<a class="secondary" href="/console">Ouvrir la console {icon('arrow')}</a>
</section>
"""

CASE_SCRIPT = """<script>
(function () {
  var tabs = Array.from(document.querySelectorAll('.case-tab'));
  var panels = Array.from(document.querySelectorAll('.case-panel'));
  var liste = document.querySelector('.case-tabs');
  var repere = null;
  if (liste && tabs.length) {
    repere = document.createElement('span');
    repere.className = 'case-repere';
    repere.setAttribute('aria-hidden', 'true');
    liste.insertBefore(repere, liste.firstChild);
    liste.classList.add('glisse');
  }
  /* offsetTop/offsetLeft se mesurent depuis le bord de PADDING du parent
     positionné, exactement là où `top:0; left:0` pose un absolu. L'onglet est
     posé dans la boite de CONTENU, donc offsetLeft vaut le padding (12px
     mesurés) et le translate reconduit le repère pile sur l'onglet : écart
     mesuré 0,0 au navigateur. Une seule mesure couvre la colonne verticale du
     bureau et la rangée horizontale du mobile. */
  function placer(tab, anime) {
    if (!repere) return;
    if (!anime) repere.style.transition = 'none';
    repere.style.setProperty('--repere-x', tab.offsetLeft + 'px');
    repere.style.setProperty('--repere-y', tab.offsetTop + 'px');
    repere.style.setProperty('--repere-w', tab.offsetWidth + 'px');
    repere.style.setProperty('--repere-h', tab.offsetHeight + 'px');
    if (!anime) { void repere.offsetWidth; repere.style.transition = ''; }
  }
  function select(tab, focus) {
    tabs.forEach(function (item) {
      var active = item === tab;
      item.setAttribute('aria-selected', active ? 'true' : 'false');
      item.tabIndex = active ? 0 : -1;
    });
    panels.forEach(function (panel) {
      var active = panel.id === 'case-' + tab.dataset.case;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
    placer(tab, true);
    if (focus) tab.focus();
  }
  tabs.forEach(function (tab, index) {
    tab.tabIndex = index === 0 ? 0 : -1;
    tab.addEventListener('click', function () { select(tab, false); });
    tab.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft' &&
          event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      var direction = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1;
      select(tabs[(index + direction + tabs.length) % tabs.length], true);
    });
  });
  /* Premier placement SANS animation : sinon le repère traverse la liste
     depuis l'angle au chargement. Et replacement au redimensionnement, la
     grille passant de la colonne à la rangée sous 900px. */
  var actif = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
  if (actif) placer(actif, false);
  window.addEventListener('resize', function () {
    var courant = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
    if (courant) placer(courant, false);
  });
})();
</script>"""

LANDING_HTML = page(
    title="monl compiler — le métier est compilé",
    description="Monl compile vos règles métier en backend autonome et contrat frontend vérifiable.",
    body=BODY,
    active="home",
    extra_css=EXTRA_CSS + landing_pourquoi.EXTRA_CSS,
    scripts=CASE_SCRIPT,
)
