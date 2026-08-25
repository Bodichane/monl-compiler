"""Le journal d'exploitation de la plateforme.

Sans lui, un incident ne laisse rien à lire : la plateforme stocke des
comptes et des clés d'API, et rien ne disait qui s'était connecté, quelle clé
avait servi, ni pourquoi une compilation avait échoué.

**Le journal ne peut PAS écrire un secret.** C'est la décision qui porte ce
module : `evenement()` masque toute valeur dont le NOM annonce un secret, et
toute valeur dont la FORME en est une (une clé `monl_…`, un jeton de forte
entropie). Compter sur la discipline de chaque point d'appel aurait suffi
jusqu'au jour où quelqu'un journalise `mot_de_passe=` par commodité — c'est
la même logique qu'à la frontière d'émission SQL du point 108 : rendre la
faute impossible plutôt que la recommander.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

NOM = "monl.plateforme"
journal = logging.getLogger(NOM)

# Un nom de champ qui annonce un secret. Comparé en minuscules, par sous-chaîne :
# `mot_de_passe`, `password`, `api_key`, `session_token` tombent tous dedans.
NOMS_SENSIBLES = ("password", "mot_de_passe", "secret", "token", "jeton",
                  "key_raw", "cle_brute", "authorization", "cookie")

# Une valeur qui EST un secret, quel que soit le nom du champ. Les clés d'API
# de la plateforme commencent par `monl_` ; les jetons de session sont des
# chaînes URL-safe longues et sans espace.
FORMES_SENSIBLES = re.compile(r"^(monl_[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,})$")

MASQUE = "[masqué]"


def configurer(flux: Any = None) -> logging.Logger:
    """Arme le journal une fois. Rappelable sans effet de bord.

    Le niveau vient de `MONL_LOG_LEVEL` (INFO par défaut). La sortie va sur
    la sortie d'erreur, que Docker, systemd et les hébergeurs collectent tous
    sans configuration — un fichier demanderait une rotation que personne
    n'écrirait.
    """
    journal.setLevel(os.environ.get("MONL_LOG_LEVEL", "INFO").upper())
    if not journal.handlers:
        sortie = logging.StreamHandler(flux or sys.stderr)
        sortie.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
        journal.addHandler(sortie)
    journal.propagate = False
    return journal


def _valeur(nom: str, valeur: Any) -> str:
    if any(motif in nom.lower() for motif in NOMS_SENSIBLES):
        return MASQUE
    texte = str(valeur)
    if FORMES_SENSIBLES.match(texte):
        return MASQUE
    if any(c.isspace() for c in texte):
        return '"' + texte.replace('"', "'").replace("\n", " ") + '"'
    return texte or "-"


def evenement(_nom: str, /, *, niveau: int = logging.INFO, **champs: Any) -> str:
    """Écrit une ligne `nom cle=valeur …` et rend le texte émis.

    Le retour existe pour les tests : ils vérifient ce qui SORT, pas ce que
    l'appelant croit avoir passé.

    Le nom de l'événement est **positionnel uniquement** (`/`). Sans ça, un
    champ appelé `nom=` — le plus naturel de tous en français — entrait en
    collision avec le paramètre et levait un `TypeError` au moment précis où
    l'on veut journaliser. Trouvé par le test, pas par relecture.
    """
    ligne = " ".join([_nom] + [f"{cle}={_valeur(cle, val)}"
                               for cle, val in champs.items() if val is not None])
    journal.log(niveau, ligne)
    return ligne


def anomalie(_nom: str, /, **champs: Any) -> str:
    return evenement(_nom, niveau=logging.WARNING, **champs)


def panne(_nom: str, /, **champs: Any) -> str:
    return evenement(_nom, niveau=logging.ERROR, **champs)
