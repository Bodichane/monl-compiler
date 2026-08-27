"""La voie unique vers l'IA : le brief, et l'ampleur qu'il annonce."""

import json
import os

from ..frontend_contract import PROMPT_FILENAME
from . import fondations, fournisseurs, reponse


# ------------------------------------------------------------ orchestration --
def brief_evolution(update_mode, retouche_mode):
    """Nom du brief d'ÉVOLUTION à donner à l'IA, ou None pour une construction
    neuve (point 93).

    Les deux modes d'évolution ne diffèrent QUE par l'origine du brief : un
    delta de spec pour `monl update`, une phrase humaine pour `monl retouche`.
    Tout le reste — joindre les fichiers actuels, rappeler le contrat,
    re-vérifier, empreindre — leur est commun, et le rester est le but : une
    seconde voie vers l'IA qui aurait ses propres garde-fous serait une voie
    par laquelle les contourner."""
    if retouche_mode:
        return fondations.RETOUCHE_PROMPT_FILENAME
    if update_mode:
        return fondations.UPDATE_PROMPT_FILENAME
    return None

def build_generation_prompt(project_dir, update_mode, retouche_mode=False):
    from ..cli import _erreur_de_chemin

    souci = _erreur_de_chemin(project_dir, fichier_requis=PROMPT_FILENAME)
    if souci:
        raise fondations.FrontendAIError(souci.replace(" ❌ ", "", 1).strip())
    with open(os.path.join(project_dir, PROMPT_FILENAME), encoding="utf-8") as fh:
        base_prompt = fh.read() + reponse._project_guidance(project_dir)
    brief = brief_evolution(update_mode, retouche_mode)
    if brief is None:
        return base_prompt + fournisseurs.RESPONSE_FORMAT_INSTRUCTIONS

    brief_path = os.path.join(project_dir, brief)
    if not os.path.exists(brief_path):
        origine = ("'monl retouche' n'a pas écrit sa consigne"
                   if retouche_mode else "lancer d'abord 'monl update'")
        raise fondations.FrontendAIError(f"{brief} est absent — {origine}.")
    with open(brief_path, encoding="utf-8") as fh:
        delta = fh.read()
    existing = reponse._read_existing_frontend(project_dir)
    files_block = "\n\n".join(
        f"### frontend/{p}\n```\n{c}\n```" for p, c in sorted(existing.items()))
    return (f"{delta}\n\n## Fichiers actuels du frontend (à faire évoluer, "
            f"pas à réécrire de zéro)\n{files_block}\n\n## Rappel du contrat "
            f"d'origine\n{base_prompt}{fournisseurs.RESPONSE_FORMAT_INSTRUCTIONS}")

def ampleur_du_contrat(project_dir):
    """Ce que le frontend doit couvrir : nombre de routes et d'entités.

    Sert à DIMENSIONNER la demande faite au modèle. Sans elle, monl réclamait
    « environ 1 500 tokens » pour `app.js` quel que soit le contrat — et le
    modèle obéissait au jeton près (1 698 mesurés sur une boutique à quinze
    routes) avant d'être refusé pour incomplétude. On demandait l'impossible,
    puis on le rejetait.
    """
    chemin = os.path.join(project_dir, "frontend_contract.json")
    try:
        with open(chemin, encoding="utf-8") as fh:
            contrat = json.load(fh)
    except (OSError, ValueError):
        return None
    routes = contrat.get("routes")
    if not isinstance(routes, list) or not routes:
        return None
    return {"routes": len(routes),
            "entites": len(contrat.get("entities") or {})}
