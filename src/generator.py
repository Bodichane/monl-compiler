import os
import secrets
import hashlib
import json
import colorsys
import re
import html
from ast_validator import MonLangAST
from parser import parse_monlang_file

# AJOUT (roadmap, "je devrais me retrouver sur une autre page") : bloc JS
# du tableau de bord, partage entre l'ancienne integration (desormais
# retiree de landing.html) et la nouvelle page dediee '/app'. Isole ici en
# tant que texte simple (pas un f-string) : le seul point d'interpolation,
# '{capabilities_json}', est substitue par .replace() dans
# _generate_dashboard_page plutot que par une f-string, pour ne pas avoir a
# doubler toutes les accolades JS de ce bloc.
DASHBOARD_JS_BLOCK = '''
    var CAPABILITIES = {capabilities_json};

    function decodeJwtActor(token) {
        try {
            var payload = token.split('.')[1];
            var padded = payload.replace(/-/g, '+').replace(/_/g, '/');
            while (padded.length % 4) padded += '=';
            var json = decodeURIComponent(atob(padded).split('').map(function (c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(json).actor || null;
        } catch (err) { return null; }
    }

    function dashInputHTML(name, type) {
        if (type === 'Boolean') {
            return '<label class="field field-checkbox"><input type="checkbox" data-field="' + name + '"> ' + name + '</label>';
        }
        var inputType = (type === 'Integer' || type === 'Float' || type === 'Money') ? 'number'
            : (type === 'Email' ? 'email' : (type === 'DateTime' || type === 'Date' ? 'date' : 'text'));
        if (type === 'Text') {
            return '<label class="field">' + name + '<textarea data-field="' + name + '" rows="2"></textarea></label>';
        }
        return '<label class="field">' + name + '<input type="' + inputType + '" data-field="' + name + '"></label>';
    }

    function collectDashFields(container) {
        var body = {};
        container.querySelectorAll('[data-field]').forEach(function (el) {
            body[el.dataset.field] = el.type === 'checkbox' ? el.checked
                : (el.type === 'number' ? Number(el.value || 0) : el.value);
        });
        return body;
    }

    // CORRECTIF (roadmap, "session expirée") : les jetons JWT expirent (1h,
    // voir la revendication 'exp' du payload). Avant ce correctif, un appel
    // qui échouait avec 401 après expiration affichait juste "Erreur : ..."
    // sans dire pourquoi ni quoi faire. Toute requête authentifiée de cette
    // page passe désormais par 'apiFetch', qui détecte le 401, efface le
    // jeton, et renvoie vers '/' avec un indicateur -- la landing peut
    // alors afficher un message clair plutôt qu'un échec muet.
    function apiFetch(url, opts) {
        return fetch(url, opts).then(function (res) {
            if (res.status === 401) {
                try { sessionStorage.removeItem('monlang_token'); } catch (err) {}
                window.location.href = '/?session_expired=1';
                throw new Error('session_expired');
            }
            return res;
        });
    }

    function renderEntityCard(entity, cap, token) {
        var actions = cap.actions;
        var fieldsHTML = Object.keys(cap.fields).map(function (f) { return dashInputHTML(f, cap.fields[f]); }).join('');
        var buttons = '';
        if (actions.indexOf('Create') !== -1) buttons += '<button type="button" class="cta cta-primary" data-act="create">Créer</button>';
        if (actions.indexOf('Read') !== -1) buttons += '<button type="button" class="cta cta-secondary" data-act="list">Rafraîchir la liste</button>';
        var idRow = '';
        if (actions.indexOf('Update') !== -1 || actions.indexOf('Delete') !== -1) {
            idRow = '<div class="dash-id-row">' +
                '<label class="field">ID<input type="number" class="dash-id"></label>' +
                (actions.indexOf('Update') !== -1 ? '<button type="button" class="cta cta-secondary" data-act="update">Modifier</button>' : '') +
                (actions.indexOf('Delete') !== -1 ? '<button type="button" class="cta cta-secondary" data-act="delete">Supprimer</button>' : '') +
                '</div>';
        }
        var card = document.createElement('div');
        card.className = 'dash-card';
        card.innerHTML = '<h3>' + entity + '</h3><p class="dash-hint">' + actions.join(' · ') + '</p>' +
            fieldsHTML + '<div class="dash-actions">' + buttons + '</div>' + idRow +
            '<div class="dash-list"></div><p class="dash-status"></p>';

        var status = card.querySelector('.dash-status');
        var list = card.querySelector('.dash-list');
        var setStatus = function (msg, ok) { status.textContent = msg; status.className = 'dash-status ' + (ok ? 'ok' : 'err'); };
        var canUpdate = actions.indexOf('Update') !== -1;
        var canDelete = actions.indexOf('Delete') !== -1;
        var canRead = actions.indexOf('Read') !== -1;

        function loadList() {
            if (!canRead) return;
            list.innerHTML = '<p class="hint">Chargement…</p>';
            apiFetch('/' + entity.toLowerCase() + '?limit=10', { headers: { 'Authorization': 'Bearer ' + token } })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    var rows = (data && data.data) || [];
                    if (!rows.length) { list.innerHTML = '<p class="hint">Aucun enregistrement pour l\\'instant.</p>'; return; }
                    list.innerHTML = '';
                    rows.forEach(function (row) { list.appendChild(renderRow(row)); });
                })
                .catch(function () { list.innerHTML = '<p class="hint">Erreur de chargement.</p>'; });
        }

        // CORRECTIF (roadmap, "tout ce qui est créé devrait apparaître
        // directement") -- suite : chaque ligne affiche désormais ses
        // propres boutons "Modifier"/"Supprimer" (pré-remplis avec le bon
        // ID) au lieu d'exiger de le retaper dans le champ à part. Le champ
        // ID manuel reste disponible pour agir sur un enregistrement qui
        // n'est pas (ou plus) dans les 10 derniers chargés.
        function renderRow(row) {
            var div = document.createElement('div');
            div.textContent = JSON.stringify(row);
            var summary = div.innerHTML.slice(0, 70);
            var rowEl = document.createElement('div');
            rowEl.className = 'dash-row';
            var rowButtons = '';
            if (canUpdate) rowButtons += '<button type="button" class="cta cta-secondary" data-row-act="edit">Modifier</button>';
            if (canDelete) rowButtons += '<button type="button" class="cta cta-secondary" data-row-act="delete">Supprimer</button>';
            rowEl.innerHTML = '<span class="dash-row-id">#' + row.id + '</span><span>' + summary + '</span>' +
                '<span class="dash-row-actions">' + rowButtons + '</span>';
            var editBtn = rowEl.querySelector('[data-row-act="edit"]');
            if (editBtn) editBtn.addEventListener('click', function () {
                card.querySelector('.dash-id').value = row.id;
                Object.keys(cap.fields).forEach(function (f) {
                    var el = card.querySelector('[data-field="' + f + '"]');
                    if (!el) return;
                    if (el.type === 'checkbox') el.checked = !!row[f]; else el.value = row[f] == null ? '' : row[f];
                });
                setStatus('Champs pré-remplis avec #' + row.id + ' — modifiez puis cliquez "Modifier".', true);
            });
            var deleteRowBtn = rowEl.querySelector('[data-row-act="delete"]');
            if (deleteRowBtn) deleteRowBtn.addEventListener('click', function () {
                if (!window.confirm('Supprimer l\\'enregistrement #' + row.id + ' ?')) return;
                doDelete(row.id);
            });
            return rowEl;
        }

        function doUpdate(id) {
            apiFetch('/' + entity.toLowerCase() + '/' + id, {
                method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify(collectDashFields(card)),
            })
                .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
                .then(function (r) {
                    setStatus(r.ok ? 'Modifié.' : ('Erreur : ' + (r.d.detail || '')), r.ok);
                    if (r.ok) loadList();
                })
                .catch(function (err) { if (err.message !== 'session_expired') setStatus('Erreur réseau.', false); });
        }

        function doDelete(id) {
            apiFetch('/' + entity.toLowerCase() + '/' + id, { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + token } })
                .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }).catch(function () { return { ok: res.ok, d: {} }; }); })
                .then(function (r) {
                    setStatus(r.ok ? 'Supprimé.' : ('Erreur : ' + (r.d.detail || '')), r.ok);
                    if (r.ok) loadList();
                })
                .catch(function (err) { if (err.message !== 'session_expired') setStatus('Erreur réseau.', false); });
        }

        var createBtn = card.querySelector('[data-act="create"]');
        if (createBtn) createBtn.addEventListener('click', function () {
            apiFetch('/' + entity.toLowerCase(), {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify(collectDashFields(card)),
            })
                .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
                .then(function (r) {
                    setStatus(r.ok ? ('Créé (id=' + r.d.id + ').') : ('Erreur : ' + (r.d.detail || '')), r.ok);
                    if (r.ok) loadList();
                })
                .catch(function (err) { if (err.message !== 'session_expired') setStatus('Erreur réseau.', false); });
        });

        var listBtn = card.querySelector('[data-act="list"]');
        if (listBtn) listBtn.addEventListener('click', loadList);

        var updateBtn = card.querySelector('[data-act="update"]');
        if (updateBtn) updateBtn.addEventListener('click', function () { doUpdate(card.querySelector('.dash-id').value); });

        var deleteBtn = card.querySelector('[data-act="delete"]');
        if (deleteBtn) deleteBtn.addEventListener('click', function () {
            var id = card.querySelector('.dash-id').value;
            if (!window.confirm('Supprimer l\\'enregistrement #' + id + ' ?')) return;
            doDelete(id);
        });

        loadList();
        return card;
    }

    function renderFunctionCard(name, cap, token) {
        var card = document.createElement('div');
        card.className = 'dash-card';
        var inputsHTML = cap.inputs.map(function (name2) { return dashInputHTML(name2, 'String'); }).join('');
        card.innerHTML = '<h3>⚙ ' + name + '</h3>' +
            (cap.description ? '<p class="dash-hint">' + cap.description + '</p>' : '') +
            inputsHTML + '<div class="dash-actions"><button type="button" class="cta cta-primary" data-act="run">Exécuter</button></div>' +
            '<p class="dash-status"></p>';
        var status = card.querySelector('.dash-status');
        card.querySelector('[data-act="run"]').addEventListener('click', function () {
            apiFetch('/workflow/' + cap.tag.toLowerCase() + '/' + name.toLowerCase(), {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify(collectDashFields(card)),
            })
                .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
                .then(function (r) {
                    status.textContent = r.ok ? 'Exécuté avec succès.' : ('Erreur : ' + (r.d.detail || ''));
                    status.className = 'dash-status ' + (r.ok ? 'ok' : 'err');
                })
                .catch(function (err) {
                    if (err.message === 'session_expired') return;
                    status.textContent = 'Erreur réseau.'; status.className = 'dash-status err';
                });
        });
        return card;
    }

    function renderDashboard(token) {
        try {
            var actor = decodeJwtActor(token);
            var content = document.getElementById('dashboardContent');
            var cap = actor ? CAPABILITIES[actor] : null;
            content.innerHTML = '';
            if (!cap || (Object.keys(cap.entities).length === 0 && Object.keys(cap.functions).length === 0)) {
                content.innerHTML = '<p class="hint">Aucune action disponible pour ce compte.</p>';
            } else {
                Object.keys(cap.entities).forEach(function (entity) {
                    content.appendChild(renderEntityCard(entity, cap.entities[entity], token));
                });
                Object.keys(cap.functions).forEach(function (name) {
                    content.appendChild(renderFunctionCard(name, cap.functions[name], token));
                });
            }
        } catch (err) { console.error('[app] tableau de bord indisponible :', err); }
    }

'''


