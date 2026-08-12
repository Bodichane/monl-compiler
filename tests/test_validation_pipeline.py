"""Contrat d'orchestration des passes du validateur."""

import pytest

from monl.validation_pipeline import DEFAULT_VALIDATION_PIPELINE


class FakeContext:
    def __init__(
        self,
        fail_constraints=False,
        fail_access=False,
        fail_public_visibility=False,
        fail_once_per=False,
        fail_restricted_fields=False,
        fail_hidden_fields=False,
        fail_categorized_fields=False,
        fail_generated_fields=False,
        fail_timestamp_fields=False,
        fail_numbered_fields=False,
        fail_enumerated_fields=False,
        fail_creation_payment_prerequisites=False,
        fail_derived_fields=False,
        fail_aggregated_fields=False,
        fail_calculation_payment_safety=False,
        fail_counter_effects=False,
        fail_payable_owner=False,
        fail_release_rules=False,
        fail_workflow_collisions=False,
        fail_ui_overrides=False,
        fail_landing=False,
        fail_capabilities=False,
        fail_assets_seeds=False,
        fail_migrations=False,
        fail_post_payment_writes=False,
    ):
        self.calls = []
        self.fail_constraints = fail_constraints
        self.fail_access = fail_access
        self.fail_public_visibility = fail_public_visibility
        self.fail_once_per = fail_once_per
        self.fail_restricted_fields = fail_restricted_fields
        self.fail_hidden_fields = fail_hidden_fields
        self.fail_categorized_fields = fail_categorized_fields
        self.fail_generated_fields = fail_generated_fields
        self.fail_timestamp_fields = fail_timestamp_fields
        self.fail_numbered_fields = fail_numbered_fields
        self.fail_enumerated_fields = fail_enumerated_fields
        self.fail_creation_payment_prerequisites = fail_creation_payment_prerequisites
        self.fail_derived_fields = fail_derived_fields
        self.fail_aggregated_fields = fail_aggregated_fields
        self.fail_calculation_payment_safety = fail_calculation_payment_safety
        self.fail_counter_effects = fail_counter_effects
        self.fail_payable_owner = fail_payable_owner
        self.fail_release_rules = fail_release_rules
        self.fail_workflow_collisions = fail_workflow_collisions
        self.fail_ui_overrides = fail_ui_overrides
        self.fail_landing = fail_landing
        self.fail_capabilities = fail_capabilities
        self.fail_assets_seeds = fail_assets_seeds
        self.fail_migrations = fail_migrations
        self.fail_post_payment_writes = fail_post_payment_writes

    def _valider_contraintes_de_champ(self):
        self.calls.append("field_constraints")
        if self.fail_constraints:
            raise ValueError("contraintes de champ invalides")

    def _valider_controle_dacces(self):
        self.calls.append("access_control")
        if self.fail_access:
            raise ValueError("contrôle d'accès invalide")

    def _valider_regle_public(self):
        self.calls.append("public_visibility")
        if self.fail_public_visibility:
            raise ValueError("visibilité publique invalide")

    def _valider_regles_once_per(self):
        self.calls.append("once_per")
        if self.fail_once_per:
            raise ValueError("unicité métier invalide")

    def _valider_regle_restrictedTo(self):
        self.calls.append("restricted_fields")
        if self.fail_restricted_fields:
            raise ValueError("restriction de champ invalide")

    def _valider_champs_masques(self):
        self.calls.append("hidden_fields")
        if self.fail_hidden_fields:
            raise ValueError("champ masqué invalide")

    def _valider_champs_categorises(self):
        self.calls.append("categorized_fields")
        if self.fail_categorized_fields:
            raise ValueError("champ catégorisé invalide")

    def _valider_champs_generes(self):
        self.calls.append("generated_fields")
        if self.fail_generated_fields:
            raise ValueError("champ généré invalide")

    def _valider_champs_horodates(self):
        self.calls.append("timestamp_fields")
        if self.fail_timestamp_fields:
            raise ValueError("champ horodaté invalide")

    def _valider_champs_numerotes(self):
        self.calls.append("numbered_fields")
        if self.fail_numbered_fields:
            raise ValueError("champ numéroté invalide")

    def _valider_champs_enumeres(self):
        self.calls.append("enumerated_fields")
        if self.fail_enumerated_fields:
            raise ValueError("champ énuméré invalide")

    def _valider_requires_own_et_payable(self):
        self.calls.append("creation_payment_prerequisites")
        if self.fail_creation_payment_prerequisites:
            raise ValueError("prérequis de création/paiement invalide")

    def _valider_champs_derives(self):
        self.calls.append("derived_fields")
        if self.fail_derived_fields:
            raise ValueError("champ dérivé invalide")

    def _valider_champs_agreges(self):
        self.calls.append("aggregated_fields")
        if self.fail_aggregated_fields:
            raise ValueError("champ agrégé invalide")

    def _valider_securite_calculs_paiement(self):
        self.calls.append("calculation_payment_safety")
        if self.fail_calculation_payment_safety:
            raise ValueError("sécurité calcul/paiement invalide")

    def _valider_effets_compteurs(self):
        self.calls.append("counter_effects")
        if self.fail_counter_effects:
            raise ValueError("effet compteur invalide")

    def _valider_proprietaire_paiement(self):
        self.calls.append("payable_owner")
        if self.fail_payable_owner:
            raise ValueError("propriétaire payable invalide")

    def _valider_regles_liberation(self):
        self.calls.append("release_rules")
        if self.fail_release_rules:
            raise ValueError("règle de libération invalide")

    def _valider_workflows_et_collisions(self):
        self.calls.append("workflow_collisions")
        if self.fail_workflow_collisions:
            raise ValueError("workflow/collision invalide")

    def _valider_ui_overrides(self):
        self.calls.append("ui_overrides")
        if self.fail_ui_overrides:
            raise ValueError("préférence UI invalide")

    def _valider_landing(self):
        self.calls.append("landing")
        if self.fail_landing:
            raise ValueError("landing invalide")

    def _valider_capacites(self):
        self.calls.append("capabilities")
        if self.fail_capabilities:
            raise ValueError("capacité invalide")

    def _valider_assets_et_seeds(self):
        self.calls.append("assets_seeds")
        if self.fail_assets_seeds:
            raise ValueError("assets/seeds invalides")

    def _valider_migrations(self):
        self.calls.append("migrations")
        if self.fail_migrations:
            raise ValueError("migrations invalides")

    def _valider_regle_apres_paiement(self):
        self.calls.append("post_payment_writes")
        if self.fail_post_payment_writes:
            raise ValueError("écriture post-paiement invalide")

    def _audit_security_rules(self):
        self.calls.append("security")
        return ["rapport sécurité"]

    def _audit_self_registration(self):
        self.calls.append("registration")
        return ["rapport inscription"]


