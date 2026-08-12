"""Orchestration explicite des passes de validation de l'AST MONL.

Les premières passes délèguent encore à des méthodes historiques de
``MonlAST``. Cette frontière permet de les extraire une par une sans modifier
l'ordre des contrôles ni les diagnostics visibles par l'utilisateur.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class ValidationContext(Protocol):
    """Surface dont les passes actuelles ont besoin."""

    def _valider_contraintes_de_champ(self) -> None: ...

    def _valider_controle_dacces(self) -> None: ...

    def _valider_regle_public(self) -> None: ...

    def _valider_regles_once_per(self) -> None: ...

    def _valider_regle_restrictedTo(self) -> None: ...

    def _valider_champs_masques(self) -> None: ...

    def _valider_champs_categorises(self) -> None: ...

    def _valider_champs_generes(self) -> None: ...

    def _valider_champs_horodates(self) -> None: ...

    def _valider_champs_numerotes(self) -> None: ...

    def _valider_champs_enumeres(self) -> None: ...

    def _valider_requires_own_et_payable(self) -> None: ...

    def _valider_champs_derives(self) -> None: ...

    def _valider_champs_agreges(self) -> None: ...

    def _valider_securite_calculs_paiement(self) -> None: ...

    def _valider_effets_compteurs(self) -> None: ...

    def _valider_proprietaire_paiement(self) -> None: ...

    def _valider_regles_liberation(self) -> None: ...

    def _valider_workflows_et_collisions(self) -> None: ...

    def _valider_ui_overrides(self) -> None: ...

    def _valider_landing(self) -> None: ...

    def _valider_capacites(self) -> None: ...

    def _valider_assets_et_seeds(self) -> None: ...

    def _valider_migrations(self) -> None: ...

    def _valider_regle_apres_paiement(self) -> None: ...

    def _audit_security_rules(self) -> list[str]: ...

    def _audit_self_registration(self) -> list[str]: ...


class ValidationPass(Protocol):
    name: str

    def run(self, context: ValidationContext) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class FieldConstraintValidationPass:
    """Valide ``required``, ``unique``, ``min`` et ``max`` avant les autres règles."""

    name: str = "field_constraints"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_contraintes_de_champ()
        return []


@dataclass(frozen=True, slots=True)
class AccessControlValidationPass:
    """Construit et valide les politiques d'accès avant les règles de présentation."""

    name: str = "access_control"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_controle_dacces()
        return []


@dataclass(frozen=True, slots=True)
class PublicVisibilityValidationPass:
    """Valide les règles ``public`` et ``publicWhen``."""

    name: str = "public_visibility"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regle_public()
        return []


@dataclass(frozen=True, slots=True)
class OncePerValidationPass:
    """Valide les contraintes d'unicité métier liées au compte courant."""

    name: str = "once_per"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_once_per()
        return []


@dataclass(frozen=True, slots=True)
class RestrictedFieldValidationPass:
    """Vérifie les restrictions de lecture de champs par rôle."""

    name: str = "restricted_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regle_restrictedTo()
        return []


@dataclass(frozen=True, slots=True)
class HiddenFieldValidationPass:
    """Prépare les champs masqués pour les validations et générateurs suivants."""

    name: str = "hidden_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_masques()
        return []


@dataclass(frozen=True, slots=True)
class CategorizedFieldValidationPass:
    """Valide les catégories calculées destinées aux réponses de lecture."""

    name: str = "categorized_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_categorises()
        return []


@dataclass(frozen=True, slots=True)
class GeneratedFieldValidationPass:
    """Valide les champs remplis depuis l'identité de l'appelant."""

    name: str = "generated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_generes()
        return []


@dataclass(frozen=True, slots=True)
class TimestampFieldValidationPass:
    """Valide les instants de création gérés par le serveur."""

    name: str = "timestamp_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_horodates()
        return []


@dataclass(frozen=True, slots=True)
class NumberedFieldValidationPass:
    """Valide les identifiants lisibles gérés par le serveur."""

    name: str = "numbered_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_numerotes()
        return []


@dataclass(frozen=True, slots=True)
class EnumeratedFieldValidationPass:
    """Valide les champs texte limités à des valeurs explicites."""

    name: str = "enumerated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_enumeres()
        return []