class MonLangSecureGenerator:
    def __init__(self, normalized_ast):
        self.ast = normalized_ast
        self.app_name = normalized_ast["meta"]["appName"]
        self.entities = normalized_ast["schema"]["entities"]
        self.relations = normalized_ast["schema"]["relations"]
        self.workflows = normalized_ast["security"]["workflows"]
        self.actors = normalized_ast["security"]["actors"]
        self.custom_functions = normalized_ast["sandbox_ai"]["custom_functions"]
        # AJOUT (post-v6, roadmap) : map "Entite.Action" -> entité propriétaire,
        # issue des règles 'ownedBy' validées par ast_validator.py.
        self.ownership = normalized_ast["security"].get("ownership", {})
        # AJOUT (roadmap, cas d'usage portfolio) : ensemble des "Entite.Action"
        # marquées 'public' — ces routes ne requièrent aucune authentification.
        # Reconstruit en tuples (entité, action) pour être comparable
        # directement à (base_target, act_type) lors de la génération des routes.
        self.public_actions = {
            tuple(ref.split(".", 1)) for ref in normalized_ast["security"].get("public", [])
        }
        # AJOUT (roadmap, écosystème de capacités -- brique 2) : ensemble des
        # "Entite.champ" marquées 'hidden' — voir _generate_secure_fastapi,
        # où ces champs sont retirés des réponses de lecture (liste et
        # détail) de leur entité, quel que soit qui appelle la route.
        # Regroupé par entité (plutôt qu'un set de tuples comme
        # public_actions) car c'est la forme directement utile à la
        # génération : "quels champs retirer pour CETTE entité".
        self.hidden_fields_by_entity = {}
        for ref in normalized_ast["security"].get("hidden_fields", []):
            entity, field = ref.split(".", 1)
            self.hidden_fields_by_entity.setdefault(entity, []).append(field)
        # AJOUT (roadmap, écosystème de capacités -- brique 3, généralisée en
        # brique 4) : règles 'decrements'/'increments' regroupées par entité
        # déclenchante — voir _generate_secure_fastapi, où la route Create de
        # cette entité gagne une étape supplémentaire après l'insertion
        # (incrémenter/décrémenter le champ ciblé sur la ligne liée,
        # retrouvée via la colonne de clé étrangère que la relation validée
        # garantit d'exister).
        self.reputation_rules_by_trigger = {}
        for r in normalized_ast["security"].get("reputation_rules", []):
            self.reputation_rules_by_trigger.setdefault(r["trigger_entity"], []).append(r)
        # AJOUT (roadmap, écosystème de capacités -- brique 5) : règles
        # 'categorized' regroupées par entité — voir _generate_secure_fastapi,
        # où les routes Read (liste + détail) de cette entité remplacent le
        # champ numérique ciblé par son libellé de catégorie avant de
        # renvoyer la réponse.
        self.categorized_fields_by_entity = {}
        for cf in normalized_ast["security"].get("categorized_fields", []):
            self.categorized_fields_by_entity.setdefault(cf["entity"], []).append(cf)
        # AJOUT (roadmap, contrôle du rendu visuel) : surcharges explicites du
        # thème/ordre/champ principal par entité, issues des blocs 'ui'.
        self.ui_overrides = normalized_ast.get("ui", {})
        # AJOUT (roadmap, front marketing) : configuration du bloc 'landing'
        # optionnel (None si absent de la spec -> comportement inchangé,
        # '/' redirige vers /docs comme avant).
        self.landing_config = normalized_ast.get("landing")
        # AJOUT (roadmap, écosystème de capacités -- brique 1) : capacités
        # déclarées via 'capability'. Purement informatif à ce stade -- rien
        # dans generate_all() ne branche encore dessus, puisque
        # l'authentification (seule capacité connue pour l'instant) est déjà
        # générée systématiquement quoi qu'il arrive. Les capacités futures
        # (masquage de champ, accès à deux parties) seront les premières à
        # réellement changer un comportement de génération selon ce qui est
        # déclaré ici.
        self.capabilities = normalized_ast.get("capabilities", [])

    def _compute_fk_placements(self):
        """CORRECTIF (roadmap) : jusqu'ici, seul le type de relation 'hasMany'
        produisait réellement une colonne de clé étrangère — 'belongsTo' et
        'hasOne' étaient acceptés par la grammaire mais totalement ignorés par
        le générateur (aucune colonne, aucun effet). Cette méthode calcule,
        pour les 3 types de relation, quelle entité porte la colonne de clé
        étrangère et vers quelle entité "propriétaire" elle pointe :
          - hasMany  : "A hasMany B" -> B porte la colonne a_id (A est parent)
          - hasOne   : idem hasMany, avec en plus une contrainte UNIQUE (1-1)
          - belongsTo: "A belongsTo B" -> A porte la colonne b_id (B est parent)
        Retourne : {entité_qui_porte_la_colonne: [{"fk_column", "owner_entity", "unique"}]}
        """
        placements = {}
        for rel in self.relations:
            if rel["type"] in ("hasMany", "hasOne"):
                owner_entity, held_entity = rel["source"], rel["target"]
            elif rel["type"] == "belongsTo":
                owner_entity, held_entity = rel["target"], rel["source"]
            else:
                continue
            placements.setdefault(held_entity, []).append({
                "fk_column": f"{owner_entity.lower()}_id",
                "owner_entity": owner_entity,
                "unique": rel["type"] == "hasOne",
            })
        return placements

    def _get_incoming_relation(self, entity):
        """Retourne la première relation entrante sur 'entity' (hasMany, hasOne,
        ou belongsTo — toutes désormais gérées, voir _compute_fk_placements),
        celle qui fournit la colonne de clé étrangère dans schema.sql, ou None
        s'il n'y en a pas. Utilisé pour peupler cette colonne à la création et
        pour le contrôle d'accès par propriété ('ownedBy')."""
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return None
        first = placements[0]
        return {"source": first["owner_entity"], "fk_column": first["fk_column"]}

    def generate_all(self):
        """Déclenche la génération déterministe et balise l'échappatoire IA.
        SUPPRESSION (roadmap, sur demande explicite) : MonLang ne génère plus
        aucun front '/ui' — seul le back-office CRUD historique (React, voir
        ancien point 19 de docs/design_decisions.md) a été retiré. Les deux
        seules sources de front possibles sont désormais : (1) '/docs', la
        documentation Swagger/OpenAPI de FastAPI, toujours disponible sans
        rien configurer ; (2) 'landing.html' sur '/', UNIQUEMENT si un bloc
        'landing' est présent dans la spec — voir _generate_landing, mode
        'ai' (IA locale) ou 'template' (fichier importé par l'utilisateur)."""
        print(f"🏗️  Génération du socle déterministe réel pour '{self.app_name}'...")
        if self.capabilities:
            print(f"🧩 Capacités déclarées : {', '.join(self.capabilities)} (voir docs/design_decisions.md point 24).")
        
        sql_content = self._generate_sql()
        api_content = self._generate_secure_fastapi()
        sandbox_content = self._generate_ai_sandbox()
        
        # Détermination des chemins physiques
        base_dir = os.path.dirname(__file__)
        sql_path = os.path.join(base_dir, "../schema.sql")
        api_path = os.path.join(base_dir, "../app.py")
        sandbox_path = os.path.join(base_dir, "../sandbox_ai.py")
        secret_path = os.path.join(base_dir, "../.jwt_secret")

        # CORRECTIF (roadmap, faille signalée) : le secret JWT était jusqu'ici
        # une chaîne fixe codée en dur dans generator.py, IDENTIQUE dans
        # absolument toutes les applications générées par MonLang. Un token
        # forgé pour une app était donc valide sur n'importe quelle autre
        # app générée par le même compilateur — quiconque lit le code source
        # public de MonLang connaît la clé secrète de toutes les applications
        # qui en sont issues. Un secret aléatoire de 32 octets est désormais
        # généré une seule fois par projet, à la première compilation, et
        # conservé dans '.jwt_secret' (à ajouter au .gitignore, jamais commité).
        # Recompiler la spec NE régénère PAS ce secret (pour ne pas invalider
        # les sessions déjà émises) — il faut le supprimer manuellement pour
        # en forcer le renouvellement.
        if not os.path.exists(secret_path):
            new_secret = secrets.token_hex(32)
            with open(secret_path, "w", encoding="utf-8") as f:
                f.write(new_secret)
            print(f"🔑 Nouveau secret JWT généré et stocké dans '.jwt_secret' (32 octets, aléatoire, propre à ce projet).")
        else:
            print("🔑 Secret JWT existant conservé ('.jwt_secret' déjà présent).")

        with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
        with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
        with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)

        print("💾 Socle généré : 'schema.sql', 'app.py' et 'sandbox_ai.py' sont prêts !")

        # AJOUT (roadmap, front marketing) : génération de 'landing.html' —
        # uniquement si un bloc 'landing' est présent dans la spec (aucun
        # changement pour les apps existantes). Toujours un gabarit 100%
        # déterministe à ce stade, que le mode soit 'ai' ou 'template' : dans
        # le cas 'ai', l'enrichissement par le LLM local est une étape
        # SÉPARÉE et non bloquante (voir ai_landing_filler.py, même pattern
        # que ai_sandbox_filler.py pour les fonctions 'custom') — la landing
        # déterministe ci-dessous EST déjà le filet de sécurité si l'IA est
        # indisponible, pas un brouillon en attente d'IA pour fonctionner.
        if self.landing_config:
            landing_content = self._generate_landing()
            landing_path = os.path.join(base_dir, "../landing.html")
            with open(landing_path, "w", encoding="utf-8") as f:
                f.write(landing_content)
            print(f"🖼️  'landing.html' généré (mode '{self.landing_config['mode']}'), servi sur '/'.")

            # AJOUT (roadmap, "je devrais me retrouver sur une autre page") :
            # 'dashboard.html', servi sur '/app', uniquement authentifié
            # (jeton lu depuis sessionStorage). Toujours déterministe, jamais
            # concerné par l'échappotoire IA (aucun texte à y rédiger).
            dashboard_content = self._generate_dashboard_page()
            dashboard_path = os.path.join(base_dir, "../dashboard.html")
            with open(dashboard_path, "w", encoding="utf-8") as f:
                f.write(dashboard_content)
            print("📋 'dashboard.html' généré, servi sur '/app' (accès protégé par jeton).")

    def _map_type_to_sql(self, type_str):
        mapping = {
            "String": "VARCHAR(255)", "Text": "TEXT", "Integer": "INTEGER",
            "Float": "REAL", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID", "Money": "NUMERIC(10, 2)"
        }
        return mapping.get(type_str, "TEXT")

    def _get_row_column_names(self, entity):
        """Reconstruit l'ordre exact des colonnes SQL d'une entité (id, puis
        attributs déclarés dans l'ordre, puis clé(s) étrangère(s) entrante(s)),
        pour convertir les tuples renvoyés par sqlite3 en objets nommés côté
        API plutôt que des tableaux positionnels — nécessaire pour un rendu
        front lisible (roadmap : front visuel, pas de JSON brut)."""
        columns = ["id"] + list(self.entities[entity].keys())
        for placement in self._compute_fk_placements().get(entity, []):
            columns.append(placement["fk_column"])
        return columns

    def _emit_categorization_lines(self, categorized_field, row_var, indent):
        """AJOUT (roadmap, écosystème de capacités -- brique 5) : génère le
        code source Python qui remplace, sur un dict de ligne déjà nommé
        (row_var), un champ numérique par son libellé de catégorie
        (ex. 'likes' -> 'likes_category'). La validation dans
        ast_validator.py garantit que 'clauses' se termine toujours par
        exactement un palier 'otherwise', et que tous les paliers 'below'
        qui précèdent sont strictement croissants -- donc la chaîne
        if/elif/.../else générée ici est toujours syntaxiquement valide et
        couvre nécessairement toute valeur possible."""
        field = categorized_field["field"]
        clauses = categorized_field["clauses"]
        cat_key = f"{field}_category"
        # repr() plutôt qu'une interpolation manuelle entre guillemets : le
        # libellé vient d'un STRING_LITERAL utilisateur et peut contenir des
        # apostrophes/antislashs -- repr() produit toujours un littéral
        # Python syntaxiquement valide, quel que soit le contenu.
        lines = [f"{indent}_v = {row_var}.pop('{field}')"]
        for i, clause in enumerate(clauses):
            label_literal = repr(clause["label"])
            if "otherwise" in clause:
                lines.append(f"{indent}else: {row_var}['{cat_key}'] = {label_literal}")
            else:
                keyword = "if" if i == 0 else "elif"
                lines.append(f"{indent}{keyword} _v < {clause['below']}: {row_var}['{cat_key}'] = {label_literal}")
        return lines

    def _generate_sql(self):
        """Génère un schéma SQL déterministe préservant les données existantes (Bug #3)."""
        sql_lines = [f"-- Socle DB Déterministe généré automatiquement pour {self.app_name}\n"]

        # AJOUT (roadmap) : table système du registre d'utilisateurs réel. Elle
        # existe indépendamment de la spec (toute application générée en a
        # besoin pour /register et /login), donc elle est injectée ici plutôt
        # que déclarée par l'utilisateur dans le DSL.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monlang_users (")
        sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
        sql_lines.append("    username VARCHAR(255) UNIQUE NOT NULL,")
        sql_lines.append("    password_hash VARCHAR(255) NOT NULL,")
        sql_lines.append("    salt VARCHAR(255) NOT NULL,")
        sql_lines.append("    actor VARCHAR(255) NOT NULL")
        sql_lines.append(");\n")

        # AJOUT (roadmap, révocation de token) : liste noire persistante des
        # tokens explicitement révoqués via /logout, avant leur expiration
        # naturelle.
        sql_lines.append("CREATE TABLE IF NOT EXISTS _monlang_revoked_tokens (")
        sql_lines.append("    jti VARCHAR(64) PRIMARY KEY,")
        sql_lines.append("    revoked_at TIMESTAMP NOT NULL")
        sql_lines.append(");\n")

        # CORRECTIF (roadmap) : placement des FK généralisé aux 3 types de
        # relation (hasMany, hasOne, belongsTo) via _compute_fk_placements,
        # au lieu de ne traiter que 'hasMany' comme précédemment.
        fk_placements = self._compute_fk_placements()

        for ent_name, attrs in self.entities.items():
            # CORRECTIF (roadmap, bug signalé -- collision avec un mot-clé SQL
            # réservé) : une entité nommée "Order" (ou toute autre déclarée
            # dans la spec qui coïncide avec un mot-clé SQLite comme ORDER,
            # GROUP, SELECT...) faisait échouer schema.sql sans que rien ne le
            # signale clairement à la compilation -- juste une erreur SQL
            # silencieuse au démarrage du serveur. Les noms de table ET de
            # colonne sont désormais systématiquement entre guillemets
            # doubles (échappement d'identifiant standard SQL, supporté par
            # SQLite), qu'ils entrent ou non en collision -- plus fiable que
            # de maintenir une liste de mots réservés à jour.
            sql_lines.append(f'CREATE TABLE IF NOT EXISTS "{ent_name.lower()}" (')
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            for attr_name, attr_type in attrs.items():
                sql_type = self._map_type_to_sql(attr_type)
                sql_lines.append(f'    "{attr_name}" {sql_type},')

            # CORRECTIF (roadmap, second bug -- masqué jusqu'ici par le
            # premier) : les colonnes de clé étrangère et leur contrainte
            # 'FOREIGN KEY' étaient auparavant émises l'une après l'autre,
            # par relation. Dès qu'une entité a 2 relations ou plus (ex.
            # OrderItem -> Order ET Product), ça produit une colonne après
            # une contrainte de table -- invalide en SQL standard (SQLite y
            # compris) : toutes les définitions de colonnes doivent précéder
            # toute contrainte de table. Les colonnes FK sont maintenant
            # toutes déclarées d'abord, puis toutes les contraintes
            # 'FOREIGN KEY' ensuite.
            for placement in fk_placements.get(ent_name, []):
                fk_col = placement["fk_column"]
                unique_kw = " UNIQUE" if placement["unique"] else ""
                sql_lines.append(f'    "{fk_col}" INTEGER{unique_kw},')

            for placement in fk_placements.get(ent_name, []):
                fk_col = placement["fk_column"]
                owner_table = placement["owner_entity"].lower()
                sql_lines.append(f'    FOREIGN KEY ("{fk_col}") REFERENCES "{owner_table}"(id),')

            sql_lines[-1] = sql_lines[-1].rstrip(",")
            sql_lines.append(");\n")
        return "\n".join(sql_lines)

    def _generate_secure_fastapi(self):
        """Génère l'API avec persistance SQLite, authentification JWT et schémas IA stricts."""
        actors_literal = ", ".join(f'"{a}"' for a in self.actors)
        api_lines = [
            "# API Déterministe Sécurisée par défaut - Ne pas modifier à la main",
            "from fastapi import FastAPI, HTTPException, Header, Depends, Request",
            "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
            "from pydantic import BaseModel",
            "from typing import List, Optional, Any",
            "import sqlite3",
            "import jwt",
            "import datetime",
            "import hashlib",
            "import os",
            "import secrets",
            "import sandbox_ai  # Importation de l'échappatoire IA isolé\n",
            f"app = FastAPI(title='{self.app_name} - Secure Core')",
            "DB_FILE = 'app.db'",
            # CORRECTIF (roadmap, faille signalée) : secret JWT lu depuis un
            # fichier propre à ce projet ('.jwt_secret', généré par
            # generator.py à la compilation), au lieu d'une chaîne fixe
            # partagée par toutes les applications générées par MonLang.
            "try:",
            "    with open('.jwt_secret', 'r', encoding='utf-8') as _f:",
            "        JWT_SECRET = _f.read().strip()",
            "    if not JWT_SECRET:",
            "        raise ValueError('.jwt_secret est vide')",
            "except (FileNotFoundError, ValueError) as _e:",
            "    raise RuntimeError(",
            "        \"Fichier '.jwt_secret' introuvable ou vide. Il est généré automatiquement \"",
            "        \"par le compilateur MonLang — relancez 'python3 src/main.py <spec.yaml>' \"",
            "        \"depuis la racine du projet avant de démarrer le serveur.\"",
            "    ) from _e",
            "JWT_ALGORITHM = 'HS256'",
            f"VALID_ACTORS = [{actors_literal}]\n",
            "security_bearer = HTTPBearer()\n",
            # CORRECTIF (roadmap, révocation de token) : la vérification du
            # token est centralisée dans une seule fonction, appelée par les
            # deux dépendances ci-dessous — avant, chacune redécodait le token
            # indépendamment, ce qui aurait pu faire oublier la vérification
            # de révocation dans l'une des deux lors d'une future modification.
            "def _decode_and_verify_token(credentials: HTTPAuthorizationCredentials) -> dict:",
            "    try:",
            "        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])",
            "    except jwt.PyJWTError:",
            "        raise HTTPException(status_code=401, detail='Token invalide ou expiré')",
            "    jti = payload.get('jti')",
            "    if jti:",
            "        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()",
            "        cursor.execute('SELECT 1 FROM _monlang_revoked_tokens WHERE jti = ?', (jti,))",
            "        revoked = cursor.fetchone(); conn.close()",
            "        if revoked:",
            "            raise HTTPException(status_code=401, detail='Ce token a été révoqué (déconnexion effectuée).')",
            "    return payload\n",

            "def verify_jwt_and_get_actor(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> str:",
            "    return _decode_and_verify_token(credentials).get('actor')\n",

            # AJOUT (post-v6, roadmap) : dépendance séparée pour récupérer l'identité
            # numérique (user_id) portée par le token, utilisée par le contrôle
            # d'accès par propriété ('ownedBy') et par le peuplement automatique
            # des colonnes de clé étrangère à la création d'un enregistrement.
            "def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> int:",
            "    return _decode_and_verify_token(credentials).get('user_id', 0)\n",
            
            "@app.on_event('startup')",
            "def init_db():",
            "    conn = sqlite3.connect(DB_FILE)",
            "    try:",
            "        with open('schema.sql', 'r', encoding='utf-8') as f:",
            "            conn.executescript(f.read())",
            "    except Exception as e:",
            "        print(f'ℹ️ DB déjà initialisée ou erreur de script: {e}')",
            "    finally:",
            "        conn.close()\n",

            # CORRECTIF (post-v6, roadmap point 4a) : redirection de la racine vers
            # la documentation Swagger/OpenAPI auto-générée par FastAPI. Ça donne un
            # « front minimal » gratuit — utilisable au navigateur, sans écrire une
            # seule requête HTTP à la main — en attendant un vrai front dédié.
            # AJOUT (roadmap, "landing" IA/template) : si un bloc 'landing' est
            # présent dans la spec, la racine sert désormais 'landing.html' (généré
            # par _generate_landing() — voir cette méthode pour le détail des deux
            # modes 'ai'/'template') au lieu de rediriger vers /docs. Comportement
            # inchangé pour toute app sans bloc 'landing' (rétrocompatible).
            "from fastapi.responses import RedirectResponse, HTMLResponse\n",
            "@app.get('/', include_in_schema=False, response_class=HTMLResponse)" if self.landing_config
            else "@app.get('/', include_in_schema=False)",
            "async def root():",
            (
                "    try:\n"
                "        with open('landing.html', 'r', encoding='utf-8') as f:\n"
                "            return HTMLResponse(content=f.read())\n"
                "    except FileNotFoundError:\n"
                "        return RedirectResponse(url='/docs')\n"
            ) if self.landing_config else "    return RedirectResponse(url='/docs')\n",
        ]

        if self.landing_config:
            # AJOUT (roadmap, "je devrais me retrouver sur une autre page") :
            # route dédiée pour 'dashboard.html'. La garde d'accès (jeton
            # requis) est côté client (sessionStorage, voir
            # _generate_dashboard_page) -- cette route sert le fichier à
            # quiconque la demande, exactement comme '/' sert 'landing.html'
            # à quiconque ; c'est chaque appel API individuel fait DEPUIS
            # cette page qui reste vérifié par le serveur, comme toujours.
            api_lines += [
                "@app.get('/app', include_in_schema=False, response_class=HTMLResponse)",
                "async def app_dashboard():",
                (
                    "    try:\n"
                    "        with open('dashboard.html', 'r', encoding='utf-8') as f:\n"
                    "            return HTMLResponse(content=f.read())\n"
                    "    except FileNotFoundError:\n"
                    "        return RedirectResponse(url='/')\n"
                ),
            ]

        api_lines += [

            # CORRECTIF (roadmap) : remplacement du modèle "actor/user_id
            # auto-déclarés par le client" par un vrai registre d'utilisateurs
            # (table _monlang_users, mot de passe haché avec sel via PBKDF2-
            # HMAC-SHA256, 100 000 itérations — pas de dépendance externe type
            # bcrypt nécessaire). LIMITE ASSUMÉE (prototype) : pas de politique
            # de mot de passe, pas de vérification d'email, pas de récupération
            # de compte — voir docs/design_decisions.md.
            "class RegisterRequest(BaseModel):",
            "    username: str",
            "    password: str",
            "    actor: str\n",
            "def _hash_password(password: str, salt_hex: str) -> str:",
            "    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), 100_000).hex()\n",

            # CORRECTIF (roadmap) : limitation de débit généralisée à un
            # nom de "bucket" (au lieu d'être câblée uniquement pour /login),
            # pour pouvoir protéger /register également — sans ça, /register
            # pouvait être utilisée pour créer des comptes en masse ou pour
            # énumérer les noms d'utilisateur déjà pris (via le code 409).
            # LIMITE ASSUMÉE (prototype) : compteur en mémoire du processus,
            # non distribué, remis à zéro au redémarrage du serveur —
            # suffisant pour freiner un script naïf, pas une attaque distribuée
            # à grande échelle (nécessiterait Redis ou équivalent en prod).
            "_RATE_LIMIT_ATTEMPTS = {}",
            "RATE_LIMIT_WINDOW_SECONDS = 60",
            "RATE_LIMIT_MAX_ATTEMPTS = 5\n",
            "def _check_rate_limit(bucket: str, client_ip: str):",
            "    now = datetime.datetime.utcnow().timestamp()",
            "    key = f'{bucket}:{client_ip}'",
            "    attempts = _RATE_LIMIT_ATTEMPTS.setdefault(key, [])",
            "    attempts[:] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]",
            "    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:",
            "        raise HTTPException(status_code=429, detail=f'Trop de tentatives ({bucket}). "
            "Réessayez dans {RATE_LIMIT_WINDOW_SECONDS} secondes.')",
            "    attempts.append(now)\n",

            "@app.post('/register', tags=['Authentication'])",
            "async def register(req: RegisterRequest, request: Request):",
            "    _check_rate_limit('register', request.client.host if request.client else 'unknown')",
            "    if req.actor not in VALID_ACTORS:",
            "        raise HTTPException(status_code=400, detail=f\"Acteur invalide. Acteurs valides : {VALID_ACTORS}\")",
            "    if len(req.password) < 8:",
            "        raise HTTPException(status_code=400, detail='Le mot de passe doit contenir au moins 8 caractères.')",
            "    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()",
            "    cursor.execute('SELECT id FROM _monlang_users WHERE username = ?', (req.username,))",
            "    if cursor.fetchone():",
            "        conn.close()",
            "        raise HTTPException(status_code=409, detail=\"Ce nom d'utilisateur existe déjà.\")",
            "    salt_hex = os.urandom(16).hex()",
            "    pwd_hash = _hash_password(req.password, salt_hex)",
            "    cursor.execute('INSERT INTO _monlang_users (username, password_hash, salt, actor) VALUES (?, ?, ?, ?)',",
            "                   (req.username, pwd_hash, salt_hex, req.actor))",
            "    conn.commit(); new_user_id = cursor.lastrowid; conn.close()",
            "    return {'status': 'success', 'user_id': new_user_id}\n",

            "class LoginRequest(BaseModel):",
            "    username: str",
            "    password: str\n",

            "@app.post('/login', tags=['Authentication'])",
            "async def login(req: LoginRequest, request: Request):",
            "    _check_rate_limit('login', request.client.host if request.client else 'unknown')",
            "    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()",
            "    cursor.execute('SELECT id, password_hash, salt, actor FROM _monlang_users WHERE username = ?', (req.username,))",
            "    row = cursor.fetchone(); conn.close()",
            "    if not row:",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    db_user_id, stored_hash, salt_hex, actor = row",
            "    if _hash_password(req.password, salt_hex) != stored_hash:",
            "        raise HTTPException(status_code=401, detail='Identifiants invalides.')",
            "    payload = {",
            "        'sub': req.username,",
            "        'actor': actor,",
            "        'user_id': db_user_id,",
            # AJOUT (roadmap, révocation de token) : identifiant unique par
            # token (jti), nécessaire pour pouvoir le révoquer individuellement
            # via /logout sans avoir à invalider tous les tokens de l'utilisateur.
            "        'jti': secrets.token_hex(16),",
            "        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)",
            "    }",
            "    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)",
            "    return {'access_token': token, 'token_type': 'bearer'}\n",

            # AJOUT (roadmap, révocation de token) : /logout enregistre le jti
            # du token courant dans une liste noire persistante — toute
            # présentation ultérieure de ce même token est alors rejetée,
            # même s'il n'a pas encore atteint sa date d'expiration naturelle.
            "@app.post('/logout', tags=['Authentication'])",
            "async def logout(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):",
            "    payload = _decode_and_verify_token(credentials)",
            "    jti = payload.get('jti')",
            "    if not jti:",
            "        raise HTTPException(status_code=400, detail='Ce token ne supporte pas la révocation (jti manquant).')",
            "    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()",
            "    cursor.execute('INSERT OR IGNORE INTO _monlang_revoked_tokens (jti, revoked_at) VALUES (?, ?)',",
            "                   (jti, datetime.datetime.utcnow().isoformat()))",
            "    conn.commit(); conn.close()",
            "    return {'status': 'success', 'detail': 'Token révoqué.'}\n",
            "# --- VALIDATION STRICTE DES DONNÉES CRUD (PYDANTIC) ---"
        ]
        
        # 1. Génération des schémas CRUD standards
        for ent_name, attrs in self.entities.items():
            api_lines.append(f"class {ent_name}Schema(BaseModel):")
            for attr_name, attr_type in attrs.items():
                py_type = "str"
                if attr_type == "Integer": py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type == "Boolean": py_type = "bool"
                api_lines.append(f"    {attr_name}: {py_type}")
            # AJOUT (roadmap, écosystème de capacités -- brique 3, généralisée
            # en brique 4) : quand la relation entrante de cette entité est
            # la cible d'une règle 'decrements'/'increments' (ex.
            # Report -> Member, ou Like -> Post), sa colonne de clé étrangère
            # n'est PAS de la même nature qu'un "ceci m'appartient" (qui se
            # peuple tout seul depuis l'identité JWT de l'appelant, voir plus
            # bas) : c'est un choix du client ("je signale/j'apprécie CETTE
            # cible précise"), donc un champ normal du corps de requête.
            owner_info_for_schema = self._get_incoming_relation(ent_name)
            if owner_info_for_schema and any(
                r["target_entity"] == owner_info_for_schema["source"]
                for r in self.reputation_rules_by_trigger.get(ent_name, [])
            ):
                api_lines.append(f"    {owner_info_for_schema['fk_column']}: int")
            api_lines.append("\n")

        # 2. Génération de schémas stricts pour les entrées de la Sandbox IA (Bug #4)
        api_lines.append("# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---")
        for func in self.custom_functions:
            func_name = func["name"]
            inputs = func.get("input", [])
            
            api_lines.append(f"class {func_name}InputSchema(BaseModel):")
            if not inputs:
                api_lines.append("    pass")
            else:
                for inp in inputs:
                    if "reference" in inp:
                        ref = inp["reference"]
                        ent, attr = ref.split(".") if "." in ref else (ref, "id")
                        attr_type = self.entities.get(ent, {}).get(attr, "String")
                        py_type = "int" if attr_type == "Integer" else ("float" if attr_type in ["Float", "Money"] else ("bool" if attr_type == "Boolean" else "str"))
                        api_lines.append(f"    {attr.replace('.', '_')}: {py_type}")
                    else:
                        inp_name = inp.get("name", "context")
                        inp_type = inp.get("type", "String")
                        py_type = "int" if inp_type == "Integer" else ("float" if inp_type in ["Float", "Money"] else ("bool" if inp_type == "Boolean" else "str"))
                        api_lines.append(f"    {inp_name}: {py_type}")
            api_lines.append("\n")

        api_lines.append("# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---")

        # CORRECTIF (post-v6) : les routes sont désormais regroupées par couple
        # (type d'action, cible), et non plus générées une fois par workflow.
        # Raison : avant ce correctif, deux workflows différents visant la même
        # action sur la même entité (ex. deux acteurs autorisés à faire "Delete Post"
        # via une règle 'sharedBy') produisaient deux définitions de route FastAPI
        # sur le même chemin ('@app.delete(\"/post/{id}\")' deux fois) — seule la
        # première déclarée restait effectivement joignable, la seconde était
        # silencieusement masquée, et son acteur recevait un 403 malgré une spec
        # valide. Le regroupement ci-dessous fusionne les acteurs autorisés en un
        # seul contrôle d'accès par route, listant tous les acteurs légitimes.
        route_map = self._compute_route_map()

        for (act_type, _key), info in route_map.items():
            allowed_actors = sorted(info["actors"])
            base_target = info["base_target"]
            target = info["target"]
            tag = info["tags"][0]

            # AJOUT (roadmap, cas d'usage portfolio) : une action marquée
            # 'public' via une règle DSL ("rule Entite.Action public") ne
            # requiert plus aucune authentification sur la route générée —
            # ni dépendance JWT, ni contrôle de rôle. Utile pour un contenu
            # librement consultable (portfolio) ou un formulaire ouvert
            # (message de contact) sans exiger de compte.
            is_public = (base_target, act_type) in self.public_actions

            if is_public:
                security_check = "    pass  # Route publique (règle 'public') : aucune authentification requise"
                dependency_injection = ""
            elif len(allowed_actors) == 1:
                security_check = (f'    if current_actor != "{allowed_actors[0]}": '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle {allowed_actors[0]} requis")')
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
            else:
                allowed_set_literal = ", ".join(f'"{a}"' for a in allowed_actors)
                security_check = (f'    if current_actor not in {{{allowed_set_literal}}}: '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle parmi [{", ".join(allowed_actors)}] requis")')
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"

            # Utilisé partout où dependency_injection doit s'insérer après
            # un ou plusieurs paramètres déjà présents dans la signature —
            # évite une virgule traînante invalide en syntaxe Python quand
            # dependency_injection est vide (route publique).
            dep_suffix = f", {dependency_injection}" if dependency_injection else ""

            if act_type == "Create":
                # AJOUT (post-v6, roadmap) : si l'entité a une relation entrante
                # (ex. "relation User hasMany Todo"), la colonne de clé étrangère
                # correspondante (ex. "user_id") est désormais réellement peuplée
                # à la création, à partir de l'identité JWT de l'appelant.
                # CORRECTIF DE GAP PRÉ-EXISTANT : cette colonne était déjà générée
                # dans schema.sql depuis les toutes premières versions, mais
                # jamais incluse dans la requête INSERT — elle restait NULL pour
                # tout enregistrement créé, rendant les relations inertes au
                # runtime malgré leur présence dans le schéma.
                owner_info = self._get_incoming_relation(base_target)
                # AJOUT (roadmap, écosystème de capacités -- brique 3,
                # généralisée en brique 4) : si cette relation entrante est la
                # cible d'une règle 'decrements'/'increments' (ex. "je
                # signale CE membre" ou "j'apprécie CE post"), ce n'est pas un
                # motif "propriétaire = appelant courant" -- le client fournit
                # explicitement la cible dans le corps de la requête (voir la
                # génération du schéma Pydantic ci-dessus), donc on ne tente
                # PAS de la peupler automatiquement depuis current_user_id.
                reputation_rules_here = self.reputation_rules_by_trigger.get(base_target, [])
                is_reputation_fk = owner_info and any(
                    r["target_entity"] == owner_info["source"] for r in reputation_rules_here
                )
                # Une route publique n'a par définition aucune identité
                # appelante fiable — on ne tente pas d'y rattacher une clé
                # étrangère "propriétaire" dans ce cas (la colonne reste NULL).
                populate_owner = owner_info and not is_public and not is_reputation_fk
                create_deps = dependency_injection
                if populate_owner:
                    create_deps += ", current_user_id: int = Depends(get_current_user_id)" if create_deps else "current_user_id: int = Depends(get_current_user_id)"
                create_deps_suffix = f", {create_deps}" if create_deps else ""

                api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
                api_lines.append(f"async def create_{base_target.lower()}(data: {base_target}Schema{create_deps_suffix}):")
                api_lines.append(security_check)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                fields = list(self.entities[base_target].keys())
                insert_columns = list(fields)
                value_exprs = [f"data.{f}" for f in fields]
                if populate_owner:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append("current_user_id")
                elif is_reputation_fk:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append(f"data.{owner_info['fk_column']}")
                columns = ", ".join(f'"{c}"' for c in insert_columns)
                placeholders = ", ".join(["?"] * len(insert_columns))
                api_lines.append(f"    query = 'INSERT INTO \"{base_target.lower()}\" ({columns}) VALUES ({placeholders})'")
                values_list = ", ".join(value_exprs)
                api_lines.append(f"    cursor.execute(query, ({values_list},))")
                api_lines.append("    conn.commit(); row_id = cursor.lastrowid")
                # AJOUT (roadmap, écosystème de capacités -- brique 3,
                # généralisée en brique 4) : effet de la règle
                # 'decrements'/'increments' -- exécuté APRÈS le commit de
                # l'insertion (le signalement/like est déjà valablement
                # enregistré quoi qu'il arrive à cette étape), sur la ligne
                # cible désignée par le client via la clé étrangère
                # ci-dessus. Une cible inexistante ne fait simplement rien
                # (UPDATE sans ligne correspondante) plutôt que d'échouer la
                # création de l'enregistrement déclencheur lui-même.
                for rule in reputation_rules_here:
                    target_table = rule["target_entity"].lower()
                    target_field = rule["target_field"]
                    amount = rule["amount"]
                    sql_op = "-" if rule["direction"] == "decrements" else "+"
                    fk_value_expr = f"data.{owner_info['fk_column']}"
                    api_lines.append(
                        f"    cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = \"{target_field}\" {sql_op} ? "
                        f"WHERE id = ?', ({amount}, {fk_value_expr}))"
                    )
                    api_lines.append("    conn.commit()")
                api_lines.append("    conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': row_id}}")
                api_lines.append("")
                
            elif act_type == "Read":
                # AJOUT (roadmap point 3, complété) : route de liste, en plus
                # de la lecture par ID déjà existante — jusqu'ici il n'existait
                # aucun moyen d'énumérer les enregistrements d'une entité sans
                # déjà connaître leurs identifiants un par un.
                # AJOUT (roadmap, pagination) : 'limit'/'offset' en paramètres
                # de requête (défaut 50, plafonné à 200), plus le nombre total
                # d'enregistrements — sans ça, une table volumineuse renverrait
                # tout d'un coup, sans borne.
                # CORRECTIF (roadmap, front visuel) : les lignes sont désormais
                # renvoyées comme des objets nommés {colonne: valeur} plutôt
                # que des tableaux positionnels bruts — un front (ou tout
                # client) n'a plus besoin de connaître l'ordre exact des
                # colonnes SQL pour afficher les données correctement.
                columns = self._get_row_column_names(base_target)
                columns_literal = ", ".join(f'"{c}"' for c in columns)
                # AJOUT (roadmap, écosystème de capacités -- brique 2) :
                # champs masqués (règle 'hidden') retirés de la réponse,
                # après construction du dict nommé mais avant de le renvoyer
                # -- jamais retirés de la base, jamais visibles par personne
                # via cette route, quel que soit qui l'appelle (contrairement
                # à 'restrictedTo', qui autorise un acteur précis).
                masked = self.hidden_fields_by_entity.get(base_target, [])
                mask_literal = ", ".join(f"'{f}'" for f in masked)
                # AJOUT (roadmap, écosystème de capacités -- brique 5) :
                # champs 'categorized' remplacés par leur libellé de
                # catégorie, dans la même passe que le masquage ci-dessus —
                # un seul parcours par ligne pour les deux transformations.
                categorized_here = self.categorized_fields_by_entity.get(base_target, [])
                list_params = f"limit: int = 50, offset: int = 0{dep_suffix}"
                api_lines.append(f"@app.get('/{base_target.lower()}', tags=['{tag}'])")
                api_lines.append(f"async def list_{base_target.lower()}({list_params}):")
                api_lines.append(security_check)
                api_lines.append("    limit = max(1, min(limit, 200))")
                api_lines.append("    offset = max(0, offset)")
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"')")
                api_lines.append("    total = cursor.fetchone()[0]")
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" LIMIT ? OFFSET ?', (limit, offset))")
                api_lines.append("    rows = cursor.fetchall(); conn.close()")
                api_lines.append(f"    _columns = [{columns_literal}]")
                api_lines.append("    named_rows = [dict(zip(_columns, row)) for row in rows]")
                row_loop_lines = []
                if masked:
                    row_loop_lines.append(f"        for _f in [{mask_literal}]: _r.pop(_f, None)")
                for cf in categorized_here:
                    row_loop_lines.extend(self._emit_categorization_lines(cf, "_r", "        "))
                if row_loop_lines:
                    api_lines.append("    for _r in named_rows:")
                    api_lines.extend(row_loop_lines)
                api_lines.append("    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}")
                api_lines.append("")

                api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def read_{base_target.lower()}(id: int{dep_suffix}):")
                api_lines.append(security_check)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
                api_lines.append("    row = cursor.fetchone(); conn.close()")
                api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
                api_lines.append(f"    named_row = dict(zip([{columns_literal}], row))")
                if masked:
                    api_lines.append(f"    for _f in [{mask_literal}]: named_row.pop(_f, None)")
                for cf in categorized_here:
                    api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
                api_lines.append("    return {'status': 'success', 'data': named_row}")
                api_lines.append("")
                
            elif act_type == "Update":
                # AJOUT (post-v6, roadmap) : si une règle 'ownedBy' cible cette
                # action, un contrôle supplémentaire vérifie que l'acteur courant
                # est bien le propriétaire de l'enregistrement, en plus du
                # contrôle de rôle habituel.
                owner_entity = self.ownership.get(f"{base_target}.Update")
                # 'ownedBy' suppose une identité appelante (current_actor) —
                # incompatible avec une route 'public', qui n'en a aucune.
                # Si les deux sont déclarées sur la même action, 'public'
                # l'emporte : la route reste ouverte, sans contrôle de
                # propriété (voir docs/design_decisions.md).
                apply_ownership = owner_entity and not is_public
                update_deps = dependency_injection
                ownership_check_lines = []
                if apply_ownership:
                    fk_col = f"{owner_entity.lower()}_id"
                    update_deps += ", current_user_id: int = Depends(get_current_user_id)" if update_deps else "current_user_id: int = Depends(get_current_user_id)"
                    # CORRECTIF (roadmap, combinaison ownedBy + sharedBy) : si
                    # cette route est partagée par plusieurs acteurs (ex. un
                    # 'Agent' qui gère tous les tickets, en plus du 'Customer'
                    # propriétaire), le contrôle de propriété ne doit s'appliquer
                    # qu'à l'acteur explicitement désigné comme propriétaire par
                    # la règle 'ownedBy' — pas aux autres acteurs qui partagent
                    # la route par ailleurs via leur propre rôle. Sans cette
                    # condition, un acteur légitimement privilégié (Agent) se
                    # retrouverait bloqué à tort, puisqu'il ne "possède" jamais
                    # la ressource au sens de la relation hasMany/belongsTo.
                    ownership_check_lines = [
                        f"    if current_actor == \"{owner_entity}\":",
                        "        _owner_conn = sqlite3.connect(DB_FILE); _owner_cur = _owner_conn.cursor()",
                        f"        _owner_cur.execute('SELECT \"{fk_col}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                        "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                        "        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                        "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
                    ]

                update_deps_suffix = f", {update_deps}" if update_deps else ""
                api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def update_{base_target.lower()}(id: int, data: {base_target}Schema{update_deps_suffix}):")
                api_lines.append(security_check)
                api_lines.extend(ownership_check_lines)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                fields = list(self.entities[base_target].keys())
                update_stmt = ", ".join([f'"{f}" = ?' for f in fields])
                api_lines.append(f"    query = 'UPDATE \"{base_target.lower()}\" SET {update_stmt} WHERE id = ?'")
                values_list = ", ".join([f"data.{f}" for f in fields])
                api_lines.append(f"    cursor.execute(query, ({values_list}, id))")
                api_lines.append("    conn.commit(); conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                api_lines.append("")

            elif act_type == "Delete":
                owner_entity = self.ownership.get(f"{base_target}.Delete")
                apply_ownership = owner_entity and not is_public
                delete_deps = dependency_injection
                ownership_check_lines = []
                if apply_ownership:
                    fk_col = f"{owner_entity.lower()}_id"
                    delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
                    # Voir le commentaire équivalent dans le bloc "Update" ci-dessus :
                    # le contrôle de propriété ne s'applique qu'à l'acteur
                    # explicitement désigné comme propriétaire par 'ownedBy'.
                    ownership_check_lines = [
                        f"    if current_actor == \"{owner_entity}\":",
                        "        _owner_conn = sqlite3.connect(DB_FILE); _owner_cur = _owner_conn.cursor()",
                        f"        _owner_cur.execute('SELECT \"{fk_col}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                        "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                        "        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                        "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
                    ]

                delete_deps_suffix = f", {delete_deps}" if delete_deps else ""
                api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
                api_lines.append(f"async def delete_{base_target.lower()}(id: int{delete_deps_suffix}):")
                api_lines.append(security_check)
                api_lines.extend(ownership_check_lines)
                api_lines.append("    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()")
                api_lines.append(f"    cursor.execute('DELETE FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
                api_lines.append("    conn.commit(); conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                api_lines.append("")
                
            elif act_type == "Execute":
                api_lines.append(f"@app.post('/workflow/{tag.lower()}/{target.lower()}', tags=['{tag}'])")
                api_lines.append(f"async def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
                api_lines.append(security_check)
                api_lines.append(f"    result = sandbox_ai.{target}(payload.dict())")
                api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
                api_lines.append("")
                    
        return "\n".join(api_lines)

    def _select_theme(self, seed=None):
        """AJOUT (roadmap, identité visuelle) : choisit un système visuel
        complet (palette, typographies, rayon de bordure, traitement des
        cartes) parmi 5 propositions distinctes et volontairement écartées
        des trois looks par défaut que produit une IA sans direction (fond
        crème + accent terracotta, fond quasi-noir + accent acide unique,
        colonnes façon journal à filets fins). Le choix est motivé par le
        vocabulaire du domaine (noms d'entités/attributs/app) quand un signal
        existe ; sinon il est réparti de façon stable (par hachage du nom de
        l'app) entre les 5 systèmes, pour que deux apps génériques différentes
        ne se ressemblent pas non plus."""
        themes = {
            "editorial": {
                "keywords": {"post", "article", "blog", "comment", "story", "author", "publish"},
                "bg": "#F3EFE1", "surface": "#FFFFFF", "ink": "#241F16",
                "accent": "#2F5D50", "accent2": "#B23A48",
                "font_display": "'Fraunces', Georgia, serif",
                "font_body": "'Inter', -apple-system, sans-serif",
                "font_mono": "'IBM Plex Mono', monospace",
                "google_fonts": "Fraunces:opsz,wght@9..144,400;9..144,600&family=Inter:wght@400;500;600",
                "radius": "4px", "card_style": "editorial",
            },
            "market": {
                "keywords": {"product", "order", "price", "cart", "shop", "invoice", "money",
                              "stock", "customer", "payment", "checkout"},
                "bg": "#EFEDE4", "surface": "#FFFFFF", "ink": "#1B2420",
                "accent": "#0B6E4F", "accent2": "#C98A00",
                "font_display": "'Barlow Condensed', sans-serif",
                "font_body": "'Work Sans', -apple-system, sans-serif",
                "font_mono": "'IBM Plex Mono', monospace",
                "google_fonts": "Barlow+Condensed:wght@600;700&family=Work+Sans:wght@400;500",
                "radius": "2px", "card_style": "market",
            },
            "console": {
                "keywords": {"todo", "task", "ticket", "issue", "workflow", "project", "bug", "status"},
                "bg": "#161A1E", "surface": "#20262C", "ink": "#E7E4DC",
                "accent": "#5B8DEF", "accent2": "#3FB68B",
                "font_display": "'IBM Plex Mono', monospace",
                "font_body": "'IBM Plex Sans', -apple-system, sans-serif",
                "font_mono": "'IBM Plex Mono', monospace",
                "google_fonts": "IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500",
                "radius": "10px", "card_style": "console",
            },
            "civic": {
                "keywords": {"reservation", "booking", "event", "member", "social", "friend",
                              "profile", "community", "guest", "appointment", "slot",
                              "professional", "schedule"},
                "bg": "#F1ECE4", "surface": "#FFFFFF", "ink": "#2B2118",
                "accent": "#3D5A80", "accent2": "#C9A227",
                "font_display": "'Newsreader', Georgia, serif",
                "font_body": "'Manrope', -apple-system, sans-serif",
                "font_mono": "'IBM Plex Mono', monospace",
                "google_fonts": "Newsreader:ital,wght@1,500;0,600&family=Manrope:wght@400;500;600",
                "radius": "18px", "card_style": "civic",
            },
            "ledger": {
                "keywords": set(),
                "bg": "#EAE6DC", "surface": "#FFFFFF", "ink": "#1E1B16",
                "accent": "#1D3557", "accent2": "#588157",
                "font_display": "'Libre Caslon Text', Georgia, serif",
                "font_body": "'IBM Plex Sans', -apple-system, sans-serif",
                "font_mono": "'IBM Plex Mono', monospace",
                "google_fonts": "Libre+Caslon+Text:wght@400;700&family=IBM+Plex+Sans:wght@400;500",
                "radius": "6px", "card_style": "ledger",
            },
        }

        # AJOUT (roadmap, contrôle du rendu visuel) : un bloc 'ui' peut forcer
        # explicitement le thème de toute l'application (le thème reste une
        # identité unique par app, partagée par toutes les entités, pas un
        # réglage par entité) — la première surcharge valide trouvée l'emporte
        # sur la sélection automatique par mots-clés.
        theme_name, theme = None, None
        for override in self.ui_overrides.values():
            requested_theme = override.get("theme")
            if requested_theme and requested_theme in themes:
                theme_name, theme = requested_theme, dict(themes[requested_theme])
                break

        if theme_name is None:
            vocabulary = (self.app_name + " " + " ".join(self.entities.keys())).lower()
            for entity_attrs in self.entities.values():
                vocabulary += " " + " ".join(entity_attrs.keys()).lower()

            scores = {name: sum(1 for kw in t["keywords"] if kw in vocabulary) for name, t in themes.items()}
            best_score = max(scores.values())

            if best_score > 0:
                candidates = sorted([n for n, s in scores.items() if s == best_score])
            else:
                candidates = sorted(themes.keys())

            hash_source = self.app_name + (":" + seed if seed else "")
            pick_index = int(hashlib.sha256(hash_source.encode()).hexdigest(), 16) % len(candidates)
            theme_name = candidates[pick_index]
            theme = dict(themes[theme_name])

        # AJOUT (roadmap, unicité visuelle par projet) : le choix ci-dessus
        # ne dépend QUE du domaine (vocabulaire de l'app) — deux projets de
        # même domaine (deux todo-lists, par exemple) obtiennent donc le
        # même thème de base à chaque fois, par construction. La graine
        # aléatoire propre au projet (voir _load_or_create_theme_seed) sert
        # ici à appliquer une variation fine SUR ce thème (teinte des
        # couleurs d'accent, rayon des bordures) sans jamais changer le
        # thème lui-même : deux todo-lists restent bien reconnaissables
        # comme telles (même palette de base, mêmes polices), mais cessent
        # d'être des pixels identiques.
        if seed:
            variation_hash = hashlib.sha256(f"{self.app_name}:{seed}".encode()).hexdigest()
            hue_shift_accent = (int(variation_hash[0:4], 16) % 41) - 20     # -20..+20 degrés
            hue_shift_accent2 = (int(variation_hash[4:8], 16) % 41) - 20
            radius_factor = 0.8 + (int(variation_hash[8:10], 16) % 41) / 100.0  # ~0.8x..1.2x
            theme["accent"] = self._shift_hue(theme["accent"], hue_shift_accent)
            theme["accent2"] = self._shift_hue(theme["accent2"], hue_shift_accent2)
            base_radius_px = float(theme["radius"].replace("px", ""))
            theme["radius"] = f"{round(base_radius_px * radius_factor, 1)}px"

        return theme_name, theme

    @staticmethod
    def _shift_hue(hex_color, degrees):
        """AJOUT (roadmap, unicité visuelle par projet) : fait pivoter la
        teinte (HSL) d'une couleur hexadécimale d'un nombre de degrés donné,
        en conservant sa luminosité et sa saturation d'origine -- donc son
        niveau de contraste avec le fond/le texte, ce qui est important pour
        la lisibilité. N'agit que sur les couleurs d'accent, jamais sur
        bg/surface/ink, pour ne pas risquer de dégrader le contraste texte."""
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        h = (h + degrees / 360.0) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))

    def _load_or_create_theme_seed(self):
        """AJOUT (roadmap, unicité visuelle par projet) : génère, à la toute
        première compilation d'un projet, une graine aléatoire de 16 octets
        conservée dans '.monlang_theme_seed' (à ajouter au .gitignore,
        jamais commitée -- même logique que '.jwt_secret'). Recompiler la
        spec NE régénère PAS la graine : le style visuel du projet reste
        stable dans le temps ; il faut supprimer le fichier à la main pour
        en tirer un nouveau look."""
        base_dir = os.path.dirname(__file__)
        seed_path = os.path.join(base_dir, "../.monlang_theme_seed")
        if not os.path.exists(seed_path):
            new_seed = secrets.token_hex(16)
            with open(seed_path, "w", encoding="utf-8") as f:
                f.write(new_seed)
            print("🎨 Nouvelle graine de variation visuelle générée et stockée dans '.monlang_theme_seed'.")
            return new_seed
        with open(seed_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def _compute_route_map(self):
        """Regroupe les actions par (type, cible) avec la liste des acteurs
        autorisés et le 'tag' (nom du premier workflow qui déclare l'action)
        -- extrait de _generate_secure_fastapi pour être réutilisé aussi par
        _compute_actor_capabilities (le tableau de bord post-connexion a
        besoin du même 'tag' que la vraie route pour appeler les fonctions
        'custom' au bon endroit). Une seule source de vérité : si cette
        logique de regroupement change un jour, les deux consommateurs
        restent forcément synchronisés."""
        route_map = {}
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".")[0] if "." in target else target
                route_key = (act_type, base_target if act_type != "Execute" else target)
                if route_key not in route_map:
                    route_map[route_key] = {"actors": set(), "tags": [], "target": target, "base_target": base_target}
                route_map[route_key]["actors"].add(required_actor)
                if wf_name not in route_map[route_key]["tags"]:
                    route_map[route_key]["tags"].append(wf_name)
        return route_map

    def _compute_actor_capabilities(self):
        """AJOUT (roadmap, "aller plus loin, comme un site moderne") : calcule,
        pour chaque acteur, les entités et actions CRUD qu'il peut réellement
        effectuer (à partir des vrais 'workflow' de la spec -- jamais deviné,
        jamais une action qui n'existe pas réellement côté API). Sert à
        peupler un tableau de bord qui apparaît sur la landing UNIQUEMENT
        après une vraie connexion (JWT), personnalisé à l'acteur connecté --
        à la différence de l'ancien back-office '/ui' (retiré, point 22) qui
        était visible sans authentification et montrait tout à tout le
        monde. Les actions 'Execute' (fonctions 'custom') sont incluses
        aussi : c'est la seule façon d'appeler une fonction 'custom' depuis
        la landing, maintenant que '/ui' n'existe plus."""
        capabilities = {}
        custom_by_name = {f["name"]: f for f in self.custom_functions}
        route_map = self._compute_route_map()
        for actor in self.actors:
            entities_for_actor = {}
            custom_for_actor = {}
            for wf in self.workflows:
                if wf["actor"] != actor:
                    continue
                for action in wf["actions"]:
                    act_type = action["type"]
                    target = action["target"]
                    if act_type == "Execute":
                        func = custom_by_name.get(target, {})
                        inputs = []
                        for inp in func.get("input", []):
                            inputs.append(inp["reference"].replace(".", "_") if "reference" in inp else inp.get("name", "value"))
                        real_tag = route_map.get(("Execute", target), {}).get("tags", [wf["name"]])[0]
                        custom_for_actor[target] = {"inputs": inputs, "description": func.get("description", ""), "tag": real_tag}
                        continue
                    base_entity = target.split(".")[0]
                    if base_entity not in self.entities:
                        continue
                    entities_for_actor.setdefault(base_entity, {"actions": set(), "fields": self.entities[base_entity]})
                    entities_for_actor[base_entity]["actions"].add(act_type)
            if entities_for_actor or custom_for_actor:
                capabilities[actor] = {
                    "entities": {
                        e: {"actions": sorted(v["actions"]), "fields": v["fields"]}
                        for e, v in entities_for_actor.items()
                    },
                    "functions": custom_for_actor,
                }
        return capabilities

    def _compute_landing_functional_context(self):
        """AJOUT (roadmap, "plus de texte superflu") : au lieu de décorer la
        landing avec des points forts inventés, on détecte ce que l'app sait
        RÉELLEMENT faire sans authentification, pour y brancher de vrais
        formulaires/aperçus fonctionnels :
          - 'contact_entity' : la première entité avec une action 'Create'
            publique (voir règle 'public', point 16) -> un vrai formulaire,
            avec les champs réels de l'entité, qui POST sur la vraie route.
          - 'preview_entity' : la première entité avec une action 'Read'
            publique, différente de 'contact_entity' -> un vrai aperçu
            chargé en direct depuis l'API (fetch), pas des cartes statiques.
          - 'actors' : toujours utilisé pour un vrai mini-formulaire de
            création de compte (/register existe systématiquement, voir
            _generate_secure_fastapi) — la seule action "Commencer"
            authentique qu'une landing puisse offrir sans back-office."""
        contact_entity, contact_fields = None, {}
        preview_entity, preview_display_field = None, None
        for entity, attrs in self.entities.items():
            if contact_entity is None and (entity, "Create") in self.public_actions:
                contact_entity, contact_fields = entity, attrs
        for entity, attrs in self.entities.items():
            if entity == contact_entity:
                continue
            if preview_entity is None and (entity, "Read") in self.public_actions:
                preview_entity = entity
                masked = self.hidden_fields_by_entity.get(entity, [])
                for attr, t in attrs.items():
                    if t in ("String", "Text") and attr not in masked:
                        preview_display_field = attr
                        break
        # CORRECTIF (roadmap, bug réel signalé par l'utilisateur -- pas
        # de bouton "Créer" visible) : les options du menu <select> Acteur
        # étaient triées par ordre alphabétique pur. Pour beaucoup de specs
        # (voir 01_todo_list.yaml : acteurs "Admin" et "User"), ça plaçait
        # "Admin" en premier -- pré-sélectionné par défaut à l'inscription,
        # alors qu'il n'a souvent AUCUN droit "Create" (ex. seulement
        # "Delete" sur Todo). Un visiteur qui s'inscrit sans toucher au menu
        # se retrouvait donc avec un tableau de bord sans aucun formulaire
        # de création -- pas un bug d'affichage, un mauvais choix de valeur
        # par défaut. Le premier acteur proposé (donc pré-sélectionné) est
        # désormais celui qui a le droit 'Create' sur au moins une entité et
        # dont le nom ne contient pas "admin" ; à égalité, ordre alphabétique.
        capabilities_for_ranking = self._compute_actor_capabilities()

        def actor_rank(actor):
            caps = capabilities_for_ranking.get(actor, {})
            has_create = any("Create" in v["actions"] for v in caps.get("entities", {}).values())
            looks_like_admin = "admin" in actor.lower()
            return (looks_like_admin, not has_create, actor)

        ordered_actors = sorted(self.actors, key=actor_rank)

        return {
            "actors": ordered_actors,
            "contact_entity": contact_entity,
            "contact_fields": contact_fields,
            "preview_entity": preview_entity,
            "preview_display_field": preview_display_field,
        }

    def _deterministic_landing_copy(self):
        """AJOUT (roadmap, "plus de texte superflu") : rédaction 100%
        déterministe (aucun appel IA) du titre/sous-titre de la landing.
        Volontairement réduite à 2 champs (fini les points forts inventés,
        l'étiquette "Nouveau" et la phrase de clôture décorative de la
        version précédente) : le reste de la page n'est plus du texte mais
        de vraies sections fonctionnelles, voir _compute_landing_functional_context.
        Le sous-titre reste concret — il nomme les entités réelles de l'app
        plutôt qu'une formule marketing générique. Filet de sécurité toujours
        disponible, que le mode soit 'ai' (avant enrichissement, ou si l'IA
        locale est hors-ligne) ou 'template'."""
        brief = (self.landing_config or {}).get("brief")
        entity_names = list(self.entities.keys())

        headline = self.app_name
        if brief:
            subheadline = brief
        elif entity_names:
            subheadline = "Gérez " + ", ".join(e.lower() + "s" for e in entity_names[:3]) + " en un seul endroit."
        else:
            subheadline = f"Découvrez {self.app_name}."

        return {
            "headline": headline,
            "subheadline": subheadline,
            "cta_label": "Commencer",
            "cta_target": "/docs",
        }

    def _generate_landing(self):
        """AJOUT (roadmap, front marketing) : point d'entrée de la
        génération de 'landing.html', servi sur '/' à la place de la
        redirection par défaut vers /docs. Deux modes, choisis par
        'landing / mode' dans la spec :
          - 'ai'       : gabarit déterministe avec emplacements balisés par
                         des commentaires <!--LANDING:clé-->...<!--/LANDING:clé-->,
                         que ai_landing_filler.py peut enrichir ensuite (étape
                         séparée, non bloquante — même pattern que 'custom').
          - 'template' : importe le fichier HTML fourni par l'utilisateur et
                         y substitue les emplacements 'data-monlang="clé"'
                         qu'il contient, pour les clés réservées connues.
        Dans les deux cas, retombe silencieusement sur le gabarit 'ai' si
        quoi que ce soit d'inattendu survient (fichier de template introuvable,
        par ex.) — générer une landing imparfaite est toujours préférable à
        faire échouer toute la compilation pour une page qui n'est, par
        construction, jamais sur le chemin critique de l'API."""
        mode = self.landing_config.get("mode", "ai")
        if mode == "template":
            template_rel_path = self.landing_config.get("template")
            base_dir = os.path.dirname(__file__)
            template_path = os.path.join(base_dir, "..", template_rel_path) if template_rel_path else None
            if template_path and os.path.isfile(template_path):
                return self._generate_landing_from_template(template_path)
            print(
                f"⚠️  'landing / template: {template_rel_path}' introuvable — "
                f"gabarit déterministe utilisé à la place (voir mode 'ai')."
            )
        return self._generate_landing_ai_shell()

    def _pick_hero_variant(self, theme_seed):
        """AJOUT (roadmap, "les sites se ressemblent") : première étape,
        volontairement petite, vers une vraie variété structurelle plutôt
        que seulement paramétrique (teinte/rayon, point 20). Choisit entre 2
        mises en page de hero écrites à la main (jamais par l'IA -- toujours
        zéro risque, pas de parsing/audit à construire) :
          - 'centered' : le hero à une colonne déjà en place.
          - 'split' : deux colonnes, texte à gauche, élément décoratif
            abstrait à droite (purement CSS, coloré via le thème).
        Choix déterministe par hash (même principe que _select_theme) : un
        projet donné garde toujours la même mise en page d'une compilation à
        l'autre, mais deux projets différents ont de bonnes chances de
        diverger structurellement, pas seulement en couleur."""
        variants = ["centered", "split"]
        h = hashlib.sha256(f"{self.app_name}:{theme_seed}:hero".encode()).hexdigest()
        return variants[int(h, 16) % len(variants)]

    def _generate_landing_ai_shell(self):
        """Gabarit de landing déterministe (mode 'ai', avant/à défaut
        d'enrichissement par le LLM local). Réutilise le système de thème
        déjà en place pour l'API (_select_theme + graine persistée par
        projet, voir point 20 de docs/design_decisions.md).

        CORRECTIF (roadmap, "plus de texte superflu, des applications
        fonctionnelles") : les versions précédentes rendaient une page de
        pure décoration -- des points forts inventés, un bouton qui ne
        menait qu'à /docs. Celle-ci ne garde du texte que le strict
        nécessaire (titre + sous-titre, 2 champs IA au lieu de 8) et
        remplace tout le reste par de VRAIES sections fonctionnelles,
        détectées par _compute_landing_functional_context :
          - un vrai mini-formulaire de création de compte + connexion
            (POST /register puis /login, toujours présent : ces routes
            existent systématiquement, voir _generate_secure_fastapi) ;
          - si l'app a une action 'Read' publique sur une entité (règle
            'public', point 16) : un aperçu chargé EN DIRECT depuis l'API
            (fetch), pas des cartes statiques ;
          - si l'app a une action 'Create' publique : un vrai formulaire,
            avec les champs réels de l'entité, qui écrit réellement en base
            via la vraie route -- pas une simulation.
        Une landing sans aucune action publique (donc sans aperçu ni
        formulaire de contact) garde au moins le formulaire de compte,
        qui fonctionne dans 100% des cas."""
        theme_seed = self._load_or_create_theme_seed()
        theme_name, theme = self._select_theme(theme_seed)
        copy = self._deterministic_landing_copy()
        ctx = self._compute_landing_functional_context()

        def marker(key, text):
            safe = html.escape(text)
            return f"<!--LANDING:{key}-->{safe}<!--/LANDING:{key}-->"

        INPUT_TYPES = {
            "String": "text", "Text": "textarea", "Integer": "number", "Float": "number",
            "Money": "number", "Boolean": "checkbox", "Email": "email",
            "DateTime": "date", "Date": "date", "UUID": "text",
        }

        # --- Navigation dynamique : seuls les ancres des sections qui
        # existent réellement sont proposées.
        nav_items = ['<a href="#get-started" class="js-scroll">Commencer</a>']
        if ctx["preview_entity"]:
            nav_items.insert(0, '<a href="#preview" class="js-scroll">Aperçu</a>')
        if ctx["contact_entity"]:
            nav_items.append('<a href="#contact" class="js-scroll">Contact</a>')
        nav_items.append('<a href="/docs" class="nav-docs">Documentation API</a>')
        nav_links_html = "\n            ".join(nav_items)

        # --- Section "aperçu en direct" (si une action Read est publique)
        preview_section = ""
        if ctx["preview_entity"]:
            entity = ctx["preview_entity"]
            preview_section = f'''
    <section class="block" id="preview">
        <h2>Aperçu</h2>
        <p class="block-sub">Chargé en direct depuis <code>GET /{entity.lower()}</code>, sans compte requis.</p>
        <div id="previewGrid" class="preview-grid">
            <p class="hint">Chargement…</p>
        </div>
    </section>'''

        # --- Section "formulaire de contact réel" (si une action Create est publique)
        contact_section = ""
        if ctx["contact_entity"]:
            entity = ctx["contact_entity"]
            fields_html_parts = []
            for attr, t in ctx["contact_fields"].items():
                input_type = INPUT_TYPES.get(t, "text")
                if input_type == "textarea":
                    fields_html_parts.append(
                        f'<label class="field">{html.escape(attr)}<textarea data-field="{html.escape(attr)}" rows="3"></textarea></label>'
                    )
                elif input_type == "checkbox":
                    fields_html_parts.append(
                        f'<label class="field field-checkbox"><input type="checkbox" data-field="{html.escape(attr)}"> {html.escape(attr)}</label>'
                    )
                else:
                    fields_html_parts.append(
                        f'<label class="field">{html.escape(attr)}<input type="{input_type}" data-field="{html.escape(attr)}"></label>'
                    )
            contact_fields_html = "\n            ".join(fields_html_parts)
            contact_section = f'''
    <section class="block" id="contact">
        <h2>Contact</h2>
        <p class="block-sub">Ce formulaire écrit réellement via <code>POST /{entity.lower()}</code>, sans compte requis.</p>
        <form id="contactForm" class="block-form" data-entity="{entity.lower()}">
            {contact_fields_html}
            <button type="submit" class="cta cta-primary">Envoyer</button>
            <p id="contactStatus" class="form-status"></p>
        </form>
    </section>'''

        actor_options = "\n                ".join(
            f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in ctx["actors"]
        )

        # --- Tableau de bord post-connexion : ce que l'acteur connecté peut
        # réellement faire (voir _compute_actor_capabilities), embarqué en
        # JSON -- entièrement déterministe (noms d'entités/champs/fonctions
        # tels que déclarés dans la spec), zéro contenu généré par l'IA ici.
        capabilities_json = json.dumps(self._compute_actor_capabilities(), ensure_ascii=False)

        # --- Hero : 2 mises en page structurellement différentes (voir
        # _pick_hero_variant) plutôt qu'une seule avec de la couleur variable.
        hero_variant = self._pick_hero_variant(theme_seed)
        if hero_variant == "split":
            hero_html = f'''
    <section class="hero hero-split">
        <div class="hero-copy">
            <h1>{marker('headline', copy['headline'])}</h1>
            <p class="subheadline">{marker('subheadline', copy['subheadline'])}</p>
            <a href="#get-started" class="cta cta-primary js-scroll">{marker('cta_label', copy['cta_label'])}</a>
        </div>
        <div class="hero-decor" aria-hidden="true">
            <span class="decor-dot" style="left: 20%; top: 24%;"></span>
            <span class="decor-dot accent2" style="left: 55%; top: 46%;"></span>
            <span class="decor-dot" style="left: 78%; top: 22%;"></span>
            <span class="decor-dot accent2" style="left: 32%; top: 72%;"></span>
            <span class="decor-dot" style="left: 82%; top: 68%;"></span>
            <svg class="decor-lines"><line x1="20%" y1="24%" x2="55%" y2="46%"/><line x1="55%" y1="46%" x2="78%" y2="22%"/><line x1="55%" y1="46%" x2="32%" y2="72%"/><line x1="55%" y1="46%" x2="82%" y2="68%"/></svg>
        </div>
    </section>'''
        else:
            hero_html = f'''
    <section class="hero">
        <h1>{marker('headline', copy['headline'])}</h1>
        <p class="subheadline">{marker('subheadline', copy['subheadline'])}</p>
        <a href="#get-started" class="cta cta-primary js-scroll">{marker('cta_label', copy['cta_label'])}</a>
    </section>'''

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.app_name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={theme['google_fonts']}&display=swap" rel="stylesheet">
<style>
    :root {{
        --bg: {theme['bg']}; --surface: {theme['surface']}; --ink: {theme['ink']};
        --accent: {theme['accent']}; --accent2: {theme['accent2']}; --radius: {theme['radius']};
        --font-display: {theme['font_display']}; --font-body: {theme['font_body']};
        --line: color-mix(in srgb, var(--ink) 12%, transparent);
        --muted: color-mix(in srgb, var(--ink) 60%, transparent);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); }}
    a {{ color: inherit; }}
    code {{ font-family: monospace; background: var(--surface); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.85em; }}

    header {{ border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--bg); z-index: 10; }}
    nav {{
        max-width: 1000px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;
        padding: 1.1rem 1.5rem;
    }}
    nav .brand {{ font-family: var(--font-display); font-weight: 700; font-size: 1.15rem; }}
    .nav-toggle {{
        display: none; background: none; border: 1px solid var(--line); border-radius: var(--radius);
        font-size: 1.1rem; padding: 0.3rem 0.6rem; color: var(--ink); cursor: pointer;
    }}
    .nav-links {{ display: flex; align-items: center; gap: 1.5rem; font-size: 0.9rem; }}
    .nav-links a {{ text-decoration: none; opacity: 0.8; }}
    .nav-links a:hover {{ opacity: 1; }}
    .nav-links .nav-docs {{
        opacity: 1; background: var(--surface); padding: 0.4rem 0.9rem; border-radius: var(--radius);
        border: 1px solid var(--line);
    }}

    main {{ max-width: 1000px; margin: 0 auto; padding: 0 1.5rem; }}

    .hero {{ text-align: center; padding: clamp(3.2rem, 7vw, 5.5rem) 1rem 3rem; max-width: 680px; margin: 0 auto; }}

    /* AJOUT (roadmap, "les sites se ressemblent") : mise en page de hero
       alternative -- 2 colonnes plutôt qu'1, élément décoratif abstrait
       plutôt que rien -- pour une vraie variété structurelle. */
    .hero-split {{
        display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 3rem; align-items: center;
        text-align: left; max-width: 980px; padding: clamp(3rem, 7vw, 5rem) 1rem 3rem;
    }}
    .hero-split .subheadline {{ margin-left: 0; }}
    .hero-split .cta {{ display: inline-block; }}
    .hero-decor {{
        position: relative; height: 260px; border-radius: var(--radius); overflow: hidden;
        background: var(--surface); border: 1px solid var(--line);
    }}
    .decor-dot {{
        position: absolute; width: 9px; height: 9px; border-radius: 50%; background: var(--accent);
        box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 16%, transparent);
    }}
    .decor-dot.accent2 {{ background: var(--accent2); box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent2) 16%, transparent); }}
    .decor-lines {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
    .decor-lines line {{ stroke: var(--line); stroke-width: 1; }}
    @media (max-width: 760px) {{
        .hero-split {{ grid-template-columns: 1fr; text-align: center; }}
        .hero-split .subheadline {{ margin-left: auto; margin-right: auto; }}
        .hero-decor {{ height: 180px; }}
    }}
    h1 {{ font-family: var(--font-display); font-size: clamp(2rem, 4.6vw, 3.1rem); line-height: 1.14; margin: 0 0 1.1rem; }}
    .subheadline {{ font-size: 1.08rem; color: var(--muted); margin: 0 0 2rem; }}
    .cta {{
        display: inline-block; text-decoration: none; font-weight: 600; font-size: 0.96rem;
        padding: 0.85rem 1.7rem; border-radius: var(--radius); border: none; cursor: pointer; font-family: inherit;
    }}
    .cta-primary {{ background: var(--accent); color: var(--surface); box-shadow: 0 8px 24px -10px var(--accent); }}

    .block {{ padding: 3rem 0; border-top: 1px solid var(--line); }}
    .block h2 {{ font-family: var(--font-display); font-size: 1.5rem; margin: 0 0 0.5rem; text-align: center; }}
    .block-sub {{ text-align: center; color: var(--muted); font-size: 0.92rem; margin: 0 0 2rem; }}

    .block-form {{
        display: flex; flex-direction: column; gap: 0.9rem; max-width: 420px; margin: 0 auto;
        background: var(--surface); padding: 1.8rem; border-radius: var(--radius);
    }}
    .field {{ display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.85rem; color: var(--muted); }}
    .field input, .field select, .field textarea {{
        font-family: inherit; font-size: 0.95rem; padding: 0.6rem 0.7rem; border-radius: calc(var(--radius) / 1.4);
        border: 1px solid var(--line); background: var(--bg); color: var(--ink);
    }}
    .field-checkbox {{ flex-direction: row; align-items: center; }}
    .form-row {{ display: flex; gap: 0.7rem; }}
    .form-status {{ font-size: 0.85rem; min-height: 1.2em; margin: 0; }}
    .form-status.ok {{ color: var(--accent); }}
    .form-status.err {{ color: #C1392B; }}

    .auth-tabs {{ display: flex; gap: 0.5rem; margin-bottom: 0.4rem; }}
    .auth-tabs button {{
        flex: 1; padding: 0.5rem; border-radius: calc(var(--radius) / 1.4); border: 1px solid var(--line);
        background: var(--bg); color: var(--muted); font-family: inherit; cursor: pointer; font-size: 0.85rem;
    }}
    .auth-tabs button.active {{ background: var(--accent); color: var(--surface); border-color: var(--accent); }}

    .preview-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.8rem; max-width: 760px; margin: 0 auto; }}
    .preview-card {{ background: var(--surface); border-radius: var(--radius); padding: 1rem 1.1rem; font-size: 0.9rem; }}
    .hint {{ color: var(--muted); font-size: 0.88rem; text-align: center; grid-column: 1 / -1; }}

    footer {{ border-top: 1px solid var(--line); margin-top: 1rem; padding: 1.8rem 1.5rem; text-align: center; }}
    .footer-copy {{ color: var(--muted); font-size: 0.78rem; margin: 0; }}

    @media (max-width: 720px) {{
        .nav-toggle {{ display: inline-block; }}
        .nav-links {{
            position: absolute; top: 100%; left: 0; right: 0; background: var(--bg); border-bottom: 1px solid var(--line);
            flex-direction: column; align-items: flex-start; padding: 1rem 1.5rem; gap: 1rem; display: none;
        }}
        .nav-links.open {{ display: flex; }}
    }}
</style>
</head>
<body>

<header>
    <nav>
        <span class="brand">{self.app_name}</span>
        <button class="nav-toggle" id="navToggle" aria-label="Ouvrir le menu">☰</button>
        <div class="nav-links" id="navLinks">
            {nav_links_html}
        </div>
    </nav>
</header>

<main>
{hero_html}
{preview_section}
    <section class="block" id="get-started">
        <h2>Créer un compte</h2>
        <p class="block-sub">Fonctionne réellement : <code>POST /register</code> puis <code>POST /login</code>.</p>
        <form id="authForm" class="block-form">
            <div class="auth-tabs">
                <button type="button" id="tabRegister" class="active">Créer un compte</button>
                <button type="button" id="tabLogin">Se connecter</button>
            </div>
            <label class="field">Nom d'utilisateur<input type="text" id="authUsername" required></label>
            <label class="field">Mot de passe (8 caractères min.)<input type="password" id="authPassword" required></label>
            <label class="field" id="actorField">Acteur
                <select id="authActor">
                {actor_options}
                </select>
            </label>
            <button type="submit" class="cta cta-primary" id="authSubmit">Créer un compte</button>
            <p id="authStatus" class="form-status"></p>
        </form>
    </section>
{contact_section}
</main>

<footer>
    <p class="footer-copy">{self.app_name} · généré par MonLang · <span id="year"></span> · <a href="/docs">Documentation API</a></p>
</footer>

<script>
    document.getElementById('navToggle').addEventListener('click', function () {{
        document.getElementById('navLinks').classList.toggle('open');
    }});
    document.querySelectorAll('.js-scroll').forEach(function (a) {{
        a.addEventListener('click', function (e) {{
            var target = document.querySelector(a.getAttribute('href'));
            if (target) {{
                e.preventDefault();
                target.scrollIntoView({{ behavior: 'smooth' }});
                document.getElementById('navLinks').classList.remove('open');
            }}
        }});
    }});
    document.getElementById('year').textContent = new Date().getFullYear();

    // --- Copier le jeton dans le presse-papiers ---
    try {{
        var copyBtn = document.getElementById('copyToken');
        if (copyBtn) {{
            copyBtn.addEventListener('click', function () {{
                var tokenValue = document.getElementById('tokenValue');
                tokenValue.select();
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(tokenValue.value).then(function () {{
                        copyBtn.textContent = 'Copié !';
                        setTimeout(function () {{ copyBtn.textContent = 'Copier'; }}, 1500);
                    }});
                }} else {{
                    document.execCommand('copy');
                }}
            }});
        }}
    }} catch (err) {{ console.error('[landing] copie du jeton indisponible :', err); }}

    // --- Formulaire de compte : vrai POST /register puis /login ---
    try {{
    (function () {{
        var mode = 'register';
        var tabRegister = document.getElementById('tabRegister');
        var tabLogin = document.getElementById('tabLogin');
        var actorField = document.getElementById('actorField');
        var submitBtn = document.getElementById('authSubmit');
        var status = document.getElementById('authStatus');

        // CORRECTIF (roadmap, "session expirée") : /app renvoie ici avec
        // '?session_expired=1' quand un appel API a répondu 401 (jeton
        // expiré ou révoqué) -- message clair plutôt qu'un retour silencieux
        // à la case départ sans explication.
        try {{
            if (new URLSearchParams(window.location.search).get('session_expired') === '1') {{
                status.textContent = 'Votre session a expiré — reconnectez-vous.';
                status.className = 'form-status err';
            }}
        }} catch (err) {{}}

        function setMode(next) {{
            mode = next;
            tabRegister.classList.toggle('active', mode === 'register');
            tabLogin.classList.toggle('active', mode === 'login');
            actorField.style.display = mode === 'register' ? 'flex' : 'none';
            submitBtn.textContent = mode === 'register' ? 'Créer un compte' : 'Se connecter';
            status.textContent = '';
        }}
        tabRegister.addEventListener('click', function () {{ setMode('register'); }});
        tabLogin.addEventListener('click', function () {{ setMode('login'); }});

        function onLoginSuccess(token) {{
            // CORRECTIF (roadmap, "je devrais me retrouver sur une autre
            // page") : la connexion ne déroule plus un tableau de bord sur
            // la landing elle-même -- elle navigue réellement vers '/app'
            // (nouvelle page, voir _generate_dashboard_page). Le jeton
            // voyage par sessionStorage (propre à cet onglet, effacé à sa
            // fermeture) plutôt que par l'URL, pour ne pas le laisser traîner
            // dans l'historique de navigation ou les journaux du serveur.
            status.textContent = 'Connecté — redirection…';
            status.className = 'form-status ok';
            try {{
                sessionStorage.setItem('monlang_token', token);
            }} catch (err) {{
                console.error('[landing] sessionStorage indisponible :', err);
            }}
            setTimeout(function () {{ window.location.href = '/app'; }}, 300);
        }}

        function doLogin(username, password) {{
            return fetch('/login', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ username: username, password: password }}) }})
                .then(function (res) {{ return res.json().then(function (data) {{ return {{ ok: res.ok, data: data }}; }}); }});
        }}

        document.getElementById('authForm').addEventListener('submit', function (e) {{
            e.preventDefault();
            try {{
                var username = document.getElementById('authUsername').value;
                var password = document.getElementById('authPassword').value;
                var actor = document.getElementById('authActor').value;

                status.textContent = '…'; status.className = 'form-status';

                if (mode === 'register') {{
                    fetch('/register', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ username: username, password: password, actor: actor }}) }})
                        .then(function (res) {{ return res.json().then(function (data) {{ return {{ ok: res.ok, data: data }}; }}); }})
                        .then(function (r) {{
                            if (!r.ok) {{ status.textContent = 'Erreur : ' + (r.data.detail || 'échec.'); status.className = 'form-status err'; return; }}
                            // CORRECTIF (roadmap, "un site moderne") : plutôt que de
                            // laisser la personne retaper ses identifiants, on enchaîne
                            // automatiquement sur la connexion -- un vrai POST /login,
                            // pas une simulation.
                            status.textContent = 'Compte créé, connexion en cours…'; status.className = 'form-status ok';
                            setMode('login');
                            return doLogin(username, password).then(function (r2) {{
                                if (r2.ok) onLoginSuccess(r2.data.access_token);
                                else {{ status.textContent = 'Compte créé — connectez-vous manuellement.'; status.className = 'form-status err'; }}
                            }});
                        }})
                        .catch(function () {{ status.textContent = 'Erreur réseau.'; status.className = 'form-status err'; }});
                }} else {{
                    doLogin(username, password)
                        .then(function (r) {{
                            if (r.ok) onLoginSuccess(r.data.access_token);
                            else {{ status.textContent = 'Erreur : ' + (r.data.detail || 'échec.'); status.className = 'form-status err'; }}
                        }})
                        .catch(function () {{ status.textContent = 'Erreur réseau.'; status.className = 'form-status err'; }});
                }}
            }} catch (err) {{
                status.textContent = 'Erreur inattendue.'; status.className = 'form-status err';
            }}
        }});
    }})();
}} catch (err) {{ console.error('[landing] section compte indisponible :', err); }}

    // --- Aperçu en direct : vrai GET, sans compte requis ---
    // CORRECTIF (roadmap, bug réel trouvé par exécution du JS via jsdom) :
    // 'fetch(...)' était appelé au premier niveau du script (hors fonction).
    // Si cet appel lève une exception SYNCHRONE pour n'importe quelle raison
    // (réseau bloqué, extension navigateur, environnement restrictif...),
    // ça arrêtait l'exécution de TOUT LE RESTE du script -- et le
    // formulaire de contact plus bas ne recevait alors jamais son
    // écouteur d'évènement. Chaque section est désormais isolée dans son
    // propre bloc try/catch : la panne d'une section ne peut plus jamais
    // empêcher les autres de fonctionner.
    try {{
        var previewGrid = document.getElementById('previewGrid');
        if (previewGrid) {{
            fetch('/{ctx["preview_entity"].lower() if ctx["preview_entity"] else ""}?limit=6')
                .then(function (res) {{ return res.json(); }})
                .then(function (data) {{
                    var rows = (data && data.data) || [];
                    if (!rows.length) {{ previewGrid.innerHTML = '<p class="hint">Aucun élément pour l\\'instant.</p>'; return; }}
                    previewGrid.innerHTML = rows.map(function (row) {{
                        var titleField = '{ctx["preview_display_field"] or ""}';
                        var title = titleField && row[titleField] ? String(row[titleField]) : ('#' + row.id);
                        var div = document.createElement('div');
                        div.textContent = title;
                        return '<div class="preview-card">' + div.innerHTML + '</div>';
                    }}).join('');
                }})
                .catch(function () {{ previewGrid.innerHTML = '<p class="hint">Aperçu momentanément indisponible.</p>'; }});
        }}
    }} catch (err) {{ console.error('[landing] section aperçu indisponible :', err); }}

    // --- Formulaire de contact : vrai POST, sans compte requis ---
    try {{
        var contactForm = document.getElementById('contactForm');
        if (contactForm) {{
            contactForm.addEventListener('submit', function (e) {{
                e.preventDefault();
                try {{
                    var entity = contactForm.dataset.entity;
                    var status = document.getElementById('contactStatus');
                    var body = {{}};
                    contactForm.querySelectorAll('[data-field]').forEach(function (el) {{
                        body[el.dataset.field] = el.type === 'checkbox' ? el.checked
                            : (el.type === 'number' ? Number(el.value || 0) : el.value);
                    }});
                    status.textContent = '…'; status.className = 'form-status';
                    fetch('/' + entity, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(body) }})
                        .then(function (res) {{ return res.json().then(function (data) {{ return {{ ok: res.ok, data: data }}; }}); }})
                        .then(function (r) {{
                            if (r.ok) {{ status.textContent = 'Envoyé, merci !'; status.className = 'form-status ok'; contactForm.reset(); }}
                            else {{ status.textContent = 'Erreur : ' + (r.data.detail || 'échec.'); status.className = 'form-status err'; }}
                        }})
                        .catch(function () {{ status.textContent = 'Erreur réseau.'; status.className = 'form-status err'; }});
                }} catch (err) {{
                    var s = document.getElementById('contactStatus');
                    if (s) {{ s.textContent = 'Erreur inattendue.'; s.className = 'form-status err'; }}
                }}
            }});
        }}
    }} catch (err) {{ console.error('[landing] section contact indisponible :', err); }}
