"""Les deux verbes : `add` et `list`.

L'outil ne supprime rien, n'écrit aucun crédit, ne recompile pas —
l'orphelin est SIGNALÉ, `monl update` reste le geste explicite."""

import os
import shutil

from ..ast_validator import DEFAULT_ASSETS_DIR, resoudre_asset
from .edition import _ecrire_paire, _poser_prop_assets, _remplacer_entree
from .fondations import NOMS_DE_CREDITS, AssetsToolError, _sha256
from .resolution import _nom_de_fichier, _resoudre_seed, chemins_declares
from .specio import _charger, _revalider


def ajouter_asset(spec_path, project_dir, source, pour=None, cible=None,
                  entity=None, field=None, nom=None, force=False):
    """Copie un fichier dans le dossier d'assets et le DÉCLARE dans la spec.

    `pour` vise une ligne de seed par une de ses valeurs ; `cible` vaut 'logo'
    ou 'favicon'. Retourne un rapport (dict) — l'affichage appartient au CLI."""
    if bool(pour) == bool(cible):
        raise AssetsToolError(
            "Préciser la destination : --for \"<valeur>\" pour une fiche de seed, "
            "ou --logo / --favicon.")
    if not os.path.isfile(source):
        raise AssetsToolError(f"'{source}' n'existe pas, ou n'est pas un fichier.")

    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    dossier = (normalized.get("assets") or {}).get("dir") or DEFAULT_ASSETS_DIR
    fichier = _nom_de_fichier(source, nom, pour, cible)

    with open(spec_path, encoding="utf-8") as fh:
        lignes = fh.readlines()

    if cible:
        # Le logo se déclare par son SEUL nom : c'est le contrat frontend qui
        # préfixe par le dossier (_assets_contract). Écrire 'assets/logo.svg'
        # ici donnerait '/site/assets/assets/logo.svg' au navigateur.
        valeur = fichier
        nouvelles, i_ligne, ancienne = _poser_prop_assets(lignes, cible, valeur, dossier)
        ou, entite, champ = f"assets.{cible}", None, None
    else:
        entite, champ, plage = _resoudre_seed(normalized, lignes, pour, entity, field)
        # Une valeur de seed est l'URL que le navigateur demandera : elle porte
        # donc le dossier.
        valeur = f"{dossier}/{fichier}"
        nouvelles, ancienne = _remplacer_entree(
            lignes, plage, lambda texte: _ecrire_paire(texte, champ, valeur))
        i_ligne = plage[0]
        ou = f"{entite}.{champ}"

    destination = os.path.join(project_dir, dossier, fichier)
    sur_place = os.path.abspath(destination) == os.path.abspath(source)
    existait = os.path.exists(destination)
    identique = existait and _sha256(destination) == _sha256(source)
    if existait and not identique and not sur_place and not force:
        raise AssetsToolError(
            f"'{dossier}/{fichier}' existe déjà avec un contenu DIFFÉRENT. "
            f"Relancer avec --force pour l'écraser, ou choisir --as <autre-nom>.")

    sauvegarde = None
    try:
        if not sur_place and not identique:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if existait:
                # Écraser sous --force reste réversible le temps de la
                # revalidation : sans cette copie, un refus du compilateur
                # laisserait l'ancien fichier détruit pour rien.
                sauvegarde = destination + ".monl-precedent"
                shutil.copy2(destination, sauvegarde)
            shutil.copy2(source, destination)
        texte = "".join(nouvelles)
        apres = _revalider(texte, spec_path)
        # LA garantie de la couche 2, énoncée précisément : ce que l'outil vient
        # d'écrire résout-il vers un vrai fichier ? Vérifié avec le résolveur du
        # COMPILATEUR (resoudre_asset), pas avec une seconde implémentation qui
        # finirait par diverger. Cette vérification est ciblée sur notre écriture
        # et non sur toute la spec : sinon un autre asset manquant rendrait
        # l'outil inutilisable là où il sert justement à en poser un.
        if not resoudre_asset(project_dir, dossier, valeur):
            raise AssetsToolError(
                f"Écriture ANNULÉE — '{valeur}' ne résout vers aucun fichier une "
                f"fois écrit. C'est exactement ce que la couche 1 refuse à la "
                f"compilation, et l'outil ne doit pas le produire.")
        # Redéclarer ce qui l'est déjà ne doit rien écrire : réécrire un texte
        # identique invaliderait l'empreinte de 'monl run --check' pour rien.
        spec_changee = texte != "".join(lignes)
        if spec_changee:
            with open(spec_path, "w", encoding="utf-8") as fh:
                fh.write(texte)
    except Exception:
        if sauvegarde and os.path.exists(sauvegarde):
            shutil.move(sauvegarde, destination)
            sauvegarde = None
        elif not existait and not sur_place and os.path.exists(destination):
            os.remove(destination)
        raise
    finally:
        if sauvegarde and os.path.exists(sauvegarde):
            os.remove(sauvegarde)

    return {
        "fichier": f"{dossier}/{fichier}",
        "valeur": valeur,
        "ou": ou,
        "entite": entite,
        "champ": champ,
        "ligne": i_ligne + 1,
        "ecrase": bool(existait and not identique and not sur_place),
        "deja_en_place": sur_place or identique,
        "remplace": ancienne if ancienne and ancienne != valeur else None,
        "spec_changee": spec_changee,
        "orphelin": _orphelin(ancienne, valeur, apres, project_dir),
        "avertissements": _avertissements(project_dir, dossier, fichier, spec_changee,
                                          apres, valeur, seed=cible is None),
    }