@dataclass(frozen=True, slots=True)
class CreationPaymentPrerequisitePass:
    """Valide les prérequis de propriété et d'encaissement."""

    name: str = "creation_payment_prerequisites"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_requires_own_et_payable()
        return []


@dataclass(frozen=True, slots=True)
class DerivedFieldValidationPass:
    """Valide les montants calculés depuis une ligne liée."""

    name: str = "derived_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_derives()
        return []


@dataclass(frozen=True, slots=True)
class AggregatedFieldValidationPass:
    """Valide les totaux calculés par agrégation de lignes enfants."""

    name: str = "aggregated_fields"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_champs_agreges()
        return []


@dataclass(frozen=True, slots=True)
class CalculationPaymentSafetyPass:
    """Recoupe les champs calculés avec les bornes et les montants payables."""

    name: str = "calculation_payment_safety"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_securite_calculs_paiement()
        return []


@dataclass(frozen=True, slots=True)
class CounterEffectValidationPass:
    """Valide les incréments et décréments déclenchés par les créations."""

    name: str = "counter_effects"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_effets_compteurs()
        return []


@dataclass(frozen=True, slots=True)
class PayableOwnerValidationPass:
    """Vérifie qu'un paiement remonte jusqu'à un compte propriétaire."""

    name: str = "payable_owner"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_proprietaire_paiement()
        return []


@dataclass(frozen=True, slots=True)
class ReleaseRuleValidationPass:
    """Valide les transitions qui rendent les compteurs consommés."""

    name: str = "release_rules"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_liberation()
        return []


@dataclass(frozen=True, slots=True)
class WorkflowCollisionValidationPass:
    """Valide les workflows et les collisions d'autorité entre acteurs."""

    name: str = "workflow_collisions"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_workflows_et_collisions()
        return []


@dataclass(frozen=True, slots=True)
class UIOverrideValidationPass:
    """Valide les champs référencés par les préférences d'interface."""

    name: str = "ui_overrides"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_ui_overrides()
        return []


@dataclass(frozen=True, slots=True)
class LandingValidationPass:
    """Normalise le contenu éditorial transmis au frontend."""

    name: str = "landing"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_landing()
        return []


@dataclass(frozen=True, slots=True)
class CapabilityValidationPass:
    """Valide les capacités et leurs options d'authentification."""

    name: str = "capabilities"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_capacites()
        return []


@dataclass(frozen=True, slots=True)
class AssetsSeedValidationPass:
    """Valide les assets locaux et les données de démonstration."""

    name: str = "assets_seeds"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_assets_et_seeds()
        return []


@dataclass(frozen=True, slots=True)
class MigrationValidationPass:
    """Valide les opérations de schéma non additives déclarées."""

    name: str = "migrations"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_migrations()
        return []


@dataclass(frozen=True, slots=True)
class PostPaymentValidationPass:
    """Valide les champs réservés à l'écriture après règlement."""

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


@dataclass(frozen=True, slots=True)
class ValidationPipeline:
    passes: Sequence[ValidationPass]

    def run(self, context: ValidationContext) -> list[str]:
        reports = []
        for validation_pass in self.passes:
            reports.extend(validation_pass.run(context))
        return reports


DEFAULT_VALIDATION_PIPELINE = ValidationPipeline((
    FieldConstraintValidationPass(),
    AccessControlValidationPass(),
    PublicVisibilityValidationPass(),
    OncePerValidationPass(),
    RestrictedFieldValidationPass(),
    HiddenFieldValidationPass(),
    CategorizedFieldValidationPass(),
    GeneratedFieldValidationPass(),
    TimestampFieldValidationPass(),
    NumberedFieldValidationPass(),
    EnumeratedFieldValidationPass(),
    CreationPaymentPrerequisitePass(),
    DerivedFieldValidationPass(),
    AggregatedFieldValidationPass(),
    CalculationPaymentSafetyPass(),
    CounterEffectValidationPass(),
    PayableOwnerValidationPass(),
    ReleaseRuleValidationPass(),
    WorkflowCollisionValidationPass(),
    UIOverrideValidationPass(),
    LandingValidationPass(),
    CapabilityValidationPass(),
    AssetsSeedValidationPass(),
    MigrationValidationPass(),
    PostPaymentValidationPass(),
    SecurityAuditPass(),
    SelfRegistrationAuditPass(),
))