</script>

</body>
</html>
"""


    def _generate_landing_from_template(self, template_path):
        """Mode 'template' : importe le fichier HTML fourni par l'utilisateur
        tel quel, et y substitue uniquement les emplacements qu'il a
        explicitement balisés avec 'data-monlang="clé"' (texte affiché) ou
        'data-monlang-href="clé"' (attribut href/src) — pour un ensemble fixe
        de clés réservées connues (voir _deterministic_landing_copy). Tout
        emplacement balisé avec une clé inconnue, ou tout le reste du
        fichier, n'est PAS modifié : MonLang ne réinterprète jamais la mise
        en page fournie par l'utilisateur, il ne fait que remplir des blancs
        explicitement désignés — substitution par expressions régulières
        volontairement simple (pas de dépendance à un parseur HTML complet),
        suffisante pour des gabarits de landing bien formés à plat."""
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        copy = self._deterministic_landing_copy()
        # CORRECTIF (roadmap) : _deterministic_landing_copy() a été réduit à
        # headline/subheadline (fini le texte décoratif superflu, voir
        # _generate_landing_ai_shell). Un gabarit importé peut néanmoins
        # exposer plus d'emplacements (ex. templates/signal.html a encore
        # 'eyebrow'/'feature_1-3'/'closing_line') : ceux-ci reçoivent un
        # texte de repli simple, dérivé des entités, calculé ici plutôt que
        # dans _deterministic_landing_copy (qui ne doit plus en dépendre).
        entity_names = list(self.entities.keys())
        fallback_features = [f"Gérez vos {e.lower()}s" for e in entity_names[:3]] or ["Simple", "Rapide", "Fiable"]
        while len(fallback_features) < 3:
            fallback_features.append("Prêt à l'emploi")

        text_values = {
            "app_name": self.app_name,
            "eyebrow": "Généré par MonLang",
            "headline": copy["headline"],
            "subheadline": copy["subheadline"],
            "cta_label": copy["cta_label"],
            "feature_1": fallback_features[0],
            "feature_2": fallback_features[1],
            "feature_3": fallback_features[2],
            "closing_line": f"Prêt à découvrir {self.app_name} ?",
        }
        href_values = {"cta_target": copy["cta_target"]}

        for key, value in text_values.items():
            safe_value = html.escape(value)
            pattern = re.compile(
                r'(<([a-zA-Z0-9]+)([^>]*\bdata-monlang="' + re.escape(key) + r'"[^>]*)>)(.*?)(</\2>)',
                re.DOTALL,
            )
            content = pattern.sub(lambda m: m.group(1) + safe_value + m.group(5), content)

        for key, value in href_values.items():
            safe_value = html.escape(value, quote=True)
            pattern = re.compile(
                r'(<[a-zA-Z0-9]+[^>]*\bdata-monlang-href="' + re.escape(key) + r'"[^>]*?\s(?:href|src)=")[^"]*(")'
            )
            content = pattern.sub(lambda m: m.group(1) + safe_value + m.group(2), content)

        # AJOUT (roadmap, "corrige tout ces points" -- mode template n'avait
        # aucune fonctionnalité réelle) : contrairement au mode 'ai', un
        # gabarit importé est un fichier HTML arbitraire fourni par
        # l'utilisateur -- MonLang ne peut pas savoir où il a prévu de mettre
        # un formulaire de connexion, ni même s'il en a prévu un du tout. Un
        # petit widget de compte, autonome et neutre visuellement (styles
        # scopés sous 'monlang-auth', pour ne jamais entrer en collision avec
        # les classes du gabarit importé), est injecté juste avant
        # '</body>' -- même comportement que le mode 'ai' : vrai
        # POST /register puis /login, redirection vers '/app' au succès.
        ctx_for_widget = self._compute_landing_functional_context()
        auth_widget = self._generate_template_auth_widget(ctx_for_widget["actors"])
        if "</body>" in content:
            content = content.replace("</body>", auth_widget + "\n</body>", 1)
        else:
            content += auth_widget

        return content

    def _generate_template_auth_widget(self, actors):
        """Widget de compte autonome injecté dans les pages du mode
        'template' (voir _generate_landing_from_template). Volontairement
        minimal (pas de tableau de bord ici, juste inscription/connexion) --
        une fois connecté, redirige vers '/app', qui lui est partagé avec le
        mode 'ai' et fonctionne à l'identique quel que soit le mode ayant
        servi la landing."""
        actor_options = "\n                    ".join(
            f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in actors
        )
        return f"""
