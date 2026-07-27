"""Classe principale du générateur : état issu de l'AST et orchestration.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""
import os
import secrets

from .admin_cli import AdminCliMixin
from .routes import RoutesMixin
from .runtime import RuntimeMixin
from .sandbox import SandboxMixin
from .schemas import SchemasMixin
from .sql_schema import SqlSchemaMixin
from .theme import ThemeMixin


class MonlSecureGenerator(
    AdminCliMixin,
    SqlSchemaMixin,
    RuntimeMixin,
    SchemasMixin,
    RoutesMixin,
    ThemeMixin,
    SandboxMixin,
):
    def __init__(self, normalized_ast, output_dir=None):
        # AJOUT (roadmap, compilation multi-projets) : 'output_dir' permet de
        # compiler chaque spec dans son propre dossier (option --output de
        # main.py) au lieu d'écraser systématiquement les artefacts à la
        # racine du dépôt. Par défaut (None), le comportement historique est
        # conservé : tout est écrit à la racine du dépôt.
        # POINT 65 : le défaut est le DOSSIER COURANT, plus un chemin déduit
        # de l'emplacement du module. Tant que le code vivait dans le dépôt,
        # remonter de deux niveaux depuis src/generator/ tombait sur la racine
        # et faisait illusion ; une fois monl installé (site-packages), le même
        # calcul écrivait l'application au milieu des paquets Python. Le
        # dossier courant est ce qu'attend n'importe quel outil en ligne de
        # commande, et il coïncide avec l'ancien comportement quand on lance
        # depuis la racine du dépôt.
        self.output_dir = os.path.abspath(output_dir or os.getcwd())
        os.makedirs(self.output_dir, exist_ok=True)
        self.ast = normalized_ast
        self.app_name = normalized_ast["meta"]["appName"]
        self.entities = normalized_ast["schema"]["entities"]
        self.relations = normalized_ast["schema"]["relations"]
        self.workflows = normalized_ast["security"]["workflows"]
        self.actors = normalized_ast["security"]["actors"]
        # AJOUT (bêta 3, correctif d'élévation de privilège) : seuls ces
        # rôles peuvent être choisis par un client à l'inscription
        # (marqueur 'selfRegister' dans la spec). Les autres sont
        # provisionnés hors ligne via le manage.py généré.
        self.self_register_actors = normalized_ast["security"].get("self_register_actors", [])
        self.custom_functions = normalized_ast["sandbox_ai"]["custom_functions"]
        # AJOUT (post-v6, roadmap) : map "Entite.Action" -> entité propriétaire,
        # issue des règles 'ownedBy' validées par ast_validator.py.
        self.ownership = normalized_ast["security"].get("ownership", {})
        # AJOUT (roadmap, brique "accès à deux parties") : table
        # {"Entite.Action": [colonnes]} issue des règles 'accessibleBy'
        # validées par ast_validator.py — chaque colonne contient
        # l'identifiant d'un utilisateur autorisé sur l'enregistrement.
        self.access_parties = normalized_ast["security"].get("access_parties", {})
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
        # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
        # champs 'generated' regroupés par entité -- retirés du schéma
        # Pydantic de la route Create (le client ne peut même pas tenter de
        # les fournir) et peuplés depuis le pseudonyme anonyme du compte
        # courant plutôt que depuis le corps de requête.
        self.generated_fields_by_entity = {}
        for gf in normalized_ast["security"].get("generated_fields", []):
            self.generated_fields_by_entity.setdefault(gf["entity"], []).append(gf["field"])
        # AJOUT (roadmap, contrôle du rendu visuel) : surcharges explicites du
        # thème/ordre/champ principal par entité, issues des blocs 'ui'.
        self.ui_overrides = normalized_ast.get("ui", {})
        # AJOUT (roadmap, écosystème de capacités -- brique 1) : capacités
        # déclarées via 'capability'. Purement informatif à ce stade -- rien
        # dans generate_all() ne branche encore dessus, puisque
        # l'authentification (seule capacité connue pour l'instant) est déjà
        # générée systématiquement quoi qu'il arrive. Les capacités futures
        # (masquage de champ, accès à deux parties) seront les premières à
        # réellement changer un comportement de génération selon ce qui est
        # déclaré ici.
        self.capabilities = normalized_ast.get("capabilities", [])
        # AJOUT (roadmap frontend, bloc 'seed') : données de démonstration à
        # insérer au démarrage si les tables sont vides (voir init_db).
        self.seeds = normalized_ast.get("seeds", [])

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
        # CORRECTIF (bêta 3) : avec plusieurs relations entrantes, prendre la
        # première déclarée revenait à désigner le « propriétaire » au hasard
        # de l'ordre d'écriture de la spec. Les règles 'ownedBy' nomment
        # explicitement l'entité propriétaire : c'est elle qui fait foi quand
        # elle existe. À défaut, on conserve la première relation déclarée.
        owners = {v for k, v in self.ownership.items() if k.split(".", 1)[0] == entity}
        chosen = next((p for p in placements if p["owner_entity"] in owners), placements[0])
        return {"source": chosen["owner_entity"], "fk_column": chosen["fk_column"]}

    def _client_fk_columns(self, entity):
        """Colonnes de clé étrangère que le CLIENT doit fournir à la création.

        Ce sont les parents de l'entité autres que le parent « propriétaire »
        (peuplé, lui, depuis l'identité JWT) : sans elles, une entité à deux
        parents ne peut pas être rattachée à sa cible (un commentaire à son
        post). N'a de sens que lorsqu'un parent propriétaire existe : sur une
        création publique, aucune identité n'est disponible et le
        comportement historique (colonnes laissées à NULL) est conservé.
        """
        owner_info = self._get_incoming_relation(entity)
        if not owner_info or (entity, "Create") in self.public_actions:
            return []
        if any(r["target_entity"] == owner_info["source"]
               for r in self.reputation_rules_by_trigger.get(entity, [])):
            return []  # cible de compteur : déjà fournie par le client
        return [p["fk_column"] for p in self._compute_fk_placements().get(entity, [])
                if p["fk_column"] != owner_info["fk_column"]]

    def _identity_fk_columns(self):
        """Colonnes de clé étrangère peuplées depuis l'identité JWT de l'appelant.

        Retourne {entité: {colonnes}}. Ce sont celles que la route Create
        remplit avec 'current_user_id' (identifiant de compte), et non avec
        une valeur du corps de requête — elles référencent donc le registre
        des comptes, pas la table métier homonyme. Même logique que
        'populate_owner' dans routes.py : une seule source de vérité mènerait
        à un couplage plus fort entre schéma et routes, les deux consomment
        donc ce helper commun.
        """
        route_map = self._compute_route_map()
        creatable = {info["base_target"] for (act, _k), info in route_map.items() if act == "Create"}
        identity_cols = {}
        for entity in self.entities:
            if entity not in creatable:
                continue
            owner_info = self._get_incoming_relation(entity)
            if not owner_info:
                continue
            if any(r["target_entity"] == owner_info["source"]
                   for r in self.reputation_rules_by_trigger.get(entity, [])):
                continue  # cible choisie par le client : vraie référence métier
            if (entity, "Create") in self.public_actions:
                continue  # aucune identité fiable : la colonne reste NULL
            identity_cols.setdefault(entity, set()).add(owner_info["fk_column"])
        return identity_cols

    def generate_all(self):
        """Déclenche la génération déterministe du BACKEND et les coquilles
        vides des blocs 'custom' (à compléter à la main). PIVOT (point 41 de
        docs/design_decisions.md) : monl ne génère plus AUCUN frontend
        (landing, dashboard, archétypes — tous retirés). L'interface est
        déléguée à une IA spécialisée via le contrat frontend
        (frontend_contract.json + FRONTEND_PROMPT.md, voir
        src/frontend_contract.py) ; '/docs' (Swagger) reste le seul front
        fourni, gratuitement, par FastAPI."""
        print(f"🏗️  Génération du socle déterministe réel pour '{self.app_name}'...")
        if self.capabilities:
            print(f"🧩 Capacités déclarées : {', '.join(self.capabilities)} (voir docs/design_decisions.md point 24).")

        sql_content = self._generate_sql()
        api_content = self._generate_secure_fastapi()
        sandbox_content = self._generate_ai_sandbox()
        manage_content = self._generate_manage_cli()

        # Détermination des chemins physiques (racine du dépôt par défaut,
        # ou dossier passé via --output — voir __init__).
        base_dir = self.output_dir
        sql_path = os.path.join(base_dir, "schema.sql")
        api_path = os.path.join(base_dir, "app.py")
        sandbox_path = os.path.join(base_dir, "sandbox_ai.py")
        manage_path = os.path.join(base_dir, "manage.py")
        secret_path = os.path.join(base_dir, ".jwt_secret")

        # CORRECTIF (roadmap, faille signalée) : le secret JWT était jusqu'ici
        # une chaîne fixe codée en dur dans generator.py, IDENTIQUE dans
        # absolument toutes les applications générées par monl. Un token
        # forgé pour une app était donc valide sur n'importe quelle autre
        # app générée par le même compilateur — quiconque lit le code source
        # public de monl connaît la clé secrète de toutes les applications
        # qui en sont issues. Un secret aléatoire de 32 octets est désormais
        # généré une seule fois par projet, à la première compilation, et
        # conservé dans '.jwt_secret' (à ajouter au .gitignore, jamais commité).
        # Recompiler la spec NE régénère PAS ce secret (pour ne pas invalider
        # les sessions déjà émises) — il faut le supprimer manuellement pour
        # en forcer le renouvellement.
        # CORRECTIF (bêta 3) : le fichier était créé avec les permissions par
        # défaut (0644 sur la plupart des systèmes) — n'importe quel compte
        # local pouvait lire le secret de signature et forger des jetons
        # valides. Il est désormais créé en 0600 (propriétaire seul), et une
        # compilation sur un projet existant resserre les permissions.
        if not os.path.exists(secret_path):
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(secrets.token_hex(32))
            print("🔑 Nouveau secret JWT généré dans '.jwt_secret' (32 octets, permissions 0600).")
        else:
            try:
                os.chmod(secret_path, 0o600)
            except OSError:
                pass
            print("🔑 Secret JWT existant conservé ('.jwt_secret', permissions 0600).")

        with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
        with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
        with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)
        with open(manage_path, "w", encoding="utf-8") as f: f.write(manage_content)

        print("💾 Socle généré : 'schema.sql', 'app.py', 'sandbox_ai.py' et 'manage.py' sont prêts !")
        if not self.self_register_actors:
            print("🔒 Aucun rôle en inscription libre : créez le premier compte avec "
                  "'python3 manage.py adduser <utilisateur> <role>'.")


    def _compute_seed_data(self):
        """AJOUT (roadmap frontend, bloc 'seed') : regroupe les données de
        démonstration par nom de table (lowercase), dans l'ordre de
        déclaration. Retourne {table: [ {champ: valeur}, ... ]}. Plusieurs
        blocs 'seed' visant la même entité sont concaténés.

        Les champs 'generated' (ex. pseudonyme anonyme d'auteur) ne sont pas
        renseignés par l'utilisateur dans le seed (le validateur le tolère
        car ils sont retirés du schéma d'entrée) ; comme à la création réelle
        ils sont assignés par le serveur, on leur donne ici une valeur
        synthétique déterministe ('Anon#1000', 'Anon#1001'…) pour que le seed
        produise des enregistrements complets et cohérents avec le rendu
        (fil social, etc.)."""
        seed_data = {}
        for seed in self.seeds:
            entity = seed["entity"]
            table = entity.lower()
            generated = self.generated_fields_by_entity.get(entity, [])
            seed_data.setdefault(table, [])
            for row in seed["rows"]:
                filled = dict(row)
                for gfield in generated:
                    if gfield not in filled:
                        # Pseudonyme synthétique stable, unique par ligne.
                        filled[gfield] = f"Anon#{1000 + len(seed_data[table])}"
                seed_data[table].append(filled)
        return seed_data

    def _compute_expected_columns(self):
        """AJOUT (roadmap long terme, migrations sans perte de données) :
        retourne {nom_table: [(colonne, type_sql), ...]} pour toutes les
        tables métier, dans l'ordre exact de _generate_sql (attributs
        déclarés puis clés étrangères entrantes). L'id n'y figure pas : il
        est toujours créé par le CREATE TABLE initial et n'est jamais
        ajouté a posteriori. Sert à init_db() pour détecter, au démarrage,
        les colonnes présentes dans la spec mais absentes d'une base déjà
        créée, et les ajouter par ALTER TABLE ADD COLUMN — opération
        purement additive, qui ne touche ni ne supprime aucune donnée
        existante."""
        fk_placements = self._compute_fk_placements()
        expected = {}
        for ent_name, attrs in self.entities.items():
            table = ent_name.lower()
            columns = []
            for attr_name, attr_type in attrs.items():
                columns.append((attr_name, self._map_type_to_sql(attr_type)))
            for placement in fk_placements.get(ent_name, []):
                columns.append((placement["fk_column"], "INTEGER"))
            expected[table] = columns
        return expected

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

    def _generate_secure_fastapi(self):
        """Assemble app.py à partir des trois couches générées séparément :
        socle runtime (auth, DB, migrations), schémas d'entrée, routes."""
        api_lines = self._generate_runtime_lines()
        api_lines += self._generate_schema_lines()
        api_lines += self._generate_route_lines()
        return "\n".join(api_lines)
