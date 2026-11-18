"""The sequence of a compilation, and the route map it produces.

Routes are analyzed by `planning`, then shared between FastAPI generation
and the frontend contract with no recomputation in the emitters."""

import os
import secrets

from ..artifacts import copy_preserved_files, publish_files, sans_sandbox, staging_directory
from ..ir import CompilationPlans, RoutePlan

# Tracking columns added by the 'payable' brick (point 74). Never supplied
# by the client, always present in read responses. Single source of truth:
# these two names were hard-coded in four layers (SQL schema, column list,
# routes, and — since point 76 — the frontend contract). Four copies of a
# column name are four chances for it to drift.
BACKEND_ARTIFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py",
                     ".jwt_secret")




class PipelineMixin:
    """The sequence of a compilation, and the route map it produces."""

    def generate_all(self):
        """Runs the deterministic generation of the BACKEND and the empty shells of
        the 'custom' blocks (to complete by hand). PIVOT (point 41 of
        docs/design_decisions.md): monl no longer generates ANY frontend (landing,
        dashboard, archetypes — all removed). The interface is delegated to a
        specialized AI through the frontend contract (frontend_contract.json +
        FRONTEND_PROMPT.md, see src/frontend_contract.py); '/docs' (Swagger) stays
        the only front end provided, for free, by FastAPI."""
        print(f"🏗️  Generating the deterministic foundation for '{self.app_name}'...")
        if self.capabilities:
            print(f"🧩 Declared capabilities: {', '.join(self.capabilities)} (see docs/design_decisions.md point 24).")

        sources = self.emitters.render()
        sql_content = sources.schema
        api_content = sources.app
        sandbox_content = sources.sandbox
        manage_content = sources.manage

        # Physical paths are resolved in a neighboring staging directory.
        # Publishing touches the current project only after the five backend
        # artifacts have been fully generated.
        target_dir = self.output_dir
        with staging_directory(target_dir) as temporary:
            copy_preserved_files(target_dir, temporary, (".jwt_secret",))
            self.output_dir = os.path.abspath(temporary)
            base_dir = self.output_dir
            sql_path = os.path.join(base_dir, "schema.sql")
            api_path = os.path.join(base_dir, "app.py")
            sandbox_path = os.path.join(base_dir, "sandbox_ai.py")
            manage_path = os.path.join(base_dir, "manage.py")
            secret_path = os.path.join(base_dir, ".jwt_secret")

            try:
                # The secret is generated once per project, kept across
                # compilations and
                # always published with owner-only permissions.
                if not os.path.exists(secret_path):
                    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(secrets.token_hex(32))
                    print("🔑 New JWT secret generated in '.jwt_secret' (32 bytes, permissions 0600).")
                else:
                    try:
                        os.chmod(secret_path, 0o600)
                    except OSError:
                        pass
                    print("🔑 Existing JWT secret kept ('.jwt_secret', permissions 0600).")

                with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
                with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
                if self.custom_functions:
                    with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)
                with open(manage_path, "w", encoding="utf-8") as f: f.write(manage_content)
            finally:
                self.output_dir = target_dir
            # `publish_files` requires every listed name to EXIST: the
            # condition must therefore apply to the list, not only to the
            # write.
            publie = (BACKEND_ARTIFACTS if self.custom_functions
                      else sans_sandbox(BACKEND_ARTIFACTS))
            publish_files(temporary, target_dir, publie)

        produits = "'schema.sql', 'app.py' and 'manage.py'"
        if self.custom_functions:
            produits = "'schema.sql', 'app.py', 'sandbox_ai.py' and 'manage.py'"
        print(f"💾 Foundation generated: {produits} are ready!")
        if not self.self_register_actors:
            print("🔒 No self-registration role: create the first account with "
                  "'python3 manage.py adduser <user> <role>'.")

    def build_compilation_plans(self) -> CompilationPlans:
        """Exposes the analyses shared by the backend and frontend emitters."""
        if hasattr(self, "compilation_plans"):
            return self.compilation_plans
        placements = self._compute_fk_placements()
        identity = self._identity_fk_columns()
        return CompilationPlans(
            route_map=self._compute_route_map(),
            foreign_key_placements={
                entity: tuple(placement.copy() for placement in values)
                for entity, values in placements.items()
            },
            identity_foreign_keys={
                entity: frozenset(columns)
                for entity, columns in identity.items()
            },
            **self._plans_par_entite(),
            **self._tables_recopiees(),
            reputation_rules_by_trigger=self.reputation_rules_by_trigger,
            entity_models=self.entity_models,
            access_policies=self.access_policies,
            actors=tuple(self.actors),
            self_register_actors=tuple(self.self_register_actors),
            auth_identifier=tuple(self.auth_identifier) if self.auth_identifier else None,
            auth_phone_prefix=self.auth_phone_prefix,
            auth_features=self.auth_features,
            payment_currency=self.payment_currency,
            payment_provider=self.payment_provider,
            public_conditions=self.public_conditions,
            required_profiles=self.required_profiles,
            payable_by_entity=self.payable_by_entity,
            transitive_ownership=self.transitive_ownership,
            postpayment_writable_by_entity=self.postpayment_writable_by_entity,
            assets=self.assets,
            once_per_rules=tuple(dict(rule) for rule in self.once_per_rules),
            upload_fields=tuple(dict(field) for field in self.upload_fields),
        )

    # The next two methods are extracted from `build_compilation_plans`
    # (complexity ceiling): same keys, same values, same copies.
    def _plans_par_entite(self):
        """The analyses computed entity by entity."""
        return {
            "client_foreign_keys": {
                entity: tuple(self._client_fk_columns(entity))
                for entity in self.entities
            },
            "incoming_relations": {
                entity: (dict(relation) if relation else None)
                for entity in self.entities
                for relation in [self._get_incoming_relation(entity)]
            },
            "payment_locked_parents": {
                entity: tuple(dict(lock) for lock in self._payment_locked_parents(entity))
                for entity in self.entities
            },
        }

    def _tables_recopiees(self):
        """The IR tables copied so that the plan shares nothing mutable with it."""
        return {
            "release_rules_by_entity": {
                entity: tuple(dict(rule) for rule in rules)
                for entity, rules in self.release_rules_by_entity.items()
            },
            "message_rules_by_trigger": {
                entity: dict(rule)
                for entity, rule in self.message_rules_by_trigger.items()
            },
            "filterable_fields": {
                entity: tuple(fields)
                for entity, fields in self.filterable_fields_by_entity.items()
            },
            "sortable_fields": {
                entity: tuple(fields)
                for entity, fields in self.sortable_fields_by_entity.items()
            },
        }

    def _generate_secure_fastapi(self):
        """Assembles app.py from the three separately generated layers: runtime
        foundation (auth, DB, migrations), input schemas, routes."""
        api_lines = self._generate_runtime_lines()
        api_lines += self._generate_schema_lines()
        api_lines += self._generate_route_lines()
        return "\n".join(api_lines)

    def _compute_route_map(self) -> dict[tuple[str, str], RoutePlan]:
        """Compatible access to the plan analyzed once before the emitters."""
        return self.route_plans
