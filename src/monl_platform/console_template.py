"""Static layout and styles for the compilation console."""

from __future__ import annotations

from .coloration import coloriser
from .theme import icon

EXTRA_CSS = """
.console-stage{position:relative;isolation:isolate;overflow:hidden}.console-ambient{position:absolute;inset:0;z-index:-1;pointer-events:none;overflow:hidden;background:radial-gradient(circle at 83% 8%,color-mix(in srgb,var(--accent) 11%,transparent),transparent 25%)}
.console-ambient::before{content:"";position:absolute;inset:22px 4% auto auto;width:min(44vw,620px);height:310px;opacity:.48;background-image:linear-gradient(color-mix(in srgb,var(--line) 55%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--line) 55%,transparent) 1px,transparent 1px);background-size:42px 42px;mask-image:radial-gradient(ellipse at center,black,transparent 72%);animation:console-grid 16s ease-in-out infinite alternate}
.console-ambient::after{content:"";position:absolute;right:8%;top:118px;width:390px;border-top:1px dashed var(--line-strong);transform:rotate(22deg);opacity:.48}
.console-node{position:absolute;width:10px;height:10px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 6px color-mix(in srgb,var(--accent) 13%,transparent);animation:console-pulse 3.6s ease-in-out infinite}.console-node-a{right:13%;top:82px}.console-node-b{right:38%;top:190px;animation-delay:-1.2s}.console-node-c{right:26%;top:300px;animation-delay:-2.4s}.console-node-d{right:6%;top:242px;width:7px;height:7px;animation-delay:-.6s}.console-node-e{right:47%;top:96px;width:7px;height:7px;animation-delay:-1.8s}.console-node-f{right:20%;top:410px;width:7px;height:7px;animation-delay:-3s}
.hero { padding: var(--space-8) 0 var(--space-7); display: grid;
        grid-template-columns: 1.05fr .95fr; gap: var(--space-7); align-items: center; }
.hero h1 { font-size: clamp(38px, 5.5vw, 66px); line-height: 1.02; letter-spacing: -.045em;
           margin-bottom: var(--space-4); }
.hero p.lede { font-size: 19px; color: var(--muted); max-width: 620px; }
.hero-actions { display: flex; gap: var(--space-3); flex-wrap: wrap; margin-top: var(--space-5); }
.proof { display: flex; flex-wrap: wrap; gap: var(--space-5); margin-top: var(--space-6);
         color: var(--muted); font-size: 14px; }
.proof span { display: inline-flex; align-items: center; gap: 7px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--brand); flex: none; }
.terminal { background: var(--code-bg); color: var(--code-ink); border-radius: var(--radius-lg);
            box-shadow: var(--shadow); overflow: hidden; }
.terminal-head { height: 46px; border-bottom: 1px solid var(--code-line); display: flex;
                 align-items: center; justify-content: space-between; padding: 0 16px;
                 font: 12px var(--mono); color: var(--code-muted); }
.lights { display: flex; gap: 6px; }
.lights i { width: 8px; height: 8px; border-radius: 50%; background: var(--code-muted); }
.terminal pre { margin: 0; padding: 24px; min-height: 340px; white-space: pre-wrap;
                font: 13px/1.72 var(--mono); }
/* `.kw` a disparu avec la coloration écrite à la main. `.arrow` marque les
   lignes de RÉSULTAT du terminal : un état, pas un mot du langage — c'est
   le genre d'emploi que l'accent garde. */
.cm { color: var(--s-cm); } .arrow { color: var(--code-accent); }

.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
         gap: var(--space-3); }
.step-no { font: 600 12px var(--mono); color: var(--brand); }
.step h3 { font-size: 18px; margin: var(--space-4) 0 var(--space-2); }
.step p { color: var(--muted); margin: 0; font-size: 15px; }

.studio { display: grid; grid-template-columns: 232px minmax(0, 1fr);
          border: 1px solid var(--line); border-radius: var(--radius-lg);
          overflow: hidden; background:color-mix(in srgb,var(--surface) 97%,transparent);box-shadow:var(--shadow),0 28px 80px color-mix(in srgb,var(--brand) 8%,transparent);backdrop-filter:blur(10px); }
.rail { position:relative; background: var(--surface-2); border-right: 1px solid var(--line); padding: var(--space-4) var(--space-3); }
.rail-title { font: 600 11px var(--mono); letter-spacing: .1em; text-transform: uppercase;
              color: var(--muted); margin: 0 10px var(--space-3); }
.rail button { width: 100%; border: 0; background: transparent; text-align: left;
               border-radius: 10px; padding: 11px 10px; color: var(--muted); cursor: pointer;
               display: flex; gap: 10px; align-items: center; min-height: 44px;
               transition: background .18s ease, color .18s ease; }
.rail button:hover { color: var(--ink); }
.rail button.active { background:transparent; color:var(--ink); font-weight:600; box-shadow:inset 2px 0 0 var(--brand); }
.rail .num { width: 22px; height: 22px; border-radius: 7px; border: 1px solid var(--line);
             display: grid; place-items: center; font: 11px var(--mono); flex: none; }
.workspace { padding: var(--space-6); min-width: 0; }
.panel { display: none; } .panel.active { display: block; }
.panel h2 { font-size: 26px; margin-bottom: var(--space-2); }
.panel .lede { color: var(--muted); margin-bottom: var(--space-5); }
.panel-actions { display:flex; justify-content:flex-end; gap:var(--space-3); margin-top:var(--space-5); }
.dialogue-card { background: var(--surface-2); border: 1px solid var(--line);
                 border-radius: var(--radius); padding: var(--space-5); }
.dialogue-log { margin-bottom: var(--space-5); background: var(--code-bg);
                color: var(--code-ink); border-radius: var(--radius); padding: var(--space-4);
                max-height: 360px; overflow: auto; }
.dialogue-log:empty { display: none; }
.dialogue-log pre { margin: 0 0 var(--space-3); white-space: pre-wrap;
                    overflow-wrap: anywhere; font: 13px/1.6 var(--mono); }
.dialogue-log pre:last-child { margin-bottom: 0; }
.dialogue-question { margin: 0 0 var(--space-4); padding: var(--space-4);
                     border: 1px solid var(--line); border-radius: var(--radius);
                     white-space: pre-wrap; overflow-wrap: anywhere;
                     font: 14px/1.65 var(--mono); }
/* Les choix du dialogue sont des BOUTONS, pas un menu de terminal recopié.
   `min(100%, 260px)` et non `260px` : une piste plus large que son conteneur
   déborde à 375 px sans que rien ne le signale (point 165). */
.dialogue-choices { display: grid; gap: var(--space-3);
                    margin: 0 0 var(--space-4);
                    grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); }
.dialogue-choice { display: grid; grid-template-columns: 26px 1fr;
                   gap: 2px var(--space-3); align-items: start; text-align: left;
                   padding: var(--space-3) var(--space-4); font: inherit;
                   color: inherit; cursor: pointer; background: var(--surface);
                   border: 1px solid var(--line); border-radius: var(--radius); }
.dialogue-choice:hover { border-color: var(--accent); }
.dialogue-choice-num { grid-row: 1 / span 2; color: var(--muted);
                       font: 13px/1.6 var(--mono); }
.dialogue-choice-label { font-weight: 600; overflow-wrap: anywhere; }
.dialogue-choice-hint { grid-column: 2; color: var(--muted); font-size: 14px;
                        overflow-wrap: anywhere; }
.dialogue-form { display: flex; gap: var(--space-3); align-items: end; }
.dialogue-form label { display: block; font-weight: 600; margin-bottom: 7px; }
.dialogue-form input { width: 100%; min-height: 46px; padding: 10px 12px;
                       border: 1px solid var(--line); border-radius: var(--radius);
                       background: var(--surface); color: var(--ink); font: 16px var(--sans); }
.dialogue-field { min-width: 0; flex: 1; }
.dialogue-actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.dialogue-complete { margin-top: var(--space-4); }
.dialogue-status { color: var(--muted); min-height: 1.5em; margin: 0 0 var(--space-4); }

.gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
           gap: var(--space-3); margin-bottom: var(--space-5); }
.example { text-align: left; background: var(--surface); border: 1px solid var(--line);
           border-radius: var(--radius); padding: var(--space-4); cursor: pointer;
           transition: border-color .18s ease, background .18s ease; }
.example:hover { border-color: var(--brand); background: var(--soft); }
.example[aria-pressed="true"] { border-color: var(--brand); background: var(--soft); }
.example b { display: block; margin-bottom: 4px; }
.example span { color: var(--muted); font-size: 14px; display: block; margin-bottom: var(--space-3); }
.chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chip { border: 1px solid var(--line); border-radius: 999px; padding: 3px 9px;
        font: 11px var(--mono); color: var(--muted); background: var(--bg); }

.field-head { display: flex; justify-content: space-between; align-items: end;
              gap: var(--space-4); margin-bottom: var(--space-2); }
.field-head label { font-weight: 600; }
.field-head small { color: var(--muted); }
textarea { width: 100%; min-height: 400px; resize: vertical; background: var(--code-bg);
           color: var(--code-ink); border: 1px solid var(--code-line); border-radius: var(--radius);
           padding: 18px; font: 13px/1.7 var(--mono); tab-size: 4; }
.toolbar { display: flex; justify-content: space-between; gap: var(--space-3);
           flex-wrap: wrap; margin-top: var(--space-4); }
.toolbar-group { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.file-label { position: relative; overflow: hidden; }
.file-label input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.hint { color: var(--muted); font-size: 13px; align-self: center; }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-bottom-width: 2px;
      border-radius: 5px; padding: 1px 5px; background: var(--surface-2); }

.feedback { margin-top: var(--space-4); border-radius: var(--radius);
            padding: var(--space-4); display: none; }
.feedback.show { display: block; }
.feedback.ok { background: var(--soft); border: 1px solid var(--brand); }
.feedback.error { background: var(--danger-bg); border: 1px solid var(--danger-line); color: var(--danger); }
.feedback pre { margin: var(--space-2) 0 0; white-space: pre-wrap; font: 13px/1.6 var(--mono); }

.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
               gap: var(--space-3); margin-bottom: var(--space-5); }
.metric { background: var(--surface-2); border: 1px solid var(--line);
          border-radius: var(--radius); padding: var(--space-4); }
.metric b { display: block; font: 600 24px var(--mono); }
.metric span { color: var(--muted); font-size: 13px; }
.entity-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--space-3); }
.entity { background: var(--surface-2); border: 1px solid var(--line);
          border-radius: var(--radius); padding: var(--space-4); }
.entity h3 { margin: 0 0 10px; font: 600 15px var(--mono); }
.routes { border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.route { display: grid; grid-template-columns: 74px minmax(120px, 1fr) 110px; gap: var(--space-3);
         padding: 11px var(--space-4); border-bottom: 1px solid var(--line);
         align-items: center; font-size: 13px; }
.route:last-child { border-bottom: 0; }
.method { font: 600 11px var(--mono); color: var(--brand); }
.path { font: 13px var(--mono); overflow-wrap: anywhere; }
.lock { color: var(--muted); text-align: right; }
.empty { padding: var(--space-8) var(--space-5); text-align: center; color: var(--muted);
         border: 1px dashed var(--line); border-radius: var(--radius); }
.download-card { background: var(--surface-2); border: 1px solid var(--line);
                 border-radius: var(--radius); padding: var(--space-5); display: flex;
                 justify-content: space-between; gap: var(--space-5); align-items: center;
                 flex-wrap: wrap; margin-bottom: var(--space-5); }
.download-card h3 { margin: 0 0 4px; }
.download-card p { margin: 0; color: var(--muted); }
.builder-card { background: var(--soft); border: 1px solid var(--line);
                border-radius: var(--radius); padding: var(--space-5); margin-top: var(--space-5); }
.builder-card h3 { margin: 0 0 var(--space-2); }
.builder-card p { color: var(--muted); margin: 0 0 var(--space-4); }
.builder-status { margin-top: var(--space-3); color: var(--muted); white-space: pre-wrap;
                 font: 13px/1.6 var(--mono); }
.history { list-style: none; padding: 0; margin: var(--space-3) 0 0; }
.history li { display: flex; justify-content: space-between; align-items: center;
              gap: var(--space-3); padding: 11px 0; border-bottom: 1px solid var(--line);
              font-size: 14px; flex-wrap: wrap; }
.history li:last-child { border-bottom: 0; }
.history .when { color: var(--muted); font: 12px var(--mono); }
.mcp { display: grid; grid-template-columns: .85fr 1.15fr; gap: var(--space-4); }
.console-head { padding: var(--space-7) 0 var(--space-5); display:flex;
                justify-content:space-between; align-items:end; gap:var(--space-5); }
.console-head h1 { font-size:clamp(32px,5vw,48px); margin-bottom:var(--space-3); }
.console-head p { color:var(--muted); max-width:680px; margin:0; }
.console-badge { display:inline-flex; align-items:center; gap:8px; white-space:nowrap;
                 color:var(--brand); background:var(--soft); border:1px solid var(--line);
                 border-radius:999px; padding:8px 12px; font:12px var(--mono); }
.panel.active { animation:panel-in .28s cubic-bezier(.2,.75,.25,1); }
@keyframes panel-in { from { opacity:0; transform:translateY(7px); } }
.spinner { width: 15px; height: 15px; border: 2px solid rgba(255, 255, 255, .35);
           border-top-color: currentColor; border-radius: 50%; animation: spin .7s linear infinite; }
.hidden { display: none !important; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes console-grid{to{transform:translate3d(-22px,14px,0)}}
@keyframes console-pulse{50%{transform:scale(1.35);box-shadow:0 0 0 12px color-mix(in srgb,var(--accent) 3%,transparent)}}
@media (max-width: 900px) {
  .hero { grid-template-columns: 1fr; padding-top: var(--space-6); }
  .studio { grid-template-columns: 1fr; }
  .rail { border-right: 0; border-bottom: 1px solid var(--line); display: flex;
          overflow-x: auto; padding: 10px; gap: 6px; }
  .rail-title { display: none; }
  .rail button { width: auto; white-space: nowrap; }
  .workspace { padding: var(--space-4); }
  .mcp { grid-template-columns: 1fr; }
  .route { grid-template-columns: 60px 1fr; } .lock { display: none; }
  .console-head { align-items:start; flex-direction:column; }
  .dialogue-form { align-items: stretch; flex-direction: column; }
  .dialogue-choices { grid-template-columns: 1fr; }
}
@media(prefers-reduced-motion:reduce){.panel.active,.console-ambient::before,.console-node{animation:none}}
"""

