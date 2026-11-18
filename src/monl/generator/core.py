"""Main generator class: state derived from the AST, and orchestration.

Extracted from the former monolithic module src/generator.py (1307 lines)
when it was split into a package — see docs/design_decisions.md."""
import os

from ..ir import CompilationIR
from ..planning import (
    plan_aggregations,
    plan_counters,
    plan_derivations,
    plan_relations,
    plan_routes,
)
from ..policies import (
    event_counter_fields,
    event_counters_by_entity,
    plan_access_policies,
    plan_entity_models,
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


def _grouper_par_entite(elements, cle=lambda e: e["entity"], valeur=lambda e: e):
    """{entity: [values]} in declaration order — the shape every family of
    marked fields takes. Extracted from `__init__` (complexity ceiling): five
    identical loops, same dictionaries, same insertion order."""
    groupes = {}
    for element in elements:
        groupes.setdefault(cle(element), []).append(valeur(element))
    return groupes

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
        # ADDED (roadmap, multi-project compilation): 'output_dir' lets each
        # spec be compiled into its own folder (--output option of main.py)
        # instead of always overwriting the artifacts at the repository root.
        # By default (None), the historical behavior is kept: everything is
        # written at the repository root.
        #
        # POINT 65: the default is the CURRENT DIRECTORY, no longer a path
        # deduced from the module's location. As long as the code lived in the
        # repository, climbing two levels from src/generator/ landed on the
        # root and seemed to work; once monl is installed (site-packages), the
        # same calculation wrote the application among the Python packages. The
        # current directory is what any command line tool expects, and it
        # matches the old behavior when run from the repository root.
        self.output_dir = os.path.abspath(output_dir or os.getcwd())
        os.makedirs(self.output_dir, exist_ok=True)
        self.ast = normalized_ast
        self.app_name = normalized_ast["meta"]["appName"]
        self.entities = normalized_ast["schema"]["entities"]
        self.relations = normalized_ast["schema"]["relations"]
        self.relation_models = plan_relations(self.relations)
        # Two analyses the emitters query from their loops: computed on first
        # request, then reread. See the methods that fill them (`modele.py`,
        # `proprietaire.py`) for the measurement that made these caches
        # necessary.
        self._fk_placements_caches = None
        self._identity_fk_caches = None
        self.workflows = normalized_ast["security"]["workflows"]
        self.actors = normalized_ast["security"]["actors"]
        # ADDED (beta 3, privilege-escalation fix): only these roles can be
        # chosen by a client at registration ('selfRegister' marker in the
        # spec). The others are provisioned offline through the generated
        # manage.py.
        self.self_register_actors = normalized_ast["security"].get("self_register_actors", [])
        self.custom_functions = normalized_ast["sandbox_ai"]["custom_functions"]
        # ADDED (post-v6, roadmap): map "Entity.Action" -> owning entity, from
        # the 'ownedBy' rules validated by ast_validator.py.
        self.ownership = normalized_ast["security"].get("ownership", {})
        # ADDED (brick 11, point 81): TRANSITIVE ownership — {entity: {"via",
        # "actor"}}. The entity does not belong directly to an actor but to an
        # intermediate record, itself owned by an actor. Consequence for the
        # whole generation: the ownership foreign key is NO LONGER filled from
        # the token, it is supplied by the client then CHECKED, and access
        # control becomes a join.
        self.transitive_ownership = normalized_ast["security"].get("transitive_ownership", {})
        # ADDED (brick 13, point 83): declared assets (folder, logo, favicon),
        # validated at compile time — every named file really exists.
        self.assets = normalized_ast.get("assets") or {}
        # BRICK B1: Upload is distinct from Image. The column only holds an
        # opaque reference; the bytes live in .monl_uploads/ at runtime, never
        # in the compiled artifacts.
        self.upload_fields = normalized_ast["security"].get("upload_fields", [])
        self.upload_fields_by_entity = {}
        for upload in self.upload_fields:
            self.upload_fields_by_entity.setdefault(upload["entity"], []).append(upload)
        # BRICK B2: a single outgoing message per declared creation. The
        # validator has already required an email account identity; this
        # dictionary connects the Create route and the contract to the same
        # rule.
        self.message_rules_by_trigger = {
            rule["trigger_entity"]: dict(rule)
            for rule in normalized_ast["security"].get("message_rules", [])
        }
        # ADDED (roadmap, "two-party access" brick): table {"Entity.Action":
        # [columns]} from the 'accessibleBy' rules validated by
        # ast_validator.py — each column holds the identifier of a user allowed
        # on the record.
        self.access_parties = normalized_ast["security"].get("access_parties", {})
        # ADDED (brick 23, point 106): table {"Entity.Action": [roles]} of the
        # SUPERVISOR roles that pierce the 'accessibleBy' check. A listed role
        # reads/updates/deletes ALL the action's records, with no party
        # restriction — the others stay confined to their columns.
        self.access_supervisors = normalized_ast["security"].get("access_supervisors", {})
        # ADDED (roadmap, portfolio use case): the set of "Entity.Action"
        # marked 'public' — these routes require no authentication. Rebuilt as
        # (entity, action) tuples to be directly comparable with (base_target,
        # act_type) during route generation.
        self.public_actions = {
            tuple(ref.split(".", 1)) for ref in normalized_ast["security"].get("public", [])
        }
        # Conditional visibility BRICK: content marked publicWhen stays
        # filtered by the API, list and detail included.
        self.public_conditions = {
            tuple(ref.split(".", 1)): value
            for ref, value in normalized_ast["security"].get(
                "public_conditions", {}).items()
        }
        # Business uniqueness BRICK: a combination of foreign keys cannot be
        # created twice for the same account and the same target.
        self.once_per_rules = normalized_ast["security"].get("once_per", [])
        # ADDED (roadmap, capability ecosystem -- brick 2): the set of
        # "Entity.field" marked 'hidden' — see _generate_secure_fastapi, where
        # these fields are removed from their entity's read responses (list and
        # detail), whoever calls the route. Grouped by entity (rather than a
        # set of tuples like public_actions) because that is the form directly
        # useful to generation: "which fields to remove for THIS entity".
        self.hidden_fields_by_entity = _grouper_par_entite(
            map(lambda ref: ref.split(".", 1),
                normalized_ast["security"].get("hidden_fields", [])),
            cle=lambda paire: paire[0], valeur=lambda paire: paire[1])
        # ADDED (roadmap, capability ecosystem -- brick 3, generalized into
        # brick 4): 'decrements'/'increments' rules grouped by triggering
        # entity — see _generate_secure_fastapi, where that entity's Create
        # route gains an extra step after the insertion (increment/decrement
        # the targeted field on the linked row, found through the foreign key
        # column the validated relation guarantees to exist).
        self.reputation_rules_by_trigger = plan_counters(
            normalized_ast["security"].get("reputation_rules", []), self.relation_models,
            normalized_ast["security"].get("field_constraints", {}))
        # ADDED (roadmap, capability ecosystem -- brick 5): 'categorized' rules
        # grouped by entity — see _generate_secure_fastapi, where that entity's
        # Read routes (list + detail) replace the targeted numeric field with
        # its category label before returning the response.
        self.categorized_fields_by_entity = _grouper_par_entite(
            normalized_ast["security"].get("categorized_fields", []))
        # ADDED (roadmap, capability ecosystem -- follow-up to brick 1):
        # 'generated' fields grouped by entity -- removed from the Create
        # route's Pydantic schema (the client cannot even try to supply them)
        # and filled from the current account's anonymous pseudonym rather than
        # from the request body.
        self.generated_fields_by_entity = _grouper_par_entite(
            normalized_ast["security"].get("generated_fields", []),
            valeur=lambda gf: gf["field"])
        # ADDED (brick 17, point 90): {Entity: RequiredEntity} — the caller
        # must already own a record of the second to create the first.
        self.required_profiles = dict(
            normalized_ast["security"].get("required_profiles", {}))
        # ADDED (brick 16, point 89): fields timestamped at creation. {Entity:
        # [field]} — the validator guarantees at most ONE per entity, but the
        # list form keeps the same handling as the other families of
        # server-filled fields.
        self.timestamp_fields_by_entity = _grouper_par_entite(
            normalized_ast["security"].get("timestamp_fields", []),
            valeur=lambda tf: tf["field"])
        # BRICK 22 (point 102): {Entity: [{field, format, period}]}. Same
        # family as the timestamp above — filled by the server at creation,
        # absent from request bodies, never rewritten.
        self.numbered_fields_by_entity = _grouper_par_entite(
            normalized_ast["security"].get("numbered_fields", []))
        # ADDED (payment brick, point 74): chargeable entity and the field
        # carrying the amount. {Entity: field} — the validator guarantees at
        # most one payable field per entity.
        self.payable_by_entity = {
            pf["entity"]: pf["field"]
            for pf in normalized_ast["security"].get("payable_fields", [])
        }
        self.postpayment_writable_by_entity = normalized_ast["security"].get(
            "writable_after_payment", {})
        # ADDED (brick 10, point 77): fields CALCULATED BY THE SERVER from a
        # linked row. {Entity: [rule, ...]} — the validator guarantees at most
        # one rule per field, but an entity can carry several.
        #
        # ADDED (brick 12, point 82): 'sumOf' sums. Two indexes, because the
        # brick reads both ways — from the PARENT to remove the field from
        # request bodies, from the CHILD to know what to recompute after each
        # line write.
        aggregations = plan_aggregations(
            normalized_ast["security"].get("aggregated_fields", []), self.relation_models)
        self.aggregated_by_entity = aggregations.by_entity
        self.aggregations_by_source = aggregations.by_source
        self.derived_by_entity = plan_derivations(
            normalized_ast["security"].get("derived_fields", []), self.relation_models)
        # POINT 85: 'required'/'unique'/'min'/'max' produced NOTHING — the
        # output was byte-identical with or without them. Grouped by entity:
        # the bounds go into the Pydantic schema (schemas.py), 'unique' becomes
        # a unique index (sql_schema.py).
        self.field_constraints = {}
        for (entite, champ), contraintes in normalized_ast["security"].get(
                "field_constraints", {}).items():
            self.field_constraints.setdefault(entite, {})[champ] = contraintes
        # ADDED (roadmap, visual rendering control): explicit per-entity
        # overrides of theme/order/main field, from the 'ui' blocks.
        self.ui_overrides = normalized_ast.get("ui", {})
        # ADDED (roadmap, capability ecosystem -- brick 1): capabilities
        # declared through 'capability'. Purely informative at this stage --
        # nothing in generate_all() hooks into it yet, since authentication
        # (the only known capability so far) is already generated
        # systematically regardless. Future capabilities (field masking,
        # two-party access) will be the first to really change generation
        # behavior according to what is declared here.
        self.capabilities = normalized_ast.get("capabilities", [])
        # POINT 95: brick 1 wakes up. 'capability auth' had always been
        # declarative — it now constrains the FORM of the account identifier.
        # None = nothing declared = historical behavior intact.
        self.auth_identifier = (normalized_ast.get("security", {})
                                .get("auth_identifier"))
        # Declared calling code: without it, '06…' and '+336…' stay two
        # accounts.
        self.auth_phone_prefix = (normalized_ast.get("security", {})
                                .get("auth_phone_prefix"))
        # BRICK B4: no runtime branch is emitted when this dictionary is empty;
        # that is the byte-for-byte guarantee for historical specs.
        self.auth_features = dict(normalized_ast.get("security", {})
                                   .get("auth_features") or {})
        # BRICK 2a: the charging currency, ALREADY resolved into {code,
        # exponent} by the validator. None when nothing is declared — the
        # default is applied only where the charge happens.
        self.payment_currency = (normalized_ast.get("security", {})
                                 .get("payment_currency"))
        # BRICK 2b: 'stripe' or 'fedapay', resolved by the validator. None when
        # nothing is declared — the default is applied only where the charge
        # happens, as for the currency.
        self.payment_provider = (normalized_ast.get("security", {})
                                 .get("payment_provider"))
        # BRICK 19 (point 96): {Entity: {field: [values]}} — a status is one
        # state among a few, not free text.
        self.enumerated_fields = (normalized_ast.get("security", {})
                                  .get("enumerated_fields") or {})
        # BRICK B3: compile-time whitelists for list parameters. The routes and
        # the contract read the same analysis, so that a field announced as
        # filterable/sortable is exactly the one the backend accepts.
        self.filterable_fields_by_entity = {}
        for item in normalized_ast["security"].get("filterable_fields", []):
            self.filterable_fields_by_entity.setdefault(item["entity"], []).append(item["field"])
        self.sortable_fields_by_entity = {}
        for item in normalized_ast["security"].get("sortable_fields", []):
            self.sortable_fields_by_entity.setdefault(item["entity"], []).append(item["field"])
        # BRICK 20 (point 98): {Entity: [rule]} — reaching a value gives back
        # what the children counted down. Indexed by the entity CARRYING the
        # field, which is the one whose Update route triggers the release.
        self.release_rules_by_entity = {}
        for regle in (normalized_ast.get("security", {}).get("release_rules") or []):
            self.release_rules_by_entity.setdefault(regle["entity"], []).append(regle)
        # ADDED (frontend roadmap, 'seed' block): demo data to insert at
        # startup if the tables are empty (see init_db).
        self.seeds = normalized_ast.get("seeds", [])
        self.migrations = normalized_ast.get("migrations", [])
        # Typed view shared by the consumers of field semantics. The historical
        # dictionaries stay available during the migration of the SQL and API
        # emitters.
        self.event_counters = event_counter_fields(normalized_ast["security"])
        # Point 202: creation initializes these counters to 0, per entity.
        self.event_counters_by_entity = event_counters_by_entity(normalized_ast["security"])
        self.entity_models = plan_entity_models(
            self.entities, normalized_ast["security"], self.derived_by_entity,
            self.aggregated_by_entity)
        # Route map computed before the policies that depend on it.
        self.route_plans = plan_routes(self.workflows)
        self.access_policies = plan_access_policies(normalized_ast["security"], self.route_plans)
        self.effect_plans = self._build_effect_plans()
        # The plan catalog becomes this instance's canonical analysis. The old
        # attributes stay exposed to the mixins during the migration, but
        # modern consumers now reuse this object.
        self.compilation_plans = self.build_compilation_plans()
        # Composed facade: the mixins stay the historical implementation, but
        # the orchestrator no longer picks each layer individually.
        self.emitters = BackendEmitter(self)
