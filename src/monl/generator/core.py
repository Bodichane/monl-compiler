"""Classe principale du générateur : état issu de l'AST et orchestration.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""
import os

from ..ir import (
    CompilationIR,
    RelationModel,
)
from .admin_cli import AdminCliMixin
from .calculs import CalculsMixin
from .emitters import BackendEmitter
from .modele import ModeleMixin
from .paiement import PaiementMixin
from .pipeline import PipelineMixin
from .prealables import PrealablesMixin
from .proprietaire import ProprietaireMixin
from .routes import RoutesMixin
from .runtime import RuntimeMixin
from .sandbox import SandboxMixin
from .schemas import SchemasMixin
from .sql_colonnes import SqlColonnesMixin
from .sql_schema import SqlSchemaMixin


class MonlSecureGenerator(
    PipelineMixin,
    ModeleMixin,
    ProprietaireMixin,
    CalculsMixin,
    PaiementMixin,
    SqlColonnesMixin,
    PrealablesMixin,
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
        # BRIQUE B1 : Upload est distinct d'Image. La colonne ne contient
        # qu'une référence opaque ; les octets vivent dans .monl_uploads/ au
        # runtime, jamais dans les artefacts compilés.
        self.upload_fields = normalized_ast["security"].get("upload_fields", [])
        self.upload_fields_by_entity = {}
        for upload in self.upload_fields:
            self.upload_fields_by_entity.setdefault(upload["entity"], []).append(upload)
        # BRIQUE B2 : un seul message sortant par création déclarée. Le
        # validateur a déjà exigé une identité de compte e-mail ; ce dictionnaire
        # sert à brancher la route Create et le contrat sur la même règle.
        self.message_rules_by_trigger = {
            rule["trigger_entity"]: dict(rule)
            for rule in normalized_ast["security"].get("message_rules", [])
        }
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
        # BRIQUE B4 : aucune branche runtime n'est émise quand ce dictionnaire
        # est vide ; c'est la garantie byte-for-byte des specs historiques.
        self.auth_features = dict(normalized_ast.get("security", {})
                                   .get("auth_features") or {})
        # BRIQUE 2a : la devise d'encaissement, DEJA resolue en
        # {code, exponent} par le validateur. None quand rien n'est declare —
        # le defaut n'est applique qu'a l'endroit ou l'on encaisse.
        self.payment_currency = (normalized_ast.get("security", {})
                                 .get("payment_currency"))
        # BRIQUE 2b : 'stripe' ou 'fedapay', resolu par le validateur. None
        # quand rien n'est declare — le defaut n'est applique qu'a l'endroit
        # ou l'on encaisse, comme pour la devise.
        self.payment_provider = (normalized_ast.get("security", {})
                                 .get("payment_provider"))
        # BRIQUE 19 (point 96) : {Entite: {champ: [valeurs]}} — un statut est un
        # état parmi quelques-uns, pas du texte libre.
        self.enumerated_fields = (normalized_ast.get("security", {})
                                  .get("enumerated_fields") or {})
        # BRIQUE B3 : whitelists de compilation pour les paramètres des listes.
        # Les routes et le contrat lisent la même analyse, afin qu'un champ
        # annoncé filtrable/triable soit exactement celui que le backend accepte.
        self.filterable_fields_by_entity = {}
        for item in normalized_ast["security"].get("filterable_fields", []):
            self.filterable_fields_by_entity.setdefault(item["entity"], []).append(item["field"])
        self.sortable_fields_by_entity = {}
        for item in normalized_ast["security"].get("sortable_fields", []):
            self.sortable_fields_by_entity.setdefault(item["entity"], []).append(item["field"])
        # BRIQUE 20 (point 98) : {Entite: [règle]} — atteindre une valeur rend
        # ce que les enfants ont décompté. Indexé par l'entité PORTEUSE du
        # champ, qui est celle dont la route Update déclenche la libération.
        self.release_rules_by_entity = {}
        for regle in (normalized_ast.get("security", {}).get("release_rules") or []):
            self.release_rules_by_entity.setdefault(regle["entity"], []).append(regle)
        # AJOUT (roadmap frontend, bloc 'seed') : données de démonstration à
        # insérer au démarrage si les tables sont vides (voir init_db).
        self.seeds = normalized_ast.get("seeds", [])
        self.migrations = normalized_ast.get("migrations", [])
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
