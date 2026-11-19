"""The routes of the generated backend, recomposed by family.

This module no longer contains ANY generation: each route family lives in
its own `routes_*.py`, and `RoutesMixin` recomposes them. A new route is
added in its family's module, never here.

All access-control SQL goes through the typed emission layer `sql`
(point 108): a value can enter it only as a bound parameter, never pasted
into the text. See generator/sql.py — the family modules each import it on
their own."""

from .routes_acces import AccesRoutesMixin
from .routes_creation import CreationRoutesMixin
from .routes_creation_transaction import CreationTransactionRoutesMixin
from .routes_lecture import LectureRoutesMixin
from .routes_lecture_filtree import LectureFiltreeRoutesMixin
from .routes_modification import ModificationRoutesMixin
from .routes_orchestration import OrchestrationRoutesMixin
from .routes_paiement import PaiementRoutesMixin
from .routes_prestataires import PrestatairesRoutesMixin
from .routes_suppression import SuppressionRoutesMixin
from .routes_uploads import UploadsRoutesMixin


class RoutesMixin(
    OrchestrationRoutesMixin,
    AccesRoutesMixin,
    UploadsRoutesMixin,
    CreationRoutesMixin,
    CreationTransactionRoutesMixin,
    LectureRoutesMixin,
    LectureFiltreeRoutesMixin,
    ModificationRoutesMixin,
    SuppressionRoutesMixin,
    PaiementRoutesMixin,
    PrestatairesRoutesMixin,
):
    """All the routes of the generated backend, by family.

    A new route is added in its family's module, never here. `RoutesMixin`
    remains the name composed by `core.py`."""