<div id="monlang-auth-widget" style="position:fixed;bottom:1.2rem;right:1.2rem;z-index:9999;font-family:system-ui,sans-serif;">
    <button id="monlang-auth-toggle" style="background:#16181D;color:#fff;border:none;border-radius:8px;padding:0.7rem 1.1rem;font-size:0.85rem;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,0.25);">
        Se connecter
    </button>
    <div id="monlang-auth-panel" hidden style="position:absolute;bottom:3.2rem;right:0;width:260px;background:#fff;color:#16181D;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,0.25);padding:1rem;">
        <div style="display:flex;gap:0.4rem;margin-bottom:0.6rem;">
            <button type="button" id="monlang-tab-register" style="flex:1;padding:0.4rem;font-size:0.78rem;border:1px solid #ddd;border-radius:6px;background:#16181D;color:#fff;cursor:pointer;">Créer un compte</button>
            <button type="button" id="monlang-tab-login" style="flex:1;padding:0.4rem;font-size:0.78rem;border:1px solid #ddd;border-radius:6px;background:#fff;color:#16181D;cursor:pointer;">Se connecter</button>
        </div>
        <input type="text" id="monlang-username" placeholder="Nom d'utilisateur" style="width:100%;box-sizing:border-box;margin-bottom:0.5rem;padding:0.5rem;font-size:0.85rem;border:1px solid #ddd;border-radius:6px;">
        <input type="password" id="monlang-password" placeholder="Mot de passe (8 car. min.)" style="width:100%;box-sizing:border-box;margin-bottom:0.5rem;padding:0.5rem;font-size:0.85rem;border:1px solid #ddd;border-radius:6px;">
        <select id="monlang-actor" style="width:100%;box-sizing:border-box;margin-bottom:0.6rem;padding:0.5rem;font-size:0.85rem;border:1px solid #ddd;border-radius:6px;">
            {actor_options}
        </select>
        <button type="button" id="monlang-submit" style="width:100%;padding:0.55rem;font-size:0.85rem;border:none;border-radius:6px;background:#16181D;color:#fff;cursor:pointer;">Créer un compte</button>
        <p id="monlang-status" style="font-size:0.76rem;min-height:1.1em;margin:0.5rem 0 0;"></p>
    </div>
