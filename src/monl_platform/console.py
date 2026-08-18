"""Console de la plateforme monl : un DIALOGUE, pas un formulaire.

Le grand formulaire d'origine posait toutes ses questions d'un coup et
lançait une construction facturée au bas de la page. Il est remplacé par le
dialogue guidé de la ligne de commande, porté au navigateur : une question à
la fois, les précédentes restant lisibles et modifiables, et le lancement
comme une étape à part entière.

Le suivi de construction s'appuie sur les étapes RÉELLEMENT journalisées
(``progress.read_stages``) : une progression inventée ferait croire que le
serveur sait où il en est.

Registre identique à la page de présentation — un terminal — et même
garantie : aucune ressource distante, tout mouvement coupé sous
``prefers-reduced-motion``.
"""

from fastapi.responses import HTMLResponse

CONSOLE_HTML = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>monl — console</title>
<style>
/* ════════════════════════════════════════════════════════════════════
   Console monl. Même registre que la page de présentation : un terminal.
   Une console qui ne ressemble pas à son produit est un raccord raté, et
   c'était le défaut d'origine.

   Le formulaire unique a été remplacé par un DIALOGUE : une question à la
   fois, la précédente restant visible comme une transcription. C'est la
   forme du dialogue guidé de la ligne de commande, portée au navigateur.

   Aucune ressource distante. Tout ce qui bouge s'arrête sous
   prefers-reduced-motion.
   ════════════════════════════════════════════════════════════════════ */
:root {
  /* La console suit l'identité de la page produit : fond papier, encre
     chaude, une seule couleur d'accent. Elle garde en revanche la CHASSE
     FIXE partout — c'est un outil de ligne de commande porté au navigateur,
     et le prétendre autrement serait un mensonge de plus.

     Chaque paire a été mesurée : la plus basse est --fg-3 sur --bg-1, à
     4,56:1. Aucune n'est sous 4,5. L'argile #b8542f sert AUTANT de texte sur
     blanc (4,83) que de fond sous du blanc (4,83) — c'est ce qui permet de
     n'en avoir qu'une, là où la page produit en a deux. */
  --bg:      #ffffff;
  --bg-1:    #faf9f7;
  --bg-2:    #f2efec;
  --bg-3:    #e7e3df;
  --fg:      #1c1917;  /* 17,49:1 */
  --fg-2:    #57534e;  /*  7,63:1 */
  --fg-3:    #78716c;  /*  4,80:1 */
  --line:    #e7e3df;
  --line-2:  #d6d0ca;

  --clay:    #b8542f;  /* 4,83:1 dans les deux sens */
  --clay-hi: #9c4526;
  --clay-ink:#ffffff;
  --clay-dim:#fdf5f1;
  --green:   #15803d;
  --green-dim:#f0fdf4;
  --blue:    #1d4ed8;
  --amber:   #a16207;
  --amber-dim:#fffbeb;
  --red:     #b91c1c;
  --red-dim: #fef2f2;

  --s1: .25rem; --s2: .5rem; --s3: .75rem; --s4: 1rem;
  --s5: 1.5rem; --s6: 2.25rem; --s7: 3.5rem;
  --r1: .3rem; --r2: .55rem; --r3: .9rem;

  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
          "DejaVu Sans Mono", "Liberation Mono", monospace;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; min-width: 320px;
  background: var(--bg); color: var(--fg);
  font: 400 14.5px/1.6 var(--mono);
  -webkit-font-smoothing: antialiased;
}
button, input, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
:where(button, input, textarea, a):focus-visible {
  outline: 2px solid var(--clay); outline-offset: 2px; border-radius: var(--r1);
}
h1, h2, h3, p { margin: 0; }
[hidden] { display: none !important; }
a { color: var(--clay); text-decoration: none; }
a:hover { color: var(--clay-hi); }

.skip-link {
  position: absolute; left: var(--s4); top: -4rem; z-index: 30;
  padding: var(--s3) var(--s4); border-radius: var(--r1);
  background: var(--clay); color: var(--clay-ink); font-weight: 700;
}
.skip-link:focus { top: var(--s4); }

/* ────────────────────────────────────────────────────────────── barre ── */
.bar {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--s4);
  padding: var(--s3) clamp(var(--s4), 4vw, var(--s6));
  /* Une couleur écrite EN DUR échappe au thème : la barre est restée
     sombre pendant que tout le reste passait au papier, et son texte,
     lui, avait suivi la variable — donc sombre sur sombre. Depuis, la
     barre voile le fond au lieu de le remplacer. */
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(10px);
}
.brand { display: inline-flex; align-items: center; gap: var(--s2); color: var(--fg); font-weight: 700; }
.brand-mark {
  display: grid; place-items: center; width: 1.55rem; height: 1.55rem;
  border-radius: var(--r1); background: var(--clay); color: var(--clay-ink);
  font-size: .78rem; font-weight: 700;
}
.bar-right { display: flex; align-items: center; gap: var(--s3); }
.account-label { color: var(--fg-3); font-size: .82rem; }

.chip {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .22rem .6rem;
  border: 1px solid var(--line-2); border-radius: 99px;
  background: var(--bg-2); color: var(--fg-2);
  font-size: .74rem; white-space: nowrap;
}
.chip b { color: var(--fg); font-variant-numeric: tabular-nums; }

