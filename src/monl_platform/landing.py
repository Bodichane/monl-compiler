"""Public product page for the compiler platform."""

from __future__ import annotations

from . import landing_cas, landing_pourquoi
from .coloration import coloriser, en_lignes
from .landing_vitrine import (
    ARBRE,
    ENTITES,
    FICHIERS,
    ROUTES,
    extrait_affiche,
)
from .theme import icon, page

GITHUB_URL = "https://github.com/Bodichane/monl-compiler"
GITHUB_ICON = ('<svg class="icon" viewBox="0 0 24 24" fill="currentColor" '
               'aria-hidden="true"><path d="M12 2C6.48 2 2 6.58 2 12.24c0 4.52 '
               '2.87 8.35 6.84 9.71.5.1.68-.22.68-.49v-1.71c-2.78.62-3.37-1.39 '
               '-3.37-1.39-.45-1.19-1.11-1.51-1.11-1.51-.91-.64.07-.63.07-.63 '
               '1 .08 1.53 1.06 1.53 1.06.9 1.59 2.35 1.13 2.92.86.09-.67.35-1.13 '
               '.64-1.39-2.22-.26-4.56-1.15-4.56-5.09 0-1.12.39-2.04 1.03-2.76 '
               '-.1-.26-.45-1.31.1-2.73 0 0 .84-.28 2.75 1.05A9.2 9.2 0 0 1 12 '
               '7.9c.85 0 1.71.12 2.5.35 1.91-1.33 2.75-1.05 2.75-1.05.55 1.42 '
               '.2 2.47.1 2.73.64.72 1.03 1.64 1.03 2.76 0 3.95-2.34 4.83-4.57 '
               '5.08.36.32.68.95.68 1.92v2.84c0 .27.18.59.69.49A10.2 10.2 0 0 0 '
               '22 12.24C22 6.58 17.52 2 12 2Z"/></svg>')

