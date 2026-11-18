"""Serializable structures produced by the validation of the DSL.

The immutable analysis plans live in ir.py. This separation keeps the
normalized dictionaries without confusing them with their resolved
analyses."""

from typing import Any, Literal, TypedDict

EntityFields = dict[str, str]
RelationKind = Literal["hasMany", "hasOne", "belongsTo"]
ActionKind = Literal["Create", "Read", "Update", "Delete", "Execute"]


class MetaIR(TypedDict):
    appName: str
    security_audit_logs: list[str]


class RelationIR(TypedDict):
    source: str
    type: RelationKind
    target: str


class ActionIR(TypedDict):
    type: ActionKind
    target: str


class WorkflowIR(TypedDict):
    name: str
    actor: str
    actions: list[ActionIR]


class ForeignKeyPlacement(TypedDict):
    fk_column: str
    owner_entity: str
    unique: bool


class DerivedFieldIR(TypedDict):
    """derivedFrom rule normalized by the validator."""

    entity: str
    field: str
    source_entity: str
    source_field: str
    factor: str


class AggregatedFieldIR(TypedDict):
    """Validated sum of a field over an entity's child rows."""

    entity: str
    field: str
    source_entity: str
    source_field: str


class FieldBoundIR(TypedDict):
    portee: Literal["longueur", "valeur"]
    valeur: int


class FieldConstraintsIR(TypedDict, total=False):
    required: bool
    unique: bool
    min: FieldBoundIR
    max: FieldBoundIR


class CounterRuleIR(TypedDict):
    trigger_entity: str
    target_entity: str
    target_field: str
    amount: int | None
    amount_field: str | None
    direction: Literal["increments", "decrements"]


class NamedFieldIR(TypedDict):
    entity: str
    field: str


class NumberedFieldIR(NamedFieldIR):
    format: str
    periode: str


class UploadFieldIR(NamedFieldIR):
    max_bytes: int
    accepted_types: list[str]


class CategoryLabelIR(TypedDict):
    label: str


class CategoryClauseIR(CategoryLabelIR, total=False):
    below: int
    otherwise: bool


class CategorizedFieldIR(NamedFieldIR):
    clauses: list[CategoryClauseIR]


class PostPaymentIR(TypedDict):
    actor: str
    fields: list[str]


class PublicConditionIR(TypedDict):
    field: str
    value: str


class TransitiveOwnershipIR(TypedDict):
    actor: str
    chain: list[str]


class SchemaIR(TypedDict):
    entities: dict[str, EntityFields]
    relations: list[RelationIR]


class SecurityIR(TypedDict):
    actors: list[str]
    self_register_actors: list[str]
    rules: list[dict[str, Any]]
    workflows: list[WorkflowIR]
    ownership: dict[str, str]
    transitive_ownership: dict[str, TransitiveOwnershipIR]
    access_parties: dict[str, list[str]]
    access_supervisors: dict[str, list[str]]
    public: list[str]
    public_conditions: dict[str, PublicConditionIR]
    once_per: list[dict[str, Any]]
    hidden_fields: list[str]
    reputation_rules: list[CounterRuleIR]
    categorized_fields: list[CategorizedFieldIR]
    generated_fields: list[NamedFieldIR]
    timestamp_fields: list[NamedFieldIR]
    numbered_fields: list[NumberedFieldIR]
    required_profiles: dict[str, str]
    payable_fields: list[NamedFieldIR]
    writable_after_payment: dict[str, PostPaymentIR]
    derived_fields: list[DerivedFieldIR]
    aggregated_fields: list[AggregatedFieldIR]
    field_constraints: dict[tuple[str, str], FieldConstraintsIR]
    auth_identifier: list[str] | None
    auth_phone_prefix: str | None
    auth_features: dict[str, Any]
    # BRICK 2a: {'code': 'XOF', 'exponent': 0} or None. The exponent is
    # RESOLVED by the validator, never recomputed here: two currency tables
    # would eventually diverge, and a unit divergence is paid for on the bank
    # statement.
    payment_currency: dict[str, Any] | None
    payment_provider: str | None
    enumerated_fields: dict[str, dict[str, list[str]]]
    filterable_fields: list[NamedFieldIR]
    sortable_fields: list[NamedFieldIR]
    release_rules: list[dict[str, Any]]
    upload_fields: list[UploadFieldIR]
    message_rules: list[dict[str, Any]]


class SandboxIR(TypedDict):
    custom_functions: list[dict[str, Any]]


class CompilationIR(TypedDict):
    """Validated representation, the shared source of all emitters."""

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
