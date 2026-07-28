(function () {
  'use strict';

  /* ---------------------------------------------------------------
   * Contenu éditorial fourni par l'auteur du projet (aucune route
   * d'API ne le sert : il n'existe que dans ce fichier). Publié tel
   * quel — seuls des sauts de paragraphe sont ajoutés pour la lecture,
   * aucun mot n'est modifié ni inventé.
   * ------------------------------------------------------------- */
  var SECTION_ABOUT = "Je m’appelle Alexandre Moreau et je suis photographe professionnel basé à Paris. Animé par la création visuelle et la quête de précision, je mets mon expertise au service de vos projets depuis maintenant plus de 8 ans.Mon travail se situe à l'intersection de la rigueur technique et de la créativité graphique. Spécialisé dans la photographie de mode, d'architecture et le corporate, je me distingue par un sens aigu de la composition, des lignes épurées et une gestion méticuleuse des contrastes.Ce qui caractérise mon approche, c’est ma capacité à transformer une idée, un visage ou un espace en une image forte. Je ne me contente pas de documenter : je structure le cadre, je sculpte la lumière et j'élimine le superflu pour ne garder que l'essentiel. Chaque projet est une opportunité de traduire un concept en une esthétique visuelle percutante, moderne et mémorable, pensée pour valoriser votre identité, vos designs ou l'image de votre marque.";

  var SECTION_SERVICES = "J'accompagne les marques, les agences, les architectes et les professionnels dans la création d'un patrimoine visuel fort. Mon objectif est de traduire votre identité et vos réalisations à travers des images percutantes, épurées et haut de gamme.Voici mes trois domaines d'intervention :1. Photographie d'Architecture & Design d'IntérieurPour qui : Architectes, designers d'intérieur, promoteurs immobiliers, hôtels et espaces de coworking.Ce que je propose : Un travail méticuleux sur les lignes, les perspectives et la lumière naturelle pour valoriser la structure et l'atmosphère de vos espaces. Idéal pour vos books de réalisations, vos publications éditoriales ou votre communication digitale.2. Mode, Éditorial & LookbooksPour qui : Marques de prêt-à-porter, créateurs d'accessoires, agences de mannequins et magazines.Ce que je propose : Des séances photo en studio ou en extérieur (lifestyle urbain) pour donner vie à vos collections. Je gère la direction artistique visuelle pour créer des lookbooks et des campagnes qui capturent l'ADN de votre marque et marquent les esprits.3. Corporate & Portrait BusinessPour qui : Entreprises, dirigeants, indépendants et équipes créatives.Ce que je propose : Des portraits professionnels modernes et valorisants (loin des clichés figés du corporate classique) ainsi que des reportages en immersion dans vos locaux. Idéal pour humaniser votre site web, alimenter vos réseaux professionnels (LinkedIn) et illustrer vos rapports annuels.";

  /* ---------------------------------------------------------------
   * Utilitaires
   * ------------------------------------------------------------- */
  function h(tag, props) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v === null || v === undefined) return;
      if (k === 'class') node.className = v;
      else if (k === 'dataset') Object.keys(v).forEach(function (dk) { node.dataset[dk] = v[dk]; });
      else if (k.indexOf('on') === 0 && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c === null || c === undefined) continue;
      if (Array.isArray(c)) {
        c.forEach(function (cc) { if (cc) node.appendChild(typeof cc === 'string' ? document.createTextNode(cc) : cc); });
      } else {
        node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
    }
    return node;
  }

  function paragraphsFromText(raw) {
    var MARK = '';
    var t = raw;
    t = t.split('Pour qui :').join(MARK + 'Pour qui :');
    t = t.split('Ce que je propose :').join(MARK + 'Ce que je propose :');
    t = t.replace(/([:.])(\d\.\s)/g, '$1' + MARK + '$2');
    t = t.replace(/\.([A-ZÀ-Ÿ])/g, '.' + MARK + '$1');
    return t.split(MARK).map(function (s) { return s.trim(); }).filter(Boolean);
  }

  function renderEditorial(containerId, raw) {
    var container = document.getElementById(containerId);
    container.innerHTML = '';
    paragraphsFromText(raw).forEach(function (text) {
      var p = document.createElement('p');
      var m;
      if ((m = text.match(/^(\d+\.)\s*([\s\S]*)$/))) {
        p.className = 'service-heading';
        var num = h('span', { class: 'service-num' }, m[1]);
        p.appendChild(num);
        p.appendChild(document.createTextNode(' ' + m[2]));
      } else if ((m = text.match(/^(Pour qui :|Ce que je propose :)\s*([\s\S]*)$/))) {
        p.appendChild(h('strong', {}, m[1]));
        p.appendChild(document.createTextNode(' ' + m[2]));
      } else {
        p.textContent = text;
      }
      container.appendChild(p);
    });
  }

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function apiFetch(path, options) {
    options = options || {};
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (options.auth) {
      var token = getToken();
      if (token) headers['Authorization'] = 'Bearer ' + token;
    }
    return fetch(path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) {
          var msg = (data && data.detail) ? data.detail : ('Erreur ' + res.status);
          var err = new Error(typeof msg === 'string' ? msg : 'Erreur ' + res.status);
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  // type: 'error' | 'success' | undefined (neutral — inherits the
  // surrounding section's own text color, always readable there;
  // only real errors/successes get a special color, so an in-progress
  // message never inherits a color tuned for the wrong background).
  function setFeedback(el, message, type) {
    el.textContent = message || '';
    el.classList.toggle('is-error', type === 'error');
    el.classList.toggle('is-success', type === 'success');
  }

  /* ---------------------------------------------------------------
   * Navigation
   * ------------------------------------------------------------- */
  function initNav() {
    var toggle = qs('#nav-toggle');
    var nav = qs('#site-nav');
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    qsa('#site-nav a').forEach(function (a) {
      a.addEventListener('click', function () {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  /* ---------------------------------------------------------------
   * Galerie (Project) — publique
   * ------------------------------------------------------------- */
  var gallery = {
    limit: 24,
    offset: 0,
    total: 0,
    items: [],
    category: null,
    cache: {}
  };

  function skeletonCards(n) {
    var frag = document.createDocumentFragment();
    for (var i = 0; i < n; i++) {
      frag.appendChild(h('div', { class: 'project-card is-skeleton' }));
    }
    return frag;
  }

  function buildProjectCard(p) {
    var card = h('button', { type: 'button', class: 'project-card', dataset: { id: String(p.id) }, 'aria-label': 'Voir le projet ' + p.title });
    var media = h('span', { class: 'project-card-media' });
    if (p.imageUrl) {
      var img = h('img', { src: p.imageUrl, alt: '', loading: 'lazy' });
      img.addEventListener('error', function () {
        img.remove();
      });
      media.appendChild(img);
    }
    card.appendChild(media);
    card.appendChild(h('span', { class: 'project-card-info' },
      h('span', { class: 'project-card-cat' }, p.category || 'Portfolio'),
      h('span', { class: 'project-card-title' }, p.title)
    ));
    card.addEventListener('click', function () { openProjectDetail(p.id); });
    return card;
  }

  function renderGalleryFilters() {
    var wrap = qs('#gallery-filters');
    wrap.innerHTML = '';
    var categories = [];
    gallery.items.forEach(function (p) {
      if (p.category && categories.indexOf(p.category) === -1) categories.push(p.category);
    });
    if (categories.length < 2) return;
    var all = h('button', { type: 'button', class: 'filter-chip' + (gallery.category === null ? ' is-active' : '') }, 'Tous');
    all.addEventListener('click', function () { gallery.category = null; renderGalleryFilters(); renderGalleryGrid(); });
    wrap.appendChild(all);
    categories.forEach(function (cat) {
      var chip = h('button', { type: 'button', class: 'filter-chip' + (gallery.category === cat ? ' is-active' : '') }, cat);
      chip.addEventListener('click', function () { gallery.category = cat; renderGalleryFilters(); renderGalleryGrid(); });
      wrap.appendChild(chip);
    });
  }

  function renderGalleryGrid() {
    var grid = qs('#gallery-grid');
    grid.innerHTML = '';
    var visible = gallery.category ? gallery.items.filter(function (p) { return p.category === gallery.category; }) : gallery.items;
    if (!visible.length) {
      grid.appendChild(h('p', { class: 'gallery-status' }, 'Aucun projet publié pour l’instant.'));
      return;
    }
    visible.forEach(function (p) { grid.appendChild(buildProjectCard(p)); });
    var more = qs('#gallery-more');
    more.hidden = gallery.offset >= gallery.total;
  }

  function loadGallery(reset) {
    if (reset) {
      gallery.offset = 0;
      gallery.items = [];
      var grid = qs('#gallery-grid');
      grid.innerHTML = '';
      grid.appendChild(skeletonCards(6));
      qs('#gallery-more').hidden = true;
    }
    var params = new URLSearchParams({ limit: gallery.limit, offset: gallery.offset });
    return apiFetch('/project?' + params.toString()).then(function (res) {
      gallery.total = res.total;
      gallery.offset += res.data.length;
      gallery.items = gallery.items.concat(res.data);
      res.data.forEach(function (p) { gallery.cache[String(p.id)] = p; });
      renderGalleryFilters();
      renderGalleryGrid();
    }).catch(function () {
      var grid = qs('#gallery-grid');
      grid.innerHTML = '';
      grid.appendChild(h('p', { class: 'gallery-status is-error' }, 'Impossible de charger les projets pour le moment.'));
    });
  }

  function openProjectDetail(id) {
    var overlay = qs('#project-overlay');
    var cached = gallery.cache[String(id)];
    if (cached) fillProjectDetail(cached);
    overlay.hidden = false;
    document.body.style.overflow = 'hidden';
    if (!cached) {
      apiFetch('/project/' + id).then(function (res) { fillProjectDetail(res.data); }).catch(function () {
        qs('#project-panel-description').textContent = 'Impossible de charger ce projet.';
      });
    }
    location.hash = '#/project/' + id;
  }

  function fillProjectDetail(p) {
    qs('#project-overlay-title').textContent = p.title;
    qs('#project-panel-category').textContent = p.category || '';
    qs('#project-panel-description').textContent = p.description || '';
    var media = qs('#project-panel-media');
    media.innerHTML = '';
    if (p.imageUrl) {
      var img = h('img', { src: p.imageUrl, alt: p.title, style: 'width:100%;height:100%;object-fit:cover;' });
      img.addEventListener('error', function () { img.remove(); });
      media.appendChild(img);
    }
  }

  function closeProjectDetail() {
    qs('#project-overlay').hidden = true;
    document.body.style.overflow = '';
    if (location.hash.indexOf('#/project/') === 0) history.replaceState(null, '', location.pathname + location.search);
  }

  /* ---------------------------------------------------------------
   * Contact (Message) — création publique
   * ------------------------------------------------------------- */
  function initContactForm() {
    var form = qs('#contact-form');
    var feedback = qs('#contact-feedback');
    form.addEventListener('submit', function (evt) {
      evt.preventDefault();
      var author = qs('#contact-author').value.trim();
      var email = qs('#contact-email').value.trim();
      var content = qs('#contact-content').value.trim();
      if (!author || !content) {
        setFeedback(feedback, 'Merci de renseigner votre nom et votre message.', 'error');
        return;
      }
      var submitBtn = qs('#contact-submit');
      submitBtn.disabled = true;
      setFeedback(feedback, 'Envoi en cours…');
      apiFetch('/message', { method: 'POST', body: { author: author, email: email, content: content } })
        .then(function () {
          setFeedback(feedback, 'Message envoyé, merci ! Je reviens vers vous rapidement.', 'success');
          form.reset();
        })
        .catch(function (err) {
          setFeedback(feedback, err.status === 429 ? 'Trop de tentatives, réessayez dans une minute.' : ("Une erreur est survenue, merci de réessayer (" + err.message + ')'), 'error');
        })
        .finally(function () { submitBtn.disabled = false; });
    });
  }

  /* ---------------------------------------------------------------
   * Espace admin
   * ------------------------------------------------------------- */
  var TOKEN_KEY = 'studionova_admin_token';
  var USER_KEY = 'studionova_admin_username';

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function setSession(token, username) {
    if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY);
    if (username) localStorage.setItem(USER_KEY, username); else localStorage.removeItem(USER_KEY);
  }
  function getUsername() { return localStorage.getItem(USER_KEY) || ''; }

  var adminState = {
    projects: { offset: 0, limit: 50, total: 0, items: [], loaded: false },
    messages: { offset: 0, limit: 50, total: 0, items: [], loaded: false }
  };

  function openAdmin() {
    qs('#admin-overlay').hidden = false;
    document.body.style.overflow = 'hidden';
    if (getToken()) {
      showAdminDashboard();
    } else {
      showAdminAuth();
    }
  }

  function closeAdmin() {
    qs('#admin-overlay').hidden = true;
    document.body.style.overflow = '';
    if (location.hash === '#/admin') history.replaceState(null, '', location.pathname + location.search);
  }

  function showAdminAuth() {
    qs('#admin-auth').hidden = false;
    qs('#admin-dashboard').hidden = true;
  }

  function showAdminDashboard() {
    qs('#admin-auth').hidden = true;
    qs('#admin-dashboard').hidden = false;
    qs('#admin-username').textContent = getUsername();
    if (!adminState.projects.loaded) loadAdminProjects(true);
    if (!adminState.messages.loaded) loadAdminMessages(true);
  }

  function initAdminAuthTabs() {
    qsa('[data-auth-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        qsa('[data-auth-tab]').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        var target = btn.getAttribute('data-auth-tab');
        qs('#login-form').hidden = target !== 'login';
        qs('#register-form').hidden = target !== 'register';
      });
    });
  }

  function initAdminDashboardTabs() {
    qsa('[data-admin-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        qsa('[data-admin-tab]').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        var target = btn.getAttribute('data-admin-tab');
        qsa('[data-admin-panel]').forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-admin-panel') !== target;
        });
      });
    });
  }

  function initLoginForm() {
    var form = qs('#login-form');
    var feedback = qs('#login-feedback');
    form.addEventListener('submit', function (evt) {
      evt.preventDefault();
      var username = qs('#login-username').value.trim();
      var password = qs('#login-password').value;
      setFeedback(feedback, 'Connexion…');
      apiFetch('/login', { method: 'POST', body: { username: username, password: password } })
        .then(function (res) {
          setSession(res.access_token, username);
          setFeedback(feedback, '');
          form.reset();
          adminState.projects.loaded = false;
          adminState.messages.loaded = false;
          showAdminDashboard();
        })
        .catch(function (err) {
          setFeedback(feedback, err.status === 401 ? 'Identifiants invalides.' : ('Erreur : ' + err.message), 'error');
        });
    });
  }

  function initRegisterForm() {
    var form = qs('#register-form');
    var feedback = qs('#register-feedback');
    form.addEventListener('submit', function (evt) {
      evt.preventDefault();
      var username = qs('#register-username').value.trim();
      var password = qs('#register-password').value;
      if (password.length < 8) {
        setFeedback(feedback, 'Le mot de passe doit contenir au moins 8 caractères.', 'error');
        return;
      }
      setFeedback(feedback, 'Création du compte…');
      apiFetch('/register', { method: 'POST', body: { username: username, password: password, actor: 'Admin' } })
        .then(function () {
          setFeedback(feedback, 'Compte créé, connexion…');
          return apiFetch('/login', { method: 'POST', body: { username: username, password: password } });
        })
        .then(function (res) {
          setSession(res.access_token, username);
          form.reset();
          adminState.projects.loaded = false;
          adminState.messages.loaded = false;
          showAdminDashboard();
        })
        .catch(function (err) {
          var msg = err.status === 409 ? "Ce nom d'utilisateur existe déjà." : err.message;
          setFeedback(feedback, msg, 'error');
        });
    });
  }

  function initLogout() {
    qs('#admin-logout').addEventListener('click', function () {
      apiFetch('/logout', { method: 'POST', auth: true }).catch(function () {}).finally(function () {
        setSession(null, null);
        adminState.projects = { offset: 0, limit: 50, total: 0, items: [], loaded: false };
        adminState.messages = { offset: 0, limit: 50, total: 0, items: [], loaded: false };
        showAdminAuth();
      });
    });
  }

  /* ---- Projets (admin) ---- */
  function loadAdminProjects(reset) {
    var state = adminState.projects;
    if (reset) { state.offset = 0; state.items = []; }
    var list = qs('#admin-projects-list');
    if (reset) list.innerHTML = '<p class="admin-empty">Chargement…</p>';
    var params = new URLSearchParams({ limit: state.limit, offset: state.offset });
    return apiFetch('/project?' + params.toString(), { auth: false }).then(function (res) {
      state.total = res.total;
      state.offset += res.data.length;
      state.items = state.items.concat(res.data);
      state.loaded = true;
      renderAdminProjects();
    }).catch(function (err) {
      list.innerHTML = '';
      list.appendChild(h('p', { class: 'admin-empty' }, 'Impossible de charger les projets (' + err.message + ').'));
    });
  }

  function renderAdminProjects() {
    var state = adminState.projects;
    qs('#admin-projects-count').textContent = state.total + ' projet' + (state.total > 1 ? 's' : '');
    var list = qs('#admin-projects-list');
    list.innerHTML = '';
    if (!state.items.length) {
      list.appendChild(h('p', { class: 'admin-empty' }, 'Aucun projet pour le moment. Créez le premier avec le bouton ci-dessus.'));
    }
    state.items.forEach(function (p) {
      var thumb = h('span', { class: 'admin-row-thumb' });
      if (p.imageUrl) thumb.style.backgroundImage = 'url("' + p.imageUrl.replace(/"/g, '%22') + '")';
      var editBtn = h('button', { type: 'button' }, 'Modifier');
      editBtn.addEventListener('click', function () { openProjectForm(p); });
      var delBtn = h('button', { type: 'button', class: 'danger' }, 'Supprimer');
      delBtn.addEventListener('click', function () { deleteProject(p); });
      var row = h('div', { class: 'admin-row' },
        thumb,
        h('span', { class: 'admin-row-main' },
          h('p', { class: 'admin-row-title' }, p.title),
          h('p', { class: 'admin-row-sub' }, p.category || '—')
        ),
        h('span', { class: 'admin-row-actions' }, editBtn, delBtn)
      );
      list.appendChild(row);
    });
    qs('#admin-projects-more').hidden = state.offset >= state.total;
  }

  function openProjectForm(project) {
    var form = qs('#project-form');
    form.hidden = false;
    qs('#project-id').value = project ? project.id : '';
    qs('#project-title').value = project ? project.title : '';
    qs('#project-category').value = project ? (project.category || '') : '';
    qs('#project-imageUrl').value = project ? (project.imageUrl || '') : '';
    qs('#project-description').value = project ? (project.description || '') : '';
    setFeedback(qs('#project-form-feedback'), '');
    qs('#project-title').focus();
  }

  function closeProjectForm() {
    qs('#project-form').hidden = true;
    qs('#project-form').reset();
    qs('#project-id').value = '';
  }

  function initProjectForm() {
    qs('#new-project-btn').addEventListener('click', function () { openProjectForm(null); });
    qs('#project-form-cancel').addEventListener('click', closeProjectForm);
    qs('#project-form').addEventListener('submit', function (evt) {
      evt.preventDefault();
      var id = qs('#project-id').value;
      var payload = {
        title: qs('#project-title').value.trim(),
        category: qs('#project-category').value.trim(),
        imageUrl: qs('#project-imageUrl').value.trim(),
        description: qs('#project-description').value.trim()
      };
      var feedback = qs('#project-form-feedback');
      if (!payload.title) {
        setFeedback(feedback, 'Le titre est obligatoire.', 'error');
        return;
      }
      setFeedback(feedback, 'Enregistrement…');
      var req = id
        ? apiFetch('/project/' + id, { method: 'PUT', auth: true, body: payload })
        : apiFetch('/project', { method: 'POST', auth: true, body: payload });
      req.then(function () {
        closeProjectForm();
        loadAdminProjects(true);
        loadGallery(true);
      }).catch(function (err) {
        setFeedback(feedback, err.status === 403 ? "Session expirée, reconnectez-vous." : err.message, 'error');
      });
    });
  }

  function deleteProject(project) {
    if (!window.confirm('Supprimer le projet « ' + project.title + ' » ?')) return;
    apiFetch('/project/' + project.id, { method: 'DELETE', auth: true }).then(function () {
      loadAdminProjects(true);
      loadGallery(true);
    }).catch(function (err) {
      window.alert('Suppression impossible : ' + err.message);
    });
  }

  /* ---- Messages (admin) ---- */
  function loadAdminMessages(reset) {
    var state = adminState.messages;
    if (reset) { state.offset = 0; state.items = []; }
    var list = qs('#admin-messages-list');
    if (reset) list.innerHTML = '<p class="admin-empty">Chargement…</p>';
    var params = new URLSearchParams({ limit: state.limit, offset: state.offset });
    return apiFetch('/message?' + params.toString(), { auth: true }).then(function (res) {
      state.total = res.total;
      state.offset += res.data.length;
      state.items = state.items.concat(res.data);
      state.loaded = true;
      renderAdminMessages();
    }).catch(function (err) {
      list.innerHTML = '';
      list.appendChild(h('p', { class: 'admin-empty' }, 'Impossible de charger les messages (' + err.message + ').'));
    });
  }

  function renderAdminMessages() {
    var state = adminState.messages;
    qs('#admin-messages-count').textContent = state.total + ' message' + (state.total > 1 ? 's' : '');
    var list = qs('#admin-messages-list');
    list.innerHTML = '';
    if (!state.items.length) {
      list.appendChild(h('p', { class: 'admin-empty' }, 'Aucun message reçu pour le moment.'));
    }
    state.items.forEach(function (m) {
      var full = h('div', { class: 'admin-message-full' }, m.content || '');
      full.hidden = true;
      var toggleBtn = h('button', { type: 'button' }, 'Lire');
      toggleBtn.addEventListener('click', function () {
        full.hidden = !full.hidden;
        toggleBtn.textContent = full.hidden ? 'Lire' : 'Masquer';
      });
      var delBtn = h('button', { type: 'button', class: 'danger' }, 'Supprimer');
      delBtn.addEventListener('click', function () { deleteMessage(m); });
      var row = h('div', { class: 'admin-row', style: 'flex-direction:column;align-items:stretch;' },
        h('div', { style: 'display:flex;gap:1em;align-items:center;width:100%;' },
          h('span', { class: 'admin-row-main' },
            h('p', { class: 'admin-row-title' }, m.author),
            h('p', { class: 'admin-row-sub' }, m.email || 'Pas d’email fourni')
          ),
          h('span', { class: 'admin-row-actions' }, toggleBtn, delBtn)
        ),
        full
      );
      list.appendChild(row);
    });
    qs('#admin-messages-more').hidden = state.offset >= state.total;
  }

  function deleteMessage(message) {
    if (!window.confirm('Supprimer le message de « ' + message.author + ' » ?')) return;
    apiFetch('/message/' + message.id, { method: 'DELETE', auth: true }).then(function () {
      loadAdminMessages(true);
    }).catch(function (err) {
      window.alert('Suppression impossible : ' + err.message);
    });
  }

  /* ---------------------------------------------------------------
   * Init
   * ------------------------------------------------------------- */
  document.addEventListener('DOMContentLoaded', function () {
    initNav();
    renderEditorial('about-body', SECTION_ABOUT);
    renderEditorial('services-body', SECTION_SERVICES);
    initContactForm();

    loadGallery(true);
    qs('#gallery-more-btn').addEventListener('click', function () { loadGallery(false); });

    qs('#project-overlay-close').addEventListener('click', closeProjectDetail);
    qs('#project-overlay').addEventListener('click', function (evt) { if (evt.target.id === 'project-overlay') closeProjectDetail(); });

    document.addEventListener('keydown', function (evt) {
      if (evt.key !== 'Escape') return;
      if (!qs('#project-overlay').hidden) closeProjectDetail();
      if (!qs('#admin-overlay').hidden) closeAdmin();
    });

    initAdminAuthTabs();
    initAdminDashboardTabs();
    initLoginForm();
    initRegisterForm();
    initLogout();
    initProjectForm();
    qs('#admin-projects-more-btn').addEventListener('click', function () { loadAdminProjects(false); });
    qs('#admin-messages-more-btn').addEventListener('click', function () { loadAdminMessages(false); });

    qs('#open-admin').addEventListener('click', openAdmin);
    qs('#admin-overlay-close').addEventListener('click', closeAdmin);
    qs('#admin-overlay').addEventListener('click', function (evt) { if (evt.target.id === 'admin-overlay') closeAdmin(); });

    if (location.hash === '#/admin') openAdmin();
    var projectMatch = location.hash.match(/^#\/project\/(\d+)$/);
    if (projectMatch) openProjectDetail(projectMatch[1]);
  });
})();
