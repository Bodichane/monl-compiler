"""Static layout and styles for the compilation console."""

from __future__ import annotations

from .coloration import coloriser
from .theme import icon

EXTRA_CSS = """
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
          overflow: hidden; background: var(--surface); box-shadow: var(--shadow); }
.rail { background: var(--surface-2); border-right: 1px solid var(--line); padding: var(--space-4) var(--space-3); }
.rail-title { font: 600 11px var(--mono); letter-spacing: .1em; text-transform: uppercase;
              color: var(--muted); margin: 0 10px var(--space-3); }
.rail button { width: 100%; border: 0; background: transparent; text-align: left;
               border-radius: 10px; padding: 11px 10px; color: var(--muted); cursor: pointer;
               display: flex; gap: 10px; align-items: center; min-height: 44px;
               transition: background .18s ease, color .18s ease; }
.rail button:hover { color: var(--ink); }
.rail button.active { background: var(--surface); color: var(--ink); font-weight: 600; }
.rail .num { width: 22px; height: 22px; border-radius: 7px; border: 1px solid var(--line);
             display: grid; place-items: center; font: 11px var(--mono); flex: none; }
.workspace { padding: var(--space-6); min-width: 0; }
.panel { display: none; } .panel.active { display: block; }
.panel h2 { font-size: 26px; margin-bottom: var(--space-2); }
.panel .lede { color: var(--muted); margin-bottom: var(--space-5); }

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
}
"""

# La SPEC passe par le coloriseur ; les lignes de résultat gardent leurs
# flèches, qui ne sont pas du langage.
TERMINAL = coloriser("""app CarnetAtelier

entity Fiche
    titre: String
    statut: String

actor Auteur selfRegister

relation Auteur hasMany Fiche

rule Fiche.statut oneOf "brouillon", "publiee"
rule Fiche.Read publicWhen statut "publiee"
rule Fiche.Update ownedBy Auteur

workflow Ecrire for Auteur
    Create Fiche
    Read Fiche
    Update Fiche""") + """

<span class="s-cm"># résultat déterministe</span>
<span class="arrow">✓</span> API FastAPI + comptes
<span class="arrow">✓</span> Schéma SQL et index
<span class="arrow">✓</span> Contrôle d'accès par enregistrement
<span class="arrow">✓</span> Contrat frontend"""

BODY = f"""
<section class="shell console-head" data-reveal>
<div><h1>Console de compilation</h1>
<p>Écrivez ou importez une spécification, vérifiez ses règles puis téléchargez
un backend autonome et son contrat frontend.</p></div>
<span class="console-badge">{icon('shield')} Compilation locale et vérifiable</span>
</section>

<section id="studio" class="shell" style="padding-bottom:var(--space-8)" data-reveal>
<div class="studio">
<aside class="rail" aria-label="Étapes du parcours">
<p class="rail-title">Parcours</p>
<button class="active" data-panel="spec" type="button">{icon('code')} Spécification</button>
<button data-panel="review" type="button">{icon('check')} Vérification</button>
<button data-panel="contract" type="button">{icon('shield')} Contrat</button>
<button data-panel="delivery" type="button">{icon('package')} Livraison</button>
</aside>
<div class="workspace">

<section class="panel active" id="panel-spec">
<h2>Décrivez l'application</h2>
<p class="lede">Quatre exemples réels, du plus simple au plus complet. Chacun
compile — ce sont des spécifications entières, pas des extraits.</p>
<div class="gallery" id="gallery" role="group" aria-label="Exemples de spécification"></div>
<div class="field-head">
<label for="spec-input">Spécification monl</label>
<small id="char-count">0 caractère</small>
</div>
<textarea id="spec-input" spellcheck="false" aria-describedby="spec-help"></textarea>
<p id="spec-help" class="hint">Fichier <code>.ml</code>, 256 ko au plus.
<a href="/guide#dsl">Référence de la syntaxe</a></p>
<div class="toolbar">
<div class="toolbar-group">
<label class="secondary file-label">{icon('upload')} Importer un .ml<input id="file-input" type="file" accept=".ml,.yaml,text/plain"></label>
<button class="ghost" id="reset-btn" type="button">Réinitialiser</button>
</div>
<div class="toolbar-group">
<span class="hint"><kbd>Ctrl</kbd> + <kbd>Entrée</kbd></span>
<button class="primary" id="validate-btn" type="button">{icon('check')}
<span class="btn-label">Vérifier la spec</span><i class="spinner hidden"></i></button>
</div>
</div>
<div class="feedback" id="validation-feedback" role="status" aria-live="polite"></div>
</section>

<section class="panel" id="panel-review">
<h2>Vérification métier</h2>
<p class="lede">Ce résumé vient du vrai parseur monl, pas d'une interprétation parallèle.</p>
<div id="review-content" class="empty">Validez d'abord une spécification.</div>
<div class="toolbar"><span></span>
<button class="primary" id="compile-btn" type="button">{icon('terminal')}
<span class="btn-label">Compiler le backend</span><i class="spinner hidden"></i></button></div>
<div class="feedback" id="compile-feedback" role="status" aria-live="polite"></div>
</section>

<section class="panel" id="panel-contract">
<h2>Backend et contrat</h2>
<p class="lede">Routes, entités et droits : de quoi construire n'importe quelle interface.</p>
<div id="contract-content" class="empty">Aucune compilation disponible.</div>
</section>

<section class="panel" id="panel-delivery">
<h2>Livraison reproductible</h2>
<p class="lede">Le backend, le schéma SQL, le contrat et les instructions sont
réunis dans une archive. Le secret JWT n'y est pas : il naît au premier démarrage.</p>
<div id="delivery-content" class="empty">Compilez un backend pour obtenir son archive.</div>
<div class="builder-card" id="builder-card">
<h3>Essayer l'API</h3>
<p>monl démarre le backend compilé et vous donne son adresse locale : la
documentation interactive et toutes les routes du contrat répondent pour de
vrai. L'interface, elle, se construit chez vous — avec l'archive, le contrat
et votre propre fournisseur.</p>
<div id="builder-content" class="empty">Compilez d'abord un projet pour démarrer son API.</div>
</div>
<h3 style="margin-top:var(--space-6)">Vos compilations</h3>
<p class="hint">Conservées dans votre compte et accessibles uniquement par vous.</p>
<ul class="history" id="history"></ul>
</section>

</div></div>
</section>
"""

