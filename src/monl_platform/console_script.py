"""Browser behavior for the compilation console."""

from __future__ import annotations

SCRIPT = """
<script>
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let validee = false, projet = null, exemples = [];

// Same completion as monl.dialogue_engine.adresse_de_lien on the server.
// An address that is not understood is refused; the browser never
// guesses.
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
  $('#char-count').textContent = n.toLocaleString('en-GB') + ' character' + (n === 1 ? '' : 's');
  validee = false;
}
function panneau(nom) {
  $$('.rail button').forEach(b => {
    const actif = b.dataset.panel === nom;
    b.classList.toggle('active', actif);
    b.setAttribute('aria-selected', String(actif));
  });
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
  if (!reponse.ok) throw new Error(data.detail || 'The request failed.');
  return data;
}

/* ----- guided dialogue: the server stays the only engine ----- */
let dialogueAnswers = [];
function rendreDialogue(messages) {
  const journal = $('#dialogue-log');
  journal.replaceChildren();
  (messages || []).forEach(ligne => {
    const bloc = document.createElement('pre');
    bloc.textContent = ligne;
    journal.appendChild(bloc);
  });
}
// POINT 171: the engine had always computed the list of choices and THREW IT
// AWAY; the console received only the TERMINAL text and stuck it in a <pre>,
// which gave eleven templates in a mush of brackets. Each option carries its
// VALUE from the server — "none" is answered with 0 and not by its rank, and
// that rule must not be rewritten here (point 146).
function rendreChoix(boite, data) {
  boite.replaceChildren();
  const options = Array.isArray(data.options) ? data.options : null;
  if (data.kind !== "choice" || !options || !options.length) {
    boite.classList.add("hidden");
    return false;
  }
  const aides = data.hints || {};
  options.forEach(option => {
    const bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "dialogue-choice";
    const rang = document.createElement("span");
    rang.className = "dialogue-choice-num";
    rang.textContent = option.value;
    const titre = document.createElement("span");
    titre.className = "dialogue-choice-label";
    titre.textContent = option.label;
    bouton.append(rang, titre);
    const aide = aides[option.label];
    if (aide) {
      const note = document.createElement("span");
      note.className = "dialogue-choice-hint";
      note.textContent = aide;
      bouton.append(note);
    }
    bouton.addEventListener("click", () => rejouerDialogue(option.value));
    boite.append(bouton);
  });
  boite.classList.remove("hidden");
  return true;
}
function afficherDialogue(data) {
  rendreDialogue(data.messages);
  const question = $('#dialogue-question');
  const formulaire = $('#dialogue-form');
  const depart = $('#dialogue-start');
  const termine = $('#dialogue-complete');
  const boite = $('#dialogue-choices');
  if (data.complete) {
    question.classList.add('hidden');
    boite.replaceChildren();
    boite.classList.add('hidden');
    formulaire.classList.add('hidden');
    depart.classList.add('hidden');
    termine.classList.remove('hidden');
    $('#dialogue-status').textContent = 'Dialogue finished: the spec is ready to check.';
    $('#spec-input').value = data.spec || '';
    compter();
    return;
  }
  const enChoix = rendreChoix(boite, data);
  // With buttons, the <pre> keeps only the TITLE: repeating the terminal menu
  // below would make people read the same thing twice. With buttons, the <pre>
  // keeps only the TITLE, sent AS IS by the server: splitting it again here
  // would require a line break inside a JS string, and this Python template
  // would turn it into a real newline — the whole page would stop running
  // (point 163, measured while writing it).
  question.textContent = enChoix
    ? (data.title || data.question || '')
    : (data.question || '');
  question.classList.remove('hidden');
  formulaire.classList.remove('hidden');
  depart.classList.add('hidden');
  termine.classList.add('hidden');
  $('#dialogue-status').textContent = data.accepted === false
    ? 'Answer refused by the engine: see the message above.'
    : 'Next question.';
  $('#dialogue-answer').value = '';
  $('#dialogue-answer').focus();
}
async function rejouerDialogue(reponse) {
  const bouton = $('#dialogue-submit');
  if (bouton) occupe(bouton, true);
  try {
    const corps = { answers: dialogueAnswers };
    if (reponse !== undefined) corps.answer = reponse;
    const data = await api('/api/dialogue', corps);
    // The AUTHORITATIVE list comes from the server: an answer it refused does
    // not enter it. So the browser never decides what counts as a valid answer
    // — it adopts what the engine kept.
    dialogueAnswers = data.answers || dialogueAnswers;
    afficherDialogue(data);
  } catch (erreur) {
    $('#dialogue-status').textContent = 'Answer refused: ' + erreur.message +
      ' You can start the dialogue over.';
    if (!dialogueAnswers.length) $('#dialogue-start').classList.remove('hidden');
  } finally { if (bouton) occupe(bouton, false); }
}
function recommencerDialogue() {
  dialogueAnswers = [];
  rendreDialogue([]);
  $('#dialogue-status').textContent = 'Start whenever you are ready.';
  $('#dialogue-question').classList.add('hidden');
  $('#dialogue-form').classList.add('hidden');
  $('#dialogue-complete').classList.add('hidden');
  $('#dialogue-start').classList.remove('hidden');
}
function verifierDialogue() {
  panneau('spec');
  valider();
}

/* ----- example catalog, served by the API ----- */
async function chargerCatalogue() {
  try {
    const data = await (await fetch('/api/examples')).json();
    exemples = data.examples || [];
  } catch (e) { exemples = []; }
  const galerie = $('#gallery');
  if (!exemples.length) { galerie.remove(); return; }
  // The DSL keywords (`public`, `seed`, `derivedFrom`…) are NOT on these cards:
  // they overflowed the third one and broke mid-word, and they only help
  // someone who already knows the language — not someone picking an example.
  // They stay on the home page, where they are the subject.
  galerie.innerHTML = exemples.map(e =>
    '<button class="example" type="button" data-id="' + echapper(e.id) + '" aria-pressed="false">' +
    '<b>' + echapper(e.name) + '</b><span>' + echapper(e.summary) +
    '</span></button>').join('');
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

/* ----- the account's persistent history ----- */
function retenir() { rendreHistorique(); }
async function rendreHistorique() {
  const el = $('#history');
  let liste = [];
  try { liste = (await (await fetch('/api/projects')).json()).projects || []; } catch (e) { /* network */ }
  if (!liste.length) {
    el.innerHTML = '<li class="muted">No compilations yet.</li>';
    return;
  }
  el.innerHTML = liste.map(x =>
    '<li><span><b>' + echapper(x.name) + '</b> <span class="when">' +
    echapper(new Date(x.created_at * 1000).toLocaleString('en-GB')) + '</span></span>' +
    '<a class="secondary" href="/api/projects/' + encodeURIComponent(x.project_id) +
    '/download">Download</a></li>').join('');
}

/* ----- rendus ----- */
function rendreVerification(s) {
  $('#review-content').className = '';
  $('#review-content').innerHTML =
    '<div class="metric-grid">' +
    '<div class="metric"><b>' + s.entity_count + '</b><span>entities</span></div>' +
    '<div class="metric"><b>' + s.actor_count + '</b><span>actors</span></div>' +
    '<div class="metric"><b>✓</b><span>syntax</span></div>' +
    '<div class="metric"><b>✓</b><span>static audit</span></div></div>' +
    '<div class="entity-grid">' +
    '<div class="entity"><h3>Entities</h3><div class="chips">' +
    s.entities.map(e => '<i class="chip">' + echapper(e) + '</i>').join('') + '</div></div>' +
    '<div class="entity"><h3>Actors</h3><div class="chips">' +
    s.actors.map(a => '<i class="chip">' + echapper(a) + '</i>').join('') + '</div></div></div>';
}
function rendreContrat(s) {
  const c = s.counts;
  $('#contract-content').className = '';
  $('#contract-content').innerHTML =
    '<div class="metric-grid">' +
    '<div class="metric"><b>' + c.entities + '</b><span>entities</span></div>' +
    '<div class="metric"><b>' + c.routes + '</b><span>routes API</span></div>' +
    '<div class="metric"><b>' + c.public_routes + '</b><span>public</span></div>' +
    '<div class="metric"><b>' + c.actors + '</b><span>actors</span></div>' +
    '<div class="metric"><b>' + c.business_rules + '</b><span>rules</span></div></div>' +
    '<div class="routes">' + s.routes.map(r =>
      '<div class="route"><span class="method">' + echapper(r.method) + '</span>' +
      '<span class="path">' + echapper(r.path) + '</span>' +
      '<span class="lock">' + (r.auth_required === false ? 'public' : 'authenticated') +
      '</span></div>').join('') + '</div>';
}
function rendreLivraison(p) {
  $('#delivery-content').className = '';
  $('#delivery-content').innerHTML =
    '<div class="download-card"><div><h3>' + echapper(p.summary.app) + '</h3>' +
    '<p>' + p.files.length + ' files · FastAPI backend · contract v' +
    echapper(p.summary.contract_version) + '</p></div>' +
    '<a class="primary" href="/api/projects/' + encodeURIComponent(p.id) +
    '/download">Download the backend</a></div>' +
    '<div class="chips">' + p.files.map(f =>
      '<i class="chip">' + echapper(f) + '</i>').join('') + '</div>';
  $('#builder-content').className = '';
  $('#builder-content').innerHTML =
    '<button class="primary" id="build-btn" type="button">Start the project\\'s API</button>' +
    '<div class="builder-status" id="builder-status" role="status" aria-live="polite"></div>';
  $('#build-btn').onclick = () => demarrerAPI(p.id);
}

async function demarrerAPI(id) {
  const bouton = $('#build-btn');
  if (!bouton) return;
  bouton.disabled = true;
  const statut = $('#builder-status');
  try {
    statut.textContent = 'Compiling the project…';
    const compile = await fetch('/api/projects/' + encodeURIComponent(id) + '/compiler',
      { method: 'POST' });
    const compileData = await compile.json();
    if (!compile.ok) throw new Error(compileData.detail || 'The compilation failed.');
    statut.textContent = 'Starting the server…';
    const reponse = await fetch('/api/projects/' + encodeURIComponent(id) + '/start',
      { method: 'POST' });
    const data = await reponse.json();
    if (!reponse.ok) throw new Error(data.detail || 'The start failed.');
    statut.innerHTML = 'API running at <b>http://127.0.0.1:' + data.port +
      '</b> — ' + compileData.routes + ' routes. ' +
      '<a href="http://127.0.0.1:' + data.port + '/docs" target="_blank" rel="noopener">' +
      'Open the interactive documentation</a>';
  } catch (erreur) {
    statut.textContent = erreur.message;
  } finally { bouton.disabled = false; }
}

/* ----- actions ----- */
async function valider() {
  const bouton = $('#validate-btn');
  occupe(bouton, true);
  try {
    const data = await api('/api/validate', { spec: $('#spec-input').value });
    if (!data.valid) {
      message('#validation-feedback', 'error', 'This specification is refused.',
        data.errors.join('\\n\\n'));
      return;
    }
    validee = true;
    rendreVerification(data.summary);
    message('#validation-feedback', 'ok', 'Valid specification: ' +
      data.summary.entity_count + ' entity(ies), ' + data.summary.actor_count + ' actor(s).');
    panneau('review');
  } catch (erreur) {
    message('#validation-feedback', 'error', 'Unable to check.', erreur.message);
  } finally { occupe(bouton, false); }
}
async function compiler() {
  if (!validee) {
    panneau('spec');
    message('#validation-feedback', 'error', 'The spec has changed: check it before compiling.');
    return;
  }
  const bouton = $('#compile-btn');
  occupe(bouton, true);
  try {
    projet = await api('/api/compile', { spec: $('#spec-input').value });
    rendreContrat(projet.summary);
    rendreLivraison(projet);
    retenir(projet);
    message('#compile-feedback', 'ok', 'Backend compiled and contract checked.');
    panneau('contract');
  } catch (erreur) {
    message('#compile-feedback', 'error', 'The compilation failed.', erreur.message);
  } finally { occupe(bouton, false); }
}

/* ----- wiring ----- */
$('#spec-input').addEventListener('input', compter);
$$('.rail button').forEach((b, index, boutons) => {
  b.onclick = () => panneau(b.dataset.panel);
  b.onkeydown = event => {
    if (!['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let suivant = index;
    if (event.key === 'Home') suivant = 0;
    else if (event.key === 'End') suivant = boutons.length - 1;
    else suivant = (index + (event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1) + boutons.length) % boutons.length;
    panneau(boutons[suivant].dataset.panel);
    boutons[suivant].focus();
  };
});
$('#delivery-next').onclick = () => panneau('delivery');
$('#contract-back').onclick = () => panneau('contract');
$('#validate-btn').onclick = valider;
$('#compile-btn').onclick = compiler;
$('#dialogue-start button').onclick = () => rejouerDialogue();
$('#dialogue-form').onsubmit = e => {
  e.preventDefault();
  rejouerDialogue($('#dialogue-answer').value);
};
$('#dialogue-reset').onclick = recommencerDialogue;
$('#dialogue-validate').onclick = verifierDialogue;
$('#reset-btn').onclick = () => {
  if (exemples.length) charger(exemples[0].id);
  panneau('spec');
};
$('#file-input').onchange = async e => {
  const fichier = e.target.files[0];
  if (!fichier) return;
  if (fichier.size > 256000) {
    message('#validation-feedback', 'error', 'This file exceeds 256 KB.');
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
  bouton.textContent = 'Copy';
  bouton.addEventListener('click', () => {
    const cible = bloc.querySelector('code') || bloc;
    navigator.clipboard.writeText(cible.innerText).then(() => {
      bouton.textContent = 'Copied';
      setTimeout(() => { bouton.textContent = 'Copy'; }, 1800);
    }, () => { bouton.textContent = 'Failed'; });
  });
  bloc.appendChild(bouton);
});
rendreHistorique();
chargerCatalogue();
</script>
"""
