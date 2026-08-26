"""La classe `MonlAST`, recomposée par mixins.

Un module par PRÉOCCUPATION, comme `generator/` l'a déjà fait : une
nouvelle règle s'ajoute dans le module de sa couche, jamais ici. Ce
fichier ne porte que l'état issu de l'AST, l'ordonnancement de la
validation, et la normalisation qui en sort."""

from typing import Any

from ..ir import CompilationIR
from ..validation_pipeline import DEFAULT_VALIDATION_PIPELINE, ValidationPipeline
from .acces import AccesMixin
from .assets import AssetsMixin
from .audit import AuditMixin
from .capacites import CapacitesMixin
from .capacites_de_liste import CapacitesDeListeMixin
from .champs import ChampsMixin
from .champs_calcules import ChampsCalculesMixin
from .champs_serveur import ChampsServeurMixin
from .collisions import CollisionsMixin
from .commerce import CommerceMixin
from .cycle_de_vie import CycleDeVieMixin
from .migrations import MigrationsMixin
from .presentation import PresentationMixin
from .uploads import UploadsMixin


class MonlAST(
        AccesMixin,
        CollisionsMixin,
        ChampsMixin,
        UploadsMixin,
        ChampsServeurMixin,
        ChampsCalculesMixin,
        CommerceMixin,
        CycleDeVieMixin,
        CapacitesMixin,
        CapacitesDeListeMixin,
        PresentationMixin,
        MigrationsMixin,
        AssetsMixin,
        AuditMixin,
):
    """L'AST validé d'une spec monl.

    Les règles vivent dans les mixins ci-dessus ; l'ordre d'exécution,
    lui, vient du pipeline (`validation_pipeline.py`) et non de l'ordre
    des bases."""

    def __init__(self, raw_json: dict[str, Any], base_dir: str | None = None):
        # AJOUT (brique 13, point 83) : 'base_dir' est le dossier du projet
        # (celui de la spec). Il n'est nécessaire qu'aux contrôles qui touchent
        # le DISQUE — vérifier qu'un asset déclaré existe vraiment. Les contrôles
        # de FORME (chemin absolu, remontée '..', URL distante) sont purs et
        # s'appliquent toujours : c'est le partage qui permet aux tests d'écrire
        # une spec en mémoire sans perdre les refus qui ne demandent pas de
        # fichier.
        self.base_dir = base_dir
        self.raw = raw_json
        self.app_name = raw_json.get("app")
        self.entities = {}
        # CORRECTIF (bêta 3, déterminisme) : la liste des acteurs était un
        # 'set', dont l'ordre d'itération dépend de PYTHONHASHSEED — deux
        # compilations de la même spec pouvaient produire un 'VALID_ACTORS'
        # différent dans app.py, ce qui contredisait la garantie « même
        # entrée, même sortie à l'octet près ». L'ordre de déclaration est
        # désormais conservé (dédoublonné).
        self.actors = list(dict.fromkeys(raw_json.get("actors", [])))
        # AJOUT (bêta 3) : acteurs ouverts à l'inscription libre (marqueur
        # 'selfRegister'). Les autres sont provisionnés hors ligne.
        self.self_register_actors = [
            a for a in dict.fromkeys(raw_json.get("self_register_actors", []))
            if a in self.actors
        ]
        self.relations = raw_json.get("relations", [])
        self.rules = raw_json.get("rules", [])
        self.workflows = raw_json.get("workflows", [])
        self.custom_logic = {c["name"]: c for c in raw_json.get("custom_logic", [])}
        self.ownership_rules = {}
        self.transitive_ownership = {}
        self.aggregated_fields = []
        self.access_party_rules = {}
        # AJOUT (brique 23, point 106) : rôles SUPERVISEURS par action régie
        # par 'accessibleBy'. Un rôle nommé ici (via une règle 'sharedBy' sur
        # la MÊME référence) transperce le contrôle par colonnes : il lit,
        # modifie ou supprime TOUS les enregistrements, quand les parties
        # restent enfermées dans les leurs.
        self.access_supervisors = {}
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
        self.seeds_raw = raw_json.get("seeds", [])
        self.assets_raw = raw_json.get("assets") or {}
        self.migrations_raw = raw_json.get("migrations", [])
        self.assets = {}
        self.public_actions = set()
        # Conditions de publication portées par `publicWhen` : elles doivent
        # être connues du générateur, pas seulement du frontend.
        self.public_conditions = {}
        # Unicités composites `oncePer` (ex. un compte ne vote qu'une fois par
        # entrée) — elles deviennent des index uniques multi-colonnes.
        self.once_per_rules = []
        self.upload_fields = []
        self.message_rules = []
        # BRIQUE B4 : options d'authentification déclarées sur capability auth.
        # Un dictionnaire vide est volontaire : il ne réveille aucune sortie
        # dans les specs historiques.
        self.auth_features = {}
        # BRIQUE 2a. None (et non EUR) tant que rien n'est déclaré : c'est la
        # règle du point 95 — une spec écrite avant cette brique doit compiler
        # à l'identique, et le défaut n'est appliqué qu'au moment d'encaisser.
        self.payment_currency = None
        self.payment_provider = None

        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(
            self, pipeline: ValidationPipeline = DEFAULT_VALIDATION_PIPELINE
    ) -> CompilationIR:
        """Exécute la validation de cohérence et l'analyse statique de sécurité."""
        print(f"🔬 Analyse statique et audit de sécurité pour '{self.app_name}'...")

        security_reports = pipeline.run(self)

        print("✅ Analyse de l'AST terminée.")
        return self.to_normalized_ast(security_reports)

    def to_normalized_ast(self, security_reports: list[str]) -> CompilationIR:
        normalized: CompilationIR = {
            "meta": {"appName": self.app_name, "security_audit_logs": security_reports},
            "schema": {"entities": self.entities, "relations": self.relations},
            "security": {
                "actors": list(self.actors),
                "self_register_actors": list(self.self_register_actors),
                "rules": self.rules, "workflows": self.workflows,
                "ownership": {f"{k[0]}.{k[1]}": v for k, v in self.ownership_rules.items()},
                "transitive_ownership": self.transitive_ownership,
                "access_parties": {f"{k[0]}.{k[1]}": v for k, v in self.access_party_rules.items()},
                # AJOUT (brique 23) : rôles superviseurs qui transpercent le
                # contrôle 'accessibleBy' — item par item, même clé.
                "access_supervisors": {f"{k[0]}.{k[1]}": v for k, v in self.access_supervisors.items()},
                "public": [f"{e}.{a}" for e, a in sorted(self.public_actions)],
                "public_conditions": {
                    f"{e}.{a}": value
                    for (e, a), value in sorted(self.public_conditions.items())
                },
                "once_per": list(self.once_per_rules),
                "hidden_fields": [f"{e}.{f}" for e, f in sorted(self.masked_fields)],
                "reputation_rules": self.reputation_rules,
                "categorized_fields": self.categorized_fields,
                "generated_fields": self.generated_fields,
                "timestamp_fields": self.timestamp_fields,
                "numbered_fields": self.numbered_fields,
                "required_profiles": self.required_profiles,
                "payable_fields": self.payable_fields,
                "writable_after_payment": self.postpayment_writable,
                "derived_fields": self.derived_fields,
                "aggregated_fields": self.aggregated_fields,
                # POINT 85 : {(entite, champ): {"required"|"unique": True,
                #             "min"|"max": {"portee", "valeur"}}}. Les clés sont
                # des tuples : le générateur les indexe, rien ne les sérialise.
                "field_constraints": self.field_constraints,
                # POINT 95 : formes acceptées pour l'identifiant de compte, ou
                # None si la spec n'en déclare aucune (comportement historique).
                "auth_identifier": self.auth_identifier,
                # POINT 95 : indicatif qui rend '06…' et '+336…' canoniques.
                # Déclaré, jamais deviné : monl ignore d'où appelle l'usager.
                "auth_phone_prefix": self.auth_phone_prefix,
                # BRIQUE 19 (point 96) : {Entite: {champ: [valeurs]}}.
                "enumerated_fields": self.enumerated_fields,
                # BRIQUE B3 : capacités de liste déclarées une par une. Ces
                # listes sont la whitelist de compilation consommée par le
                # générateur ; le client ne peut donc ni inventer une colonne
                # ni un opérateur.
                "filterable_fields": self.filterable_fields,
                "sortable_fields": self.sortable_fields,
                # BRIQUE 20 (point 98) : [{entity, field, value, releases}] —
                # atteindre la valeur rend ce que les enfants ont consommé.
                "release_rules": self.release_rules,
                "upload_fields": self.upload_fields,
                "message_rules": self.message_rules,
                # BRIQUE B4 : configuration d'authentification, vide quand la
                # spec ne demande aucune capacité nouvelle.
                "auth_features": self.auth_features,
                "payment_currency": self.payment_currency,
                "payment_provider": self.payment_provider,
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())},
            "ui": self.ui_overrides,
            "landing": self.landing,
            "capabilities": self.capabilities,
            "seeds": self.seeds,
            "assets": self.assets,
            "migrations": self.migrations,
        }
        return normalized
