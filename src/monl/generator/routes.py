"""Les routes du backend généré, recomposées par famille.

Ce module ne contient plus AUCUNE génération : chaque famille de routes vit
dans son propre `routes_*.py`, et `RoutesMixin` les recompose. Une route
nouvelle s'ajoute dans le module de sa famille, jamais ici.

Tout le SQL de contrôle d'accès passe par la couche d'émission typée `sql`
(point 108) : une valeur ne peut y entrer que liée en paramètre, jamais collée
dans le texte. Voir generator/sql.py — les modules de famille l'importent
chacun pour leur propre compte.
"""

from .routes_acces import AccesRoutesMixin
from .routes_creation import CreationRoutesMixin
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
    LectureRoutesMixin,
    LectureFiltreeRoutesMixin,
    ModificationRoutesMixin,
    SuppressionRoutesMixin,
    PaiementRoutesMixin,
    PrestatairesRoutesMixin,
):
    """Toutes les routes du backend généré, par famille.

    Une route nouvelle s'ajoute dans le module de sa famille, jamais
    ici. `RoutesMixin` reste le nom composé par `core.py`."""