EXTRA_CSS = """
.landing-hero { position:relative; isolation:isolate; min-height:calc(100svh - 68px); padding: 84px 0 112px; display:grid; grid-template-columns:minmax(0,1.04fr) minmax(420px,.96fr);
  gap:clamp(42px,7vw,94px); align-items:center; }
.landing-hero::before { content:""; position:absolute; width:520px; height:520px; right:-180px; top:-170px;
  border-radius:50%; pointer-events:none; filter:blur(4px);
  background:radial-gradient(circle,color-mix(in srgb,var(--brand) 12%,transparent),transparent 68%); z-index:-1; animation:landing-glow 14s ease-in-out infinite alternate; }
.landing-hero::after { content:""; position:absolute; inset:0; pointer-events:none; z-index:-1; opacity:.48;
  background-image:linear-gradient(color-mix(in srgb,var(--line) 42%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--line) 42%,transparent) 1px,transparent 1px);
  background-size:48px 48px; mask-image:radial-gradient(ellipse at 70% 35%,black,transparent 72%); }
.landing-network { position:absolute; inset:0; z-index:-1; pointer-events:none; }
.landing-network::before { content:""; position:absolute; width:42%; right:5%; top:22%; border-top:1px dashed var(--line-strong); transform:rotate(-17deg); opacity:.55; }
.landing-network::after { content:""; position:absolute; width:30%; right:17%; top:42%; border-top:1px dashed var(--line-strong); transform:rotate(28deg); opacity:.4; }
.landing-node { position:absolute; width:9px; height:9px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 6px color-mix(in srgb,var(--accent) 12%,transparent); animation:landing-node 4.4s ease-in-out infinite; }
.landing-node-a { right:24%; top:19%; }.landing-node-b { right:11%; top:39%; animation-delay:-1.4s; }.landing-node-c { left:47%; top:10%; animation-delay:-2.8s; }.landing-node-d { right:38%; top:46%; width:7px; height:7px; animation-delay:-.8s; }.landing-node-e { right:4%; top:16%; width:7px; height:7px; animation-delay:-2s; }.landing-node-f { left:40%; top:56%; width:7px; height:7px; animation-delay:-3.2s; }
.landing-hero>div:not(.landing-network),.landing-hero>aside { position:relative; z-index:1; }
.hero-copy { padding-bottom:var(--space-5); }.hero-copy .eyebrow{margin-bottom:var(--space-5)}
.hero-copy::after { content:"01 / SPEC → API"; position:absolute; left:-52px; top:50%; transform:rotate(-90deg) translateX(-50%); transform-origin:left top; color:var(--muted); font:600 10px var(--mono); letter-spacing:.14em; opacity:.7; }
.landing-hero h1 { max-width: 760px; margin: 0 0 var(--space-5);
  font-size: clamp(48px, 7vw, 82px); line-height: .94; letter-spacing: -.06em; text-wrap:balance; }
.landing-hero h1 span { display:block; color:var(--accent); font-style:italic; font-weight:640; }
.landing-hero .lede { max-width: 650px; margin: 0 0 var(--space-6);
  color: var(--muted); font-size: clamp(18px, 2.2vw, 21px); }
.hero-actions { display:flex; flex-wrap:wrap; gap:var(--space-3); }
.trust { display:flex; flex-wrap:wrap; gap:var(--space-5);
  margin-top:var(--space-6); color:var(--muted); font-size:14px; }
.trust span { display:inline-flex; gap:7px; align-items:center; }
.trust .icon { color:var(--ink); }
.proof-deck { position:relative; z-index:4; display:grid; grid-template-columns:1.35fr .8fr .8fr 1.35fr;
  margin-top:-54px; margin-bottom:var(--space-7); border:1px solid var(--line); border-radius:var(--radius-lg);
  overflow:hidden; background:color-mix(in srgb,var(--surface) 94%,transparent); box-shadow:var(--shadow); }
.proof-deck div { min-height:112px; padding:22px clamp(16px,2.5vw,30px); border-right:1px solid var(--line); display:flex; flex-direction:column; justify-content:center; }
.proof-deck div:last-child{border-right:0}.proof-deck div:first-child{background:var(--code-bg);color:var(--code-ink)}
.proof-deck b{display:block;font:700 clamp(19px,2vw,26px) var(--mono);letter-spacing:-.04em}
.proof-deck span{color:var(--muted);font-size:12px}.proof-deck div:first-child span{color:var(--code-muted)}.proof-deck .proof-word{color:inherit}
.proof-rail { position:relative; }
.hero-visual { position:relative; perspective:1100px; transform-style:preserve-3d; }
.start-card { position:relative; background:var(--code-bg); color:var(--code-ink); border:1px solid var(--line);
  border-radius:calc(var(--radius-lg) + 4px); padding:var(--space-3); box-shadow:0 28px 70px rgba(0,0,0,.22);
  transform:rotate(1deg) rotateX(var(--tilt-x,0deg)) rotateY(var(--tilt-y,0deg)); transform-style:preserve-3d;
  transition:transform .42s var(--ease-out),box-shadow .28s ease; }
.start-card::before { content:""; position:absolute; inset:18px -16px -16px 18px; border:1px solid var(--line);
  border-radius:inherit; z-index:-1; background:var(--surface-2); transform:rotate(-2deg); }
.demo-window { border:1px solid color-mix(in srgb,var(--code-ink) 15%,transparent);border-radius:14px;overflow:hidden;background:var(--code-bg); }
.demo-bar { display:flex;align-items:center;gap:7px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.1);font:11px var(--mono);color:var(--code-muted); }
.demo-bar i { width:7px;height:7px;border-radius:50%;background:var(--code-line); }.demo-bar i:first-child{background:var(--code-accent)}
.demo-bar span { margin-left:auto;display:inline-flex;align-items:center;gap:6px;color:var(--code-accent); }
.demo-bar span::before { content:"";width:6px;height:6px;border-radius:50%;background:var(--code-accent);box-shadow:0 0 0 4px rgba(229,164,95,.16); }
.demo-code { padding:22px 20px 18px;font:12px/1.85 var(--mono);color:var(--code-muted); }
.demo-code b, .demo-code strong { font-weight:500 }
/* Le balayage dit qu'il se passe quelque chose ; il ne dit rien de plus,
   donc il n'a pas besoin de l'accent. En encre de code, le mouvement reste
   et une couleur de moins traverse la page. */
.scan-line { height:1px;background:linear-gradient(90deg,transparent,var(--code-ink),transparent);opacity:.5;animation:scan 3.2s ease-in-out infinite; }
.demo-result { display:grid;grid-template-columns:1.25fr repeat(3,.6fr);gap:1px;background:rgba(255,255,255,.1);border-top:1px solid rgba(255,255,255,.1); }
.demo-result div { padding:14px;background:var(--code-bg); }.demo-result b{display:block;color:var(--code-ink);font:600 16px var(--mono)}
.demo-result span{font:10px var(--mono);color:var(--code-muted)}.demo-result .verified b{color:var(--code-accent);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
@media (hover:hover){.start-card:hover{transform:translateY(-5px) rotate(.35deg) rotateX(var(--tilt-x,0deg)) rotateY(var(--tilt-y,0deg));box-shadow:0 38px 84px rgba(0,0,0,.3)}}
@keyframes scan { 0%,100%{transform:translateY(-8px);opacity:.25} 50%{transform:translateY(8px);opacity:1} }
@keyframes landing-glow { to { transform:translate3d(-24px,18px,0) scale(1.06); } }
@keyframes landing-node { 50% { transform:scale(1.35); box-shadow:0 0 0 12px color-mix(in srgb,var(--accent) 3%,transparent); } }
.float-card { position:absolute; z-index:3; display:flex; align-items:center; gap:9px; min-height:44px; padding:9px 13px;
  border:1px solid var(--line); border-radius:12px; background:var(--surface); color:var(--ink); box-shadow:var(--shadow);
  font:600 12px var(--mono); animation:hero-float 4.8s ease-in-out infinite; }
.float-card .icon{color:var(--accent)}.float-a{right:-30px;top:13%;}.float-b{left:-42px;bottom:12%;animation-delay:-2.4s}
@keyframes hero-float { 50% { transform:translateY(-9px) rotate(.5deg); } }
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
.flow-stage:nth-child(2) p { color:var(--code-muted); }
/* Le titre en HAUT, les étiquettes en BAS. Avant, c'était l'inverse :
   `margin-top:auto` sur le titre le poussait d'un espace libre qui
   dépend de la longueur du paragraphe, donc les trois titres se posaient
   à trois hauteurs différentes. Le surtitre le masquait — lui était
   aligné — et le défaut est apparu en le retirant. */
.flow-stage h3 { margin:0 0 10px; font-size:clamp(22px,2.4vw,29px); }
.flow-stage p { color:var(--muted); margin:0; }
.flow-stage .stage-tags { display:flex; flex-wrap:wrap; gap:6px;
  margin-top:auto; padding-top:22px; }
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
.compiler-layout { display:grid; grid-template-columns:minmax(230px,.58fr) minmax(0,1.42fr); gap:clamp(40px,8vw,110px); align-items:start; }
.compiler-layout>.section-head { position:sticky; top:100px; margin:0; }
.output-flow { display:grid; grid-template-columns:1fr; gap:var(--space-4); align-items:center; }
.mini-spec { margin:0; min-height:300px; }
.flow-arrow { width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:var(--brand);color:var(--on-brand); transform:rotate(90deg); margin:-2px auto; box-shadow:0 0 0 10px color-mix(in srgb,var(--brand) 7%,transparent); }
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
.layer:nth-child(2) p{color:var(--code-muted)}.layer:nth-child(2) .layer-label{color:var(--code-ink)}
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
  .landing-hero { min-height:0; padding:56px 0 92px; grid-template-columns:1fr; }
  .hero-copy::after{display:none}.hero-visual{width:min(100%,620px);margin-inline:auto}.float-a{right:-8px}.float-b{left:-8px}
  .pipeline,.bento,.step-list,.editorial,.platform-flow { grid-template-columns:1fr; }
  .flow-stage { min-height:220px; border-right:0; border-bottom:1px solid var(--line); }.flow-stage:last-child{border-bottom:0}
  .proof-deck{grid-template-columns:1fr 1fr;margin-top:-44px}.proof-deck div{border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.proof-deck div:nth-child(2n){border-right:0}.proof-deck div:nth-last-child(-n+2){border-bottom:0}
  .layers{grid-template-columns:1fr}.layer:nth-child(2){transform:none}.layer-arrow{display:none}
  .compiler-layout{grid-template-columns:1fr}.compiler-layout>.section-head{position:static}.output-flow { grid-template-columns:1fr; }.flow-arrow{transform:rotate(90deg);margin:auto}
  .pipeline article:not(:last-child)::after { display:none; }
  .bento article:first-child { grid-column:auto; }
}
@media(max-width:520px){.start-card{transform:none}.start-card::before{display:none}.float-card{position:static;margin-top:var(--space-3);animation:none}.hero-visual{display:flex;flex-direction:column}.demo-result{grid-template-columns:1fr 1fr}.capability-grid{grid-template-columns:1fr}.capability{border-right:0;border-bottom:1px solid var(--line)!important}.capability:last-child{border-bottom:0!important}}
@media(prefers-reduced-motion:reduce){.scan-line,.landing-hero::before,.landing-node,.float-card{animation:none}.start-card{transition:none}}
"""


