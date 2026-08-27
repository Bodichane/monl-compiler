"""Le pilote de validation : l'ORDRE dans lequel les refus s'appliquent.

Chaque passe nomme la méthode du validateur qu'elle déclenche. C'est
cette antériorité qui a rendu le découpage du validateur évident au
point 152 : les frontières existaient déjà, écrites ici.

La surface publique n'a pas bougé en devenant un paquet."""

from .contrats import ValidationPipeline
from .defaut import DEFAULT_VALIDATION_PIPELINE

__all__ = [
    "DEFAULT_VALIDATION_PIPELINE",
    "ValidationPipeline",
]
