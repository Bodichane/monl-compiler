"""One pass per family of refusals, in the order the driver plays them."""

from dataclasses import dataclass

from .contrats import ValidationContext


@dataclass(frozen=True, slots=True)
class FieldConstraintValidationPass:
    """Validates ``required``, ``unique``, ``min`` and ``max`` before the other
    rules."""

    name: str = "field_constraints"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_contraintes_de_champ()
        return []

@dataclass(frozen=True, slots=True)
class AccessControlValidationPass:
    """Builds and validates the access policies before the presentation rules."""

    name: str = "access_control"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_controle_dacces()
        return []

@dataclass(frozen=True, slots=True)
class PublicVisibilityValidationPass:
    """Validates the ``public`` and ``publicWhen`` rules."""

    name: str = "public_visibility"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regle_public()
        return []

@dataclass(frozen=True, slots=True)
class OncePerValidationPass:
    """Validates the business uniqueness constraints tied to the current
    account."""

    name: str = "once_per"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_once_per()
        return []

@dataclass(frozen=True, slots=True)
class RestrictedFieldValidationPass:
    """Checks the per-role field read restrictions."""

    name: str = "restricted_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regle_restrictedTo()
        return []

@dataclass(frozen=True, slots=True)
class HiddenFieldValidationPass:
    """Prepares the hidden fields for the following validations and generators."""

    name: str = "hidden_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_masques()
        return []

@dataclass(frozen=True, slots=True)
class CategorizedFieldValidationPass:
    """Validates the computed categories meant for read responses."""

    name: str = "categorized_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_categorises()
        return []

@dataclass(frozen=True, slots=True)
class GeneratedFieldValidationPass:
    """Validates the fields filled from the caller's identity."""

    name: str = "generated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_generes()
        return []

@dataclass(frozen=True, slots=True)
class TimestampFieldValidationPass:
    """Validates the creation moments managed by the server."""

    name: str = "timestamp_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_horodates()
        return []

@dataclass(frozen=True, slots=True)
class NumberedFieldValidationPass:
    """Validates the readable identifiers managed by the server."""

    name: str = "numbered_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_numerotes()
        return []

@dataclass(frozen=True, slots=True)
class EnumeratedFieldValidationPass:
    """Validates the text fields limited to explicit values."""

    name: str = "enumerated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_enumeres()
        return []

@dataclass(frozen=True, slots=True)
class ListQueryCapabilityValidationPass:
    """Validates the exact filters and sorts declared on lists."""

    name: str = "list_query_capabilities"

    def run(self, context: ValidationContext) -> list[str]:
        # The pipeline is also exercised by fake test contexts and by
        # historical integrations. A new optional pass must not make these
        # contexts unable to check the order of the passes they already knew.
        validation = getattr(context, "_valider_capacites_de_liste", None)
        if validation is not None:
            validation()
        return []

@dataclass(frozen=True, slots=True)
class CreationPaymentPrerequisitePass:
    """Validates the ownership and payment prerequisites."""

    name: str = "creation_payment_prerequisites"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_requires_own_et_payable()
        return []

@dataclass(frozen=True, slots=True)
class DerivedFieldValidationPass:
    """Validates the amounts calculated from a linked row."""

    name: str = "derived_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_derives()
        return []

@dataclass(frozen=True, slots=True)
class AggregatedFieldValidationPass:
    """Validates the totals calculated by aggregating child rows."""

    name: str = "aggregated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_agreges()
        return []

@dataclass(frozen=True, slots=True)
class CalculationPaymentSafetyPass:
    """Cross-checks the calculated fields against the bounds and the payable
    amounts."""

    name: str = "calculation_payment_safety"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_securite_calculs_paiement()
        return []

@dataclass(frozen=True, slots=True)
class CounterEffectValidationPass:
    """Validates the increments and decrements triggered by creations."""

    name: str = "counter_effects"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_effets_compteurs()
        return []

@dataclass(frozen=True, slots=True)
class PayableOwnerValidationPass:
    """Checks that a payment climbs up to an owning account."""

    name: str = "payable_owner"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_proprietaire_paiement()
        return []

@dataclass(frozen=True, slots=True)
class ReleaseRuleValidationPass:
    """Validates the transitions that give back consumed counters."""

    name: str = "release_rules"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_liberation()
        return []

@dataclass(frozen=True, slots=True)
class WorkflowCollisionValidationPass:
    """Validates the workflows and the authority collisions between actors."""

    name: str = "workflow_collisions"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_workflows_et_collisions()
        # B1 shares the "workflows then dependent validations" boundary. The
        # getattr keeps compatibility with the test contexts and historical
        # integrations that still implement the old protocol.
        upload_validation = getattr(context, "_valider_champs_uploades", None)
        if upload_validation is not None:
            upload_validation()
        return []

@dataclass(frozen=True, slots=True)
class UIOverrideValidationPass:
    """Validates the fields referenced by the interface preferences."""

    name: str = "ui_overrides"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_ui_overrides()
        return []

@dataclass(frozen=True, slots=True)
class LandingValidationPass:
    """Normalizes the editorial content passed to the frontend."""

    name: str = "landing"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_landing()
        return []

@dataclass(frozen=True, slots=True)
class CapabilityValidationPass:
    """Validates the capabilities and their authentication options."""

    name: str = "capabilities"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_capacites()
        return []

@dataclass(frozen=True, slots=True)
class MessageRuleValidationPass:
    """Validates the outgoing messages after the account identity is resolved."""

    name: str = "message_rules"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_message()
        return []

@dataclass(frozen=True, slots=True)
class AssetsSeedValidationPass:
    """Validates the local assets and the demo data."""

    name: str = "assets_seeds"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_assets_et_seeds()
        return []

@dataclass(frozen=True, slots=True)
class MigrationValidationPass:
    """Validates the declared non-additive schema operations."""

    name: str = "migrations"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_migrations()
        return []

@dataclass(frozen=True, slots=True)
class PostPaymentValidationPass:
    """Validates the fields reserved for writing after payment."""

    name: str = "post_payment_writes"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regle_apres_paiement()
        return []

@dataclass(frozen=True, slots=True)
class SecurityAuditPass:
    name: str = "security_audit"

    def run(self, context: ValidationContext) -> list[str]:
        return context._audit_security_rules()

@dataclass(frozen=True, slots=True)
class SelfRegistrationAuditPass:
    name: str = "self_registration_audit"

    def run(self, context: ValidationContext) -> list[str]:
        return context._audit_self_registration()