def _orphelin(ancienne, valeur, normalized, project_dir):
    """L'ancien fichier est-il devenu orphelin ? SIGNALÉ, jamais supprimé.

    Décision assumée : un fichier déposé par l'humain ne s'efface pas sur la
    déduction d'un outil de déclaration. Il peut servir ailleurs — le frontend
    de SneakerLab référence en dur trois photos que la spec ignore."""
    if not ancienne or ancienne == valeur:
        return None
    dossier, declares = chemins_declares(normalized)
    if ancienne in declares:
        return None
    if not resoudre_asset(project_dir, dossier, ancienne):
        return None
    return ancienne

def _avertissements(project_dir, dossier, fichier, spec_changee, normalized,
                    valeur, seed):
    """Ce que la réussite n'implique PAS. Des pièges vécus, pas des hypothèses."""
    messages = []
    # 0. Poser une photo ne rend pas le projet compilable : les AUTRES assets
    # déclarés et absents le bloquent toujours. L'outil ne vérifie que ce qu'il
    # écrit (voir _valider) — il doit donc dire ce qui manque encore, sinon
    # 'monl update' échouerait sans qu'on sache pourquoi.
    _dossier, declares = chemins_declares(normalized)
    manquants = [c for c in sorted(declares)
                 if c != valeur and not resoudre_asset(project_dir, dossier, c)]
    if manquants:
        messages.append(
            f"{len(manquants)} autre(s) asset déclaré(s) reste(nt) absent(s) : "
            + ", ".join(manquants)
            + ". La compilation les refusera — 'monl assets list' fait le point.")
    # 1. Le seed ne nourrit qu'une base NEUVE. La migration de SneakerLab à la
    # couche 1 l'a montré : 12 fiches gardaient l'ancien chemin, et le site
    # aurait affiché 12 cadres vides sans que rien ne le signale. Ne concerne
    # QUE l'édition d'un seed : le dire en posant un logo serait un
    # avertissement hors sujet, et un avertissement hors sujet apprend à les
    # ignorer tous.
    if seed and spec_changee and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append(
            "La base existe déjà : le bloc 'seed' ne nourrit qu'une base NEUVE. "
            "Les fiches déjà enregistrées gardent leur ancienne valeur — les "
            "corriger via l'API (PUT) ou repartir d'une base vide.")
    # 2. Crédits : complétude, jamais véracité (point 83).
    for candidat in NOMS_DE_CREDITS:
        chemin = os.path.join(project_dir, dossier, candidat)
        if not os.path.exists(chemin):
            continue
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            if fichier not in fh.read():
                messages.append(
                    f"{dossier}/{candidat} ne mentionne pas '{fichier}'. monl ne "
                    f"peut pas vérifier une attribution, seulement constater "
                    f"qu'elle manque.")
        break
    # 3. La spec a changé : les artefacts ne l'ont pas suivie.
    if spec_changee:
        messages.append("Spec modifiée : lancer 'monl update' pour resynchroniser "
                        "backend et contrat.")
    return messages

# ----------------------------------------------------------------- list --
def lister_assets(spec_path, project_dir):
    """Ce que la spec déclare, ce qui est présent, ce qui traîne sans être déclaré."""
    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    dossier, declares = chemins_declares(normalized)

    lignes, resolus = [], set()
    for chemin in sorted(declares):
        trouve = resoudre_asset(project_dir, dossier, chemin)
        if trouve:
            resolus.add(os.path.realpath(trouve))
        lignes.append({
            "chemin": chemin,
            "origines": declares[chemin],
            "present": bool(trouve),
            # Un logo est déclaré par son seul nom : dire OÙ il a été trouvé
            # évite de laisser croire qu'il vit à la racine du projet.
            "resolu": os.path.relpath(trouve, project_dir) if trouve else None,
            "taille": os.path.getsize(trouve) if trouve else None,
        })

    # « Orphelin » n'est pas un reproche : un fichier de crédits, ou une photo
    # posée en dur dans une page du frontend, vit légitimement ici sans que la
    # spec la déclare. Le rapport constate, il ne juge pas.
    racine = os.path.join(project_dir, dossier)
    orphelins = []
    if os.path.isdir(racine):
        for base, _sous, fichiers in os.walk(racine):
            for nom in fichiers:
                chemin = os.path.join(base, nom)
                if os.path.realpath(chemin) not in resolus:
                    orphelins.append(os.path.relpath(chemin, project_dir))
    return {"dir": dossier, "declares": lignes, "orphelins": sorted(orphelins)}
