"""La console de compilation, séparée de la vitrine publique.

Le parcours en quatre panneaux — écrire, vérifier, lire le contrat, livrer —
vient de la première version et n'avait pas de raison de changer : il suit
l'ordre réel des opérations, et chaque étape refuse d'avancer tant que la
précédente n'a pas répondu.

Ce qui manquait, et qui est ajouté ici.

**Les exemples.** Le studio ouvrait sur une spec en dur, écrite dans le
JavaScript de la page. Quatre spécifications réelles vivent désormais dans
`examples.py`, chargées par l'API — donc les mêmes pour la console, pour un
agent MCP et pour `curl`, et compilées par les tests.

**L'historique.** Les compilations sont rattachées au compte côté serveur :
un rechargement ou un autre navigateur retrouve les projets autorisés, sans
jamais exposer ceux d'un autre compte.

**Le clavier et le presse-papier.** `Ctrl+Entrée` valide, et tout bloc de
code se copie. Une console qu'on ne peut piloter qu'à la souris fait
retaper à la main une configuration MCP.
"""

from __future__ import annotations

from .theme import icon, page

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
.kw { color: var(--code-accent); } .cm { color: var(--code-muted); } .arrow { color: var(--code-accent); }

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

TERMINAL = """<span class="kw">app</span> CarnetAtelier

<span class="kw">entity</span> Fiche
    titre: String
    statut: String

<span class="kw">actor</span> Auteur selfRegister

<span class="kw">relation</span> Auteur hasMany Fiche

<span class="kw">rule</span> Fiche.statut oneOf "brouillon", "publiee"
<span class="kw">rule</span> Fiche.Read publicWhen statut "publiee"
<span class="kw">rule</span> Fiche.Update ownedBy Auteur

<span class="kw">workflow</span> Ecrire <span class="kw">for</span> Auteur
    Create Fiche
    Read Fiche
    Update Fiche

<span class="cm"># résultat déterministe</span>
<span class="arrow">✓</span> API FastAPI + comptes
<span class="arrow">✓</span> Schéma SQL et index
<span class="arrow">✓</span> Contrôle d'accès par enregistrement
<span class="arrow">✓</span> Contrat frontend"""

BODY = f"""
<section class="shell console-head" data-reveal>
<div><span class="eyebrow">Espace de travail</span>
<h1>Console de compilation</h1>
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
<h3>Construction du site</h3>
<p>La compilation vérifie le backend. La construction produit ensuite le site,
son historique et son suivi de consommation. Une panne d'image reste un
<strong>Avertissement de construction</strong> : le frontend texte est conservé.</p>
<div id="builder-content" class="empty">Compilez d'abord un projet pour lancer sa construction.</div>
</div>
<h3 style="margin-top:var(--space-6)">Vos compilations</h3>
<p class="hint">Conservées dans votre compte et accessibles uniquement par vous.</p>
<ul class="history" id="history"></ul>
</section>

</div></div>
</section>
"""

