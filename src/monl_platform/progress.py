"""Étapes RÉELLES d'une construction, pour le suivi en direct de la console.

Un suivi qui invente sa progression est pire qu'un suivi absent : il fait
croire que le serveur sait où il en est. Les étapes lues ici viennent du
journal de consommation que la couche IA écrit au fur et à mesure
(``.monl_ai_usage.jsonl``) — une ligne par appel effectivement rendu, avec sa
durée et ses jetons. Rien n'est extrapolé.

Le rattachement se fait par HORODATAGE et non par ``run_id`` : l'identifiant
d'exécution n'est enregistré sur la construction qu'à sa FIN, or c'est
justement pendant qu'elle tourne qu'on veut la suivre.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from monl.usage import USAGE_FILENAME

#: Les fichiers que la génération par morceaux produit toujours, dans cet
#: ordre. Ils servent à annoncer ce qui RESTE à faire ; monl les déclare, la
#: console ne les devine pas.
PLANNED_STAGES = ("index.html", "styles.css", "app.js")


def _moment(value):
    if not value or not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _event_kind(stage: str) -> str:
    if stage == "image":
        return "image"
    return "fichier" if "." in stage else "etape"


def read_stages(project_dir, started_at, finished_at=None) -> list[dict]:
    """Étapes journalisées entre le début et la fin d'une construction.

    ``finished_at`` absent signifie « encore en cours » : on prend tout ce qui
    a été écrit depuis le début. Un journal absent rend une liste vide — un
    projet peut très bien n'avoir jamais appelé d'IA.
    """
    debut = _moment(started_at)
    if debut is None:
        return []
    fin = _moment(finished_at)
    journal = Path(project_dir) / USAGE_FILENAME
    if not journal.is_file():
        return []

    etapes = []
    with journal.open("r", encoding="utf-8") as flux:
        for ligne in flux:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                evenement = json.loads(ligne)
            except json.JSONDecodeError:
                # Une ligne tronquée est une écriture en cours, pas une erreur.
                continue
            moment = _moment(evenement.get("timestamp"))
            if moment is None or moment < debut:
                continue
            if fin is not None and moment > fin:
                continue
            nom = str(evenement.get("stage") or "construction")
            etapes.append({
                "name": nom,
                "kind": _event_kind(nom),
                "model": evenement.get("model"),
                "seconds": evenement.get("duration_seconds"),
                "input_tokens": evenement.get("input_tokens"),
                "output_tokens": evenement.get("output_tokens"),
                "retry": evenement.get("retry"),
                "at": evenement.get("timestamp"),
            })
    return etapes


def planned_remaining(etapes) -> list[str]:
    """Fichiers annoncés que le journal n'a pas encore vus passer."""
    vus = {etape["name"] for etape in etapes}
    return [nom for nom in PLANNED_STAGES if nom not in vus]
