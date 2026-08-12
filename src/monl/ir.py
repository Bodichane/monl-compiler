"""Types de l'interface entre validation, analyse et génération.

L'IR reste volontairement composée de conteneurs Python simples : les
émetteurs existants peuvent donc être migrés progressivement, sans conversion
globale ni changement du JSON produit. Ces ``TypedDict`` rendent toutefois la
frontière explicite et vérifiable par un analyseur de types.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

EntityFields = dict[str, str]
RelationKind = Literal["hasMany", "hasOne", "belongsTo"]
EffectKind = Literal[
    "derive",
    "aggregate",
    "increment",
    "decrement",
    "release",
    "payment_lock",
    "postpayment_write",
    "message",
]

# Colonnes sémantiques communes au schéma, au runtime et au contrat frontend.
# Elles appartiennent à l'IR, pas à un émetteur particulier.
PAYMENT_STATUS_COLUMN = "payment_status"
PAYMENT_REF_COLUMN = "payment_ref"
PAYMENT_TRACKING_COLUMNS = (PAYMENT_STATUS_COLUMN, PAYMENT_REF_COLUMN)


class MetaIR(TypedDict):
    appName: str
    security_audit_logs: list[str]


class SchemaIR(TypedDict):
    entities: dict[str, EntityFields]
    relations: list[dict[str, Any]]


class SecurityIR(TypedDict):
    actors: list[str]
    self_register_actors: list[str]
    rules: list[dict[str, Any]]
    workflows: list[dict[str, Any]]
    ownership: dict[str, str]
    transitive_ownership: dict[str, dict[str, Any]]
    access_parties: dict[str, list[str]]
    access_supervisors: dict[str, list[str]]
    public: list[str]
    public_conditions: dict[str, dict[str, Any]]
    once_per: list[dict[str, Any]]
    hidden_fields: list[str]
    reputation_rules: list[dict[str, Any]]
    categorized_fields: list[dict[str, Any]]
    generated_fields: list[dict[str, Any]]
    timestamp_fields: list[dict[str, Any]]
    numbered_fields: list[dict[str, Any]]
    required_profiles: list[dict[str, Any]]
    payable_fields: list[dict[str, Any]]
    writable_after_payment: dict[str, dict[str, Any]]
    derived_fields: list[dict[str, Any]]
    aggregated_fields: list[dict[str, Any]]
    field_constraints: dict[tuple[str, str], dict[str, Any]]
    auth_identifier: list[str] | None
    auth_phone_prefix: str | None
    enumerated_fields: dict[str, dict[str, list[str]]]
    release_rules: list[dict[str, Any]]
    upload_fields: list[dict[str, Any]]
    message_rules: list[dict[str, Any]]


class SandboxIR(TypedDict):
    custom_functions: list[dict[str, Any]]


class CompilationIR(TypedDict):
    """Représentation validée, source commune de tous les émetteurs."""

    meta: MetaIR
    schema: SchemaIR
    security: SecurityIR
    sandbox_ai: SandboxIR
    ui: dict[str, Any]
    landing: dict[str, Any] | None
    capabilities: list[str]
    seeds: list[dict[str, Any]]
    assets: dict[str, Any]
    migrations: list[dict[str, Any]]


class CompilationGenerator(Protocol):
    """Surface minimale du générateur exposée par ``CompilationResult``."""

    ast: CompilationIR
    app_name: str
    compilation_plans: "CompilationPlans"


@dataclass(slots=True)
class RoutePlan:
    """Route logique fusionnée depuis un ou plusieurs workflows.

    Une route n'est pas encore du code FastAPI ni une entrée du contrat JSON :
    c'est le plan commun que ces deux émetteurs rendent ensuite chacun dans
    leur format.
    """

    action: str
    key: str
    target: str
    base_target: str
    actors: set[str]
    tags: list[str]

    def allow(self, actor: str, workflow: str) -> None:
        self.actors.add(actor)
        if workflow not in self.tags:
            self.tags.append(workflow)


@dataclass(frozen=True, slots=True)
class FieldPolicy:
    """Sémantique consolidée d'un champ après validation."""

    name: str
    type: str
    hidden_in_reads: bool
    server_generated: bool
    categorized_in_reads: bool
    postpayment_only: bool
    allowed_values: tuple[str, ...]
    constraints: Mapping[str, Any]
    derived_rule: Mapping[str, Any] | None
    aggregate_rule: Mapping[str, Any] | None
    timestamped: bool
    numbering_rule: Mapping[str, Any] | None
    upload_rule: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class EntityModel:
    """Entité et politiques de ses champs, indexées par leur nom."""

    name: str
    fields: Mapping[str, FieldPolicy]