def feature(symbol: str, title: str, text: str, delay: int = 0) -> str:
    return f"""<article class="card lift" data-reveal style="--reveal-delay:{delay}ms">
<span class="feature-icon">{icon(symbol)}</span><h3>{title}</h3><p>{text}</p></article>"""






#: Texte brut, confronté ligne à ligne à `SPEC_VITRINE` par un témoin : un
#: extrait recopié à la main finit toujours par montrer une règle inexistante.
DEMO_HERO_SOURCE = """app LittleShop

entity Product
  price: Money
  stock: Integer

rule Product.stock min 0
rule Product.Read public"""
DEMO_HERO = en_lignes(DEMO_HERO_SOURCE)

MINI_SPEC = coloriser(extrait_affiche())

#: Chaque nom vient de `ARBRE`, dont le témoin exige qu'il figure dans
#: l'archive réellement compilée. Écrire un nom ici ne suffit plus à le
#: faire exister — c'est tout l'objet de `landing_vitrine`.
ARBRE_HTML = "<br>".join(
    f'{"└──" if i == len(ARBRE) - 1 else "├──"} {nom} <span>{role}</span>'
    for i, (nom, role) in enumerate(ARBRE))


LANDING_MOTION = """<script>
(function () {
  var visual = document.querySelector('.hero-visual');
  var card = document.querySelector('.start-card');
  if (!visual || !card || window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      window.matchMedia('(pointer: coarse)').matches) return;
  var frame = 0;
  visual.addEventListener('pointermove', function (event) {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(function () {
      var box = visual.getBoundingClientRect();
      var x = (event.clientX - box.left) / box.width - .5;
      var y = (event.clientY - box.top) / box.height - .5;
      card.style.setProperty('--tilt-x', (-y * 3).toFixed(2) + 'deg');
      card.style.setProperty('--tilt-y', (x * 3).toFixed(2) + 'deg');
    });
  });
  visual.addEventListener('pointerleave', function () {
    if (frame) cancelAnimationFrame(frame);
    card.style.setProperty('--tilt-x', '0deg');
    card.style.setProperty('--tilt-y', '0deg');
  });
})();
</script>"""


