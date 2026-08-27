"""Où vit un projet, et ce que monl sait de lui.

POINT 105 : le dossier existe-t-il, PUIS porte-t-il un projet.
`_erreur_de_chemin` pose la PREMIÈRE question, partagée par les quatre
points d'entrée — sans elle, `monl frontend` conseillait « lancer 'monl
compile' » pour un dossier jamais trouvé."""

import hashlib
import json
import os
import sys

from ..frontend_contract import CONTRACT_FILENAME, contract_sha256
from . import nomenclature, signature


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()

def _load_state(project_dir):
    path = os.path.join(project_dir, nomenclature.STATE_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def _erreur_de_chemin(project_dir, *, fichier_requis=None):
    """Message d'erreur pour un dossier ou un artefact frontend absent.

    POINT 105 : « monl.json introuvable — ce dossier n'est pas un projet monl »
    s'affichait aussi quand le dossier n'existait pas du tout, et `monl frontend`
    allait jusqu'à conseiller « lancer 'monl compile' ». Le message envoyait donc
    corriger une compilation absente alors que c'est le CHEMIN qui était faux —
    une hypothèse affichée comme un diagnostic, exactement ce que le point 97
    reproche au conseil de reformulation.

    Deux niveaux, dans l'ordre où les questions se posent : le dossier
    existe-t-il, PUIS porte-t-il un projet. Le brief frontend est le niveau
    suivant pour la commande qui doit le donner à une IA : le nommer ici évite
    de laisser une ouverture de fichier répondre à la place du CLI."""
    if os.path.isdir(project_dir):
        if fichier_requis and not os.path.isfile(
                os.path.join(project_dir, fichier_requis)):
            return (f" ❌ Contrat frontend incomplet : {fichier_requis} absent — "
                    "lancer d'abord 'monl compile'.")
        return None
    lignes = [f" ❌ Dossier introuvable : {project_dir}"]
    # La faute la plus courante, et celle qui a motivé ce point : un chemin
    # RELATIF écrit avec une barre oblique de tête. `/projets/X` n'est pas
    # « projets/X ici » — c'est « X dans le dossier projets À LA RACINE DU
    # SYSTÈME », qui n'existe évidemment pas.
    if project_dir.startswith(os.sep):
        voisin = project_dir.lstrip(os.sep)
        if os.path.isdir(voisin):
            lignes.append(
                f"    Le chemin commence par « {os.sep} » : il est cherché à la "
                f"racine du système, pas depuis ici.")
            lignes.append(f"    Vouliez-vous dire : {voisin}")
    lignes.append("    (le contenu du dossier n'a pas encore été regardé : "
                  "c'est le chemin qui bloque, pas la compilation)")
    return "\n".join(lignes)

def _save_state(project_dir, spec_relpath, spec_source_path=None):
    from .. import __version__
    spec_path = spec_source_path or os.path.join(project_dir, spec_relpath)
    state = {
        "spec": spec_relpath,
        # POINT 85 : avec QUOI ce projet a été construit. Purement informatif —
        # la détection d'un artefact périmé (point 81) reste fondée sur une
        # régénération, parce qu'un numéro de version peut ne pas bouger quand
        # la génération, elle, a changé. C'est exactement ce qui s'est produit
        # des points 74 à 84. Le numéro sert à NOMMER l'écart, pas à le trouver.
        "compiler_version": __version__,
        "spec_sha256": _sha256_file(spec_path),
        "contract_sha256": contract_sha256(project_dir),
        # POINT 64 : empreinte du backend généré. « app.py reste scellé » était
        # une promesse que RIEN ne mesurait : la cohérence ne vérifiait que
        # l'existence de ces fichiers, et une retouche à la main passait sans
        # bruit — alors que 'monl run' annonce « spec ↔ backend ↔ contrat ↔
        # frontend » vérifiés. Découvert en écrivant le premier test du
        # parcours de commandes, pas en relisant le code.
        "backend_sha256": {
            nom: _sha256_file(os.path.join(project_dir, nom))
            for nom in nomenclature.SCELLE_ARTEFACTS
            if os.path.exists(os.path.join(project_dir, nom))
        },
    }
    with open(os.path.join(project_dir, nomenclature.STATE_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return state

def _situer_projet(project_dir, geste):
    """(dossier absolu, chemin de la spec) — ou sortie en erreur.

    Partagé par 'update' et 'diff' : les deux partent du même état, et un seul
    des deux qui saurait le lire serait une divergence de plus."""
    project_dir = os.path.abspath(project_dir)
    souci = _erreur_de_chemin(project_dir)
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(project_dir)
    if state is None:
        print(f" ❌ {nomenclature.STATE_FILENAME} introuvable — rien à {geste} ici.")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    return project_dir, spec_path

def _signature_precedente(project_dir):
    """La signature du contrat DÉJÀ posé, ou des ensembles vides s'il n'y en a
    pas encore — auquel cas tout est « ajouté », ce qui est exact."""
    contract_path = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(contract_path):
        return (set(), set(), set(), set(), set(), set(), {}, set(), {}, {})
    with open(contract_path, encoding="utf-8") as fh:
        return signature._contract_signature(json.load(fh))

# ----------------------------------------------------------------- assets --
def _spec_du_projet(project_dir):
    """Chemin de la spec d'un projet compilé, d'après monl.json.

    Passer le chemin à assets_tool plutôt que de lui faire relire monl.json :
    l'état du projet est une affaire du CLI, et un second lecteur de monl.json
    serait un second endroit à corriger."""
    souci = _erreur_de_chemin(os.path.abspath(project_dir))
    if souci:
        print(souci)
        sys.exit(1)
    state = _load_state(os.path.abspath(project_dir))
    if state is None:
        print(f" ❌ {nomenclature.STATE_FILENAME} introuvable — ce dossier n'est pas un projet "
              "monl compilé (lancer 'monl' ou 'monl compile').")
        sys.exit(1)
    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(os.path.abspath(project_dir), state["spec"])
    if not os.path.exists(spec_path):
        print(f" ❌ Spec introuvable : {spec_path}")
        sys.exit(1)
    return spec_path

def _assets_dir_du_projet(project_dir):
    """Dossier d'assets déclaré, lu dans le CONTRAT et non dans la spec.

    Le contrat est déjà dérivé de la spec et vérifié cohérent avec elle : le
    relire ici éviterait un second parseur à faire dériver. Retourne None si le
    projet n'en déclare pas — le wrapper n'ajoute alors aucun montage."""
    chemin = os.path.join(project_dir, CONTRACT_FILENAME)
    if not os.path.exists(chemin):
        return None
    try:
        with open(chemin, encoding="utf-8") as fh:
            return (json.load(fh).get("assets") or {}).get("dir") or None
    except (OSError, ValueError):
        return None
