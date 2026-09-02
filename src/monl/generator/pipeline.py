"""L'enchaînement d'une compilation, et la carte des routes qu'elle produit.

`_compute_route_map` est la SOURCE UNIQUE du regroupement des routes,
partagée entre la génération FastAPI et le contrat frontend
(`frontend_contract.py`) — ne pas dupliquer cette logique ailleurs."""

import os
import secrets

from ..artifacts import copy_preserved_files, publish_files, sans_sandbox, staging_directory
from ..ir import CompilationPlans, RoutePlan

# Colonnes de suivi ajoutées par la brique 'payable' (point 74). Jamais
# fournies par le client, toujours présentes dans les réponses de lecture.
# Source unique de vérité : ces deux noms étaient écrits en dur dans quatre
# couches (schéma SQL, liste de colonnes, routes, et — depuis le point 76 —
# le contrat frontend). Quatre copies d'un nom de colonne, c'est quatre
# occasions de le faire dériver.
BACKEND_ARTIFACTS = ("app.py", "schema.sql", "sandbox_ai.py", "manage.py",
                     ".jwt_secret")




class PipelineMixin:
    """L'enchaînement d'une compilation, et la carte des routes qu'elle produit."""

    def generate_all(self):
        """Déclenche la génération déterministe du BACKEND et les coquilles
        vides des blocs 'custom' (à compléter à la main). PIVOT (point 41 de
        docs/design_decisions.md) : monl ne génère plus AUCUN frontend
        (landing, dashboard, archétypes — tous retirés). L'interface est
        déléguée à une IA spécialisée via le contrat frontend
        (frontend_contract.json + FRONTEND_PROMPT.md, voir
        src/frontend_contract.py) ; '/docs' (Swagger) reste le seul front
        fourni, gratuitement, par FastAPI."""
        print(f"🏗️  Génération du socle déterministe réel pour '{self.app_name}'...")
        if self.capabilities:
            print(f"🧩 Capacités déclarées : {', '.join(self.capabilities)} (voir docs/design_decisions.md point 24).")

        sources = self.emitters.render()
        sql_content = sources.schema
        api_content = sources.app
        sandbox_content = sources.sandbox
        manage_content = sources.manage

        # Détermination des chemins physiques dans un staging voisin. La
        # publication ne touche au projet courant qu'après la génération
        # complète des cinq artefacts backend.
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
                # Le secret est généré une fois par projet, conservé entre
                # compilations et toujours publié avec le mode propriétaire seul.
                if not os.path.exists(secret_path):
                    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(secrets.token_hex(32))
                    print("🔑 Nouveau secret JWT généré dans '.jwt_secret' (32 octets, permissions 0600).")
                else:
                    try:
                        os.chmod(secret_path, 0o600)
                    except OSError:
                        pass
                    print("🔑 Secret JWT existant conservé ('.jwt_secret', permissions 0600).")

                with open(sql_path, "w", encoding="utf-8") as f: f.write(sql_content)
                with open(api_path, "w", encoding="utf-8") as f: f.write(api_content)
                if self.custom_functions:
                    with open(sandbox_path, "w", encoding="utf-8") as f: f.write(sandbox_content)
                with open(manage_path, "w", encoding="utf-8") as f: f.write(manage_content)
            finally:
                self.output_dir = target_dir
            # `publish_files` exige que tout nom listé EXISTE : la condition
            # doit donc porter sur la liste, pas seulement sur l'écriture.
            publie = (BACKEND_ARTIFACTS if self.custom_functions
                      else sans_sandbox(BACKEND_ARTIFACTS))
            publish_files(temporary, target_dir, publie)

        produits = "'schema.sql', 'app.py' et 'manage.py'"
        if self.custom_functions:
            produits = "'schema.sql', 'app.py', 'sandbox_ai.py' et 'manage.py'"
        print(f"💾 Socle généré : {produits} sont prêts !")
        if not self.self_register_actors:
            print("🔒 Aucun rôle en inscription libre : créez le premier compte avec "
                  "'python3 manage.py adduser <utilisateur> <role>'.")

    def build_compilation_plans(self) -> CompilationPlans:
        """Expose les analyses communes aux émetteurs backend et frontend."""
        if hasattr(self, "compilation_plans"):
            return self.compilation_plans
        placements = self._compute_fk_placements()
        identity = self._identity_fk_columns()
        return CompilationPlans(
            route_map=self._compute_route_map(),
            foreign_key_placements={
                entity: tuple(dict(placement) for placement in values)
                for entity, values in placements.items()
            },
            identity_foreign_keys={
                entity: frozenset(columns)
                for entity, columns in identity.items()
            },
            client_foreign_keys={
                entity: tuple(self._client_fk_columns(entity))
                for entity in self.entities
            },
            incoming_relations={
                entity: (dict(relation) if relation else None)
                for entity in self.entities
                for relation in [self._get_incoming_relation(entity)]
            },
            payment_locked_parents={
                entity: tuple(dict(lock) for lock in self._payment_locked_parents(entity))
                for entity in self.entities
            },
            reputation_rules_by_trigger={
                entity: tuple(dict(rule) for rule in rules)
                for entity, rules in self.reputation_rules_by_trigger.items()
            },
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
            release_rules_by_entity={
                entity: tuple(dict(rule) for rule in rules)
                for entity, rules in self.release_rules_by_entity.items()
            },
            transitive_ownership=self.transitive_ownership,
            postpayment_writable_by_entity=self.postpayment_writable_by_entity,
            assets=self.assets,
            once_per_rules=tuple(dict(rule) for rule in self.once_per_rules),
            upload_fields=tuple(dict(field) for field in self.upload_fields),
            message_rules_by_trigger={
                entity: dict(rule)
                for entity, rule in self.message_rules_by_trigger.items()
            },
            filterable_fields={
                entity: tuple(fields)
                for entity, fields in self.filterable_fields_by_entity.items()
            },
            sortable_fields={
                entity: tuple(fields)
                for entity, fields in self.sortable_fields_by_entity.items()
            },
        )

    def _generate_secure_fastapi(self):
        """Assemble app.py à partir des trois couches générées séparément :
        socle runtime (auth, DB, migrations), schémas d'entrée, routes."""
        api_lines = self._generate_runtime_lines()
        api_lines += self._generate_schema_lines()
        api_lines += self._generate_route_lines()
        return "\n".join(api_lines)

    def _compute_route_map(self) -> dict[tuple[str, str], RoutePlan]:
        """Regroupe les actions par (type, cible) avec la liste des acteurs
        autorisés et le 'tag' (nom du premier workflow qui déclare l'action)
        -- extrait de _generate_secure_fastapi pour être réutilisé aussi par
        _compute_actor_capabilities (le tableau de bord post-connexion a
        besoin du même 'tag' que la vraie route pour appeler les fonctions
        'custom' au bon endroit). Une seule source de vérité : si cette
        logique de regroupement change un jour, les deux consommateurs
        restent forcément synchronisés."""
        if hasattr(self, "route_plans"):
            return self.route_plans
        route_map: dict[tuple[str, str], RoutePlan] = {}
        for wf in self.workflows:
            wf_name = wf["name"]
            required_actor = wf["actor"]
            for action in wf["actions"]:
                act_type = action["type"]
                target = action["target"]
                base_target = target.split(".")[0] if "." in target else target
                route_key = (act_type, base_target if act_type != "Execute" else target)
                if route_key not in route_map:
                    route_map[route_key] = RoutePlan(
                        action=act_type,
                        key=route_key[1],
                        target=target,
                        base_target=base_target,
                        actors=set(),
                        tags=[],
                    )
                route_map[route_key].allow(required_actor, wf_name)
        return route_map
