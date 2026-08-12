"""Classe principale du générateur : état issu de l'AST et orchestration.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""
import os
import secrets

from ..artifacts import copy_preserved_files, publish_files, staging_directory
from ..ir import (
    PAYMENT_STATUS_COLUMN,
    AccessPolicy,
    CompilationIR,
    CompilationPlans,
    EffectPlan,
    EntityModel,
    FieldPolicy,
    RelationModel,
    RoutePlan,
)
from . import sql
from .admin_cli import AdminCliMixin
from .emitters import BackendEmitter
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
BACKEND_ARTIFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py",
                     ".jwt_secret")


class MonlSecureGenerator(
    AdminCliMixin,
    SqlSchemaMixin,
    RuntimeMixin,
    SchemasMixin,
    RoutesMixin,
    SandboxMixin,
):
    def __init__(self, normalized_ast: CompilationIR, output_dir=None):
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
        self.relation_models = [
            RelationModel(source=relation["source"], kind=relation["type"],
                          target=relation["target"])
            for relation in self.relations
        ]
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
        # AJOUT (brique 23, point 106) : table {\"Entite.Action\": [rôles]}
        # des rôles SUPERVISEURS qui transpercent le contrôle 'accessibleBy'.
        # Un rôle listé lit/modifie/supprime TOUS les enregistrements de
        # l'action, sans restriction de partie — les autres restent confinés
        # à leurs colonnes.
        self.access_supervisors = normalized_ast["security"].get("access_supervisors", {})
        # AJOUT (roadmap, cas d'usage portfolio) : ensemble des "Entite.Action"
        # marquées 'public' — ces routes ne requièrent aucune authentification.
        # Reconstruit en tuples (entité, action) pour être comparable
        # directement à (base_target, act_type) lors de la génération des routes.
        self.public_actions = {
            tuple(ref.split(".", 1)) for ref in normalized_ast["security"].get("public", [])
        }
        # BRIQUE visibilité conditionnelle : un contenu marqué publicWhen
        # reste filtré par l'API, liste et détail compris.
        self.public_conditions = {
            tuple(ref.split(".", 1)): value
            for ref, value in normalized_ast["security"].get(
                "public_conditions", {}).items()
        }
        # BRIQUE unicité métier : une combinaison de clés étrangères ne peut
        # être créée deux fois pour le même compte et la même cible.
        self.once_per_rules = normalized_ast["security"].get("once_per", [])
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
        # BRIQUE 22 (point 102) : {Entite: [{champ, format, periode}]}. Même
        # famille que l'horodatage ci-dessus — peuplé par le serveur à la
        # création, absent des corps de requête, jamais réécrit.
        self.numbered_fields_by_entity = {}
        for nf in normalized_ast["security"].get("numbered_fields", []):
            self.numbered_fields_by_entity.setdefault(nf["entity"], []).append(nf)
        # AJOUT (brique paiement, point 74) : entité encaissable et champ
        # portant le montant. {Entite: champ} — le validateur garantit au
        # plus un champ payable par entité.
        self.payable_by_entity = {
            pf["entity"]: pf["field"]
            for pf in normalized_ast["security"].get("payable_fields", [])
        }
        self.postpayment_writable_by_entity = normalized_ast["security"].get(
            "writable_after_payment", {})
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
        # Vue typée commune aux consommateurs de la sémantique des champs.
        # Les dictionnaires historiques restent disponibles pendant la
        # migration des émetteurs SQL et API.
        self.entity_models = self._build_entity_models()
        # Carte de routes calculée avant les politiques qui en dépendent.
        self.route_plans = self._compute_route_map()
        self.access_policies = self._build_access_policies()
        self.effect_plans = self._build_effect_plans()
        # Le catalogue de plans devient l'analyse canonique de cette instance.
        # Les anciens attributs restent exposés aux mixins pendant la migration,
        # mais les consommateurs modernes réutilisent désormais cet objet.
        self.compilation_plans = self.build_compilation_plans()
        # Façade composée : les mixins restent l'implémentation historique,
        # mais l'orchestrateur ne choisit plus chaque couche individuellement.
        self.emitters = BackendEmitter(self)

    def _build_entity_models(self) -> dict[str, EntityModel]:
        """Consolide une fois les politiques réparties dans l'IR validée."""
        models = {}
        for entity, fields in self.entities.items():
            derived = {r["field"]: r for r in self.derived_by_entity.get(entity, [])}
            aggregated = {
                r["field"]: r for r in self.aggregated_by_entity.get(entity, [])
            }
            numbered = {
                r["field"]: r for r in self.numbered_fields_by_entity.get(entity, [])
            }
            generated = set(self.generated_fields_by_entity.get(entity, []))
            hidden = set(self.hidden_fields_by_entity.get(entity, []))
            categorized = {
                r["field"] for r in self.categorized_fields_by_entity.get(entity, [])
            }
            timestamped = set(self.timestamp_fields_by_entity.get(entity, []))
            postpayment = set(
                self.postpayment_writable_by_entity.get(entity, {}).get("fields", [])
            )
            policies = {}
            for name, type_ in fields.items():
                derived_rule = derived.get(name)
                aggregate_rule = aggregated.get(name)
                numbering_rule = numbered.get(name)
                server_generated = (
                    name in generated
                    or derived_rule is not None
                    or aggregate_rule is not None
                    or numbering_rule is not None
                    or name in timestamped
                )
                policies[name] = FieldPolicy(
                    name=name,
                    type=type_,
                    hidden_in_reads=name in hidden,
                    server_generated=server_generated,
                    categorized_in_reads=name in categorized,
                    postpayment_only=name in postpayment,
                    allowed_values=tuple(
                        self.enumerated_fields.get(entity, {}).get(name, [])
                    ),
                    constraints=self.field_constraints.get(entity, {}).get(name, {}),
                    derived_rule=derived_rule,
                    aggregate_rule=aggregate_rule,
                    timestamped=name in timestamped,
                    numbering_rule=numbering_rule,
                )
            models[entity] = EntityModel(name=entity, fields=policies)
        return models

    def _build_access_policies(self) -> dict[tuple[str, str], AccessPolicy]:
        """Consolide les sources de contrôle d'accès par route logique."""
        policies = {}
        for (action, _key), route in self._compute_route_map().items():
            entity = route.base_target
            reference = f"{entity}.{action}"
            condition = self.public_conditions.get((entity, "Read")) \
                if action == "Read" else None
            policies[(entity, action)] = AccessPolicy(
                entity=entity,
                action=action,
                actors=frozenset(route.actors),
                public=((entity, action) in self.public_actions or condition is not None),
                public_condition=condition,
                owner_entity=self.ownership.get(reference),
                transitive_ownership=self.transitive_ownership.get(entity),
                party_fields=tuple(self.access_parties.get(reference, [])),
                supervisors=frozenset(self.access_supervisors.get(reference, [])),
            )
        return policies

    def _build_effect_plans(self) -> tuple[EffectPlan, ...]:
        """Réunit les effets validés dans un catalogue commun et ordonné."""
        plans = []
        for entity, rules in self.derived_by_entity.items():
            plans.extend(EffectPlan(
                kind="derive", trigger_entity=entity, target_entity=entity,
                field=rule["field"], source_entity=rule["source_entity"],
                source_field=rule["source_field"], config=rule,
            ) for rule in rules)
        for source, rules in self.aggregations_by_source.items():
            plans.extend(EffectPlan(
                kind="aggregate", trigger_entity=source,
                target_entity=rule["entity"], field=rule["field"],
                source_entity=source, source_field=rule["source_field"], config=rule,
            ) for rule in rules)
        for trigger, rules in self.reputation_rules_by_trigger.items():
            plans.extend(EffectPlan(
                kind="increment" if rule["direction"] == "increments" else "decrement",
                trigger_entity=trigger, target_entity=rule["target_entity"],
                field=rule["target_field"], source_entity=None,
                source_field=rule.get("amount_field"), config=rule,
            ) for rule in rules)
        for entity, rules in self.release_rules_by_entity.items():
            plans.extend(EffectPlan(
                kind="release", trigger_entity=entity,
                target_entity=rule["releases"], field=rule["field"],
                source_entity=None, source_field=None, config=rule,
            ) for rule in rules)
        plans.extend(EffectPlan(
            kind="payment_lock", trigger_entity=entity, target_entity=entity,
            field=field, source_entity=None, source_field=None,
            config={"entity": entity, "field": field},
        ) for entity, field in self.payable_by_entity.items())
        plans.extend(EffectPlan(
            kind="postpayment_write", trigger_entity=entity, target_entity=entity,
            field=None, source_entity=None, source_field=None, config=config,
        ) for entity, config in self.postpayment_writable_by_entity.items())
        return tuple(plans)

    def _effects(self, kind, *, trigger=None, target=None):
        return [plan for plan in self.effect_plans
                if plan.kind == kind
                and (trigger is None or plan.trigger_entity == trigger)
                and (target is None or plan.target_entity == target)]

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
        for relation in self.relation_models:
            placements.setdefault(relation.held_entity, []).append({
                "fk_column": relation.fk_column,
                "owner_entity": relation.owner_entity,
                "unique": relation.unique,
            })
        return placements

    def _derived_field_names(self, entity):
        """Champs de 'entity' calculés par le serveur (brique 10, point 77).

        Ils doivent être traités comme les champs 'generated' partout où le
        client pourrait les fournir : absents du schéma Pydantic, et exclus des
        valeurs d'écriture qu'on lit dans `data`."""
        return [plan.field for plan in self._effects("derive", target=entity)]

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

    def _fk_to(self, child, parent):
        """Colonne de clé étrangère sur 'child' qui désigne 'parent'.

        Même convention et même garde que _derived_source_fk : si la colonne
        manque, la validation et le placement des clés étrangères ont divergé —
        et écrire une jointure sur None rendrait tout visible à tous."""
        for p in self._compute_fk_placements().get(child, []):
            if p["owner_entity"] == parent:
                return p["fk_column"]
        raise ValueError(
            f"Génération : aucune colonne de clé étrangère de '{child}' ne désigne "
            f"'{parent}', alors que le validateur exigeait cette relation pour une "
            f"chaîne de propriété transitive."
        )

    def _transitive_chain(self, entity):
        """Chaîne de propriété transitive de 'entity', ou None (briques 11 et 24).

        Retourne ce qu'il faut pour TOUTES les jointures de contrôle d'accès,
        quelle que soit la profondeur : l'acteur au bout de la chaîne, la
        colonne qui, sur le DERNIER maillon, porte l'identifiant du compte
        propriétaire ('actor_fk'), et la liste 'hops' des maillons, de bas en
        haut, chacun avec sa table et la colonne de clé étrangère qui, sur le
        niveau juste dessous, désigne ce maillon :
          - hops[0].ref : sur 'entity', pointe vers hops[0].table ;
          - hops[i].ref : sur hops[i-1].table, pointe vers hops[i].table.
        Source unique de vérité de la brique : routes, schémas et contrat
        frontend passent tous par ici."""
        chaine = self.transitive_ownership.get(entity)
        if not chaine:
            return None
        hops_raw = chaine["chain"]
        acteur = chaine["actor"]
        if not hops_raw:
            raise ValueError(
                f"Génération : '{entity}' est en propriété transitive mais sa chaîne "
                f"est vide -- le validateur a divergé. Echec plutôt que jointure "
                f"sur rien."
            )
        # Maillon du bas : la clé étrangère sur 'entity' vers le premier maillon.
        hop_bas = {"table": hops_raw[0].lower(),
                   "ref": self._fk_to(entity, hops_raw[0])}
        hops = [hop_bas]
        for i in range(1, len(hops_raw)):
            hops.append({"table": hops_raw[i].lower(),
                         "ref": self._fk_to(hops_raw[i - 1], hops_raw[i])})
        actor_fk = self._fk_to(hops_raw[-1], acteur)
        return {"via": hops_raw[0], "via_fk": hop_bas["ref"],
                "via_table": hop_bas["table"], "actor": acteur,
                "actor_fk": actor_fk, "hops": hops, "len": len(hops)}

    def _chain_read_where(self, entity, actor_frag):
        """Fragment SQL 'WHERE' (objet sql.Sql) qui borne 'entity' aux lignes du
        compte courant. 'actor_frag' est la valeur du compte, liée par sql.bind
        — jamais un fragment de texte.

        Sous chaîne à un ou plusieurs maillons, un 'IN' imbriqué par maillon :
        la colonne de clé étrangère du niveau courant est comparée aux
        identifiants du maillon suivant, jusqu'au maillon final filtré par
        'actor_fk = ?'. Un maillon absent ne rend aucune ligne (une ligne
        orpheline n'appartient à personne). Retourne None si 'entity' n'est pas
        en propriété transitive."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        frag = sql.cat(sql.ident(chaine["actor_fk"]), sql.kw(" = "), actor_frag)
        for h in reversed(chaine["hops"]):
            frag = sql.cat(sql.ident(h["ref"]), sql.kw(" IN (SELECT id FROM "),
                           sql.ident(h["table"]), sql.kw(" WHERE "), frag,
                           sql.kw(")"))
        return sql.cat(sql.kw(" WHERE "), frag)

    def _chain_owner_scalar(self, entity, first_hop):
        """Sous-requête scalaire (objet sql.Sql) qui rend l'id de COMPTE du
        propriétaire d'un enregistrement, à partir de l'id du PREMIER maillon.
        'first_hop' est ce PREMIER maillon sous forme de fragment sql.Sql — soit
        une valeur liée (sql.bind, cas des routes qui reçoivent la clé étrangère
        du client), soit une sous-requête (cas de _chain_owner_from_row). Dans
        tous les cas, aucune valeur ne traverse le texte SQL.

        Grimpe la chaîne maillon par maillon : la colonne de clé étrangère du
        niveau courant désigne le maillon suivant, et la dernière sélection
        'actor_fk' rend le compte. Tout maillon absent rend NULL donc
        « appartient à personne ». None si 'entity' n'est pas transitive."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        hops = chaine["hops"]
        expr = sql.cat(sql.kw("("), first_hop, sql.kw(")"))
        for i in range(1, len(hops)):
            h = hops[i]
            prev = hops[i - 1]
            expr = sql.cat(sql.kw('(SELECT '), sql.ident(h["ref"]),
                           sql.kw(' FROM '), sql.ident(prev["table"]),
                           sql.kw(' WHERE id = '), expr, sql.kw(')'))
        dernier = hops[-1]
        return sql.cat(sql.kw('(SELECT '), sql.ident(chaine["actor_fk"]),
                       sql.kw(' FROM '), sql.ident(dernier["table"]),
                       sql.kw(' WHERE id = '), expr, sql.kw(')'))

    def _chain_owner_from_row(self, entity, id_frag=None):
        """id de COMPTE du propriétaire d'une ligne de 'entity' (objet sql.Sql),
        sous chaîne transitive de profondeur quelconque. None si non transitive.
        'id_frag' est l'identifiant de la ligne sous forme de fragment sql.Sql
        (par défaut la valeur liée 'id', l'usage de _owner_lookup_sql)."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        if id_frag is None:
            id_frag = sql.bind("id")
        ref_bas = chaine["hops"][0]["ref"]
        first_hop = sql.cat(sql.kw('(SELECT '), sql.ident(ref_bas),
                            sql.kw(' FROM '), sql.ident(entity.lower()),
                            sql.kw(' WHERE id = '), id_frag, sql.kw(')'))
        return self._chain_owner_scalar(entity, first_hop)

    def _chain_join(self, entity, alias_root="t"):
        """Séquence de JOIN qui fait remonter 'entity' jusqu'au maillon final.

        Retourne (depuis_sql, alias_dernier_maillon, acteur_fk) pour les routes
        de règlement : chaque maillon rejoint son parent par sa clé étrangère,
        et le dernier maillon 'alias_dernier_maillon' porte la colonne 'acteur_fk'
        du compte. Le montant, l'état et le propriétaire sortent ainsi de la
        MÊME lecture — l'invariant du point 87. Ne porte aucune valeur client,
        rien que des identifiants et des alias internes."""
        chaine = self._transitive_chain(entity)
        # (appelé seulement quand chaine n'est pas None ; sinon erreur claire)
        depuis = sql.cat(sql.ident(entity.lower()), sql.kw(f" {alias_root}"))
        cur = alias_root
        for i, h in enumerate(chaine["hops"]):
            alias = f"m{i + 1}"
            depuis = sql.cat(depuis, sql.kw(" JOIN "), sql.ident(h["table"]),
                             sql.kw(f" {alias} ON {alias}.id = {cur}."),
                             sql.ident(h["ref"]))
            cur = alias
        return depuis.text, cur, chaine["actor_fk"]

    def _aggregated_field_names(self, entity):
        """Champs de 'entity' qui sont une SOMME de ses enfants (brique 12).

        Traités partout comme les champs 'derivedFrom' : absents du schéma
        Pydantic, et jamais lus dans `data`."""
        return [plan.field for plan in self._effects("aggregate", target=entity)]

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
        for plan in self._effects("aggregate", trigger=source_entity):
            fk = next((p["fk_column"] for p in placements
                       if p["owner_entity"] == plan.target_entity), None)
            # Le validateur a exigé la relation parent-enfant : arriver ici sans
            # colonne signifie que validation et placement des clés étrangères
            # ont divergé. Échouer à la génération vaut mieux qu'émettre une
            # requête qui additionnerait la table entière.
            if not fk:
                raise ValueError(
                    f"Génération : aucune colonne de clé étrangère de "
                    f"'{source_entity}' ne désigne '{plan.target_entity}', alors que "
                    f"le validateur l'exigeait pour 'sumOf'."
                )
            recalculs.append({
                "fk_column": fk,
                "sql": (f'UPDATE "{plan.target_entity.lower()}" SET "{plan.field}" = '
                        f'(SELECT ROUND(COALESCE(SUM("{plan.source_field}"), 0), 2) '
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

    def _counter_fk_columns(self, trigger_entity):
        """FK écrites par la branche compteur à la création.

        Chaque colonne vient de `_decrement_fk_column`, quelle que soit la
        position de la relation dans la spec. La liste est dédoublonnée pour
        qu'une entité qui porte plusieurs effets sur la même cible n'ajoute
        cette FK qu'une seule fois à son schéma et à son INSERT.
        """
        colonnes = []
        for rule in self.reputation_rules_by_trigger.get(trigger_entity, []):
            fk_column = self._decrement_fk_column(trigger_entity, rule)
            if fk_column and fk_column not in colonnes:
                colonnes.append(fk_column)
        return colonnes

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
        for plan in self._effects("aggregate", trigger=source_entity):
            parent = plan.target_entity
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
            # Briques 11 et 24 : une sous-requête scalaire remonte toute la
            # chaîne jusqu'au compte, quelle que soit sa profondeur. Elle rend
            # un id de compte (None si un maillon manque), donc la comparaison
            # chez l'appelant est inchangée par rapport à la propriété directe.
            return chaine["actor"], sql.cat(
                sql.kw("SELECT "), self._chain_owner_from_row(entity))
        return owner_entity, sql.cat(
            sql.kw("SELECT "), sql.ident(f"{owner_entity.lower()}_id"),
            sql.kw(" FROM "), sql.ident(entity.lower()),
            sql.kw(" WHERE id = "), sql.bind("id"))

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

        Le complément exact de `_identity_fk_columns` : tout parent que le
        jeton ne désigne pas doit être désigné par l'appelant, sans quoi la
        colonne reste NULL et le rattachement demandé disparaît (un commentaire
        sans son article, une variante sans son produit). Deux exclusions, et
        deux seulement — la colonne d'identité, peuplée depuis le JWT, et la
        cible d'un compteur, déclarée à part par `schemas.py` et la branche
        `is_reputation_fk` de `routes.py` : la répéter ici l'écrirait deux fois.

        Sur une création publique, aucune identité n'est disponible et le
        comportement historique (colonnes laissées à NULL) est conservé.

        POINT 99 : le cas « aucune colonne d'identité » n'est plus réservé aux
        entités transitives. Une entité fille d'une table MÉTIER (une variante
        et son produit) n'a pas de propriétaire déduit du jeton : toutes ses
        clés étrangères viennent donc du client.
        """
        if (entity, "Create") in self.public_actions:
            return []
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return []
        exclues = set(self._identity_fk_columns().get(entity, set()))
        # POINT 92 : la colonne d'une cible de compteur est celle que
        # `_decrement_fk_column` trouve pour CHAQUE règle, pas celle de la
        # première relation entrante. Avec deux relations (Post et Member),
        # `_get_incoming_relation` peut désigner Post alors que l'identité
        # peuple member_id ; l'ancienne décision excluait alors post_id de
        # l'INSERT et créait une ligne orpheline. La branche
        # `is_reputation_fk` de routes.py écrit déjà chaque cible : on l'exclut
        # ici pour qu'elle soit écrite exactement une fois.
        exclues.update(self._counter_fk_columns(entity))
        # Brique 11 (point 81) : sous propriété transitive, le parent
        # « propriétaire » est justement celui que le CLIENT doit désigner (« je
        # rattache cette ligne à CETTE commande ») -- il n'est plus déduit du
        # jeton. Il rejoint donc les autres parents (aucune colonne d'identité
        # n'existe alors), et la route Create vérifie ensuite que
        # l'enregistrement désigné appartient bien à l'appelant.
        return [p["fk_column"] for p in placements if p["fk_column"] not in exclues]

    def _identity_fk_columns(self):
        """Colonnes de clé étrangère peuplées depuis l'identité JWT de l'appelant.

        Retourne {entité: {colonnes}}. Ce sont celles que la route Create
        remplit avec 'current_user_id' (identifiant de compte), et non avec
        une valeur du corps de requête — elles référencent donc le registre
        des comptes, pas la table métier homonyme. C'est la source UNIQUE de
        cette distinction : le schéma SQL en tire son 'REFERENCES', le contrat
        son 'references_account', la route Create son 'populate_owner', la
        route de règlement la colonne qu'elle compare à l'appelant, et
        'requiresOwn' la colonne où chercher une fiche.

        POINT 99 : le parent doit être un ACTEUR. « Peuplée depuis l'identité de
        l'appelant » n'a de sens que si le parent EST un compte : une entité
        fille d'une table métier (une variante et son produit) n'a pas de
        propriétaire à déduire du jeton. Sans cette condition, une telle colonne
        recevait `current_user_id` et se déclarait `REFERENCES _monl_users` — la
        variante était rattachée au vendeur qui l'avait créée, jamais à son
        produit, et le client ne pouvait désigner aucun parent. Le nom de la
        colonne disait une chose, son contenu une autre : le défaut du point 80,
        par l'autre bout du même mécanisme.

        Le choix ne dépend PAS de l'ordre de déclaration des relations : seuls
        les parents acteurs sont candidats, et la règle 'ownedBy' tranche entre
        eux s'il y en a plusieurs.
        """
        route_map = self._compute_route_map()
        creatable = {plan.base_target for (act, _k), plan in route_map.items()
                     if act == "Create"}
        identity_cols = {}
        for entity in self.entities:
            if entity not in creatable:
                continue
            if (entity, "Create") in self.public_actions:
                continue  # aucune identité fiable : la colonne reste NULL
            if entity in self.transitive_ownership:
                # Brique 11 : la colonne contient un id d'enregistrement
                # intermédiaire, pas un id de compte -- elle référence donc la
                # vraie table métier, et non '_monl_users'.
                continue
            cibles_compteur = {r["target_entity"]
                               for r in self.reputation_rules_by_trigger.get(entity, [])}
            candidats = [p for p in self._compute_fk_placements().get(entity, [])
                         if p["owner_entity"] in self.actors
                         # cible choisie par le client : vraie référence métier
                         and p["owner_entity"] not in cibles_compteur]
            if not candidats:
                continue
            proprietaires = {v for k, v in self.ownership.items()
                             if k.split(".", 1)[0] == entity}
            choisi = next((p for p in candidats if p["owner_entity"] in proprietaires),
                          candidats[0])
            identity_cols.setdefault(entity, set()).add(choisi["fk_column"])
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

        sources = self.emitters.render()
        sql_content = sources.schema
        api_content = sources.app
        sandbox_content = sources.sandbox
        manage_content = sources.manage

        # Détermination des chemins physiques dans un staging voisin. La
        # publication ne touche au projet courant qu'après la génération
        # complète des cinq artefacts backend.
        target_dir = self.output_dir
        with staging_directory(target_dir) as temporary:
            copy_preserved_files(target_dir, temporary, (".jwt_secret",))
            self.output_dir = os.path.abspath(temporary)
            base_dir = self.output_dir
            sql_path = os.path.join(base_dir, "schema.sql")
            api_path = os.path.join(base_dir, "app.py")
            sandbox_path = os.path.join(base_dir, "sandbox_ai.py")
            manage_path = os.path.join(base_dir, "manage.py")
            secret_path = os.path.join(base_dir, ".jwt_secret")

            try:
                # Le secret est généré une fois par projet, conservé entre
                # compilations et toujours publié avec le mode propriétaire seul.
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
            finally:
                self.output_dir = target_dir
            publish_files(temporary, target_dir, BACKEND_ARTIFACTS)

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
        (fil social, etc.).

        BRIQUE 21 (point 100) : chaque entrée est désormais un COUPLE
        {"values": {...}, "parent": None | {...}}, et non plus la seule ligne.
        Le rattachement d'un enfant ne peut pas être résolu ici : l'`id` du
        parent n'existe qu'une fois la ligne insérée, et le socle ne sème une
        table que si elle est VIDE — un parent déjà peuplé par de vraies données
        ne serait donc pas réinséré, et un rang calculé à la compilation
        désignerait la mauvaise ligne. La désignation voyage telle quelle et se
        résout par un SELECT au démarrage."""
        seed_data = {}
        for seed in self.seeds:
            entity = seed["entity"]
            table = entity.lower()
            generated = self.generated_fields_by_entity.get(entity, [])
            parent = seed.get("parent")
            rattachement = None
            if parent:
                rattachement = {
                    "column": f"{parent['entity'].lower()}_id",
                    "table": parent["entity"].lower(),
                    "field": parent["field"],
                    "value": parent["value"],
                }
            seed_data.setdefault(table, [])
            for row in seed["rows"]:
                filled = dict(row)
                for gfield in generated:
                    if gfield not in filled:
                        # Pseudonyme synthétique stable, unique par ligne.
                        filled[gfield] = f"Anon#{1000 + len(seed_data[table])}"
                seed_data[table].append({"values": filled, "parent": rattachement})
        return seed_data

    def _unique_fields(self, entity):
        """Les champs de cette entité déclarés 'unique' (point 85)."""
        return sorted(champ for champ, contraintes
                      in self.field_constraints.get(entity, {}).items()
                      if contraintes.get("unique"))

    def _once_per_rules_for(self, entity):
        return [rule for rule in self.once_per_rules
                if rule["trigger_entity"] == entity]

    def _condition_exemptions(self, entity):
        """POINT 116 : QUI échappe à la condition 'publicWhen' de cette entité.

        Rend (superviseurs déclarés, colonnes d'identité du propriétaire).
        Source UNIQUE des deux exemptions : la route de lecture les émet, et
        `runtime.py` s'en sert pour n'écrire la dépendance d'identité
        facultative QUE si au moins une exemption existe — sans quoi une spec
        sans superviseur ni propriétaire porterait une fonction que rien
        n'appelle. Deux calculs séparés finiraient par diverger, et c'est le
        genre d'écart qui rouvre un contrôle d'accès.
        """
        if (entity, "Read") not in self.public_conditions:
            return [], []
        superviseurs = sorted(self.access_supervisors.get(f"{entity}.Read", []))
        proprietaire = sorted(self._identity_fk_columns().get(entity, set()))
        return superviseurs, proprietaire

    def _condition_identity_needed(self):
        """Vrai si au moins une lecture conditionnée porte une exemption."""
        return any(any(self._condition_exemptions(entity))
                   for entity, action in self.public_conditions
                   if action == "Read")

    def _compute_once_per_indexes(self):
        """Index uniques multi-colonnes issus des règles `oncePer`."""
        indexes = []
        placements = self._compute_fk_placements()
        for rule in self.once_per_rules:
            entity = rule["trigger_entity"]
            columns = []
            for parent in rule["parents"]:
                placement = next(
                    (p for p in placements.get(entity, [])
                     if p["owner_entity"] == parent), None)
                if not placement:
                    raise ValueError(
                        f"Génération : aucune clé étrangère de '{entity}' ne désigne "
                        f"'{parent}', alors que 'oncePer' l'exige.")
                # POINT 116 : un index composite sur une colonne que la route
                # Create n'écrit JAMAIS ne refuse rien — SQLite tient deux NULL
                # pour distincts, donc la règle passe la compilation, crée son
                # index, et laisse voter dix fois. C'est arrivé sur
                # `exemples/03_reseau_social.ml` : la colonne visée par un
                # `increments` sort de l'INSERT quand elle est la PREMIÈRE
                # relation entrante, et `oncePer Member, Post` ne mordait plus.
                # Refuser plutôt que produire une règle sans effet — c'est
                # exactement ce que le point 85 a fermé pour `unique`.
                ecrites = set(self._client_fk_columns(entity))
                ecrites |= set(self._identity_fk_columns().get(entity, set()))
                # La branche compteur de la route Create écrit ces colonnes
                # hors des FK client. Le refus reste donc actif pour une
                # colonne réellement jamais écrite, sans rejeter une écriture
                # serveur réelle.
                ecrites |= set(self._counter_fk_columns(entity))
                if placement["fk_column"] not in ecrites:
                    raise ValueError(
                        f"Génération : 'oncePer' sur '{entity}' désigne '{parent}', "
                        f"mais la colonne '{placement['fk_column']}' n'est jamais "
                        f"écrite à la création — l'unicité ne refuserait rien. "
                        f"Déclarer la relation vers l'acteur AVANT celle visée par "
                        f"un 'increments'/'decrements', pour que la colonne du "
                        f"parent reste fournie par le client.")
                columns.append(placement["fk_column"])
            index_name = "idx_once_per_{}_{}".format(
                entity.lower(), "_".join(c.lower() for c in columns))
            indexes.append((entity.lower(), columns, index_name))
        return indexes

    def _compute_unique_indexes(self):
        """POINT 85 : [(table, colonne, nom_d_index)] pour chaque 'rule
        Entite.champ unique'.

        Source unique du nom d'index, pour que la création au démarrage et toute
        vérification ultérieure désignent le même objet. Le nom porte la table et
        la colonne : deux entités peuvent avoir un champ homonyme.

        POINT 102 : un champ 'numbered' y entre sans avoir à déclarer 'unique'.
        Un numéro de commande en double n'est pas un numéro — l'exiger dans la
        spec ferait dépendre la garantie d'une ligne qu'on peut oublier d'écrire.
        Le nom d'index étant dérivé de la table et de la colonne, déclarer les
        deux ne produit qu'un seul index."""
        vises = {
            (entite, champ)
            for entite, champs in self.field_constraints.items()
            for champ, contraintes in champs.items()
            if contraintes.get("unique")
        }
        vises |= {(entite, regle["field"])
                  for entite, regles in self.numbered_fields_by_entity.items()
                  for regle in regles}
        return [
            (entite.lower(), champ, f"idx_unique_{entite.lower()}_{champ.lower()}")
            for entite, champ in sorted(vises)
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

    def _compute_numbered_columns(self):
        """POINT 102 : [(table, colonne)] pour chaque 'rule Entite.champ numbered'.

        Même usage que `_compute_timestamp_columns` et même honnêteté : les
        enregistrements antérieurs à la règle n'ont PAS de numéro, et on ne leur
        en invente pas — les numéroter au démarrage prétendrait un ordre
        d'arrivée que le serveur n'a pas observé."""
        return [
            (entite.lower(), regle["field"])
            for entite, regles in sorted(self.numbered_fields_by_entity.items())
            for regle in regles
        ]

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
            # Float est un nombre binaire, pas une monnaie : DOUBLE PRECISION
            # est le type partagé SQLite/PostgreSQL. Money reste NUMERIC à
            # échelle fixe ci-dessous, car ses valeurs partent chez Stripe et
            # un flottant binaire n'est pas un type d'argent.
            "Float": "DOUBLE PRECISION", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID",
            "Money": "NUMERIC(10, 2)",
            # Brique 13 (point 83) : 'Image' stocke un CHEMIN relatif au projet,
            # pas le binaire. Même colonne qu'un String, donc — la différence est
            # ailleurs : le validateur vérifie que le fichier existe, et le
            # contrat le déclare comme média sans avoir à deviner d'après le nom.
            "Image": "VARCHAR(255)",
        }
        return mapping.get(type_str, "TEXT")

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

    def _compute_route_map(self) -> dict[tuple[str, str], RoutePlan]:
        """Regroupe les actions par (type, cible) avec la liste des acteurs
        autorisés et le 'tag' (nom du premier workflow qui déclare l'action)
        -- extrait de _generate_secure_fastapi pour être réutilisé aussi par
        _compute_actor_capabilities (le tableau de bord post-connexion a
        besoin du même 'tag' que la vraie route pour appeler les fonctions
        'custom' au bon endroit). Une seule source de vérité : si cette
        logique de regroupement change un jour, les deux consommateurs
        restent forcément synchronisés."""
        if hasattr(self, "route_plans"):
            return self.route_plans
        route_map: dict[tuple[str, str], RoutePlan] = {}
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".")[0] if "." in target else target
                route_key = (act_type, base_target if act_type != "Execute" else target)
                if route_key not in route_map:
                    route_map[route_key] = RoutePlan(
                        action=act_type,
                        key=route_key[1],
                        target=target,
                        base_target=base_target,
                        actors=set(),
                        tags=[],
                    )
                route_map[route_key].allow(required_actor, wf_name)
        return route_map

    def build_compilation_plans(self) -> CompilationPlans:
        """Expose les analyses communes aux émetteurs backend et frontend."""
        if hasattr(self, "compilation_plans"):
            return self.compilation_plans
        placements = self._compute_fk_placements()
        identity = self._identity_fk_columns()
        return CompilationPlans(
            route_map=self._compute_route_map(),
            foreign_key_placements={
                entity: tuple(dict(placement) for placement in values)
                for entity, values in placements.items()
            },
            identity_foreign_keys={
                entity: frozenset(columns)
                for entity, columns in identity.items()
            },
            client_foreign_keys={
                entity: tuple(self._client_fk_columns(entity))
                for entity in self.entities
            },
            incoming_relations={
                entity: (dict(relation) if relation else None)
                for entity in self.entities
                for relation in [self._get_incoming_relation(entity)]
            },
            payment_locked_parents={
                entity: tuple(dict(lock) for lock in self._payment_locked_parents(entity))
                for entity in self.entities
            },
            reputation_rules_by_trigger={
                entity: tuple(dict(rule) for rule in rules)
                for entity, rules in self.reputation_rules_by_trigger.items()
            },
            entity_models=self.entity_models,
            access_policies=self.access_policies,
            actors=tuple(self.actors),
            self_register_actors=tuple(self.self_register_actors),
            auth_identifier=tuple(self.auth_identifier) if self.auth_identifier else None,
            auth_phone_prefix=self.auth_phone_prefix,
            public_conditions=self.public_conditions,
            required_profiles=self.required_profiles,
            payable_by_entity=self.payable_by_entity,
            release_rules_by_entity={
                entity: tuple(dict(rule) for rule in rules)
                for entity, rules in self.release_rules_by_entity.items()
            },
            transitive_ownership=self.transitive_ownership,
            postpayment_writable_by_entity=self.postpayment_writable_by_entity,
            assets=self.assets,
            once_per_rules=tuple(dict(rule) for rule in self.once_per_rules),
        )

    def _generate_secure_fastapi(self):
        """Assemble app.py à partir des trois couches générées séparément :
        socle runtime (auth, DB, migrations), schémas d'entrée, routes."""
        api_lines = self._generate_runtime_lines()
        api_lines += self._generate_schema_lines()
        api_lines += self._generate_route_lines()
        return "\n".join(api_lines)