/* ──────────────────────────────────────────────────────────── boutons ── */
.button {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .5rem .9rem;
  border: 1px solid var(--clay); border-radius: var(--r1);
  background: var(--clay); color: var(--clay-ink);
  font-weight: 600; font-size: .86rem;
  transition: background-color .15s ease, border-color .15s ease, color .15s ease;
}
.button:hover { background: var(--clay-hi); border-color: var(--clay-hi); }
.button.secondary { background: transparent; color: var(--fg); border-color: var(--line-2); }
.button.secondary:hover { background: var(--bg-2); border-color: var(--fg-3); }
.button.danger { background: var(--red-dim); color: var(--red); border-color: #5a2b28; }
.button.danger:hover { background: var(--red); color: var(--clay-ink); border-color: var(--red); }
.button.small { padding: .34rem .65rem; font-size: .78rem; }
.button[disabled] { cursor: wait; opacity: .45; }

/* ──────────────────────────────────────────────────────── connexion ── */
.page { width: min(1200px, calc(100% - 2rem)); margin: 0 auto; padding: var(--s6) 0 var(--s7); }
.narrow { width: min(440px, 100%); margin: clamp(var(--s6), 9vh, var(--s7)) auto; }
.eyebrow {
  display: block; margin-bottom: var(--s2);
  color: var(--clay); font-size: .7rem; font-weight: 700; letter-spacing: .15em;
  text-transform: uppercase;
}
h1 { font-size: clamp(1.35rem, 2.6vw, 1.8rem); font-weight: 700; letter-spacing: -.02em; line-height: 1.2; }
h2 { font-size: 1.02rem; font-weight: 700; letter-spacing: -.01em; }
h3 { font-size: .92rem; font-weight: 700; }
.lede { max-width: 60ch; margin-top: var(--s3); color: var(--fg-2); font-size: .92rem; }
.help { margin: 0; color: var(--fg-3); font-size: .8rem; font-weight: 400; }

.panel {
  padding: clamp(var(--s4), 2.4vw, var(--s5));
  border: 1px solid var(--line); border-radius: var(--r3);
  background: var(--bg-1);
}
.auth-card { margin-top: var(--s5); }
.auth-switch {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--s1);
  margin-bottom: var(--s5); padding: var(--s1);
  background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--r2);
}
.tab-button {
  padding: .5rem .8rem; border: 1px solid transparent; border-radius: var(--r1);
  background: transparent; color: var(--fg-2); font-weight: 600; font-size: .86rem;
}
.tab-button[aria-selected="true"] { background: var(--bg-3); border-color: var(--line-2); color: var(--fg); }

.form-grid { display: grid; gap: var(--s4); }
label { display: grid; gap: var(--s1); font-weight: 600; }
label span { font-size: .84rem; }
input, textarea {
  width: 100%; padding: .58rem .7rem;
  border: 1px solid var(--line-2); border-radius: var(--r1);
  background: var(--bg-2); color: var(--fg);
  transition: border-color .14s ease;
}
input:hover, textarea:hover { border-color: var(--fg-3); }
input:focus, textarea:focus { border-color: var(--clay); }
input::placeholder, textarea::placeholder { color: var(--fg-3); }
textarea { min-height: 7rem; resize: vertical; }
textarea.spec { min-height: 15rem; font-size: .82rem; line-height: 1.65; }
.form-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s3); }

.notice {
  margin-top: var(--s4); padding: var(--s3) var(--s4);
  border: 1px solid var(--line-2); border-left-width: 3px; border-radius: var(--r1);
  background: var(--bg-2); font-size: .86rem;
}
.notice.error { border-color: #5a2b28; background: var(--red-dim); color: var(--red); }
#alert { margin-bottom: var(--s4); }

/* ─────────────────────────────────────────────────────────── agencement ── */
.layout {
  display: grid; grid-template-columns: minmax(210px, 260px) minmax(0, 1fr);
  gap: var(--s5); align-items: start; margin-top: var(--s5);
}
.side { position: sticky; top: 4.2rem; display: grid; gap: var(--s3); }
.side-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
.project-list { display: grid; gap: var(--s2); }
.project-item {
  display: block; width: 100%; padding: .6rem .75rem; text-align: left;
  border: 1px solid var(--line); border-left: 2px solid transparent;
  border-radius: var(--r2); background: var(--bg-1); color: var(--fg);
  transition: border-color .14s ease, background-color .14s ease;
}
.project-item:hover { border-color: var(--line-2); background: var(--bg-2); }
.project-item[aria-current="true"] { border-color: var(--line-2); border-left-color: var(--clay); background: var(--bg-2); }
.project-item strong { display: block; font-size: .88rem; font-weight: 600; }
.project-item span { display: block; color: var(--fg-3); font-size: .76rem; }
.empty, .loading { color: var(--fg-3); font-size: .84rem; }

/* ───────────────────────────────────────────────────────────── dialogue ── */
.dialog { padding: 0; overflow: hidden; }
.dialog-head {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s3);
  padding: var(--s3) var(--s5);
  border-bottom: 1px solid var(--line); background: var(--bg-2);
}
.dialog-head .t { color: var(--fg-2); font-size: .82rem; }
.pips { display: flex; gap: .3rem; }
.pips i { width: .45rem; height: .45rem; border-radius: 50%; background: var(--line-2); transition: background-color .2s ease; }
.pips i.done { background: var(--clay-dim); }
.pips i.now { background: var(--clay); }
.dialog-body { padding: var(--s5); }

.transcript { display: grid; gap: var(--s2); margin-bottom: var(--s5); }
.transcript:empty { display: none; }
.said { display: grid; grid-template-columns: 1.2rem 1fr; gap: var(--s2); font-size: .85rem; }
.said .m { color: var(--green); }
.said b { color: var(--fg-2); font-weight: 400; }
.said i { color: var(--fg); font-style: normal; }
.said button {
  justify-self: start; padding: 0; border: 0; background: none;
  color: var(--fg-3); font-size: .76rem; text-decoration: underline;
}
.said button:hover { color: var(--clay); }

.ask { display: grid; gap: var(--s3); }
.ask-q { display: grid; grid-template-columns: 1.2rem 1fr; gap: var(--s2); }
.ask-q .m { color: var(--blue); font-weight: 700; }
.ask-q h2 { font-size: 1.05rem; }
.ask-help { margin-left: 1.7rem; color: var(--fg-2); font-size: .85rem; }
.ask-field { margin-left: 1.7rem; }
.ask-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s3); margin: var(--s4) 0 0 1.7rem; }
.ask-hint { color: var(--fg-3); font-size: .76rem; }

.choices { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--s2); }
.choice {
  padding: var(--s3); text-align: left;
  border: 1px solid var(--line); border-radius: var(--r2);
  background: var(--bg-2); color: var(--fg);
  transition: border-color .14s ease, background-color .14s ease;
}
.choice:hover { border-color: var(--line-2); background: var(--bg-3); }
.choice[aria-pressed="true"] { border-color: var(--clay); background: var(--clay-dim); }
.choice b { display: block; font-size: .88rem; font-weight: 600; }
.choice span { display: block; margin-top: var(--s1); color: var(--fg-2); font-size: .78rem; line-height: 1.55; }
.choice .num { color: var(--fg-3); font-size: .72rem; }

.pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s2); }
.recap { display: grid; gap: var(--s2); }
.recap-row {
  display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: var(--s3);
  padding: var(--s3); border: 1px solid var(--line); border-radius: var(--r1);
  background: var(--bg-2); font-size: .85rem;
}
.recap-row b { color: var(--fg-3); font-weight: 400; }
.recap-row span { overflow-wrap: anywhere; }

/* ──────────────────────────────────────────────────────────── production ── */
.project-header { display: flex; align-items: start; justify-content: space-between; gap: var(--s4); margin-bottom: var(--s4); }
.project-header h2 { word-break: break-word; }
.project-meta { color: var(--fg-3); font-size: .82rem; }

.build-status {
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: .24rem .6rem; border: 1px solid transparent; border-radius: 99px;
  font-size: .76rem; font-weight: 700; white-space: nowrap;
}
.build-status.waiting, .build-status.running { background: var(--amber-dim); color: var(--amber); border-color: #5c4718; }
.build-status.success { background: var(--green-dim); color: var(--green); border-color: #2b5a3a; }
.build-status.failure { background: var(--red-dim); color: var(--red); border-color: #5a2b28; }
.build-status.none { background: var(--bg-2); color: var(--fg-3); border-color: var(--line); }

.run {
  margin-top: var(--s4); padding: var(--s4) var(--s5);
  border: 1px solid var(--line); border-radius: var(--r2); background: var(--bg-1);
}
.run-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s3); margin-bottom: var(--s3); }
.run-title { display: inline-flex; align-items: center; gap: var(--s2); font-size: .92rem; font-weight: 600; }
.run-title .spin { color: var(--amber); }
.run-clock { color: var(--fg-3); font-size: .82rem; font-variant-numeric: tabular-nums; }

.steps { display: grid; gap: .1rem; }
.step-line {
  display: grid; grid-template-columns: 1.2rem minmax(0, 11rem) 1fr auto;
  gap: var(--s3); align-items: baseline;
  padding: .28rem 0; font-size: .84rem;
}
.step-line .g { text-align: center; }
.step-line.ok  .g { color: var(--green); }
.step-line.now .g { color: var(--amber); }
.step-line.todo .g { color: var(--fg-3); }
.step-line.todo { color: var(--fg-3); }
.step-line .nm { color: var(--fg); overflow-wrap: anywhere; }
.step-line.todo .nm { color: var(--fg-3); }
.step-line .md { color: var(--fg-3); font-size: .78rem; overflow-wrap: anywhere; }
.step-line .tk { color: var(--fg-2); font-size: .78rem; font-variant-numeric: tabular-nums; white-space: nowrap; }

.run-foot {
  display: flex; flex-wrap: wrap; gap: var(--s4);
  margin-top: var(--s4); padding-top: var(--s3); border-top: 1px solid var(--line);
  color: var(--fg-2); font-size: .82rem;
}
.run-foot b { color: var(--fg); font-variant-numeric: tabular-nums; }

.report { margin-top: var(--s4); padding: var(--s4); border: 1px solid #5a2b28; border-radius: var(--r2); background: var(--red-dim); }
.report h3 { color: var(--red); margin-bottom: var(--s2); }
.report pre { max-height: 24rem; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--fg); font: .82rem/1.65 var(--mono); }
.report.warn { border-color: #5c4718; background: var(--amber-dim); }
.report.warn h3 { color: var(--amber); }

.site-panel { margin-top: var(--s4); padding: var(--s4) var(--s5); border: 1px solid var(--line); border-left: 3px solid var(--clay); border-radius: var(--r2); background: var(--bg-1); }
.site-host { display: block; margin: var(--s2) 0 var(--s3); padding: var(--s3); overflow-wrap: anywhere; border: 1px solid var(--line); border-radius: var(--r1); background: var(--bg-2); font-size: .92rem; }
.site-instructions { color: var(--fg-2); font-size: .84rem; }
.site-command { display: block; margin-top: var(--s2); padding: var(--s3); overflow-wrap: anywhere; border: 1px solid var(--line); border-radius: var(--r1); background: var(--bg-3); font-size: .8rem; line-height: 1.6; }
.site-actions { display: flex; flex-wrap: wrap; gap: var(--s2); margin-top: var(--s3); }
.since { color: var(--fg-2); font-size: .84rem; }
.snap { margin-top: var(--s3); color: var(--fg-3); font-size: .78rem; overflow-wrap: anywhere; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.pulse { animation: pulse 1.4s ease-in-out infinite; }

/* ───────────────────────────────────────────────────────────── largeurs ── */
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .side { position: static; }
}
@media (max-width: 620px) {
  .page { width: calc(100% - 1.4rem); }
  .bar { flex-direction: column; align-items: stretch; position: static; }
  .bar-right { justify-content: space-between; }
  .pair, .choices { grid-template-columns: 1fr; }
  .step-line { grid-template-columns: 1.2rem 1fr; }
  .step-line .md, .step-line .tk { grid-column: 2; }
  .recap-row { grid-template-columns: 1fr; gap: var(--s1); }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">Aller au contenu</a>

<header class="bar">
  <a class="brand" href="/"><span class="brand-mark">m</span>monl / console</a>
  <div class="bar-right">
    <span class="chip" id="quota-chip" hidden>quota <b id="quota-value">—</b></span>
    <span class="account-label" id="account-label"></span>
    <button id="logout-button" class="button secondary small" type="button" hidden>Se déconnecter</button>
  </div>
</header>

<main id="main-content" class="page">

  <!-- ─────────────────────────────────────────────────── connexion ── -->
  <section id="auth-view" class="narrow">
    <span class="eyebrow">Console monl</span>
    <h1 id="auth-title">Construire un site, une question à la fois.</h1>
    <p class="lede">Le même dialogue guidé que la ligne de commande. Vous répondez,
      monl compile, puis sert le site sous sa propre adresse.</p>
    <div class="panel auth-card">
      <div class="auth-switch" role="tablist">
        <button id="login-tab" class="tab-button" type="button" role="tab" aria-selected="true">Se connecter</button>
        <button id="register-tab" class="tab-button" type="button" role="tab" aria-selected="false">Créer un compte</button>
      </div>
      <form id="auth-form" class="form-grid">
        <label><span>Identifiant</span><input id="auth-identifier" name="identifier" autocomplete="username" required></label>
        <label><span>Mot de passe</span><input id="auth-password" name="password" type="password" autocomplete="current-password" required></label>
        <div class="form-actions">
          <button id="auth-submit" class="button" type="submit">Se connecter</button>
        </div>
        <p id="auth-help" class="help">Votre identifiant et votre mot de passe restent liés à ce compte de plateforme.</p>
      </form>
    </div>
  </section>

  <!-- ───────────────────────────────────────────────────── console ── -->
  <section id="console-view" hidden>
    <div id="alert"></div>

    <div class="layout">
      <aside class="side">
        <div class="side-head">
          <h2 id="projects-title">Vos sites</h2>
          <button id="refresh-button" class="button secondary small" type="button">Actualiser</button>
        </div>
        <div id="project-list" class="project-list"><p class="loading">Chargement…</p></div>
        <button id="new-project-button" class="button secondary small" type="button">+ Nouveau site</button>
        <p class="help" id="quota-note"></p>
      </aside>

      <div>
        <!-- Dialogue guidé -->
        <section id="dialog-view" class="panel dialog" aria-labelledby="new-project-title">
          <div class="dialog-head">
            <span class="t" id="new-project-title">Nouveau site</span>
            <span class="t"><span class="pips" id="pips"></span> <span id="step-count"></span></span>
          </div>
          <div class="dialog-body">
            <div class="transcript" id="transcript"></div>
            <div class="ask" id="ask"></div>
          </div>
        </section>

        <!-- Projet sélectionné -->
        <section id="project-view" class="panel" hidden></section>
      </div>
    </div>
  </section>
</main>

<script>
(function () {
  "use strict";

  var API = "";
  var CLE = "monl_console_token";
  var reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var GLYPHES = ["⠻", "⠽", "⠾", "⠷", "⠯", "⠟", "⠏", "⠇"];

  var etat = {
    token: window.localStorage.getItem(CLE),
    mode: "login",
    compte: null,
    projets: [],
    catalogue: [],
    choisi: null,
    vue: "dialogue",
    pas: 0,
    reponses: {},
    horloge: null,
    sondage: null,
    tick: 0
  };

  var byId = function (id) { return document.getElementById(id); };
  var vide = function (el) { while (el.firstChild) { el.removeChild(el.firstChild); } return el; };
  var mk = function (tag, cls, texte) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (texte !== undefined && texte !== null) el.textContent = String(texte);
    return el;
  };

  /* ─────────────────────────────────────────────────── les questions ──
     Une étape = une question. L'ordre est celui du dialogue de la ligne de
     commande : ce qu'on construit, comment ça s'appelle, à quoi ça sert,
     puis les choix qui coûtent. Le récapitulatif est une étape à part
     entière — lancer une construction se facture, on ne le déclenche pas
     par surprise au bas d'un formulaire. */
  var ETAPES = [
    {
      id: "source",
      question: "Que voulez-vous construire ?",
      aide: "Dix modèles servent de point de départ. Chacun est testé compilable.",
      rendu: rendreSource,
      valide: function () {
        if (etat.reponses.source === "spec") {
          return (etat.reponses.spec || "").trim() ? null : "Collez une spec .ml, ou revenez au catalogue.";
        }
        return etat.choisi ? null : "Choisissez un modèle.";
      },
      resume: function () {
        return etat.reponses.source === "spec" ? "une spec .ml collée" : (etat.choisi || "—");
      }
    },
    {
      id: "slug",
      question: "Quelle adresse pour le site ?",
      aide: "Elle formera le début du domaine. Minuscules, chiffres et tirets.",
      rendu: function (zone) { champTexte(zone, "slug", "mon-site", 1); },
      valide: function () {
        var v = (etat.reponses.slug || "").trim();
        if (!v) return "Une adresse est nécessaire.";
        if (!/^[a-z0-9][a-z0-9-]*$/.test(v)) return "Minuscules, chiffres et tirets seulement.";
        return null;
      },
      resume: function () { return (etat.reponses.slug || "").trim(); }
    },
    {
      id: "app_name",
      question: "Comment s'appelle l'application ?",
      aide: "Le nom affiché. Un identifiant sans espace ni accent.",
      rendu: function (zone) { champTexte(zone, "app_name", "MonProjet", 1); },
      valide: function () {
        var v = (etat.reponses.app_name || "").trim();
        if (!v) return "Un nom est nécessaire.";
        if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(v)) return "Lettres, chiffres et tirets bas, en commençant par une lettre.";
        return null;
      },
      resume: function () { return (etat.reponses.app_name || "").trim(); },
      saute: function () { return etat.reponses.source === "spec"; }
    },
    {
      id: "description",
      question: "En une phrase, à quoi sert ce site ?",
      aide: "Cette phrase oriente les textes et le registre visuel. Facultative.",
      rendu: function (zone) { champTexte(zone, "description", "Une boutique de céramique artisanale, ton éditorial sobre.", 3); },
      valide: function () { return null; },
      resume: function () { return (etat.reponses.description || "").trim() || "aucune"; },
      saute: function () { return etat.reponses.source === "spec"; }
    },
    {
      id: "images",
      question: "Générer des illustrations ?",
      aide: "Chaque image est une requête facturée. Sans elles, l'interface se contente de typographie et de blocs de couleur.",
      rendu: function (zone) { ouiNon(zone, "images"); },
      valide: function () { return etat.reponses.images === undefined ? "Répondez oui ou non." : null; },
      resume: function () { return etat.reponses.images ? "oui" : "non"; }
    },
    {
      id: "routes",
      question: "Router certains fichiers vers un autre modèle ?",
      aide: "Une cible par ligne, au format CIBLE=MODELE. Laissez vide pour n'utiliser qu'un seul modèle.",
      rendu: function (zone) { champTexte(zone, "routes", "styles.css=aliceai-llm-flash/latest", 3); },
      valide: function () {
        var lignes = (etat.reponses.routes || "").split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
        var vues = {};
        for (var i = 0; i < lignes.length; i++) {
          var sep = lignes[i].indexOf("=");
          if (sep <= 0) return "Format attendu : CIBLE=MODELE (ligne " + (i + 1) + ").";
          var cible = lignes[i].slice(0, sep).trim();
          if (!cible || !lignes[i].slice(sep + 1).trim()) return "Cible ou modèle vide (ligne " + (i + 1) + ").";
          if (vues[cible]) return "La cible « " + cible + " » est répétée.";
          vues[cible] = 1;
        }
        return null;
      },
      resume: function () {
        var n = (etat.reponses.routes || "").split("\n").filter(function (l) { return l.trim(); }).length;
        return n ? n + " règle" + (n > 1 ? "s" : "") : "un seul modèle";
      }
    },
    {
      id: "recap",
      question: "Tout est prêt.",
      aide: "Relisez, puis lancez. Une construction consomme des jetons et peut durer plusieurs minutes.",
      rendu: rendreRecap,
      valide: function () { return null; },
      final: true
    }
  ];

  /* ──────────────────────────────────────────────────────── transport ── */
  function api(chemin, options) {
    options = options || {};
    var entetes = options.headers || {};
    if (etat.token) entetes.Authorization = "Bearer " + etat.token;
    if (options.body && !entetes["Content-Type"]) entetes["Content-Type"] = "application/json";
    return fetch(API + chemin, {
      method: options.method || "GET",
      headers: entetes,
      body: options.body
    }).then(function (r) {
      if (r.status === 401) { deconnecter(); throw new Error("session expirée"); }
      return r.json().catch(function () { return {}; }).then(function (corps) {
        if (!r.ok) throw new Error((corps && corps.detail) || ("erreur " + r.status));
        return corps;
      });
    });
  }

  function alerte(message, erreur) {
    var zone = vide(byId("alert"));
    if (!message) return;
    var bloc = mk("div", "notice" + (erreur ? " error" : ""), message);
    zone.appendChild(bloc);
    if (!erreur) window.setTimeout(function () { if (bloc.parentNode) bloc.remove(); }, 6000);
  }

  /* ─────────────────────────────────────────────────────── connexion ── */
  function basculer(mode) {
    etat.mode = mode;
    byId("login-tab").setAttribute("aria-selected", String(mode === "login"));
    byId("register-tab").setAttribute("aria-selected", String(mode === "register"));
    byId("auth-submit").textContent = mode === "login" ? "Se connecter" : "Créer le compte";
    byId("auth-password").setAttribute("autocomplete", mode === "login" ? "current-password" : "new-password");
  }
  byId("login-tab").addEventListener("click", function () { basculer("login"); });
  byId("register-tab").addEventListener("click", function () { basculer("register"); });

  byId("auth-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var bouton = byId("auth-submit");
    bouton.disabled = true;
    var corps = JSON.stringify({
      identifier: byId("auth-identifier").value.trim(),
      password: byId("auth-password").value
    });
    var chemin = etat.mode === "login" ? "/login" : "/register";
    api(chemin, { method: "POST", body: corps }).then(function (reponse) {
      if (etat.mode === "register" && !reponse.token) {
        basculer("login");
        alerte("Compte créé. Connectez-vous.");
        return null;
      }
      etat.token = reponse.token;
      window.localStorage.setItem(CLE, etat.token);
      return charger();
    }).catch(function (err) {
      alerte(err.message, true);
    }).then(function () { bouton.disabled = false; });
  });

  function deconnecter() {
    etat.token = null;
    window.localStorage.removeItem(CLE);
    arreterHorloge();
    byId("console-view").hidden = true;
    byId("auth-view").hidden = false;
    byId("logout-button").hidden = true;
    byId("quota-chip").hidden = true;
    byId("account-label").textContent = "";
  }
  byId("logout-button").addEventListener("click", deconnecter);

  /* ────────────────────────────────────────────────────── chargement ── */
  function charger() {
    return Promise.all([
      api("/account"),
      api("/usage"),
      api("/catalogue"),
      api("/projects")
    ]).then(function (r) {
      etat.compte = r[0].account;
      etat.catalogue = (r[2] && r[2].models) || [];
      etat.projets = (r[3] && r[3].projects) || [];
      byId("auth-view").hidden = true;
      byId("console-view").hidden = false;
      byId("logout-button").hidden = false;
      byId("account-label").textContent = (etat.compte && etat.compte.identifier) || "";
      quota(r[1] && r[1].usage);
      listeProjets();
      if (etat.vue === "projet" && etat.projetId) return ouvrirProjet(etat.projetId);
      rendreEtape();
      return null;
    }).catch(function (err) { alerte(err.message, true); });
  }

  function nombre(n) {
    return typeof n === "number" ? new Intl.NumberFormat("fr-FR").format(n) : "—";
  }

  function quota(u) {
    if (!u) return;
    byId("quota-chip").hidden = false;
    byId("quota-value").textContent = nombre(u.consumed_tokens) + " / " + nombre(u.limit_tokens);
    var reste = u.remaining_tokens;
    byId("quota-note").textContent = typeof reste === "number"
      ? nombre(reste) + " jetons restants sur ce compte." : "";
  }

  var ETIQUETTES = {
    reussie: "réussie", echouee: "échouée",
    en_cours: "en cours", en_attente: "en attente"
  };

  function listeProjets() {
    var zone = vide(byId("project-list"));
    if (!etat.projets.length) {
      zone.appendChild(mk("p", "empty", "Aucun site pour l'instant."));
      return;
    }
    etat.projets.forEach(function (p) {
      var b = mk("button", "project-item");
      b.type = "button";
      b.setAttribute("aria-current", String(etat.vue === "projet" && etat.projetId === p.id));
      b.appendChild(mk("strong", null, p.slug));
      var dernier = (p.builds || [])[(p.builds || []).length - 1];
      var etiquette = dernier ? (ETIQUETTES[dernier.state] || dernier.state) : "pas de construction";
      b.appendChild(mk("span", null, etiquette + " · " + (p.builds || []).length + " construction"
        + ((p.builds || []).length > 1 ? "s" : "")));
      b.addEventListener("click", function () { ouvrirProjet(p.id); });
      zone.appendChild(b);
    });
  }

  /* ──────────────────────────────────────────────── le dialogue guidé ── */
  function etapesActives() {
    return ETAPES.filter(function (e) { return !(e.saute && e.saute()); });
  }

  function rendreEtape() {
    etat.vue = "dialogue";
    arreterHorloge();
    byId("project-view").hidden = true;
    byId("dialog-view").hidden = false;
    listeProjets();

    var actives = etapesActives();
    if (etat.pas >= actives.length) etat.pas = actives.length - 1;
    var etape = actives[etat.pas];

    var pips = vide(byId("pips"));
    actives.forEach(function (_e, i) {
      var p = mk("i");
      if (i < etat.pas) p.className = "done";
      if (i === etat.pas) p.className = "now";
      pips.appendChild(p);
    });
    byId("step-count").textContent = "étape " + (etat.pas + 1) + " / " + actives.length;

    // Transcription : ce qui a déjà été répondu reste lisible, et cliquable.
    var trans = vide(byId("transcript"));
    actives.slice(0, etat.pas).forEach(function (e, i) {
      var ligne = mk("div", "said");
      ligne.appendChild(mk("span", "m", "✓"));
      var corps = mk("div");
      corps.appendChild(mk("b", null, e.question + "  "));
      corps.appendChild(mk("i", null, e.resume ? e.resume() : ""));
      var modifier = mk("button", null, "modifier");
      modifier.type = "button";
      modifier.addEventListener("click", function () { etat.pas = i; rendreEtape(); });
      corps.appendChild(document.createElement("br"));
      corps.appendChild(modifier);
      ligne.appendChild(corps);
      trans.appendChild(ligne);
    });

    var ask = vide(byId("ask"));
    var entete = mk("div", "ask-q");
    entete.appendChild(mk("span", "m", etape.final ? "✦" : "?"));
    var titre = mk("h2", null, etape.question);
    entete.appendChild(titre);
    ask.appendChild(entete);
    if (etape.aide) ask.appendChild(mk("p", "ask-help", etape.aide));

    var champ = mk("div", "ask-field");
    ask.appendChild(champ);
    etape.rendu(champ);

    var actions = mk("div", "ask-actions");
    if (etat.pas > 0) {
      var retour = mk("button", "button secondary", "← Retour");
      retour.type = "button";
      retour.addEventListener("click", function () { etat.pas -= 1; rendreEtape(); });
      actions.appendChild(retour);
    }
    var suite = mk("button", "button", etape.final ? "Créer et lancer la construction" : "Continuer →");
    suite.type = "button";
    suite.id = etape.final ? "create-project-button" : "next-button";
    suite.addEventListener("click", function () { avancer(suite); });
    actions.appendChild(suite);
    if (!etape.final) actions.appendChild(mk("span", "ask-hint", "Entrée pour continuer"));
    else actions.appendChild(mk("span", "ask-hint", "cette action consomme des jetons"));
    ask.appendChild(actions);
  }

  function avancer(bouton) {
    var actives = etapesActives();
    var etape = actives[etat.pas];
    var faute = etape.valide();
    if (faute) { alerte(faute, true); return; }
    alerte("");
    if (!etape.final) { etat.pas += 1; rendreEtape(); return; }
    creer(bouton);
  }

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || byId("console-view").hidden) return;
    if (etat.vue !== "dialogue") return;
    var cible = e.target;
    if (cible && cible.tagName === "TEXTAREA" && !(e.ctrlKey || e.metaKey)) return;
    var bouton = byId("next-button") || byId("create-project-button");
    if (bouton) { e.preventDefault(); avancer(bouton); }
  });

  function champTexte(zone, cle, exemple, lignes) {
    var el;
    if (lignes > 1) {
      el = document.createElement("textarea");
      el.style.minHeight = (lignes * 1.9) + "rem";
    } else {
      el = document.createElement("input");
      el.type = "text";
    }
    el.value = etat.reponses[cle] || "";
    el.placeholder = exemple;
    el.spellcheck = false;
    el.addEventListener("input", function () { etat.reponses[cle] = el.value; });
    zone.appendChild(el);
    window.setTimeout(function () { el.focus(); }, 0);
  }

  function ouiNon(zone, cle) {
    var paire = mk("div", "pair");
    [["oui", true], ["non", false]].forEach(function (couple) {
      var b = mk("button", "choice");
      b.type = "button";
      b.setAttribute("aria-pressed", String(etat.reponses[cle] === couple[1]));
      b.appendChild(mk("b", null, couple[0]));
      b.appendChild(mk("span", null, couple[1]
        ? "Des illustrations sont produites, et facturées à la requête."
        : "Aucune image produite. Rien n'est facturé au-delà du texte."));
      b.addEventListener("click", function () {
        etat.reponses[cle] = couple[1];
        rendreEtape();
      });
      paire.appendChild(b);
    });
    zone.appendChild(paire);
  }

  function rendreSource(zone) {
    var onglets = mk("div", "pair");
    [["Un modèle du catalogue", "modele"], ["J'ai déjà une spec .ml", "spec"]].forEach(function (c) {
      var b = mk("button", "choice");
      b.type = "button";
      b.setAttribute("aria-pressed", String((etat.reponses.source || "modele") === c[1]));
      b.appendChild(mk("b", null, c[0]));
      b.addEventListener("click", function () { etat.reponses.source = c[1]; rendreEtape(); });
      onglets.appendChild(b);
    });
    zone.appendChild(onglets);

    if (etat.reponses.source === "spec") {
      var aire = document.createElement("textarea");
      aire.className = "spec";
      aire.id = "spec-input";
      aire.spellcheck = false;
      aire.placeholder = "app MonProjet\n\nentity Item\n    label: String\n…";
      aire.value = etat.reponses.spec || "";
      aire.style.marginTop = "1rem";
      aire.addEventListener("input", function () { etat.reponses.spec = aire.value; });
      zone.appendChild(aire);
      return;
    }

    var grille = mk("div", "choices");
    grille.style.marginTop = "1rem";
    etat.catalogue.forEach(function (m, i) {
      var b = mk("button", "choice");
      b.type = "button";
      b.setAttribute("aria-pressed", String(etat.choisi === m.name));
      b.appendChild(mk("span", "num", "modèle " + (i + 1)));
      b.appendChild(mk("b", null, m.name));
      if (m.hint) b.appendChild(mk("span", null, m.hint));
      b.addEventListener("click", function () { etat.choisi = m.name; rendreEtape(); });
      grille.appendChild(b);
    });
    zone.appendChild(grille);
  }

  function rendreRecap(zone) {
    var actives = etapesActives();
    var liste = mk("div", "recap");
    actives.slice(0, -1).forEach(function (e) {
      var ligne = mk("div", "recap-row");
      ligne.appendChild(mk("b", null, e.question));
      ligne.appendChild(mk("span", null, e.resume ? e.resume() : ""));
      liste.appendChild(ligne);
    });
    zone.appendChild(liste);
  }

  function creer(bouton) {
    bouton.disabled = true;
    var routes = {};
    (etat.reponses.routes || "").split("\n").forEach(function (ligne) {
      ligne = ligne.trim();
      if (!ligne) return;
      var sep = ligne.indexOf("=");
      routes[ligne.slice(0, sep).trim()] = ligne.slice(sep + 1).trim();
    });
    var charge = {
      slug: (etat.reponses.slug || "").trim(),
      generate_images: !!etat.reponses.images,
      model_routes: routes
    };
    if (etat.reponses.source === "spec") {
      charge.spec = etat.reponses.spec;
    } else {
      charge.model = etat.choisi;
      charge.app_name = (etat.reponses.app_name || "").trim();
      var d = (etat.reponses.description || "").trim();
      if (d) charge.description = d;
    }
    api("/projects", { method: "POST", body: JSON.stringify(charge) }).then(function (r) {
      var projet = r.project;
      return api("/projects/" + projet.id + "/builds", { method: "POST" }).then(function () {
        etat.reponses = {};
        etat.choisi = null;
        etat.pas = 0;
        alerte("Projet créé, construction mise en file.");
        return ouvrirProjet(projet.id);
      });
    }).catch(function (err) {
      alerte(err.message, true);
    }).then(function () { bouton.disabled = false; });
  }

  byId("new-project-button").addEventListener("click", function () {
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    etat.projetId = null;
    etat.pas = 0;
    rendreEtape();
  });
  byId("refresh-button").addEventListener("click", function () { charger(); });

  /* ─────────────────────────────────────────── suivi de construction ── */
  function ouvrirProjet(id) {
    etat.projetId = id;
    etat.vue = "projet";
    // Adresse profonde : un projet doit pouvoir se rouvrir, se partager et
    // se retrouver par le bouton « précédent ». Sans ça, un rechargement
    // pendant une construction de plusieurs minutes ramène au dialogue.
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#projet-" + id);
    }
    byId("dialog-view").hidden = true;
    byId("project-view").hidden = false;
    listeProjets();
    return rafraichirProjet();
  }

  function projetCourant() {
    for (var i = 0; i < etat.projets.length; i++) {
      if (etat.projets[i].id === etat.projetId) return etat.projets[i];
    }
    return null;
  }

  function rafraichirProjet() {
    if (!etat.projetId) return Promise.resolve();
    return api("/projects/" + etat.projetId).then(function (r) {
      var projet = r.project;
      var trouve = false;
      etat.projets = etat.projets.map(function (p) {
        if (p.id === projet.id) { trouve = true; return projet; }
        return p;
      });
      if (!trouve) etat.projets.unshift(projet);
      var dernier = (projet.builds || [])[(projet.builds || []).length - 1];
      if (!dernier) { rendreProjet([]); return null; }
      return api("/projects/" + projet.id + "/builds/" + dernier.id + "/etapes")
        .then(function (s) { rendreProjet(s); return null; })
        .catch(function () { rendreProjet(null); return null; });
    }).catch(function (err) { alerte(err.message, true); });
  }

  function duree(depuis, jusqua) {
    var a = depuis ? new Date(depuis).getTime() : 0;
    if (!a) return "";
    var b = jusqua ? new Date(jusqua).getTime() : Date.now();
    var s = Math.max(0, Math.floor((b - a) / 1000));
    var m = Math.floor(s / 60);
    return (m < 10 ? "0" : "") + m + ":" + ((s % 60) < 10 ? "0" : "") + (s % 60);
  }

  function arreterHorloge() {
    if (etat.horloge) { window.clearInterval(etat.horloge); etat.horloge = null; }
    if (etat.sondage) { window.clearInterval(etat.sondage); etat.sondage = null; }
  }

  var CLASSES = { reussie: "success", echouee: "failure", en_cours: "running", en_attente: "waiting" };

  function rendreProjet(suivi) {
    var projet = projetCourant();
    var vue = vide(byId("project-view"));
    if (!projet) { vue.appendChild(mk("p", "empty", "Projet introuvable.")); return; }

    var tete = mk("div", "project-header");
    var gauche = mk("div");
    gauche.appendChild(mk("span", "eyebrow", "Projet"));
    gauche.appendChild(mk("h2", null, projet.slug));
    gauche.appendChild(mk("p", "project-meta",
      "créé le " + new Date(projet.created_at).toLocaleString("fr-FR")));
    tete.appendChild(gauche);

    var builds = projet.builds || [];
    var build = builds[builds.length - 1];
    var badge = mk("span", "build-status " + (build ? (CLASSES[build.state] || "none") : "none"),
      build ? (ETIQUETTES[build.state] || build.state) : "pas encore lancée");
    tete.appendChild(badge);
    vue.appendChild(tete);

    if (!build) {
      vue.appendChild(mk("p", "since", "Ce projet n'a pas encore de construction."));
      vue.appendChild(boutonConstruire(projet));
      return;
    }

    var enCours = build.state === "en_cours" || build.state === "en_attente";

    var bloc = mk("div", "run");
    var head = mk("div", "run-head");
    var titre = mk("div", "run-title");
    var glyphe = mk("span", "spin", enCours ? GLYPHES[0] : (build.state === "reussie" ? "✓" : "✗"));
    glyphe.id = "run-glyph";
    if (!enCours) glyphe.className = build.state === "reussie" ? "spin ok" : "spin ko";
    if (!enCours) glyphe.style.color = build.state === "reussie" ? "var(--green)" : "var(--red)";
    titre.appendChild(glyphe);
    titre.appendChild(mk("span", null, "Construction #" + build.id
      + (enCours ? " — en cours" : (build.state === "reussie" ? " — terminée" : " — échouée"))));
    head.appendChild(titre);
    var horloge = mk("span", "run-clock", duree(build.started_at, build.finished_at));
    horloge.id = "run-clock";
    head.appendChild(horloge);
    bloc.appendChild(head);

    // Étapes RÉELLES : ce que le journal de la construction a enregistré.
    var etapes = (suivi && suivi.stages) || [];
    var restant = (suivi && suivi.remaining) || [];
    var liste = mk("div", "steps");
    etapes.forEach(function (e) {
      var l = mk("div", "step-line ok");
      l.appendChild(mk("span", "g", "✓"));
      l.appendChild(mk("span", "nm", e.name + (e.retry ? " (reprise " + e.retry + ")" : "")));
      l.appendChild(mk("span", "md", e.model || ""));
      var t = [];
      if (typeof e.seconds === "number") t.push(e.seconds.toFixed(1).replace(".", ",") + " s");
      if (typeof e.output_tokens === "number") t.push(nombre(e.output_tokens) + " jetons");
      l.appendChild(mk("span", "tk", t.join(" · ")));
      liste.appendChild(l);
    });
    if (enCours) {
      var courante = mk("div", "step-line now");
      var g2 = mk("span", "g " + (reduit ? "" : "pulse"), GLYPHES[0]);
      g2.id = "run-step-glyph";
      courante.appendChild(g2);
      courante.appendChild(mk("span", "nm", restant.length ? restant[0] : "vérification"));
      courante.appendChild(mk("span", "md", "en cours"));
      courante.appendChild(mk("span", "tk", ""));
      liste.appendChild(courante);
      restant.slice(1).forEach(function (nom) {
        var l = mk("div", "step-line todo");
        l.appendChild(mk("span", "g", "○"));
        l.appendChild(mk("span", "nm", nom));
        l.appendChild(mk("span", "md", "à venir"));
        l.appendChild(mk("span", "tk", ""));
        liste.appendChild(l);
      });
    }
    if (!etapes.length && !enCours) {
      liste.appendChild(mk("p", "empty", "Aucune étape IA journalisée pour cette construction."));
    }
    bloc.appendChild(liste);

    var pied = mk("div", "run-foot");
    var ajoute = function (etiquette, valeur) {
      var s = mk("span", null, etiquette + " ");
      s.appendChild(mk("b", null, valeur));
      pied.appendChild(s);
    };
    ajoute("jetons", nombre(build.tokens_consumed));
    ajoute("coût", build.price_status === "declared" && build.cost !== null && build.cost !== undefined
      ? new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(build.cost)
        + " " + (build.currency || "")
      : "non déclaré");
    if (build.snapshot_path) ajoute("snapshot", build.snapshot_path);
    bloc.appendChild(pied);
    vue.appendChild(bloc);

    if (build.error_message) {
      var err = mk("div", "report");
      err.appendChild(mk("h3", null, "Erreurs de vérification"));
      err.appendChild(mk("pre", null, build.error_message));
      vue.appendChild(err);
    }
    if (build.warning_message) {
      var avert = mk("div", "report warn");
      avert.appendChild(mk("h3", null, "Avertissement de construction"));
      avert.appendChild(mk("pre", null, build.warning_message));
      vue.appendChild(avert);
    }

    if (!enCours) vue.appendChild(boutonConstruire(projet));

    if (build.state === "reussie") vue.appendChild(panneauSite(projet));

    arreterHorloge();
    if (enCours) {
      etat.horloge = window.setInterval(function () {
        var h = byId("run-clock");
        if (h) h.textContent = duree(build.started_at, null);
        etat.tick += 1;
        var g = byId("run-glyph");
        var gg = byId("run-step-glyph");
        if (!reduit) {
          if (g) g.textContent = GLYPHES[etat.tick % GLYPHES.length];
          if (gg) gg.textContent = GLYPHES[etat.tick % GLYPHES.length];
        }
      }, 120);
      etat.sondage = window.setInterval(rafraichirProjet, 2500);
    }
  }

  function boutonConstruire(projet) {
    var zone = mk("div", "site-actions");
    var b = mk("button", "button", "Lancer une construction");
    b.type = "button";
    b.addEventListener("click", function () {
      b.disabled = true;
      api("/projects/" + projet.id + "/builds", { method: "POST" })
        .then(function () { return rafraichirProjet(); })
        .catch(function (err) { alerte(err.message, true); })
        .then(function () { b.disabled = false; });
    });
    zone.appendChild(b);
    return zone;
  }

  function panneauSite(projet) {
    var bloc = mk("div", "site-panel");
    bloc.appendChild(mk("span", "eyebrow", "Site servi"));
    bloc.appendChild(mk("h3", null, "Adresse réelle"));
    bloc.appendChild(mk("code", "site-host", projet.host || ""));
    if (projet.running) {
      bloc.appendChild(mk("p", "site-instructions",
        "Le site est démarré. En local, le nom d'hôte peut ne pas résoudre : "
        + "utilisez l'en-tête Host ou une entrée /etc/hosts."));
      bloc.appendChild(mk("code", "site-command",
        'curl -H "Host: ' + (projet.host || "") + '" ' + window.location.origin + "/site/"));
    } else {
      bloc.appendChild(mk("p", "site-instructions", "Le site n'est pas démarré."));
    }
    var actions = mk("div", "site-actions");
    var bascule = mk("button", "button " + (projet.running ? "danger" : "secondary"),
      projet.running ? "Arrêter le site" : "Démarrer le site");
    bascule.type = "button";
    bascule.addEventListener("click", function () {
      bascule.disabled = true;
      api("/projects/" + projet.id + "/" + (projet.running ? "stop" : "start"), { method: "POST" })
        .then(function () { return rafraichirProjet(); })
        .catch(function (err) { alerte(err.message, true); })
        .then(function () { bascule.disabled = false; });
    });
    actions.appendChild(bascule);
    bloc.appendChild(actions);
    return bloc;
  }

  /* ───────────────────────────────────────────────────────── démarrage ── */
  function projetDeLAdresse() {
    var m = /^#projet-(\d+)$/.exec(window.location.hash || "");
    return m ? parseInt(m[1], 10) : null;
  }

  window.addEventListener("hashchange", function () {
    var id = projetDeLAdresse();
    if (id && id !== etat.projetId) ouvrirProjet(id);
    if (!id && etat.vue === "projet") { etat.projetId = null; etat.pas = 0; rendreEtape(); }
  });

  basculer("login");
  var demande = projetDeLAdresse();
  if (demande) { etat.projetId = demande; etat.vue = "projet"; }
  if (etat.token) charger(); else byId("auth-view").hidden = false;
})();
</script>
</body>
</html>
'''


def console_response():
    """Rend la console."""
    return HTMLResponse(content=CONSOLE_HTML)
