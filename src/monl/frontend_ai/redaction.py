"""The single path to the AI: the brief, and the scope it announces."""

import json
import os

from ..frontend_contract import PROMPT_FILENAME
from . import fondations, fournisseurs, reponse


# ------------------------------------------------------------ orchestration --
def brief_evolution(update_mode, retouche_mode):
    """Name of the EVOLUTION brief to give the AI, or None for a new build
    (point 93).

    The two evolution modes differ ONLY in the origin of the brief: a spec
    delta for `monl update`, a human sentence for `monl retouche`. Everything
    else — attaching the current files, recalling the contract, re-checking,
    fingerprinting — is shared, and keeping it so is the goal: a second path
    to the AI with its own safeguards would be a path to bypass them."""
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
        origine = ("'monl retouche' did not write its instruction"
                   if retouche_mode else "run 'monl update' first")
        raise fondations.FrontendAIError(f"{brief} is missing — {origine}.")
    with open(brief_path, encoding="utf-8") as fh:
        delta = fh.read()
    existing = reponse._read_existing_frontend(project_dir)
    files_block = "\n\n".join(
        f"### frontend/{p}\n```\n{c}\n```" for p, c in sorted(existing.items()))
    return (f"{delta}\n\n## Current frontend files (to evolve, "
            f"not to rewrite from scratch)\n{files_block}\n\n## Reminder of the "
            f"original contract\n{base_prompt}{fournisseurs.RESPONSE_FORMAT_INSTRUCTIONS}")

def ampleur_du_contrat(project_dir):
    """What the frontend must cover: number of routes and entities.

    Used to SIZE the request made to the model. Without it, monl asked for
    "about 1,500 tokens" for `app.js` whatever the contract — and the model
    obeyed to the token (1,698 measured on a fifteen-route shop) before being
    refused for incompleteness. We asked for the impossible, then rejected it."""
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
