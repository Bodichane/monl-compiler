"""Console web autonome de la plateforme monl.

La console est un artefact de la plateforme, pas un site produit et pas une
sortie de l'IA. Elle reste volontairement dans un seul document : aucun CDN,
aucun fichier distant et aucune étape de build ne sont nécessaires pour la
servir.
"""

from fastapi.responses import HTMLResponse

CONSOLE_HTML = r'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>monl — console</title>
  <style>
    :root {
      --ink: #18222d;
      --muted: #5d6b78;
      --line: #d8e0e7;
      --paper: #f4f7f9;
      --surface: #ffffff;
      --accent: #155e75;
      --accent-dark: #0b4558;
      --accent-soft: #e0f2f5;
      --success: #17633f;
      --success-soft: #e5f5ec;
      --warning: #8a4b0f;
      --warning-soft: #fff3df;
      --danger: #a12c34;
      --danger-soft: #fff0f1;
      --focus: #f2a900;
      --shadow: 0 16px 40px rgba(24, 34, 45, 0.08);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      min-width: 320px;
      background: var(--paper);
      color: var(--ink);
      line-height: 1.5;
    }
    button, input, textarea { font: inherit; }
    button { cursor: pointer; }
    button:focus-visible, input:focus-visible, textarea:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }
    .skip-link {
      position: absolute;
      left: 1rem;
      top: -4rem;
      z-index: 10;
      padding: .65rem .9rem;
      background: var(--ink);
      color: #fff;
      border-radius: .4rem;
    }
    .skip-link:focus { top: 1rem; }
    .app-shell { min-height: 100vh; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1rem clamp(1rem, 4vw, 3.5rem);
      background: var(--ink);
      color: #fff;
    }
    .brand {
      display: inline-flex;
      align-items: center;
      gap: .7rem;
      color: inherit;
      text-decoration: none;
      font-weight: 800;
      letter-spacing: .02em;
    }
    .brand-mark {
      display: grid;
      place-items: center;
      width: 2rem;
      height: 2rem;
      border: 2px solid #b9edf2;
      border-radius: .55rem;
      color: #b9edf2;
      font-size: .85rem;
    }
    .topbar-meta { display: flex; align-items: center; gap: 1rem; }
    .account-label { color: #d6e2e8; font-size: .9rem; }
    .page {
      width: min(1280px, calc(100% - 2rem));
      margin: 0 auto;
      padding: clamp(1.5rem, 4vw, 3.5rem) 0 5rem;
    }
    .narrow { width: min(560px, 100%); margin: 3rem auto; }
    .eyebrow {
      margin: 0 0 .35rem;
      color: var(--accent);
      font-size: .74rem;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
    }
    h1, h2, h3, h4, p { margin-top: 0; }
    h1, h2, h3, h4 { line-height: 1.15; }
    h1 { max-width: 750px; margin-bottom: 1rem; font-size: clamp(2rem, 5vw, 4.5rem); }
    h2 { margin-bottom: .65rem; font-size: clamp(1.35rem, 3vw, 2rem); }
    h3 { margin-bottom: .5rem; font-size: 1.05rem; }
    .lede { max-width: 720px; color: var(--muted); font-size: 1.08rem; }
    .panel {
      padding: clamp(1rem, 3vw, 1.75rem);
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 1rem;
      box-shadow: var(--shadow);
    }
    .auth-intro { padding: 1rem 0 0; }
    .auth-card { margin-top: 1.5rem; }
    .auth-switch {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .3rem;
      margin-bottom: 1.5rem;
      padding: .3rem;
      background: var(--paper);
      border-radius: .65rem;
    }
    .tab-button, .button {
      border: 1px solid transparent;
      border-radius: .55rem;
      padding: .7rem 1rem;
      color: var(--ink);
      background: transparent;
      font-weight: 700;
    }
    .tab-button[aria-selected="true"] {
      background: var(--surface);
      border-color: var(--line);
      box-shadow: 0 2px 7px rgba(24, 34, 45, .07);
    }
    .button {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .button:hover { background: var(--accent-dark); border-color: var(--accent-dark); }
    .button.secondary { background: var(--surface); color: var(--accent-dark); border-color: #9db9c3; }
    .button.secondary:hover { background: var(--accent-soft); }
    .button.danger { background: var(--danger); border-color: var(--danger); }
    .button.danger:hover { background: #7e2028; border-color: #7e2028; }
    .button.small { padding: .5rem .75rem; font-size: .9rem; }
    .button[disabled] { cursor: wait; opacity: .55; }
    .form-grid { display: grid; gap: 1rem; }
    .form-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    label { display: grid; gap: .38rem; color: var(--ink); font-weight: 700; }
    label span { font-size: .9rem; }
    input, textarea {
      width: 100%;
      border: 1px solid #aab9c4;
      border-radius: .5rem;
      padding: .72rem .8rem;
      color: var(--ink);
      background: #fff;
    }
    input::placeholder, textarea::placeholder { color: #687985; }
    textarea { min-height: 9rem; resize: vertical; }
    textarea.spec { min-height: 18rem; font: .86rem/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .help { margin: 0; color: var(--muted); font-size: .87rem; font-weight: 400; }
    .form-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .7rem; margin-top: .35rem; }
    .notice {
      margin: 1rem 0 0;
      padding: .8rem 1rem;
      border-left: 4px solid var(--accent);
      background: var(--accent-soft);
      border-radius: .35rem;
    }
    .notice.error { border-left-color: var(--danger); background: var(--danger-soft); color: #6f1d25; }
    [hidden] { display: none !important; }
    #alert { margin-bottom: 1.25rem; }
    .console-intro { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: 2rem; }
    .console-intro h1 { margin-bottom: .5rem; font-size: clamp(2rem, 5vw, 3.6rem); }
    .usage-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: .75rem;
      margin-bottom: 1.5rem;
    }
    .metric { padding: 1rem; background: var(--surface); border: 1px solid var(--line); border-radius: .8rem; }
    .metric-label { display: block; color: var(--muted); font-size: .82rem; }
    .metric-value { display: block; margin-top: .2rem; font-size: clamp(1.15rem, 3vw, 1.65rem); font-weight: 800; }
    .metric-note { margin: .25rem 0 0; color: var(--muted); font-size: .78rem; }
    .workspace { display: grid; grid-template-columns: minmax(220px, .75fr) minmax(0, 1.65fr); gap: 1.5rem; align-items: start; }
    .section-heading { display: flex; align-items: start; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
    .section-heading h2 { margin-bottom: 0; }
    .project-list { display: grid; gap: .65rem; }
    .project-item {
      display: block;
      width: 100%;
      padding: .9rem 1rem;
      border: 1px solid var(--line);
      border-radius: .65rem;
      background: #fff;
      text-align: left;
    }
    .project-item:hover, .project-item[aria-current="true"] { border-color: var(--accent); background: #f1fbfc; }
    .project-item strong, .project-item span { display: block; }
    .project-item span { color: var(--muted); font-size: .84rem; }
    .empty { padding: 1rem 0; color: var(--muted); }
    .catalogue-panel { margin-bottom: 1.5rem; }
    .model-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .65rem; }
    .model-card {
      min-height: 128px;
      padding: .9rem;
      border: 1px solid var(--line);
      border-radius: .7rem;
      background: #fff;
      color: var(--ink);
      text-align: left;
    }
    .model-card:hover, .model-card[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); }
    .model-card p { margin-bottom: 0; color: var(--muted); font-size: .85rem; }
    .model-card .model-number { color: var(--accent); font-size: .75rem; font-weight: 800; }
    .composer-tabs { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
    .composer-tab { border: 1px solid #9db9c3; border-radius: 99px; padding: .5rem .85rem; background: #fff; color: var(--accent-dark); font-weight: 700; }
    .composer-tab[aria-selected="true"] { background: var(--accent); color: #fff; }
    .project-header { display: flex; align-items: start; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }
    .project-header h2 { margin-bottom: .25rem; word-break: break-word; }
    .project-meta { margin: 0; color: var(--muted); }
    .build-panel { margin-bottom: 1rem; }
    .build-header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
    .build-status {
      display: inline-flex;
      align-items: center;
      gap: .4rem;
      border-radius: 99px;
      padding: .35rem .65rem;
      font-size: .82rem;
      font-weight: 800;
      white-space: nowrap;
    }
    .build-status.waiting, .build-status.running { background: var(--warning-soft); color: var(--warning); }
    .build-status.success { background: var(--success-soft); color: var(--success); }
    .build-status.failure { background: var(--danger-soft); color: var(--danger); }
    .build-status.none { background: var(--paper); color: var(--muted); }
    .progress-rail { height: .55rem; margin: 1rem 0; overflow: hidden; border-radius: 99px; background: #e6edf1; }
    .progress-rail span { display: block; width: 62%; height: 100%; border-radius: inherit; background: var(--accent); }
    .progress-rail.waiting span { width: 28%; background: var(--warning); }
    .progress-rail.failure span { width: 100%; background: var(--danger); }
    .progress-rail.success span { width: 100%; background: var(--success); }
    .since { margin: 0; color: var(--muted); }
    .build-details { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-top: 1rem; }
    .detail { padding: .7rem; border: 1px solid var(--line); border-radius: .55rem; background: #fbfcfd; }
    .detail small { display: block; color: var(--muted); }
    .detail strong { display: block; overflow-wrap: anywhere; }
    .error-report { margin-top: 1rem; padding: 1rem; border: 1px solid #e7b8bd; border-radius: .6rem; background: var(--danger-soft); }
    .error-report h3 { color: var(--danger); }
    .error-report pre { max-height: 28rem; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: #4e171d; font: .87rem/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .warning-report { border-color: #e9c98e; background: var(--warning-soft); }
    .warning-report h3 { color: var(--warning); }
    .warning-report pre { color: #5f3a0c; }
    .site-panel { margin-top: 1rem; border-left: 4px solid var(--accent); }
    .site-host { display: block; margin: .5rem 0 1rem; padding: .8rem; overflow-wrap: anywhere; border: 1px solid var(--line); border-radius: .5rem; background: #f8fbfc; font: 1rem ui-monospace, SFMono-Regular, Menlo, monospace; }
    .site-instructions { margin: 0; color: var(--muted); }
    .site-command { display: block; margin-top: .6rem; padding: .7rem; overflow-wrap: anywhere; border-radius: .45rem; background: var(--ink); color: #effcff; font: .83rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
    .site-actions { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: 1rem; }
    .loading { color: var(--muted); }
    @media (max-width: 820px) {
      .workspace { grid-template-columns: 1fr; }
      .console-intro { align-items: start; flex-direction: column; }
    }
    @media (max-width: 560px) {
      .page { width: min(100% - 1rem, 1280px); padding-top: 1rem; }
      .topbar { align-items: start; flex-direction: column; }
      .topbar-meta { width: 100%; justify-content: space-between; }
      .form-grid.two, .usage-strip, .build-details { grid-template-columns: 1fr; }
      .build-header, .project-header { flex-direction: column; }
      .build-status { white-space: normal; }
      .model-grid { grid-template-columns: 1fr; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Aller au contenu</a>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="monl, console d'administration">
        <span class="brand-mark" aria-hidden="true">m</span>
        <span>monl / console</span>
      </a>
      <div class="topbar-meta">
        <span id="account-label" class="account-label" hidden></span>
        <button id="logout-button" class="button secondary small" type="button" hidden>Se déconnecter</button>
      </div>
    </header>

    <main id="main-content" class="page">
      <div id="alert" class="notice" role="alert" hidden></div>

      <section id="auth-view" class="narrow" aria-labelledby="auth-title">
        <div class="auth-intro">
          <p class="eyebrow">Créer directement</p>
          <h1 id="auth-title">Votre console de sites.</h1>
          <p class="lede">Choisissez un modèle ou apportez votre spec <code>.ml</code>. Chaque construction reste visible, du premier jeton jusqu'au site servi.</p>
        </div>
        <div class="panel auth-card">
          <div class="auth-switch" role="tablist" aria-label="Accès à la console">
            <button id="login-tab" class="tab-button" type="button" role="tab" aria-selected="true">Se connecter</button>
            <button id="register-tab" class="tab-button" type="button" role="tab" aria-selected="false">Créer un compte</button>
          </div>
          <form id="auth-form" class="form-grid">
            <label><span>Identifiant</span><input id="auth-identifier" name="identifier" type="text" autocomplete="username" required></label>
            <label><span>Mot de passe</span><input id="auth-password" name="password" type="password" autocomplete="current-password" minlength="8" required></label>
            <button id="auth-submit" class="button" type="submit">Se connecter</button>
          </form>
          <p id="auth-help" class="help">Votre identifiant et votre mot de passe restent liés à ce compte de plateforme.</p>
        </div>
      </section>

      <section id="console-view" hidden aria-labelledby="console-title">
        <div class="console-intro">
          <div>
            <p class="eyebrow">Espace de travail</p>
            <h1 id="console-title">Construire, suivre, servir.</h1>
            <p class="lede">Une construction peut durer plusieurs minutes. Son état et son horodatage restent affichés pendant toute l'attente.</p>
          </div>
          <button id="refresh-button" class="button secondary" type="button">Actualiser</button>
        </div>

        <section class="usage-strip" aria-label="Consommation du compte">
          <div class="metric"><span class="metric-label">Jetons consommés</span><strong id="usage-consumed" class="metric-value">—</strong><p class="metric-note">cumul réel des constructions</p></div>
          <div class="metric"><span class="metric-label">Jetons restants</span><strong id="usage-remaining" class="metric-value">—</strong><p id="usage-limit" class="metric-note">quota —</p></div>
          <div class="metric"><span class="metric-label">Coût</span><strong id="usage-cost" class="metric-value">—</strong><p id="usage-cost-note" class="metric-note">aucun coût affiché avant déclaration du tarif</p></div>
        </section>

        <section class="panel catalogue-panel" aria-labelledby="new-project-title">
          <div class="section-heading">
            <div><p class="eyebrow">Nouveau projet</p><h2 id="new-project-title">Choisir le point de départ</h2></div>
          </div>
          <div class="composer-tabs" role="tablist" aria-label="Source de la spec">
            <button id="model-mode" class="composer-tab" type="button" role="tab" aria-selected="true">Un modèle du catalogue</button>
            <button id="spec-mode" class="composer-tab" type="button" role="tab" aria-selected="false">Coller une spec .ml</button>
          </div>
          <div id="model-source">
            <p class="help">Les dix modèles sont ceux du catalogue monl. La carte choisie est envoyée au service, puis construite par le pipeline habituel.</p>
            <div id="model-grid" class="model-grid" aria-live="polite"><p class="loading">Chargement du catalogue…</p></div>
          </div>
          <div id="spec-source" hidden>
            <label><span>Spec monl (.ml)</span><textarea id="spec-input" class="spec" spellcheck="false" placeholder="app MonProjet\n\nentity ..."></textarea></label>
            <label><span>Ou déposer un fichier .ml</span><input id="spec-file" type="file" accept=".ml,text/plain"></label>
            <p class="help">La spec est envoyée telle quelle. Les erreurs de vérification seront conservées dans le rapport de construction.</p>
          </div>
          <form id="project-form" class="form-grid" style="margin-top: 1.25rem">
            <div class="form-grid two">
              <label><span>Slug du site</span><input id="project-slug" type="text" required placeholder="mon-site" pattern="[^/\\\\]+" autocomplete="off"><span class="help">Il deviendra le début de l'adresse du site.</span></label>
              <label><span>Nom de l'application</span><input id="app-name" type="text" value="MonProjet" autocomplete="off"><span class="help">Utilisé si vous partez d'un modèle.</span></label>
            </div>
            <label><span>Description</span><textarea id="project-description" style="min-height: 6rem" placeholder="Ce que le site doit permettre…"></textarea></label>
            <div class="form-grid two">
              <label><span>Images générées</span><span><input id="generate-images" type="checkbox"> Générer les visuels matriciels planifiés</span><span class="help">Ce choix est explicite et peut entraîner une requête facturée par image.</span></label>
              <label><span>Routage des modèles</span><textarea id="model-routes" style="min-height: 6rem" spellcheck="false" placeholder="styles.css=aliceai-llm-flash/latest"></textarea><span class="help">Une cible par ligne, au format CIBLE=MODELE. Laissez vide pour un seul modèle.</span></label>
            </div>
            <div class="form-actions"><button id="create-project-button" class="button" type="submit">Créer et lancer la construction</button><span id="create-help" class="help">Le suivi apparaîtra dès la mise en file.</span></div>
          </form>
        </section>

        <div class="workspace">
          <aside class="panel" aria-labelledby="projects-title">
            <div class="section-heading"><div><p class="eyebrow">Vos sites</p><h2 id="projects-title">Projets</h2></div></div>
            <div id="project-list" class="project-list" aria-live="polite"><p class="loading">Chargement des projets…</p></div>
          </aside>
          <section id="project-detail" class="panel" hidden aria-labelledby="detail-title"></section>
        </div>
      </section>
    </main>
  </div>

  <script>
    (() => {
      "use strict";

      const state = {
        token: window.localStorage.getItem("monl_console_token"),
        account: null,
        catalogue: [],
        projects: [],
        selectedModel: null,
        selectedProjectId: null,
        sourceMode: "model",
        authMode: "login",
        refreshTimer: null,
        refreshing: false
      };

      const byId = (id) => document.getElementById(id);
      const authView = byId("auth-view");
      const consoleView = byId("console-view");
      const alertBox = byId("alert");

      function showAlert(message, isError = false) {
        alertBox.textContent = message || "";
        alertBox.classList.toggle("error", isError);
        alertBox.hidden = !message;
      }

      function setAuthenticated(account) {
        state.account = account;
        authView.hidden = true;
        consoleView.hidden = false;
        byId("account-label").textContent = account.identifier;
        byId("account-label").hidden = false;
        byId("logout-button").hidden = false;
      }

      function setLoggedOut() {
        state.token = null;
        state.account = null;
        window.localStorage.removeItem("monl_console_token");
        if (state.refreshTimer) window.clearInterval(state.refreshTimer);
        state.refreshTimer = null;
        authView.hidden = false;
        consoleView.hidden = true;
        byId("account-label").hidden = true;
        byId("logout-button").hidden = true;
      }

      async function api(path, options = {}) {
        const headers = new Headers(options.headers || {});
        if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
        if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
          headers.set("Content-Type", "application/json");
        }
        const response = await fetch(path, { ...options, headers });
        const raw = await response.text();
        let data = {};
        try { data = raw ? JSON.parse(raw) : {}; } catch (_error) { data = { detail: raw }; }
        if (!response.ok) {
          if (response.status === 401 && state.token) {
            setLoggedOut();
            throw new Error("Votre session a expiré. Connectez-vous à nouveau.");
          }
          throw new Error(data.detail || `La requête a échoué (${response.status}).`);
        }
        return data;
      }

      function formatNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
        return new Intl.NumberFormat("fr-FR").format(Number(value));
      }

      function formatDate(value) {
        if (!value) return "date inconnue";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "date inconnue";
        return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(date);
      }

      function elapsed(value) {
        if (!value) return "durée inconnue";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "durée inconnue";
        let seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
        const minutes = Math.floor(seconds / 60);
        seconds %= 60;
        if (minutes < 1) return `${seconds} seconde${seconds > 1 ? "s" : ""}`;
        const hours = Math.floor(minutes / 60);
        if (hours < 1) return `${minutes} minute${minutes > 1 ? "s" : ""}`;
        const rest = minutes % 60;
        return `${hours} h${rest ? ` ${rest} min` : ""}`;
      }

      function addText(parent, tag, text, className) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        element.textContent = text;
        parent.appendChild(element);
        return element;
      }

      function setAuthMode(mode) {
        state.authMode = mode;
        const login = mode === "login";
        byId("login-tab").setAttribute("aria-selected", String(login));
        byId("register-tab").setAttribute("aria-selected", String(!login));
        byId("auth-submit").textContent = login ? "Se connecter" : "Créer mon compte";
        byId("auth-password").setAttribute("autocomplete", login ? "current-password" : "new-password");
        byId("auth-help").textContent = login
          ? "Votre identifiant et votre mot de passe restent liés à ce compte de plateforme."
          : "Un mot de passe de huit caractères minimum protège ce compte de plateforme.";
      }

      async function submitAuth(event) {
        event.preventDefault();
        const button = byId("auth-submit");
        button.disabled = true;
        showAlert("");
        try {
          const data = await api(state.authMode === "login" ? "/login" : "/register", {
            method: "POST",
            body: JSON.stringify({
              identifier: byId("auth-identifier").value.trim(),
              password: byId("auth-password").value
            })
          });
          state.token = data.token;
          window.localStorage.setItem("monl_console_token", state.token);
          setAuthenticated(data.account);
          await loadConsole();
          startPolling();
        } catch (error) {
          showAlert(error.message, true);
        } finally {
          button.disabled = false;
        }
      }

      function setSourceMode(mode) {
        state.sourceMode = mode;
        const model = mode === "model";
        byId("model-mode").setAttribute("aria-selected", String(model));
        byId("spec-mode").setAttribute("aria-selected", String(!model));
        byId("model-source").hidden = !model;
        byId("spec-source").hidden = model;
        byId("app-name").disabled = !model;
      }

      function renderCatalogue() {
        const grid = byId("model-grid");
        grid.replaceChildren();
        state.catalogue.forEach((model, index) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "model-card";
          button.setAttribute("aria-pressed", String(state.selectedModel === model.name));
          addText(button, "span", `Modèle ${index + 1}`, "model-number");
          addText(button, "h3", model.name);
          addText(button, "p", model.hint || "Point de départ monl.");
          button.addEventListener("click", () => {
            state.selectedModel = model.name;
            renderCatalogue();
          });
          grid.appendChild(button);
        });
        if (!state.catalogue.length) addText(grid, "p", "Le catalogue est momentanément indisponible.", "empty");
      }

      async function loadCatalogue() {
        try {
          const data = await api("/catalogue");
          state.catalogue = data.models || [];
          if (!state.selectedModel && state.catalogue[0]) state.selectedModel = state.catalogue[0].name;
          renderCatalogue();
        } catch (error) {
          byId("model-grid").replaceChildren();
          addText(byId("model-grid"), "p", `Catalogue indisponible : ${error.message}`, "empty");
        }
      }

      function currentProject() {
        return state.projects.find((project) => project.id === state.selectedProjectId) || null;
      }

      function renderProjectList() {
        const list = byId("project-list");
        list.replaceChildren();
        if (!state.projects.length) {
          addText(list, "p", "Aucun projet pour le moment. Choisissez un modèle ci-dessus pour commencer.", "empty");
          return;
        }
        state.projects.forEach((project) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "project-item";
          button.setAttribute("aria-current", String(project.id === state.selectedProjectId));
          addText(button, "strong", project.slug);
          addText(button, "span", `${projectStateLabel(project)} · ${project.builds.length} construction${project.builds.length > 1 ? "s" : ""}`);
          button.addEventListener("click", () => {
            state.selectedProjectId = project.id;
            renderProjectList();
            renderProjectDetail();
          });
          list.appendChild(button);
        });
      }

      function projectStateLabel(project) {
        const build = project.builds[project.builds.length - 1];
        if (!build) return "pas de construction";
        return buildLabel(build.state);
      }

      function buildLabel(stateName) {
        return {
          en_attente: "en attente",
          en_cours: "en cours",
          reussie: "réussie",
          echouee: "échouée"
        }[stateName] || stateName || "inconnue";
      }

      function buildTone(stateName) {
        return { en_attente: "waiting", en_cours: "running", reussie: "success", echouee: "failure" }[stateName] || "none";
      }

      function renderBuild(build, project) {
        const panel = document.createElement("section");
        panel.className = "build-panel";
        panel.setAttribute("aria-labelledby", "build-title");
        const latest = build || { state: "pas_de_construction" };
        const tone = buildTone(latest.state);
        const header = document.createElement("div");
        header.className = "build-header";
        const heading = document.createElement("div");
        addText(heading, "p", "Construction", "eyebrow");
        addText(heading, "h3", build ? `Construction #${build.id}` : "Aucune construction", "build-title");
        header.appendChild(heading);
        addText(header, "span", build ? buildLabel(build.state) : "pas encore lancée", `build-status ${tone}`);
        panel.appendChild(header);

        if (!build) {
          addText(panel, "p", "Votre projet est prêt. Lancez une construction pour générer le site et suivre son avancement ici.", "since");
        } else {
          const started = build.started_at || build.created_at;
          const progress = document.createElement("div");
          progress.className = `progress-rail ${tone}`;
          addText(progress, "span", "", "");
          progress.firstElementChild.setAttribute("aria-hidden", "true");
          progress.setAttribute("role", "progressbar");
          progress.setAttribute("aria-label", `Construction ${buildLabel(build.state)}`);
          panel.appendChild(progress);
          if (build.state === "en_cours") {
            addText(panel, "p", `Construction en cours depuis ${elapsed(started)}. Le service travaille toujours, même si le résultat n'est pas encore disponible.`, "since");
          } else if (build.state === "en_attente") {
            addText(panel, "p", `Construction en attente depuis ${elapsed(build.created_at)}. Elle est bien enregistrée et sera prise en charge par le worker.`, "since");
          } else {
            addText(panel, "p", `${build.state === "reussie" ? "Terminée" : "Terminée avec une erreur"} le ${formatDate(build.finished_at || build.created_at)}.`, "since");
          }
          const details = document.createElement("div");
          details.className = "build-details";
          const tokenText = build.tokens_consumed === null || build.tokens_consumed === undefined ? "non connu" : formatNumber(build.tokens_consumed);
          const costText = build.price_status === "declared" && build.cost !== null && build.cost !== undefined
            ? `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(Number(build.cost))} ${build.currency || ""}`.trim()
            : "non déclaré";
          [["Jetons", tokenText], ["Coût", costText], ["Demandée", formatDate(build.created_at)]].forEach(([label, value]) => {
            const detail = document.createElement("div");
            detail.className = "detail";
            addText(detail, "small", label);
            addText(detail, "strong", value);
            details.appendChild(detail);
          });
          panel.appendChild(details);
          if (build.snapshot_path) {
            const snapshot = document.createElement("p");
            snapshot.className = "since";
            addText(snapshot, "strong", "Snapshot conservé : ");
            addText(snapshot, "code", build.snapshot_path);
            panel.appendChild(snapshot);
          }
          if (build.state === "echouee") {
            const report = document.createElement("div");
            report.className = "error-report";
            addText(report, "h3", "Erreurs de vérification");
            addText(report, "p", "Rapport brut de la construction — aucun détail n'est remplacé par un message générique.");
            addText(report, "pre", build.error_message || build.error || "Aucun détail d'erreur fourni.");
            panel.appendChild(report);
          } else if (build.warning_message) {
            const report = document.createElement("div");
            report.className = "error-report warning-report";
            addText(report, "h3", "Avertissement de construction");
            addText(report, "p", "Le site est disponible, mais un élément demandé n'a pas pu être produit.");
            addText(report, "pre", build.warning_message);
            panel.appendChild(report);
          }
        }
        const actions = document.createElement("div");
        actions.className = "form-actions";
        const buildButton = document.createElement("button");
        buildButton.type = "button";
        buildButton.className = "button small";
        buildButton.textContent = build && ["en_attente", "en_cours"].includes(build.state) ? "Construction en cours…" : "Lancer une construction";
        buildButton.disabled = Boolean(build && ["en_attente", "en_cours"].includes(build.state));
        buildButton.addEventListener("click", () => enqueueBuild(project.id));
        actions.appendChild(buildButton);
        panel.appendChild(actions);
        return panel;
      }

      function renderSite(project, build) {
        const panel = document.createElement("section");
        panel.className = "site-panel";
        panel.setAttribute("aria-labelledby", "site-title");
        addText(panel, "p", "Site servi", "eyebrow");
        addText(panel, "h3", "Adresse réelle", "site-title");
        addText(panel, "code", project.host || `${project.slug}.domaine`, "site-host");
        const built = build && build.state === "reussie";
        if (!built) {
          addText(panel, "p", "L'adresse apparaîtra ici après une construction réussie.", "site-instructions");
          return panel;
        }
        const platformOrigin = window.location.origin;
        const command = `curl -H "Host: ${project.host}" ${platformOrigin}/site/`;
        addText(panel, "p", project.running
          ? "Le site est démarré. En local, le nom d'hôte ne résout pas tout seul : utilisez l'en-tête Host ou une entrée /etc/hosts."
          : "Le site est arrêté. Démarrez-le, puis utilisez l'en-tête Host ou une entrée /etc/hosts ; un lien direct silencieusement cassé n'est pas proposé.", "site-instructions");
        addText(panel, "code", command, "site-command");
        const actions = document.createElement("div");
        actions.className = "site-actions";
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = project.running ? "button danger small" : "button small";
        toggle.textContent = project.running ? "Arrêter le site" : "Démarrer le site";
        toggle.addEventListener("click", () => toggleSite(project));
        actions.appendChild(toggle);
        panel.appendChild(actions);
        return panel;
      }

      function renderProjectDetail() {
        const detail = byId("project-detail");
        const project = currentProject();
        if (!project) {
          detail.hidden = true;
          detail.replaceChildren();
          return;
        }
        detail.hidden = false;
        detail.replaceChildren();
        const header = document.createElement("div");
        header.className = "project-header";
        const heading = document.createElement("div");
        addText(heading, "p", "Projet sélectionné", "eyebrow");
        addText(heading, "h2", project.slug, "detail-title");
        addText(heading, "p", `Créé le ${formatDate(project.created_at)}`, "project-meta");
        header.appendChild(heading);
        detail.appendChild(header);
        const latest = project.builds[project.builds.length - 1] || null;
        detail.appendChild(renderBuild(latest, project));
        detail.appendChild(renderSite(project, latest));
      }

      function renderUsage(data) {
        const usage = data.usage || {};
        byId("usage-consumed").textContent = formatNumber(usage.consumed_tokens);
        byId("usage-remaining").textContent = formatNumber(usage.remaining_tokens);
        byId("usage-limit").textContent = `sur ${formatNumber(usage.limit_tokens)} jetons`;
        const builds = state.projects.flatMap((project) => project.builds || []);
        const declared = builds.filter((build) => build.price_status === "declared" && build.cost !== null && build.cost !== undefined);
        const undeclared = builds.some((build) => build.price_status === "not_declared");
        if (!declared.length) {
          byId("usage-cost").textContent = "non déclaré";
          byId("usage-cost-note").textContent = undeclared ? "le tarif n'est pas déclaré pour ces constructions" : "aucun coût déclaré";
        } else {
          const total = declared.reduce((sum, build) => sum + Number(build.cost), 0);
          const currency = declared.find((build) => build.currency)?.currency || "";
          byId("usage-cost").textContent = `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(total)} ${currency}`.trim();
          byId("usage-cost-note").textContent = undeclared ? "coûts déclarés uniquement ; le reste est non déclaré" : "coûts déclarés par le fournisseur";
        }
      }

      async function loadConsole(silent = false) {
        if (!state.token || state.refreshing) return;
        state.refreshing = true;
        try {
          const [projects, usage] = await Promise.all([api("/projects"), api("/usage")]);
          state.projects = projects.projects || [];
          if (!state.projects.some((project) => project.id === state.selectedProjectId)) {
            state.selectedProjectId = state.projects[0]?.id || null;
          }
          renderProjectList();
          renderProjectDetail();
          renderUsage(usage);
          if (!silent) showAlert("");
        } catch (error) {
          if (!silent) showAlert(error.message, true);
        } finally {
          state.refreshing = false;
        }
      }

      function startPolling() {
        if (state.refreshTimer) window.clearInterval(state.refreshTimer);
        state.refreshTimer = window.setInterval(() => loadConsole(true), 2500);
      }

      async function enqueueBuild(projectId) {
        try {
          await api(`/projects/${projectId}/builds`, { method: "POST" });
          showAlert("Construction mise en file. Son état et son horodatage sont suivis ci-dessous.");
          await loadConsole();
        } catch (error) { showAlert(error.message, true); }
      }

      async function toggleSite(project) {
        const action = project.running ? "stop" : "start";
        try {
          await api(`/projects/${project.id}/${action}`, { method: "POST" });
          showAlert(project.running ? "Site arrêté." : "Site démarré. L'adresse reste accessible par son hôte réel.");
          await loadConsole();
        } catch (error) { showAlert(error.message, true); }
      }

      async function submitProject(event) {
        event.preventDefault();
        const button = byId("create-project-button");
        const payload = { slug: byId("project-slug").value.trim() };
        const routeLines = byId("model-routes").value.split("\n").map((line) => line.trim()).filter(Boolean);
        const modelRoutes = {};
        for (const declaration of routeLines) {
          const separator = declaration.indexOf("=");
          if (separator <= 0 || separator === declaration.length - 1) {
            showAlert(`Routage invalide : ${declaration}. Utilisez CIBLE=MODELE.`, true);
            return;
          }
          const target = declaration.slice(0, separator).trim();
          const model = declaration.slice(separator + 1).trim();
          if (!target || !model || Object.prototype.hasOwnProperty.call(modelRoutes, target)) {
            showAlert(`Routage invalide ou cible répétée : ${target || declaration}.`, true);
            return;
          }
          modelRoutes[target] = model;
        }
        payload.model_routes = modelRoutes;
        payload.generate_images = byId("generate-images").checked;
        if (state.sourceMode === "model") {
          if (!state.selectedModel) { showAlert("Choisissez un modèle du catalogue.", true); return; }
          payload.model = state.selectedModel;
          payload.app_name = byId("app-name").value.trim() || "MonProjet";
          payload.description = byId("project-description").value.trim();
        } else {
          payload.spec = byId("spec-input").value;
          if (!payload.spec.trim()) { showAlert("Collez une spec .ml avant de créer le projet.", true); return; }
        }
        button.disabled = true;
        try {
          const created = await api("/projects", { method: "POST", body: JSON.stringify(payload) });
          const project = created.project;
          await api(`/projects/${project.id}/builds`, { method: "POST" });
          byId("project-form").reset();
          byId("app-name").value = "MonProjet";
          byId("generate-images").checked = false;
          state.selectedProjectId = project.id;
          showAlert("Projet créé et construction mise en file. Le suivi reste visible pendant l'attente.");
          await loadConsole();
        } catch (error) { showAlert(error.message, true); }
        finally { button.disabled = false; }
      }

      byId("login-tab").addEventListener("click", () => setAuthMode("login"));
      byId("register-tab").addEventListener("click", () => setAuthMode("register"));
      byId("auth-form").addEventListener("submit", submitAuth);
      byId("logout-button").addEventListener("click", () => { setLoggedOut(); showAlert("Vous êtes déconnecté."); });
      byId("model-mode").addEventListener("click", () => setSourceMode("model"));
      byId("spec-mode").addEventListener("click", () => setSourceMode("spec"));
      byId("project-form").addEventListener("submit", submitProject);
      byId("refresh-button").addEventListener("click", () => loadConsole());
      byId("spec-file").addEventListener("change", async (event) => {
        const file = event.target.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith(".ml")) { showAlert("La spec fournie doit être un fichier .ml.", true); return; }
        byId("spec-input").value = await file.text();
        setSourceMode("spec");
      });

      setAuthMode("login");
      setSourceMode("model");
      loadCatalogue();
      if (state.token) {
        api("/projects").then(async () => {
          try {
            const accountResponse = await api("/account");
            setAuthenticated(accountResponse.account);
            await loadConsole();
            startPolling();
          } catch (_error) { setLoggedOut(); }
        }).catch(() => setLoggedOut());
      }
    })();
  </script>
</body>
</html>'''


def console_response():
    """Retourne la console avec un type de contenu HTML explicite."""
    return HTMLResponse(content=CONSOLE_HTML)