@dataclass(frozen=True, slots=True)
class RelationModel:
    """Relation validée et orientation physique de sa clé étrangère."""

    source: str
    kind: RelationKind
    target: str

    @property
    def owner_entity(self) -> str:
        return self.target if self.kind == "belongsTo" else self.source

    @property
    def held_entity(self) -> str:
        return self.source if self.kind == "belongsTo" else self.target

    @property
    def fk_column(self) -> str:
        return f"{self.owner_entity.lower()}_id"

    @property
    def unique(self) -> bool:
        return self.kind == "hasOne"


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """Décision d'accès consolidée pour une action sur une cible."""

    entity: str
    action: str
    actors: frozenset[str]
    public: bool
    public_condition: Mapping[str, Any] | None
    owner_entity: str | None
    transitive_ownership: Mapping[str, Any] | None
    party_fields: tuple[str, ...]
    supervisors: frozenset[str]


@dataclass(frozen=True, slots=True)
class EffectPlan:
    """Effet métier validé, indépendant de son rendu SQL ou HTTP."""

    kind: EffectKind
    trigger_entity: str
    target_entity: str
    field: str | None
    source_entity: str | None
    source_field: str | None
    config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CompilationPlans:
    """Analyses dérivées partagées par les émetteurs.

    Le générateur reste l'implémentation historique de ces calculs, mais le
    contrat frontend reçoit désormais ce résultat nommé plutôt que de lire ses
    méthodes privées. Les deux émetteurs consomment donc la même analyse.
    """

    route_map: Mapping[tuple[str, str], RoutePlan]
    foreign_key_placements: Mapping[str, tuple[Mapping[str, Any], ...]]
    identity_foreign_keys: Mapping[str, frozenset[str]]
    client_foreign_keys: Mapping[str, tuple[str, ...]]
    incoming_relations: Mapping[str, Mapping[str, Any] | None]
    payment_locked_parents: Mapping[str, tuple[Mapping[str, Any], ...]]
    reputation_rules_by_trigger: Mapping[str, tuple[Mapping[str, Any], ...]]
    entity_models: Mapping[str, EntityModel]
    access_policies: Mapping[tuple[str, str], AccessPolicy]
    actors: tuple[str, ...]
    self_register_actors: tuple[str, ...]
    auth_identifier: tuple[str, ...] | None
    auth_phone_prefix: str | None
    public_conditions: Mapping[tuple[str, str], Mapping[str, Any]]
    required_profiles: Mapping[str, str]
    payable_by_entity: Mapping[str, str]
    release_rules_by_entity: Mapping[str, tuple[Mapping[str, Any], ...]]
    transitive_ownership: Mapping[str, Mapping[str, Any]]
    postpayment_writable_by_entity: Mapping[str, Mapping[str, Any]]
    assets: Mapping[str, Any]
    once_per_rules: tuple[Mapping[str, Any], ...]
    upload_fields: tuple[Mapping[str, Any], ...]
    message_rules_by_trigger: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class CompilationResult:
    """Résultat nommé d'une compilation backend réussie."""

    ir: CompilationIR
    generator: CompilationGenerator
    plans: CompilationPlans