</div>
<script>
(function () {{
    var mode = 'register';
    var toggle = document.getElementById('monlang-auth-toggle');
    var panel = document.getElementById('monlang-auth-panel');
    var tabR = document.getElementById('monlang-tab-register');
    var tabL = document.getElementById('monlang-tab-login');
    var actorSel = document.getElementById('monlang-actor');
    var submitBtn = document.getElementById('monlang-submit');
    var status = document.getElementById('monlang-status');

    toggle.addEventListener('click', function () {{ panel.hidden = !panel.hidden; }});

    function setMode(next) {{
        mode = next;
        tabR.style.background = mode === 'register' ? '#16181D' : '#fff';
        tabR.style.color = mode === 'register' ? '#fff' : '#16181D';
        tabL.style.background = mode === 'login' ? '#16181D' : '#fff';
        tabL.style.color = mode === 'login' ? '#fff' : '#16181D';
        actorSel.style.display = mode === 'register' ? 'block' : 'none';
        submitBtn.textContent = mode === 'register' ? 'Créer un compte' : 'Se connecter';
        status.textContent = '';
    }}
    tabR.addEventListener('click', function () {{ setMode('register'); }});
    tabL.addEventListener('click', function () {{ setMode('login'); }});

    function doLogin(username, password) {{
        return fetch('/login', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ username: username, password: password }}) }})
            .then(function (res) {{ return res.json().then(function (data) {{ return {{ ok: res.ok, data: data }}; }}); }});
    }}

    submitBtn.addEventListener('click', function () {{
        try {{
            var username = document.getElementById('monlang-username').value;
            var password = document.getElementById('monlang-password').value;
            var actor = actorSel.value;
            status.textContent = '…';

            if (mode === 'register') {{
                fetch('/register', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ username: username, password: password, actor: actor }}) }})
                    .then(function (res) {{ return res.json().then(function (data) {{ return {{ ok: res.ok, data: data }}; }}); }})
                    .then(function (r) {{
                        if (!r.ok) {{ status.textContent = 'Erreur : ' + (r.data.detail || 'échec.'); return; }}
                        status.textContent = 'Compte créé, connexion…';
                        setMode('login');
                        return doLogin(username, password).then(function (r2) {{
                            if (r2.ok) {{
                                status.textContent = 'Connecté — redirection…';
                                try {{ sessionStorage.setItem('monlang_token', r2.data.access_token); }} catch (err) {{}}
                                setTimeout(function () {{ window.location.href = '/app'; }}, 300);
                            }} else {{ status.textContent = 'Compte créé — connectez-vous manuellement.'; }}
                        }});
                    }})
                    .catch(function () {{ status.textContent = 'Erreur réseau.'; }});
            }} else {{
                doLogin(username, password).then(function (r) {{
                    if (r.ok) {{
                        status.textContent = 'Connecté — redirection…';
                        try {{ sessionStorage.setItem('monlang_token', r.data.access_token); }} catch (err) {{}}
                        setTimeout(function () {{ window.location.href = '/app'; }}, 300);
                    }} else {{ status.textContent = 'Erreur : ' + (r.data.detail || 'échec.'); }}
                }}).catch(function () {{ status.textContent = 'Erreur réseau.'; }});
            }}
        }} catch (err) {{ status.textContent = 'Erreur inattendue.'; }}
    }});
}})();
</script>
"""



    def _generate_dashboard_page(self):
        """AJOUT (roadmap, "je devrais me retrouver sur une autre page") :
        seconde page, servie sur '/app', qui n'existe que si un bloc
        'landing' est présent. Contrairement à 'landing.html' (accessible à
        n'importe qui, c'est une page marketing), celle-ci exige un vrai
        jeton JWT : lu depuis sessionStorage au chargement, et si absent,
        renvoie immédiatement vers '/' plutôt que d'afficher une page vide
        -- ce n'est pas une route protégée côté serveur (chaque appel API
        depuis cette page reste vérifié par le serveur comme n'importe quel
        appel authentifié ; la protection ici est seulement pour l'expérience
        -- éviter d'atterrir sur une page cassée sans jeton), mais elle
        empêche d'y arriver "par erreur" en tapant l'URL sans s'être connecté.
        Reprend le même thème que 'landing.html' (cohérence visuelle) et le
        même tableau de bord que l'ancienne version intégrée -- extrait ici
        tel quel plutôt que dupliqué en le réécrivant."""
        theme_seed = self._load_or_create_theme_seed()
        theme_name, theme = self._select_theme(theme_seed)
        capabilities_json = json.dumps(self._compute_actor_capabilities(), ensure_ascii=False)
        dashboard_js = DASHBOARD_JS_BLOCK.replace("{capabilities_json}", capabilities_json)

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.app_name} — Votre espace</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={theme['google_fonts']}&display=swap" rel="stylesheet">
<style>
    :root {{
        --bg: {theme['bg']}; --surface: {theme['surface']}; --ink: {theme['ink']};
        --accent: {theme['accent']}; --accent2: {theme['accent2']}; --radius: {theme['radius']};
        --font-display: {theme['font_display']}; --font-body: {theme['font_body']};
        --line: color-mix(in srgb, var(--ink) 12%, transparent);
        --muted: color-mix(in srgb, var(--ink) 60%, transparent);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); }}
    a {{ color: inherit; }}
    code {{ font-family: monospace; background: var(--surface); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.85em; }}

    header {{ border-bottom: 1px solid var(--line); }}
    nav {{
        max-width: 1000px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center;
        padding: 1.1rem 1.5rem;
    }}
    nav .brand {{ font-family: var(--font-display); font-weight: 700; font-size: 1.15rem; }}
    .nav-links {{ display: flex; align-items: center; gap: 1rem; font-size: 0.88rem; }}
    .nav-links a, .nav-links button {{
        text-decoration: none; color: inherit; font-family: inherit; font-size: inherit; cursor: pointer;
        background: none; border: 1px solid var(--line); border-radius: var(--radius); padding: 0.4rem 0.9rem;
    }}

    main {{ max-width: 1000px; margin: 0 auto; padding: 2.4rem 1.5rem 4rem; }}
    main h1 {{ font-family: var(--font-display); font-size: 1.7rem; margin: 0 0 0.3rem; }}
    main .lead {{ color: var(--muted); font-size: 0.94rem; margin: 0 0 2rem; }}

    .token-box {{
        max-width: 100%; margin: 0 0 2rem; background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--radius); padding: 1.1rem 1.3rem;
    }}
    .token-box summary {{ cursor: pointer; font-size: 0.86rem; font-weight: 600; }}
    .token-row {{ display: flex; gap: 0.5rem; margin-top: 0.8rem; }}
    .token-row input {{
        flex: 1; font-family: monospace; font-size: 0.75rem; padding: 0.55rem 0.6rem; border-radius: calc(var(--radius) / 1.4);
        border: 1px solid var(--line); background: var(--bg); color: var(--ink); min-width: 0;
    }}
    .token-row button {{
        padding: 0.55rem 1rem; font-size: 0.82rem; white-space: nowrap; border-radius: calc(var(--radius) / 1.4);
        border: 1px solid var(--line); background: var(--bg); color: var(--ink); cursor: pointer; font-family: inherit;
    }}

    .cta {{
        display: inline-block; text-decoration: none; font-weight: 600; font-size: 0.9rem;
        padding: 0.6rem 1.1rem; border-radius: var(--radius); border: none; cursor: pointer; font-family: inherit;
    }}
    .cta-primary {{ background: var(--accent); color: var(--surface); }}
    .cta-secondary {{ background: transparent; color: var(--ink); border: 1px solid var(--line); }}

    .field {{ display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.85rem; color: var(--muted); }}
    .field input, .field select, .field textarea {{
        font-family: inherit; font-size: 0.95rem; padding: 0.6rem 0.7rem; border-radius: calc(var(--radius) / 1.4);
        border: 1px solid var(--line); background: var(--bg); color: var(--ink);
    }}
    .field-checkbox {{ flex-direction: row; align-items: center; }}

    .dashboard-grid {{
        display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.1rem;
    }}
    .dash-card {{ background: var(--surface); border-radius: var(--radius); padding: 1.3rem 1.4rem; text-align: left; }}
    .dash-card h3 {{ font-family: var(--font-display); font-size: 1.05rem; margin: 0 0 0.3rem; }}
    .dash-card .dash-hint {{ font-size: 0.78rem; color: var(--muted); margin: 0 0 1rem; }}
    .dash-card .field {{ margin-bottom: 0.6rem; }}
    .dash-actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.4rem; }}
    .dash-actions .cta {{ padding: 0.5rem 0.9rem; font-size: 0.82rem; }}
    .dash-id-row {{ display: flex; gap: 0.5rem; align-items: flex-end; margin-top: 0.9rem; }}
    .dash-id-row .field {{ flex: 1; margin-bottom: 0; }}
    .dash-list {{ margin-top: 0.9rem; display: flex; flex-direction: column; gap: 0.5rem; }}
    .dash-row {{
        background: var(--bg); border: 1px solid var(--line); border-radius: calc(var(--radius) / 1.4);
        padding: 0.55rem 0.75rem; font-size: 0.82rem; display: flex; align-items: center; justify-content: space-between;
        gap: 0.6rem; flex-wrap: wrap;
    }}
    .dash-row .dash-row-id {{ color: var(--muted); font-family: monospace; flex-shrink: 0; }}
    .dash-row > span:nth-child(2) {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 80px; }}
    .dash-row-actions {{ display: flex; gap: 0.4rem; flex-shrink: 0; }}
    .dash-row-actions .cta {{ padding: 0.3rem 0.6rem; font-size: 0.74rem; }}
    .dash-status {{ font-size: 0.8rem; min-height: 1.1em; margin: 0.5rem 0 0; }}
    .dash-status.ok {{ color: var(--accent); }}
    .dash-status.err {{ color: #C1392B; }}
    .hint {{ color: var(--muted); font-size: 0.88rem; }}
</style>
</head>
<body>

<header>
    <nav>
        <span class="brand">{self.app_name}</span>
        <div class="nav-links">
            <a href="/docs">Documentation API</a>
            <a href="/">Accueil</a>
            <button type="button" id="logoutBtn">Se déconnecter</button>
        </div>
    </nav>
</header>

<main>
    <h1>Votre espace</h1>
    <p class="lead">Propre à votre compte — chaque action ci-dessous appelle réellement l'API avec votre jeton.</p>

    <details class="token-box">
        <summary>Voir mon jeton (pour appeler l'API depuis /docs ou ailleurs)</summary>
        <div class="token-row">
            <input type="text" id="tokenValue" readonly>
            <button type="button" id="copyToken">Copier</button>
        </div>
    </details>

    <div id="dashboardContent" class="dashboard-grid">
        <p class="hint">Chargement…</p>
    </div>
</main>

<script>
{dashboard_js}
    // --- Garde d'accès : sans jeton en session, retour à l'accueil ---
    // (protection d'expérience, pas de sécurité -- chaque appel API reste
    // vérifié par le serveur quoi qu'il arrive)
    (function () {{
        var token = null;
        try {{ token = sessionStorage.getItem('monlang_token'); }} catch (err) {{ token = null; }}
        if (!token) {{ window.location.href = '/'; return; }}

        document.getElementById('tokenValue').value = token;
        document.getElementById('copyToken').addEventListener('click', function () {{
            var el = document.getElementById('tokenValue');
            el.select();
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(el.value);
            }} else {{
                document.execCommand('copy');
            }}
        }});
        document.getElementById('logoutBtn').addEventListener('click', function () {{
            try {{ sessionStorage.removeItem('monlang_token'); }} catch (err) {{}}
            window.location.href = '/';
        }});

        renderDashboard(token);
    }})();
</script>

</body>
</html>
"""

    def _generate_ai_sandbox(self):
        """Balise les frontières d'isolation pour le code généré par l'IA."""
        sb_lines = ["# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX\n"]
        for func in self.custom_functions:
            name = func["name"]
            desc = func.get("description", "Logique métier custom.").strip()
            sb_lines.append(f"def {name}(context: dict) -> dict:\n    \"\"\"\n    CONSIGNE IA : {desc}\n    \"\"\"\n    # TODO:\n    return {{'message': 'Coquille vide déterministe pour {name}'}}\n")
        return "\n".join(sb_lines)

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../todo.yaml")
    try:
        raw_json = parse_monlang_file(sample_path)
        ast_manager = MonLangAST(raw_json)
        normalized_ast = ast_manager.validate_and_audit()
        generator = MonLangSecureGenerator(normalized_ast)
        generator.generate_all()
    except Exception as e:
        print(f"❌ Échec : {e}")
