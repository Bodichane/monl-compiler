"""Socle runtime de l'application générée : imports, secret JWT,
init_db/migrations/seed, inscription, connexion, révocation de jeton,
limitation de débit.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


from .runtime_annexes import AnnexesRuntimeMixin
from .runtime_connexion import ConnexionRuntimeMixin
from .runtime_fonctions_auth import FonctionsAuthRuntimeMixin
from .runtime_jetons import JetonsRuntimeMixin
from .runtime_migrations import MigrationsRuntimeMixin
from .runtime_montage import MontageRuntimeMixin
from .runtime_pool import PoolRuntimeMixin
from .runtime_preparation import PreparationRuntimeMixin
from .runtime_socle import SocleRuntimeMixin


class RuntimeMixin(
    SocleRuntimeMixin,
    PoolRuntimeMixin,
    JetonsRuntimeMixin,
    MontageRuntimeMixin,
    ConnexionRuntimeMixin,
    MigrationsRuntimeMixin,
    PreparationRuntimeMixin,
    FonctionsAuthRuntimeMixin,
    AnnexesRuntimeMixin,
):
    """Le socle du app.py généré, par famille.

    Les deux méthodes qui restent ici sont celles qui ORCHESTRENT :
    `_generate_runtime_lines` assemble les trois étages dans l'ordre, et
    `_cors_methods` est lue par plusieurs d'entre eux. Tout le reste vit
    dans le module de sa famille."""

    def _cors_methods(self):
        """Méthodes réellement émises par l'application générée."""
        methods = {"GET", "POST"}  # racine, santé et authentification
        action_methods = {
            "Read": "GET",
            "Create": "POST",
            "Update": "PUT",
            "Delete": "DELETE",
            "Execute": "POST",
        }
        for plan in self._compute_route_map().values():
            method = action_methods.get(plan.action)
            if method:
                methods.add(method)
        if self.payable_by_entity:
            methods.add("POST")
        if self.postpayment_writable_by_entity:
            methods.add("PUT")
        return [method for method in ("GET", "POST", "PUT", "DELETE")
                if method in methods]

    def _generate_runtime_lines(self):
        """Lignes de app.py jusqu'aux schémas Pydantic (incluses)."""
        api_lines, totp_migration_lines = self._socle_et_schemas()
        # POINT 116 : identité FACULTATIVE, et elle n'existe que pour les
        # lectures publiques conditionnées ('publicWhen'). Une route publique
        # ne doit JAMAIS répondre 401 : un jeton absent, invalide ou révoqué
        # laisse simplement l'appelant anonyme. Cette dépendance ne peut donc
        # que DONNER des droits (superviseur, propriétaire), jamais en retirer
        # — c'est ce qui la rend sûre sur une route ouverte à tous. Émise
        # seulement si une EXEMPTION existe (`_condition_exemptions`, source
        # unique) : sans superviseur ni propriétaire, aucune route ne l'appelle
        # et l'app.py produit reste celui d'avant le point 116.
        api_lines = self._socle_base_et_uploads(api_lines, totp_migration_lines)

        # ── POINT 95 : la forme de l'identifiant de compte ──────────────
        # Le champ reste nommé 'username' SUR LE FIL. Le renommer en 'email'
        # aurait cassé le formulaire d'inscription de tout projet existant,
        # pour un gain cosmétique ; c'est le CONTRAT qui dit désormais quelle
        # forme il attend, et l'IA d'interface qui étiquette le champ.
        #
        # LA substance de la brique n'est pas la validation, c'est la
        # NORMALISATION. 'Jean@Ex.com' et 'jean@ex.com' sont la même boîte,
        # '06 12 34 56 78' et '+33612345678' le même numéro : sans forme
        # canonique, le contrôle d'unicité est contournable (deux comptes pour
        # une personne) et la connexion échoue selon la façon dont on tape.
        api_lines += self._generate_identifier_helpers()
        api_lines += self._generate_message_runtime_lines()
        api_lines += self._generate_auth_feature_helpers()

        api_lines = self._socle_authentification(api_lines)
        return api_lines
