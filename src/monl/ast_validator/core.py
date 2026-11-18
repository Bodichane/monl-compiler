"""The `MonlAST` class, recomposed from mixins.

One module per CONCERN, as `generator/` already did: a new rule is added
in its layer's module, never here. This file carries only the state
derived from the AST, the ordering of validation, and the normalization
that comes out of it."""

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
    """The validated AST of a monl spec.

    The rules live in the mixins above; the execution order comes from the
    pipeline (`validation_pipeline.py`), not from the order of the bases."""

    def __init__(self, raw_json: dict[str, Any], base_dir: str | None = None):
        # ADDED (brick 13, point 83): 'base_dir' is the project's folder (the
        # spec's). It is needed only by the checks that touch the DISK —
        # checking that a declared asset really exists. The FORM checks
        # (absolute path, '..' traversal, remote URL) are pure and always
        # apply: that split is what lets tests write a spec in memory without
        # losing the refusals that need no file.
        self.base_dir = base_dir
        self.raw = raw_json
        self.app_name = raw_json.get("app")
        self.entities = {}
        # FIX (beta 3, determinism): the actor list was a 'set', whose
        # iteration order depends on PYTHONHASHSEED — two compilations of the
        # same spec could produce a different 'VALID_ACTORS' in app.py, which
        # contradicted the "same input, byte-identical output" guarantee. The
        # declaration order is now kept (deduplicated).
        self.actors = list(dict.fromkeys(raw_json.get("actors", [])))
        # ADDED (beta 3): actors open to self-registration ('selfRegister'
        # marker). The others are provisioned offline.
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
        # ADDED (brick 23, point 106): SUPERVISOR roles per action governed by
        # 'accessibleBy'. A role named here (through a 'sharedBy' rule on the
        # SAME reference) pierces the column check: it reads, updates or
        # deletes ALL the records, while the parties stay locked into their
        # own.
        self.access_supervisors = {}
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
        self.seeds_raw = raw_json.get("seeds", [])
        self.assets_raw = raw_json.get("assets") or {}
        self.migrations_raw = raw_json.get("migrations", [])
        self.assets = {}
        self.public_actions = set()
        # Publication conditions carried by `publicWhen`: the generator must
        # know them, not only the frontend.
        self.public_conditions = {}
        # `oncePer` composite uniqueness (e.g. an account votes only once per
        # entry) — they become multi-column unique indexes.
        self.once_per_rules = []
        self.upload_fields = []
        self.message_rules = []
        # BRICK B4: authentication options declared on capability auth. An
        # empty dictionary is deliberate: it wakes up no output in historical
        # specs.
        self.auth_features = {}
        # BRICK 2a. None (not EUR) as long as nothing is declared: this is the
        # point 95 rule — a spec written before this brick must compile
        # identically, and the default is applied only at charging time.
        self.payment_currency = None
        self.payment_provider = None

        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(
            self, pipeline: ValidationPipeline = DEFAULT_VALIDATION_PIPELINE
    ) -> CompilationIR:
        """Runs the consistency validation and the static security analysis."""
        print(f"🔬 Static analysis and security audit for '{self.app_name}'...")

        security_reports = pipeline.run(self)

        print("✅ AST analysis complete.")
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
                # ADDED (brick 23): supervisor roles that pierce the
                # 'accessibleBy' check — item by item, same key.
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
                # POINT 85: {(entity, field): {"required"|"unique": True,
                #             "min"|"max": {"portee", "valeur"}}}. The keys are tuples:
                # the generator indexes them, nothing serializes them.
                "field_constraints": self.field_constraints,
                # POINT 95: accepted forms for the account identifier, or None
                # if the spec declares none (historical behavior).
                "auth_identifier": self.auth_identifier,
                # POINT 95: the calling code that makes '06…' and '+336…'
                # canonical. Declared, never guessed: monl does not know where
                # the user calls from.
                "auth_phone_prefix": self.auth_phone_prefix,
                # BRIQUE 19 (point 96) : {Entite: {champ: [valeurs]}}.
                "enumerated_fields": self.enumerated_fields,
                # BRICK B3: list capabilities declared one by one. These lists
                # are the compile-time whitelist consumed by the generator; the
                # client can therefore invent neither a column nor an operator.
                "filterable_fields": self.filterable_fields,
                "sortable_fields": self.sortable_fields,
                # BRICK 20 (point 98): [{entity, field, value, releases}] —
                # reaching the value gives back what the children consumed.
                "release_rules": self.release_rules,
                "upload_fields": self.upload_fields,
                "message_rules": self.message_rules,
                # BRICK B4: authentication configuration, empty when the spec
                # asks for no new capability.
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