PIPELINE = DEFAULT_VALIDATION_PIPELINE


def test_pipeline_execute_les_passes_dans_lordre_et_agrege_les_rapports():
    context = FakeContext()

    reports = PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields",
        "hidden_fields", "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields",
        "enumerated_fields", "creation_payment_prerequisites", "derived_fields", "aggregated_fields",
        "calculation_payment_safety", "counter_effects", "payable_owner", "release_rules", "workflow_collisions",
        "ui_overrides", "landing", "capabilities", "assets_seeds", "migrations", "post_payment_writes", "security",
        "registration",
    ]
    assert reports == ["rapport sécurité", "rapport inscription"]


def test_pipeline_sarrete_immediatement_sur_une_validation_invalide():
    context = FakeContext(fail_post_payment_writes=True)

    with pytest.raises(ValueError, match="écriture post-paiement invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields",
        "hidden_fields", "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields",
        "enumerated_fields", "creation_payment_prerequisites", "derived_fields", "aggregated_fields",
        "calculation_payment_safety", "counter_effects", "payable_owner", "release_rules", "workflow_collisions",
        "ui_overrides", "landing", "capabilities", "assets_seeds", "migrations", "post_payment_writes",
    ]


def test_pipeline_sarrete_avant_la_structure_si_les_contraintes_sont_invalides():
    context = FakeContext(fail_constraints=True)

    with pytest.raises(ValueError, match="contraintes de champ invalides"):
        PIPELINE.run(context)

    assert context.calls == ["field_constraints"]


def test_pipeline_sarrete_avant_la_structure_si_le_controle_dacces_est_invalide():
    context = FakeContext(fail_access=True)

    with pytest.raises(ValueError, match="contrôle d'accès invalide"):
        PIPELINE.run(context)

    assert context.calls == ["field_constraints", "access_control"]


def test_pipeline_sarrete_avant_la_structure_si_la_visibilite_publique_est_invalide():
    context = FakeContext(fail_public_visibility=True)

    with pytest.raises(ValueError, match="visibilité publique invalide"):
        PIPELINE.run(context)

    assert context.calls == ["field_constraints", "access_control", "public_visibility"]


def test_pipeline_sarrete_avant_la_structure_si_once_per_est_invalide():
    context = FakeContext(fail_once_per=True)

    with pytest.raises(ValueError, match="unicité métier invalide"):
        PIPELINE.run(context)

    assert context.calls == ["field_constraints", "access_control", "public_visibility", "once_per"]


