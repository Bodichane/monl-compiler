"""Browser behavior for the compilation console."""

from __future__ import annotations

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

/* ----- dialogue guidé : le serveur reste l'unique moteur ----- */
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
// POINT 171 : le moteur calculait la liste des choix depuis toujours et la
// JETAIT ; la console ne recevait que le texte de TERMINAL et le collait dans
// un <pre>, ce qui donnait onze modèles en une bouillie de crochets. Chaque
// option porte sa VALEUR depuis le serveur — « aucun » se répond par 0 et non
// par son rang, et cette règle ne doit pas être réécrite ici (point 146).
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
    $('#dialogue-status').textContent = 'Dialogue terminé : la spec est prête à vérifier.';
    $('#spec-input').value = data.spec || '';
    compter();
    return;
  }
  const enChoix = rendreChoix(boite, data);
  // Avec des boutons, le <pre> ne garde que l'INTITULÉ : répéter le menu de
  // terminal en dessous ferait lire deux fois la même chose.
  // Avec des boutons, le <pre> ne garde que l'INTITULÉ, envoyé TEL QUEL par
  // le serveur : le redécouper ici demanderait un retour à la ligne dans une
  // chaîne JS, et ce gabarit Python le transformerait en vrai saut de ligne —
  // la page entière cesserait de s'exécuter (point 163, mesuré en l'écrivant).
  question.textContent = enChoix
    ? (data.title || data.question || '')
    : (data.question || '');
  question.classList.remove('hidden');
  formulaire.classList.remove('hidden');
  depart.classList.add('hidden');
  termine.classList.add('hidden');
  $('#dialogue-status').textContent = data.accepted === false
    ? 'Réponse refusée par le moteur : voyez le message ci-dessus.'
    : 'Question suivante.';
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
    // La liste FAISANT AUTORITÉ vient du serveur : une réponse qu'il a refusée
    // n'y entre pas. Le navigateur ne décide donc jamais ce qui compte comme
    // une réponse valide — il adopte ce que le moteur a retenu.
    dialogueAnswers = data.answers || dialogueAnswers;
    afficherDialogue(data);
  } catch (erreur) {
    $('#dialogue-status').textContent = 'Réponse refusée : ' + erreur.message +
      ' Vous pouvez recommencer le dialogue.';
    if (!dialogueAnswers.length) $('#dialogue-start').classList.remove('hidden');
  } finally { if (bouton) occupe(bouton, false); }
}
function recommencerDialogue() {
  dialogueAnswers = [];
  rendreDialogue([]);
  $('#dialogue-status').textContent = 'Commencez quand vous êtes prêt.';
  $('#dialogue-question').classList.add('hidden');
  $('#dialogue-form').classList.add('hidden');
  $('#dialogue-complete').classList.add('hidden');
  $('#dialogue-start').classList.remove('hidden');
}
function verifierDialogue() {
  panneau('spec');
  valider();
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
    '<button class="primary" id="build-btn" type="button">Démarrer l\\'API</button>' +
    '<div class="builder-status" id="builder-status" role="status" aria-live="polite"></div>';
  $('#build-btn').onclick = () => demarrerAPI(p.id);
}

async function demarrerAPI(id) {
  const bouton = $('#build-btn');
  if (!bouton) return;
  bouton.disabled = true;
  const statut = $('#builder-status');
  try {
    statut.textContent = 'Compilation du projet…';
    const compile = await fetch('/api/projects/' + encodeURIComponent(id) + '/compiler',
      { method: 'POST' });
    const compileData = await compile.json();
    if (!compile.ok) throw new Error(compileData.detail || 'La compilation a échoué.');
    statut.textContent = 'Démarrage du serveur…';
    const reponse = await fetch('/api/projects/' + encodeURIComponent(id) + '/start',
      { method: 'POST' });
    const data = await reponse.json();
    if (!reponse.ok) throw new Error(data.detail || 'Le démarrage a échoué.');
    statut.innerHTML = 'API en marche sur <b>http://127.0.0.1:' + data.port +
      '</b> — ' + compileData.routes + ' routes. ' +
      '<a href="http://127.0.0.1:' + data.port + '/docs" target="_blank" rel="noopener">' +
      'Ouvrir la documentation interactive</a>';
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
