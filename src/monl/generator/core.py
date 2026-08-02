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

# Colonnes de suivi ajoutées par la brique 'payable' (point 74). Jamais
# fournies par le client, toujours présentes dans les réponses de lecture.
# Source unique de vérité : ces deux noms étaient écrits en dur dans quatre
# couches (schéma SQL, liste de colonnes, routes, et — depuis le point 76 —
# le contrat frontend). Quatre copies d'un nom de colonne, c'est quatre
# occasions de le faire dériver.
PAYMENT_STATUS_COLUMN = "payment_status"
PAYMENT_REF_COLUMN = "payment_ref"
PAYMENT_TRACKING_COLUMNS = (PAYMENT_STATUS_COLUMN, PAYMENT_REF_COLUMN)


class MonlSecureGenerator(
    AdminCliMixin,
    SqlSchemaMixin,
    RuntimeMixin,
    SchemasMixin,
    RoutesMixin,
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
        # AJOUT (brique 11, point 81) : propriété TRANSITIVE — {entité:
        # {"via", "actor"}}. L'entité n'appartient pas directement à un acteur
        # mais à un enregistrement intermédiaire, lui-même possédé par un
        # acteur. Conséquence sur toute la génération : la clé étrangère de
        # propriété n'est PLUS peuplée depuis le jeton, elle est fournie par le
        # client puis VÉRIFIÉE, et le contrôle d'accès devient une jointure.
        self.transitive_ownership = normalized_ast["security"].get("transitive_ownership", {})
        # AJOUT (brique 13, point 83) : assets déclarés (dossier, logo, favicon),
        # validés à la compilation — chaque fichier nommé existe réellement.
        self.assets = normalized_ast.get("assets") or {}
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
        # AJOUT (brique 17, point 90) : {Entite: EntiteExigee} — l'appelant doit
        # déjà posséder un enregistrement de la seconde pour créer la première.
        self.required_profiles = dict(
            normalized_ast["security"].get("required_profiles", {}))
        # AJOUT (brique 16, point 89) : champs horodatés à la création.
        # {Entite: [champ]} — le validateur garantit au plus UN par entité,
        # mais la forme liste garde le même maniement que les autres familles
        # de champs peuplés par le serveur.
        self.timestamp_fields_by_entity = {}
        for tf in normalized_ast["security"].get("timestamp_fields", []):
            self.timestamp_fields_by_entity.setdefault(tf["entity"], []).append(tf["field"])
        # AJOUT (brique paiement, point 74) : entité encaissable et champ
        # portant le montant. {Entite: champ} — le validateur garantit au
        # plus un champ payable par entité.
        self.payable_by_entity = {
            pf["entity"]: pf["field"]
            for pf in normalized_ast["security"].get("payable_fields", [])
        }
        # AJOUT (brique 10, point 77) : champs CALCULÉS PAR LE SERVEUR depuis
        # une ligne liée. {Entite: [règle, ...]} — le validateur garantit au
        # plus une règle par champ, mais une entité peut en porter plusieurs.
        # AJOUT (brique 12, point 82) : sommes 'sumOf'. Deux index, parce que la
        # brique se lit dans les deux sens — depuis le PARENT pour retirer le
        # champ des corps de requête, depuis l'ENFANT pour savoir quoi recalculer
        # après chaque écriture de ligne.
        self.aggregated_by_entity = {}
        self.aggregations_by_source = {}
        for regle in normalized_ast["security"].get("aggregated_fields", []):
            self.aggregated_by_entity.setdefault(regle["entity"], []).append(regle)
            self.aggregations_by_source.setdefault(regle["source_entity"], []).append(regle)
        self.derived_by_entity = {}
        for regle in normalized_ast["security"].get("derived_fields", []):
            self.derived_by_entity.setdefault(regle["entity"], []).append(regle)
        # POINT 85 : 'required'/'unique'/'min'/'max' ne produisaient RIEN — la
        # sortie était identique à l'octet avec ou sans elles. Regroupées par
        # entité : les bornes partent dans le schéma Pydantic (schemas.py),
        # 'unique' devient un index unique (sql_schema.py).
        self.field_constraints = {}
        for (entite, champ), contraintes in normalized_ast["security"].get(
                "field_constraints", {}).items():
            self.field_constraints.setdefault(entite, {})[champ] = contraintes
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
        # POINT 95 : la brique 1 se réveille. 'capability auth' était déclaratif
        # depuis toujours — il contraint désormais la FORME de l'identifiant de
        # compte. None = rien de déclaré = comportement historique intact.
        self.auth_identifier = (normalized_ast.get("security", {})
                                .get("auth_identifier"))
        # Indicatif déclaré : sans lui, '06…' et '+336…' restent deux comptes.
        self.auth_phone_prefix = (normalized_ast.get("security", {})
                                  .get("auth_phone_prefix"))
        # BRIQUE 19 (point 96) : {Entite: {champ: [valeurs]}} — un statut est un
        # état parmi quelques-uns, pas du texte libre.
        self.enumerated_fields = (normalized_ast.get("security", {})
                                  .get("enumerated_fields") or {})
        # BRIQUE 20 (point 98) : {Entite: [règle]} — atteindre une valeur rend
        # ce que les enfants ont décompté. Indexé par l'entité PORTEUSE du
        # champ, qui est celle dont la route Update déclenche la libération.
        self.release_rules_by_entity = {}
        for regle in (normalized_ast.get("security", {}).get("release_rules") or []):
            self.release_rules_by_entity.setdefault(regle["entity"], []).append(regle)
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

    def _derived_field_names(self, entity):
        """Champs de 'entity' calculés par le serveur (brique 10, point 77).

        Ils doivent être traités comme les champs 'generated' partout où le
        client pourrait les fournir : absents du schéma Pydantic, et exclus des
        valeurs d'écriture qu'on lit dans `data`."""
        return [r["field"] for r in self.derived_by_entity.get(entity, [])]

    def _derived_source_fk(self, entity, source_entity):
        """Colonne de clé étrangère de 'entity' qui désigne la ligne de
        'source_entity' à lire. Le validateur a garanti que la relation existe
        et que la source n'est PAS le propriétaire — donc cette colonne est
        fournie par le client, jamais déduite du jeton."""
        for placement in self._compute_fk_placements().get(entity, []):
            if placement["owner_entity"] == source_entity:
                return placement["fk_column"]
        # Le validateur a déjà exigé la relation : arriver ici signifie que la
        # validation et le placement des clés étrangères ont divergé. Échouer à
        # la génération vaut mieux qu'émettre 'data.None' dans le app.py.
        raise ValueError(
            f"Génération : aucune colonne de clé étrangère de '{entity}' ne "
            f"désigne '{source_entity}', alors que le validateur l'exigeait "
            f"pour 'derivedFrom'."
        )

    def _transitive_chain(self, entity):
        """Chaîne de propriété transitive de 'entity', ou None (brique 11).

        Retourne les DEUX colonnes que la jointure de contrôle d'accès met en
        regard : celle qui, sur 'entity', désigne l'enregistrement
        intermédiaire (fournie par le client), et celle qui, sur cet
        intermédiaire, porte l'identifiant du compte propriétaire (peuplée
        depuis le jeton). Source unique de vérité de la brique : routes,
        schémas et contrat frontend passent tous par ici."""
        chaine = self.transitive_ownership.get(entity)
        if not chaine:
            return None
        placements = self._compute_fk_placements()
        via, acteur = chaine["via"], chaine["actor"]
        via_fk = next((p["fk_column"] for p in placements.get(entity, [])
                       if p["owner_entity"] == via), None)
        actor_fk = next((p["fk_column"] for p in placements.get(via, [])
                         if p["owner_entity"] == acteur), None)
        # Le validateur a exigé les deux relations : arriver ici sans colonne
        # signifie que validation et placement des clés étrangères ont divergé.
        # Échouer à la génération vaut mieux qu'écrire une jointure sur None,
        # qui filtrerait sur rien -- donc rendrait tout visible à tous.
        if not via_fk or not actor_fk:
            raise ValueError(
                f"Génération : la chaîne de propriété '{entity}' -> '{via}' -> "
                f"'{acteur}' manque d'une colonne de clé étrangère "
                f"(via={via_fk}, acteur={actor_fk})."
            )
        return {"via": via, "via_fk": via_fk, "via_table": via.lower(),
                "actor": acteur, "actor_fk": actor_fk}

    def _aggregated_field_names(self, entity):
        """Champs de 'entity' qui sont une SOMME de ses enfants (brique 12).

        Traités partout comme les champs 'derivedFrom' : absents du schéma
        Pydantic, et jamais lus dans `data`."""
        return [r["field"] for r in self.aggregated_by_entity.get(entity, [])]

    def _aggregation_recomputes(self, source_entity):
        """Sommes à recalculer après toute écriture sur 'source_entity'.

        Retourne, par règle, la requête de recalcul et la colonne de clé
        étrangère qui désigne le parent. La somme est RECALCULÉE depuis la table
        plutôt qu'ajustée d'un delta : un ajustement se désynchronise dès qu'une
        écriture échoue à mi-chemin, un recalcul est toujours juste. COALESCE
        pour qu'un panier vidé retombe à 0 et non à NULL ; ROUND parce qu'une
        somme de flottants dérive (0.1 + 0.2), et c'est un montant."""
        recalculs = []
        placements = self._compute_fk_placements().get(source_entity, [])
        for regle in self.aggregations_by_source.get(source_entity, []):
            fk = next((p["fk_column"] for p in placements
                       if p["owner_entity"] == regle["entity"]), None)
            # Le validateur a exigé la relation parent-enfant : arriver ici sans
            # colonne signifie que validation et placement des clés étrangères
            # ont divergé. Échouer à la génération vaut mieux qu'émettre une
            # requête qui additionnerait la table entière.
            if not fk:
                raise ValueError(
                    f"Génération : aucune colonne de clé étrangère de "
                    f"'{source_entity}' ne désigne '{regle['entity']}', alors que "
                    f"le validateur l'exigeait pour 'sumOf'."
                )
            recalculs.append({
                "fk_column": fk,
                "sql": (f'UPDATE "{regle["entity"].lower()}" SET "{regle["field"]}" = '
                        f'(SELECT ROUND(COALESCE(SUM("{regle["source_field"]}"), 0), 2) '
                        f'FROM "{source_entity.lower()}" WHERE "{fk}" = ?) '
                        f'WHERE id = ?'),
            })
        return recalculs

    def _decrement_fk_column(self, trigger_entity, rule):
        """Colonne de 'trigger_entity' qui désigne l'enregistrement DÉCRÉMENTÉ,
        ou None (point 92).

        Source unique des trois branchements d'un `decrements`/`increments` —
        création, modification, suppression. C'est ici qu'a vécu le bug du
        point 86 : la colonne visée est celle qui pointe vers l'entité de la
        RÈGLE, pas la relation « propriétaire », et les deux ne coïncident que
        tant que l'entité déclenchante n'a qu'UNE relation entrante. Le calcul
        était recopié à chaque branchement ; le recopier une fois de plus, c'est
        rouvrir la porte à la troisième occurrence du même défaut."""
        placements = self._compute_fk_placements().get(trigger_entity, [])
        return next((p["fk_column"] for p in placements
                     if p["owner_entity"] == rule["target_entity"]), None)

    def _payment_lock_field(self, entity):
        """Champ 'payable' de 'entity', ou None. Un enregistrement encaissé ne
        se modifie plus : c'est ce que verrouille la brique 18 (point 91)."""
        return self.payable_by_entity.get(entity)

    def _payment_locked_parents(self, source_entity):
        """Parents PAYABLES dont une écriture sur 'source_entity' changerait le
        montant. Source unique du verrou, partagée par Create, Update et Delete.

        C'est le pendant de `_aggregation_recomputes` : partout où une écriture
        sur l'enfant RECALCULE le total d'un parent, ce total peut déjà avoir
        été encaissé. Verrouiller le seul parent ne suffisait pas — le trou se
        prenait par la ligne : 89 € réglés, puis une paire à 149 € ajoutée à la
        même commande, et le serveur affichait 238 € toujours marqués 'payee'
        (vérifié contre un vrai serveur avant d'écrire ce code).

        Retourne la colonne de clé étrangère qui désigne le parent, son entité
        et sa table. Un parent non payable ne verrouille rien : un panier de
        pièces détachées reste modifiable, c'est l'encaissement qui fige."""
        verrous = []
        vus = set()
        placements = self._compute_fk_placements().get(source_entity, [])
        for regle in self.aggregations_by_source.get(source_entity, []):
            parent = regle["entity"]
            if parent not in self.payable_by_entity or parent in vus:
                continue
            fk = next((p["fk_column"] for p in placements
                       if p["owner_entity"] == parent), None)
            # Sans colonne, `_aggregation_recomputes` lève déjà à la génération :
            # inutile de doubler l'erreur, mais hors de question de verrouiller
            # sur une clé devinée.
            if not fk:
                continue
            vus.add(parent)
            verrous.append({"fk_column": fk, "entity": parent,
                            "table": parent.lower()})
        return verrous

    def _payment_lock_lines(self, table, id_expr, entity, indent="    ",
                            var="_regle"):
        """Lignes de garde : refuse l'écriture si l'enregistrement visé est
        encaissé. 409 et non 403 — ce n'est pas un droit qui manque, c'est un
        état définitif, et le message dit lequel."""
        return [
            f"{indent}cursor.execute('SELECT \"{PAYMENT_STATUS_COLUMN}\" FROM "
            f"\"{table}\" WHERE id = ?', ({id_expr},))",
            f"{indent}{var} = cursor.fetchone()",
            f"{indent}if {var} and {var}[0] == 'payee':",
            f"{indent}    conn.close()",
            f"{indent}    raise HTTPException(status_code=409, detail=(",
            f"{indent}        '{entity} déjà réglé : un enregistrement encaissé ne peut "
            f"plus être '",
            f"{indent}        'modifié ni supprimé. Passez par un remboursement chez le "
            f"prestataire.'))",
        ]

    def _owner_lookup_sql(self, entity, owner_entity):
        """Requête qui rend l'id de COMPTE du propriétaire d'un enregistrement,
        et l'acteur auquel opposer le contrôle. Partagée par Update et Delete
        (routes.py) — deux blocs jusqu'ici identiques, qu'il aurait fallu
        corriger deux fois.

        Sous propriété transitive (brique 11), c'est une jointure sur
        l'intermédiaire ; elle renvoie la même chose qu'en propriété directe
        (un id de compte), donc la comparaison qui suit chez l'appelant est
        inchangée. Un intermédiaire absent ne rend aucune ligne : une ligne
        orpheline n'appartient à personne, et le 404 de l'appelant convient."""
        chaine = self._transitive_chain(entity)
        if chaine:
            return chaine["actor"], (
                f'SELECT p."{chaine["actor_fk"]}" FROM "{entity.lower()}" t '
                f'JOIN "{chaine["via_table"]}" p ON p.id = t."{chaine["via_fk"]}" '
                f'WHERE t.id = ?'
            )
        return owner_entity, (
            f'SELECT "{owner_entity.lower()}_id" FROM "{entity.lower()}" WHERE id = ?'
        )

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
        # AJOUT (brique 11, point 81) : sous propriété transitive, le parent
        # « propriétaire » est justement celui que le CLIENT doit désigner (« je
        # rattache cette ligne à CETTE commande ») -- il n'est plus déduit du
        # jeton. Il rejoint donc les autres parents, et la route Create vérifie
        # ensuite que l'enregistrement désigné appartient bien à l'appelant.
        if entity in self.transitive_ownership:
            return [p["fk_column"] for p in self._compute_fk_placements().get(entity, [])]
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
            if entity in self.transitive_ownership:
                # Brique 11 : la colonne contient un id d'enregistrement
                # intermédiaire, pas un id de compte -- elle référence donc la
                # vraie table métier, et non '_monl_users'.
                continue
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

    def _unique_fields(self, entity):
        """Les champs de cette entité déclarés 'unique' (point 85)."""
        return sorted(champ for champ, contraintes
                      in self.field_constraints.get(entity, {}).items()
                      if contraintes.get("unique"))

    def _compute_unique_indexes(self):
        """POINT 85 : [(table, colonne, nom_d_index)] pour chaque 'rule
        Entite.champ unique'.

        Source unique du nom d'index, pour que la création au démarrage et toute
        vérification ultérieure désignent le même objet. Le nom porte la table et
        la colonne : deux entités peuvent avoir un champ homonyme."""
        return [
            (entite.lower(), champ, f"idx_unique_{entite.lower()}_{champ.lower()}")
            for entite, champs in sorted(self.field_constraints.items())
            for champ, contraintes in sorted(champs.items())
            if contraintes.get("unique")
        ]

    def _profile_lookup(self, entity):
        """POINT 90 : (table, colonne) où chercher la fiche que 'requiresOwn'
        exige, ou None si la règle ne s'applique pas à cette entité.

        La colonne est celle que la route Create de l'entité EXIGÉE peuple
        depuis le jeton — donc celle qui porte un identifiant de COMPTE. Elle
        vient de `_identity_fk_columns`, source unique de cette distinction
        depuis le point 88 : la retrouver autrement, c'est réécrire la moitié du
        bug que ce point-là a corrigé."""
        requise = self.required_profiles.get(entity)
        if not requise:
            return None
        colonnes = self._identity_fk_columns().get(requise, set())
        if not colonnes:
            return None
        return requise.lower(), sorted(colonnes)[0]

    def _profile_dependents(self, entity):
        """POINT 96 : entités qui EXIGENT une fiche de 'entity' pour exister.

        Pendant exact de `_profile_lookup`, à l'autre bout du cycle de vie.
        `requiresOwn` gardait la CRÉATION et rien d'autre : sur
        `projets/SneakerLab`, supprimer sa fiche client laissait la commande en
        base — une commande en carnet sans destinataire, exactement l'état que
        le point 90 avait été écrit pour empêcher. Le trou se rouvrait par
        l'autre bout.

        Retourne [(table, colonne de compte)] : où chercher les enregistrements
        qui deviendraient orphelins."""
        dependantes = []
        for dependante, requise in sorted(self.required_profiles.items()):
            if requise != entity:
                continue
            colonnes = self._identity_fk_columns().get(dependante, set())
            if not colonnes:
                # Sans colonne d'identité, rien ne relie la dépendante à un
                # compte : on ne devine pas plutôt que de refuser à tort.
                continue
            dependantes.append((dependante, dependante.lower(), sorted(colonnes)[0]))
        return dependantes

    def _profile_account_column(self, entity):
        """Colonne de compte de l'entité EXIGÉE elle-même — pour compter les
        fiches restantes. `requiresOwn` demande « au moins une » : supprimer
        l'avant-dernière est donc légitime, seule la DERNIÈRE est refusée."""
        colonnes = self._identity_fk_columns().get(entity, set())
        return sorted(colonnes)[0] if colonnes else None

    def _compute_timestamp_columns(self):
        """POINT 89 : [(table, colonne)] pour chaque 'rule Entite.champ timestamp'.

        Sert uniquement au constat de démarrage : compter les enregistrements
        antérieurs à l'ajout de la règle, qui n'auront jamais de date."""
        return [
            (entite.lower(), champ)
            for entite, champs in sorted(self.timestamp_fields_by_entity.items())
            for champ in sorted(champs)
        ]

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
            if ent_name in self.payable_by_entity:
                # Le DEFAULT compte ici autant que dans le CREATE TABLE : sur
                # une base existante, SQLite l'applique aux lignes déjà
                # présentes. Sans lui, ajouter `payable` à une spec en
                # production laisserait les anciens enregistrements à NULL et
                # les nouveaux à 'en_attente' — deux façons de dire la même
                # chose, que toute lecture devrait ensuite réconcilier.
                columns.append(("payment_status", "VARCHAR(32) DEFAULT 'en_attente'"))
                columns.append(("payment_ref", "VARCHAR(255)"))
            for placement in fk_placements.get(ent_name, []):
                columns.append((placement["fk_column"], "INTEGER"))
            expected[table] = columns
        return expected

    def _map_type_to_sql(self, type_str):
        mapping = {
            "String": "VARCHAR(255)", "Text": "TEXT", "Integer": "INTEGER",
            "Float": "REAL", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID",
            "Money": "NUMERIC(10, 2)",
            # Brique 13 (point 83) : 'Image' stocke un CHEMIN relatif au projet,
            # pas le binaire. Même colonne qu'un String, donc — la différence est
            # ailleurs : le validateur vérifie que le fichier existe, et le
            # contrat le déclare comme média sans avoir à deviner d'après le nom.
            "Image": "VARCHAR(255)",
        }
        return mapping.get(type_str, "TEXT")

    def _get_row_column_names(self, entity):
        """Reconstruit l'ordre exact des colonnes SQL d'une entité (id, puis
        attributs déclarés dans l'ordre, puis clé(s) étrangère(s) entrante(s)),
        pour convertir les tuples renvoyés par sqlite3 en objets nommés côté
        API plutôt que des tableaux positionnels — nécessaire pour un rendu
        front lisible (roadmap : front visuel, pas de JSON brut)."""
        columns = ["id"] + list(self.entities[entity].keys())
        if entity in self.payable_by_entity:
            columns += list(PAYMENT_TRACKING_COLUMNS)
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