SCRIPT = """
<script>
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let validee = false, projet = null, exemples = [];

// Même complétion que monl.dialogue_engine.adresse_de_lien côté serveur.
// Une adresse incomprise est refusée ; le navigateur ne devine jamais.
function adresseDeLien(saisie) {
  saisie = (saisie || '').trim();
  if (!saisie) return null;
  if (/^(https?:[/][/]|mailto:|tel:)/i.test(saisie)) return saisie;
  var compact = saisie.replace(/ /g, '');
  if (/^[+]?[0-9.-]{6,20}$/.test(compact)) return 'tel:' + compact;
  if (saisie.indexOf(' ') !== -1) return null;
  if (saisie.indexOf('@') !== -1 && saisie.split('@').pop().indexOf('.') !== -1) {
    return 'mailto:' + saisie;
  }
  var domaine = saisie.split('/')[0];
  if (domaine.indexOf('.') > 0) return 'https://' + saisie;
  return null;
}

function echapper(v) {
  return String(v ?? '').replace(/[&<>'"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}
function compter() {
  const n = [...$('#spec-input').value].length;
  $('#char-count').textContent = n.toLocaleString('fr-FR') + ' caractère' + (n > 1 ? 's' : '');
  validee = false;
}
function panneau(nom) {
  $$('.rail button').forEach(b => b.classList.toggle('active', b.dataset.panel === nom));
  $$('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + nom));
}
function occupe(bouton, actif) {
  bouton.disabled = actif;
  bouton.querySelector('.spinner').classList.toggle('hidden', !actif);
  bouton.querySelector('.btn-label').classList.toggle('hidden', actif);
}
function message(selecteur, type, texte, detail) {
  const el = $(selecteur);
  el.className = 'feedback show ' + type;
  el.innerHTML = '<b>' + echapper(texte) + '</b>' +
    (detail ? '<pre>' + echapper(detail) + '</pre>' : '');
}
async function api(chemin, corps) {
  const reponse = await fetch(chemin, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corps)
  });
  const data = await reponse.json();
  if (!reponse.ok) throw new Error(data.detail || 'La requête a échoué.');
  return data;
}

/* ----- catalogue d'exemples, servi par l'API ----- */
async function chargerCatalogue() {
  try {
    const data = await (await fetch('/api/examples')).json();
    exemples = data.examples || [];
  } catch (e) { exemples = []; }
  const galerie = $('#gallery');
  if (!exemples.length) { galerie.remove(); return; }
  galerie.innerHTML = exemples.map(e =>
    '<button class="example" type="button" data-id="' + echapper(e.id) + '" aria-pressed="false">' +
    '<b>' + echapper(e.name) + '</b><span>' + echapper(e.summary) + '</span>' +
    '<span class="chips">' + (e.teaches || []).map(t =>
      '<i class="chip">' + echapper(t) + '</i>').join('') + '</span></button>').join('');
  $$('.example').forEach(bouton => bouton.onclick = () => charger(bouton.dataset.id));
  const demande = new URLSearchParams(window.location.search).get('example');
  charger(exemples.some(e => e.id === demande) ? demande : exemples[0].id);
}
async function charger(id) {
  const reponse = await fetch('/api/examples/' + encodeURIComponent(id));
  if (!reponse.ok) return;
  $('#spec-input').value = (await reponse.json()).spec;
  compter();
  $$('.example').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.id === id)));
  $('#validation-feedback').className = 'feedback';
}

/* ----- historique persistant du compte ----- */
function retenir() { rendreHistorique(); }
async function rendreHistorique() {
  const el = $('#history');
  let liste = [];
  try { liste = (await (await fetch('/api/projects')).json()).projects || []; } catch (e) { /* réseau */ }
  if (!liste.length) {
    el.innerHTML = '<li class="muted">Aucune compilation pour le moment.</li>';
    return;
  }
  el.innerHTML = liste.map(x =>
    '<li><span><b>' + echapper(x.name) + '</b> <span class="when">' +
    echapper(new Date(x.created_at * 1000).toLocaleString('fr-FR')) + '</span></span>' +
    '<a class="secondary" href="/api/projects/' + encodeURIComponent(x.project_id) +
    '/download">Télécharger</a></li>').join('');
}

/* ----- rendus ----- */
function rendreVerification(s) {
  $('#review-content').className = '';
  $('#review-content').innerHTML =
    '<div class="metric-grid">' +
    '<div class="metric"><b>' + s.entity_count + '</b><span>entités</span></div>' +
    '<div class="metric"><b>' + s.actor_count + '</b><span>acteurs</span></div>' +
    '<div class="metric"><b>✓</b><span>syntaxe</span></div>' +
    '<div class="metric"><b>✓</b><span>audit statique</span></div></div>' +
    '<div class="entity-grid">' +
    '<div class="entity"><h3>Entités</h3><div class="chips">' +
    s.entities.map(e => '<i class="chip">' + echapper(e) + '</i>').join('') + '</div></div>' +
    '<div class="entity"><h3>Acteurs</h3><div class="chips">' +
    s.actors.map(a => '<i class="chip">' + echapper(a) + '</i>').join('') + '</div></div></div>';
}
function rendreContrat(s) {
  const c = s.counts;
  $('#contract-content').className = '';
  $('#contract-content').innerHTML =
    '<div class="metric-grid">' +
    '<div class="metric"><b>' + c.entities + '</b><span>entités</span></div>' +
    '<div class="metric"><b>' + c.routes + '</b><span>routes API</span></div>' +
    '<div class="metric"><b>' + c.public_routes + '</b><span>publiques</span></div>' +
    '<div class="metric"><b>' + c.actors + '</b><span>acteurs</span></div>' +
    '<div class="metric"><b>' + c.business_rules + '</b><span>règles</span></div></div>' +
    '<div class="routes">' + s.routes.map(r =>
      '<div class="route"><span class="method">' + echapper(r.method) + '</span>' +
      '<span class="path">' + echapper(r.path) + '</span>' +
      '<span class="lock">' + (r.auth_required === false ? 'public' : 'authentifié') +
      '</span></div>').join('') + '</div>';
}
function rendreLivraison(p) {
  $('#delivery-content').className = '';
  $('#delivery-content').innerHTML =
    '<div class="download-card"><div><h3>' + echapper(p.summary.app) + '</h3>' +
    '<p>' + p.files.length + ' fichiers · backend FastAPI · contrat v' +
    echapper(p.summary.contract_version) + '</p></div>' +
    '<a class="primary" href="/api/projects/' + encodeURIComponent(p.id) +
    '/download">Télécharger le backend</a></div>' +
    '<div class="chips">' + p.files.map(f =>
      '<i class="chip">' + echapper(f) + '</i>').join('') + '</div>';
  $('#builder-content').className = '';
  $('#builder-content').innerHTML =
    '<button class="primary" id="build-btn" type="button">Créer et lancer la construction</button>' +
    '<div class="builder-status" id="builder-status" role="status" aria-live="polite"></div>';
  $('#build-btn').onclick = () => lancerConstruction(p.id);
}

async function lancerConstruction(id) {
  const bouton = $('#build-btn');
  if (!bouton) return;
  bouton.disabled = true;
  try {
    const reponse = await fetch('/api/projects/' + encodeURIComponent(id) + '/builds', { method: 'POST' });
    const data = await reponse.json();
    if (!reponse.ok) throw new Error(data.detail || 'La construction a échoué.');
    afficherConstruction(data.build);
    await suivreConstruction(id, data.build.id);
  } catch (erreur) {
    $('#builder-status').textContent = erreur.message;
  } finally { bouton.disabled = false; }
}
function afficherConstruction(build) {
  const statut = $('#builder-status');
  if (!statut) return;
  const texte = build.warning_message || build.error_message;
  statut.textContent = (build.state || 'en_attente') +
    (texte ? '\n' + texte : '');
}
async function suivreConstruction(id, buildId) {
  for (let essai = 0; essai < 120; essai += 1) {
    const reponse = await fetch('/api/projects/' + encodeURIComponent(id) + '/builds/' + buildId);
    if (!reponse.ok) return;
    const data = await reponse.json();
    afficherConstruction(data.build);
    if (!['en_attente', 'en_cours'].includes(data.build.state)) {
      retenir();
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}

/* ----- actions ----- */
async function valider() {
  const bouton = $('#validate-btn');
  occupe(bouton, true);
  try {
    const data = await api('/api/validate', { spec: $('#spec-input').value });
    if (!data.valid) {
      message('#validation-feedback', 'error', 'Cette spécification est refusée.',
        data.errors.join('\\n\\n'));
      return;
    }
    validee = true;
    rendreVerification(data.summary);
    message('#validation-feedback', 'ok', 'Spécification valide : ' +
      data.summary.entity_count + ' entité(s), ' + data.summary.actor_count + ' acteur(s).');
    panneau('review');
  } catch (erreur) {
    message('#validation-feedback', 'error', 'Vérification impossible.', erreur.message);
  } finally { occupe(bouton, false); }
}
async function compiler() {
  if (!validee) {
    panneau('spec');
    message('#validation-feedback', 'error', 'La spec a changé : vérifiez-la avant de compiler.');
    return;
  }
  const bouton = $('#compile-btn');
  occupe(bouton, true);
  try {
    projet = await api('/api/compile', { spec: $('#spec-input').value });
    rendreContrat(projet.summary);
    rendreLivraison(projet);
    retenir(projet);
    message('#compile-feedback', 'ok', 'Backend compilé et contrat vérifié.');
    panneau('contract');
  } catch (erreur) {
    message('#compile-feedback', 'error', 'La compilation a échoué.', erreur.message);
  } finally { occupe(bouton, false); }
}

/* ----- câblage ----- */
$('#spec-input').addEventListener('input', compter);
$$('.rail button').forEach(b => b.onclick = () => panneau(b.dataset.panel));
$('#validate-btn').onclick = valider;
$('#compile-btn').onclick = compiler;
$('#reset-btn').onclick = () => {
  if (exemples.length) charger(exemples[0].id);
  panneau('spec');
};
$('#file-input').onchange = async e => {
  const fichier = e.target.files[0];
  if (!fichier) return;
  if (fichier.size > 256000) {
    message('#validation-feedback', 'error', 'Ce fichier dépasse 256 ko.');
    return;
  }
  $('#spec-input').value = await fichier.text();
  compter();
  $$('.example').forEach(b => b.setAttribute('aria-pressed', 'false'));
};
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); valider(); }
});
document.querySelectorAll('.codeblock').forEach(bloc => {
  const bouton = document.createElement('button');
  bouton.type = 'button';
  bouton.className = 'copy';
  bouton.textContent = 'Copier';
  bouton.addEventListener('click', () => {
    const cible = bloc.querySelector('code') || bloc;
    navigator.clipboard.writeText(cible.innerText).then(() => {
      bouton.textContent = 'Copié';
      setTimeout(() => { bouton.textContent = 'Copier'; }, 1800);
    }, () => { bouton.textContent = 'Échec'; });
  });
  bloc.appendChild(bouton);
});
rendreHistorique();
chargerCatalogue();
</script>
"""

CONSOLE_HTML = page(
    title="monl compiler — le métier est compilé",
    description="Décrivez vos règles métier. Monl compile un backend autonome, "
                "son schéma SQL et son contrat frontend.",
    body=BODY,
    active="console",
    scripts=SCRIPT,
    extra_css=EXTRA_CSS,
)