BODY = f"""
<section class="shell landing-hero"><div class="landing-network" aria-hidden="true"><i class="landing-node landing-node-a"></i><i class="landing-node landing-node-b"></i><i class="landing-node landing-node-c"></i><i class="landing-node landing-node-d"></i><i class="landing-node landing-node-e"></i><i class="landing-node landing-node-f"></i></div>
<div class="hero-copy"><h1 data-reveal style="--reveal-delay:60ms">Describe your business.<span>Monl builds the backend.</span></h1>
<p class="lede" data-reveal style="--reveal-delay:120ms">Declare your data, the people who act on it and the rules that must never be bypassed. Monl checks them, then hands you an API, its SQL schema and an exact contract for your interfaces.</p>
<div class="hero-actions" data-reveal style="--reveal-delay:180ms">
<a class="primary" href="/console">{icon('terminal')} Try it in the console</a>
<a class="secondary" href="/docs">{icon('book')} Read the documentation</a>
<a class="secondary github-link" href="{GITHUB_URL}" target="_blank" rel="noopener">{GITHUB_ICON} View the project on GitHub</a></div>
<div class="trust" data-reveal style="--reveal-delay:220ms">
<span>{icon('check')} Start from an example</span><span>{icon('check')} Check before you compile</span>
<span>{icon('check')} Run it wherever you want</span></div></div>
<div class="hero-visual" data-reveal style="--reveal-delay:120ms"><aside class="start-card" aria-label="A Monl compilation">
<div class="demo-window"><div class="demo-bar"><i></i><i></i><i></i><span>verified specification</span></div>
<div class="demo-code">{DEMO_HERO}</div>
<div class="scan-line"></div><div class="demo-result"><div class="verified"><b>{icon('check')} valid</b><span>business audit</span></div>
<div><b>{ENTITES}</b><span>entities</span></div><div><b>{ROUTES}</b><span>routes</span></div><div><b>{FICHIERS}</b><span>files</span></div></div></div></aside>
<span class="float-card float-a" aria-hidden="true">{icon('shield')} Verified permissions</span><span class="float-card float-b" aria-hidden="true">{icon('package')} Self-contained archive</span></div>
</section>

<section class="shell proof-deck proof-rail" aria-label="Compiler evidence" data-reveal>
<div><b>4</b><span>examples to start from</span></div><div><b>0</b><span>network calls to compile</span></div>
<div><b class="proof-word">Verified</b><span>before the archive is produced</span></div><div><b class="proof-word">Yours</b><span>self-contained backend, no lock-in</span></div>
</section>

<section class="band"><div class="shell section compiler-layout">
<div class="section-head" data-reveal><h2>A clear rule becomes a usable backend.</h2>
<p>Here is what Monl produces from a shop spec: the results are rechecked every time the compiler changes.</p></div>
<div class="output-flow" data-reveal><pre class="codeblock mini-spec"><code>{MINI_SPEC}</code></pre>
<span class="flow-arrow">{icon('arrow')}</span><div class="artifact"><div class="artifact-head"><b>LittleShop</b><span class="muted">self-contained archive</span></div>
<div class="artifact-body"><div class="artifact-stats"><div><b>{ENTITES}</b><span>entities</span></div><div><b>{ROUTES}</b><span>API routes</span></div><div><b>{FICHIERS}</b><span>files</span></div></div>
<div class="tree"><b>backend/</b><br>{ARBRE_HTML}</div></div></div></div>
</div></section>

<section class="shell section" aria-labelledby="position-title">
<div class="section-head" data-reveal><h2 id="position-title">Keep your infrastructure. Make the business rules non-negotiable.</h2>
<p>Your cloud and PostgreSQL run the application. Monl turns your rules into behavior the server enforces, whatever interface calls the API.</p></div>
<div class="platform-flow" data-reveal>
<article class="flow-stage"><h3>The foundations</h3><p>Database, compute, storage and network stay with the provider you choose.</p><div class="stage-tags"><span>Postgres</span><span>cloud</span><span>self-hosted</span></div></article>
<article class="flow-stage"><h3>Verified business rules</h3><p>Actors, permissions, ownership, payments and invariants become a consistent API and contract. The same engine for MCP agents.</p><div class="stage-tags"><span>spec.ml</span><span>audit</span><span>contract</span></div></article>
<article class="flow-stage"><h3>Every experience</h3><p>Web, mobile and agents use the same routes and permissions without guessing them.</p><div class="stage-tags"><span>web</span><span>mobile</span><span>MCP</span></div></article>
</div></section>

{landing_pourquoi.SECTIONS}
<section class="band"><div class="shell section editorial">
<div class="section-head" data-reveal><h2>Security is not an instruction given to the frontend.</h2>
<p>It is derived from the specification and repeated in every layer produced. The limits stay explicit.</p>
<a class="secondary" href="/security">Read the security model {icon('arrow')}</a></div>
<div class="capability-grid">
<article class="capability" data-reveal><span class="feature-icon">{icon('shield')}</span><h3>Permissions compiled per actor</h3><p>Public read, session, ownership and privileged role are distinguished route by route.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('check')}</span><h3>Server-side invariants</h3><p>Stock, amounts, uniqueness, allowed states and the freeze after payment never depend on the browser.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('code')}</span><h3>An exact frontend contract</h3><p>Each interface receives the available routes, fields, actions and authentication requirements.</p></article>
<article class="capability" data-reveal><span class="feature-icon">{icon('key')}</span><h3>Secrets created on your side</h3><p>The JWT secret does not travel in the archive and stays under the operator’s control.</p></article>
</div></div></section>

<section class="shell section"><div class="section-head" data-reveal><h2>Four applications, four families of rules actually tested.</h2>
<p>Each example is a complete specification served by the platform. Open it in the console, adapt it, then compile its backend.</p></div>
{landing_cas.EXPLORATEUR}</section>

<section class="shell final" data-reveal>
<h2>Compile a real business rule.</h2>
<p>Your projects stay available in your account and every archive remains self-contained.</p>
<a class="secondary" href="/console">Open the console {icon('arrow')}</a>
</section>
"""


LANDING_HTML = page(
    title="MONL — the business is compiled",
    description="Monl compiles your business rules into a self-contained backend and a verifiable frontend contract.",
    body=BODY,
    active="home",
    extra_css=EXTRA_CSS + landing_cas.EXTRA_CSS + landing_pourquoi.EXTRA_CSS,
    scripts=LANDING_MOTION + landing_cas.CASE_SCRIPT,
)
