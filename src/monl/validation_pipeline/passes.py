"""Une passe par famille de refus, dans l'ordre où le pilote les joue."""

from dataclasses import dataclass

from .contrats import ValidationContext


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
class ListQueryCapabilityValidationPass:
    """Valide les filtres exacts et tris déclarés sur les listes."""

    name: str = "list_query_capabilities"

    def run(self, context: ValidationContext) -> list[str]:
        # La pipeline est aussi exercée par des faux contextes de tests et par
        # des intégrations historiques. Une nouvelle passe optionnelle ne doit
        # pas rendre ces contextes incapables de vérifier l'ordre des passes
        # qu'ils connaissaient déjà.
        validation = getattr(context, "_valider_capacites_de_liste", None)
        if validation is not None:
            validation()
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
        # B1 partage la frontière "workflows puis validations dépendantes".
        # Le getattr garde la compatibilité avec les contextes de test et les
        # intégrations historiques qui implémentent encore l'ancien protocole.
        upload_validation = getattr(context, "_valider_champs_uploades", None)
        if upload_validation is not None:
            upload_validation()
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
class MessageRuleValidationPass:
    """Valide les messages sortants après résolution de l'identité du compte."""

    name: str = "message_rules"

    def run(self, context: ValidationContext) -> list[str]:
        context._valider_regles_message()
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