# La SPEC passe par le coloriseur ; les lignes de résultat gardent leurs
# flèches, qui ne sont pas du langage.
TERMINAL = coloriser("""app WorkshopNotebook

entity Note
    title: String
    status: String

actor Author selfRegister

relation Author hasMany Note

rule Note.status oneOf "draft", "published"
rule Note.Read publicWhen status "published"
rule Note.Update ownedBy Author

workflow Write for Author
    Create Note
    Read Note
    Update Note""") + """

<span class="s-cm"># deterministic result</span>
<span class="arrow">✓</span> FastAPI API + accounts
<span class="arrow">✓</span> SQL schema and indexes
<span class="arrow">✓</span> Per-record access control
<span class="arrow">✓</span> Frontend contract"""

BODY = f"""
<div class="console-stage"><div class="console-ambient" aria-hidden="true"><i class="console-node console-node-a"></i><i class="console-node console-node-b"></i><i class="console-node console-node-c"></i><i class="console-node console-node-d"></i><i class="console-node console-node-e"></i><i class="console-node console-node-f"></i></div>
<section class="shell console-head" data-reveal>
<div><h1>Compilation console</h1>
<p>Answer the guided dialogue or write a specification, check its rules,
then download a self-contained backend and its frontend contract.</p></div>
<span class="console-badge">{icon('shield')} Local, verifiable compilation</span>
</section>

<section id="studio" class="shell" style="padding-bottom:var(--space-8)" data-reveal>
<div class="studio">
<aside class="rail" role="tablist" aria-label="Steps of the path">
<p class="rail-title">Path</p>
<button data-panel="dialogue" role="tab" aria-controls="panel-dialogue" aria-selected="false" type="button">{icon('terminal')} Guided dialogue</button>
<button class="active" data-panel="spec" role="tab" aria-controls="panel-spec" aria-selected="true" type="button">{icon('code')} Specification</button>
<button data-panel="review" role="tab" aria-controls="panel-review" aria-selected="false" type="button">{icon('check')} Review</button>
<button data-panel="contract" role="tab" aria-controls="panel-contract" aria-selected="false" type="button">{icon('shield')} Contract</button>
<button data-panel="delivery" role="tab" aria-controls="panel-delivery" aria-selected="false" type="button">{icon('package')} Delivery</button>
</aside>
<div class="workspace">

<section class="panel" id="panel-dialogue">
<h2>Build it by answering questions</h2>
<p class="lede">The same deterministic dialogue as <code>monl</code>. The console
replays the answers already given and shows you the next question.</p>
<div class="dialogue-card">
<div id="dialogue-log" class="dialogue-log" aria-label="Dialogue log"></div>
<p id="dialogue-status" class="dialogue-status" role="status" aria-live="polite">
Start whenever you are ready.</p>
<pre id="dialogue-question" class="dialogue-question hidden"></pre>
<div id="dialogue-choices" class="dialogue-choices hidden" role="group"
     aria-label="Choices offered"></div>
<form id="dialogue-form" class="dialogue-form hidden">
<div class="dialogue-field"><label for="dialogue-answer">Your answer</label>
<input id="dialogue-answer" name="answer" type="text" autocomplete="off"></div>
<div class="dialogue-actions"><button class="primary" id="dialogue-submit" type="submit">
<span class="btn-label">Send the answer</span><i class="spinner hidden"></i></button>
<button class="ghost" id="dialogue-reset" type="button">Start over</button></div>
</form>
<div id="dialogue-start" class="dialogue-complete">
<button class="primary" type="button">Start the dialogue</button>
</div>
<div id="dialogue-complete" class="dialogue-complete hidden">
<p class="feedback ok show">The spec is ready. It will go through
<code>/api/validate</code> again before any compilation.</p>
<button class="primary" id="dialogue-validate" type="button">Check the spec and continue</button>
</div>
</div>
</section>

<section class="panel active" id="panel-spec">
<h2>Describe the application</h2>
<p class="lede">Paste a spec, import a file or go through the guided dialogue.
The examples below are complete specifications, not excerpts.</p>
<div class="gallery" id="gallery" role="group" aria-label="Specification examples"></div>
<div class="field-head">
<label for="spec-input">Monl specification</label>
<small id="char-count">0 characters</small>
</div>
<textarea id="spec-input" spellcheck="false" aria-describedby="spec-help"></textarea>
<p id="spec-help" class="hint"><code>.ml</code> file, 256 KB at most.
<a href="/guide#dsl">Syntax reference</a></p>
<div class="toolbar">
<div class="toolbar-group">
<label class="secondary file-label">{icon('upload')} Import a .ml<input id="file-input" type="file" accept=".ml,.yaml,text/plain"></label>
<button class="ghost" id="reset-btn" type="button">Reset</button>
</div>
<div class="toolbar-group">
<span class="hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
<button class="primary" id="validate-btn" type="button">{icon('check')}
<span class="btn-label">Check the spec</span><i class="spinner hidden"></i></button>
</div>
</div>
<div class="feedback" id="validation-feedback" role="status" aria-live="polite"></div>
</section>

<section class="panel" id="panel-review">
<h2>Business review</h2>
<p class="lede">This summary comes from the real monl parser, not from a parallel interpretation.</p>
<div id="review-content" class="empty">Validate a specification first.</div>
<div class="toolbar"><span></span>
<button class="primary" id="compile-btn" type="button">{icon('terminal')}
<span class="btn-label">Compile the backend</span><i class="spinner hidden"></i></button></div>
<div class="feedback" id="compile-feedback" role="status" aria-live="polite"></div>
</section>

<section class="panel" id="panel-contract" role="tabpanel" tabindex="0">
<h2>Backend and contract</h2>
<p class="lede">Routes, entities and permissions: everything needed to build any interface.</p>
<div id="contract-content" class="empty">No compilation available.</div>
<div class="panel-actions"><button class="primary" id="delivery-next" type="button">See the delivery {icon('arrow')}</button></div>
</section>

<section class="panel" id="panel-delivery" role="tabpanel" tabindex="0">
<h2>Reproducible delivery</h2>
<p class="lede">The backend, the SQL schema, the contract and the instructions are
gathered in one archive. The JWT secret is not in it: it is created on first start.</p>
<div id="delivery-content" class="empty">Compile a backend to get its archive.</div>
<div class="builder-card" id="builder-card">
<h3>Try the API</h3>
<p>monl starts the compiled backend and gives you its local address: the
interactive documentation and every route in the contract really respond. The
interface is built on your side — with the archive, the contract and your own
provider.</p>
<div id="builder-content" class="empty">Compile a project first to start its API.</div>
</div>
<h3 style="margin-top:var(--space-6)">Your compilations</h3>
<p class="hint">Kept in your account and accessible only by you.</p>
<ul class="history" id="history"></ul>
<div class="panel-actions"><button class="secondary" id="contract-back" type="button">{icon('arrow')} Back to the contract</button></div>
</section>

</div></div>
</section>
</div>
"""