def test_pipeline_sarrete_avant_la_structure_si_restricted_to_est_invalide():
    context = FakeContext(fail_restricted_fields=True)

    with pytest.raises(ValueError, match="restriction de champ invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields"
    ]


def test_pipeline_sarrete_avant_la_structure_si_hidden_est_invalide():
    context = FakeContext(fail_hidden_fields=True)

    with pytest.raises(ValueError, match="champ masqué invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields"
    ]


def test_pipeline_sarrete_avant_la_structure_si_categorized_est_invalide():
    context = FakeContext(fail_categorized_fields=True)

    with pytest.raises(ValueError, match="champ catégorisé invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_generated_est_invalide():
    context = FakeContext(fail_generated_fields=True)

    with pytest.raises(ValueError, match="champ généré invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_timestamp_est_invalide():
    context = FakeContext(fail_timestamp_fields=True)

    with pytest.raises(ValueError, match="champ horodaté invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_numbered_est_invalide():
    context = FakeContext(fail_numbered_fields=True)

    with pytest.raises(ValueError, match="champ numéroté invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_one_of_est_invalide():
    context = FakeContext(fail_enumerated_fields=True)

    with pytest.raises(ValueError, match="champ énuméré invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields", "enumerated_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_derived_est_invalide():
    context = FakeContext(fail_derived_fields=True)

    with pytest.raises(ValueError, match="champ dérivé invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields", "enumerated_fields",
        "creation_payment_prerequisites", "derived_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_agregated_est_invalide():
    context = FakeContext(fail_aggregated_fields=True)

    with pytest.raises(ValueError, match="champ agrégé invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields", "enumerated_fields",
        "creation_payment_prerequisites", "derived_fields", "aggregated_fields",
    ]


def test_pipeline_sarrete_avant_la_structure_si_les_prerequis_de_paiement_sont_invalides():
    context = FakeContext(fail_creation_payment_prerequisites=True)

    with pytest.raises(ValueError, match="prérequis de création/paiement invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields", "enumerated_fields",
        "creation_payment_prerequisites",
    ]


def test_pipeline_sarrete_avant_la_structure_si_la_securite_calcul_paiement_est_invalide():
    context = FakeContext(fail_calculation_payment_safety=True)

    with pytest.raises(ValueError, match="sécurité calcul/paiement invalide"):
        PIPELINE.run(context)

    assert context.calls == [
        "field_constraints", "access_control", "public_visibility", "once_per", "restricted_fields", "hidden_fields",
        "categorized_fields", "generated_fields", "timestamp_fields", "numbered_fields", "enumerated_fields",
        "creation_payment_prerequisites", "derived_fields", "aggregated_fields", "calculation_payment_safety",
    ]


def test_pipeline_sarrete_avant_la_structure_si_un_effet_compteur_est_invalide():
    context = FakeContext(fail_counter_effects=True)

    with pytest.raises(ValueError, match="effet compteur invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "counter_effects"


def test_pipeline_sarrete_avant_la_structure_si_le_proprietaire_payable_est_invalide():
    context = FakeContext(fail_payable_owner=True)

    with pytest.raises(ValueError, match="propriétaire payable invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "payable_owner"


def test_pipeline_sarrete_avant_la_structure_si_une_liberation_est_invalide():
    context = FakeContext(fail_release_rules=True)

    with pytest.raises(ValueError, match="règle de libération invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "release_rules"


def test_pipeline_sarrete_avant_la_structure_si_un_workflow_est_invalide():
    context = FakeContext(fail_workflow_collisions=True)

    with pytest.raises(ValueError, match="workflow/collision invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "workflow_collisions"


def test_pipeline_sarrete_avant_la_structure_si_une_configuration_ui_est_invalide():
    context = FakeContext(fail_ui_overrides=True)

    with pytest.raises(ValueError, match="préférence UI invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "ui_overrides"


def test_pipeline_sarrete_avant_la_structure_si_le_landing_est_invalide():
    context = FakeContext(fail_landing=True)

    with pytest.raises(ValueError, match="landing invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "landing"


def test_pipeline_sarrete_avant_la_structure_si_une_capacite_est_invalide():
    context = FakeContext(fail_capabilities=True)

    with pytest.raises(ValueError, match="capacité invalide"):
        PIPELINE.run(context)

    assert context.calls[-1] == "capabilities"


def test_pipeline_sarrete_avant_la_structure_si_un_asset_ou_seed_est_invalide():
    context = FakeContext(fail_assets_seeds=True)

    with pytest.raises(ValueError, match="assets/seeds invalides"):
        PIPELINE.run(context)

    assert context.calls[-1] == "assets_seeds"
