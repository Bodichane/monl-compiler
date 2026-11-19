"""Runtime foundation of the generated application: imports, JWT secret,
init_db/migrations/seed, registration, login, token revocation, rate
limiting.

Extracted from the former monolithic module src/generator.py (1307 lines)
when it was split into a package — see docs/design_decisions.md."""


from .runtime_auth_functions import FunctionsAuthRuntimeMixin
from .runtime_base import BaseRuntimeMixin
from .runtime_extras import AnnexesRuntimeMixin
from .runtime_login import LoginRuntimeMixin
from .runtime_migrations import MigrationsRuntimeMixin
from .runtime_mounting import MontageRuntimeMixin
from .runtime_pool import PoolRuntimeMixin
from .runtime_preparation import PreparationRuntimeMixin
from .runtime_tokens import TokensRuntimeMixin
from .runtime_verification import VerificationRuntimeMixin


class RuntimeMixin(
    BaseRuntimeMixin,
    VerificationRuntimeMixin,
    PoolRuntimeMixin,
    TokensRuntimeMixin,
    MontageRuntimeMixin,
    LoginRuntimeMixin,
    MigrationsRuntimeMixin,
    PreparationRuntimeMixin,
    FunctionsAuthRuntimeMixin,
    AnnexesRuntimeMixin,
):
    """The foundation of the generated app.py, by family.

    The two methods left here are the ones that ORCHESTRATE:
    `_generate_runtime_lines` assembles the three stages in order, and
    `_cors_methods` is read by several of them. Everything else lives in its
    family's module."""

    def _cors_methods(self):
        """Methods actually emitted by the generated application."""
        methods = {"GET", "POST"}  # root, health and authentication
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
        """Lines of app.py up to the Pydantic schemas (included)."""
        api_lines = self._base_and_schemas()
        # POINT 116: OPTIONAL identity, and it exists only for conditional
        # public reads ('publicWhen'). A public route must NEVER answer 401: a
        # missing, invalid or revoked token simply leaves the caller anonymous.
        # This dependency can therefore only GRANT permissions (supervisor,
        # owner), never remove any — that is what makes it safe on a route open
        # to everyone. Emitted only if an EXEMPTION exists
        # (`_condition_exemptions`, single source): with neither supervisor nor
        # owner, no route calls it and the produced app.py stays the one from
        # before point 116.
        api_lines = self._base_base_and_uploads(api_lines)

        # ── POINT 95: the form of the account identifier ──
        # The field stays named 'username' ON THE WIRE. Renaming it to 'email'
        # would have broken the registration form of every existing project for
        # a cosmetic gain; it is the CONTRACT that now says which form it
        # expects, and the interface AI that labels the field.
        #
        # THE substance of the brick is not validation, it is NORMALIZATION.
        # 'Jean@Ex.com' and 'jean@ex.com' are the same mailbox, '06 12 34 56
        # 78' and '+33612345678' the same number: without a canonical form, the
        # uniqueness check can be bypassed (two accounts for one person) and
        # login fails depending on how it is typed.
        api_lines += self._generate_identifier_helpers()
        api_lines += self._generate_message_runtime_lines()
        api_lines += self._generate_auth_feature_helpers()

        api_lines = self._base_authentication(api_lines)
        return api_lines
