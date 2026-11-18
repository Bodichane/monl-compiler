"""The two verbs: `add` and `list`.

The tool deletes nothing, writes no credit, does not recompile — an orphan
is REPORTED, `monl update` stays the explicit action."""

import os
import shutil

from ..ast_validator import DEFAULT_ASSETS_DIR, resoudre_asset
from .edition import _ecrire_paire, _poser_prop_assets, _remplacer_entree
from .fondations import NOMS_DE_CREDITS, AssetsToolError, _sha256
from .resolution import _nom_de_fichier, _resoudre_seed, chemins_declares
from .specio import _charger, _revalider


# The next two functions are extracted from `ajouter_asset` (complexity
# ceiling): same checks, same message, same rollback.
def _etat_destination(project_dir, dossier, fichier, source, force):
    """(destination, in place, existed, identical) — refuses to overwrite
    DIFFERENT contents without --force."""
    destination = os.path.join(project_dir, dossier, fichier)
    sur_place = os.path.abspath(destination) == os.path.abspath(source)
    existait = os.path.exists(destination)
    identique = existait and _sha256(destination) == _sha256(source)
    if existait and not identique and not sur_place and not force:
        raise AssetsToolError(
            f"'{dossier}/{fichier}' already exists with DIFFERENT contents. "
            f"Run again with --force to overwrite it, or choose --as <another-name>.")
    return destination, sur_place, existait, identique


def _annuler_copie(sauvegarde, destination, existait, sur_place):
    """Puts the disk back as it was: the overwritten file is restored, a newly
    copied one is removed. Once moved back, the backup no longer exists, so
    the caller's `finally` has nothing left to delete."""
    if sauvegarde and os.path.exists(sauvegarde):
        shutil.move(sauvegarde, destination)
    elif not existait and not sur_place and os.path.exists(destination):
        os.remove(destination)


def _drapeaux_du_rapport(existait, identique, sur_place, ancienne, valeur):
    """The report's three derived flags, in their display order."""
    return {
        "ecrase": bool(existait and not identique and not sur_place),
        "deja_en_place": sur_place or identique,
        "remplace": ancienne if ancienne and ancienne != valeur else None,
    }


def ajouter_asset(spec_path, project_dir, source, pour=None, cible=None,
                  entity=None, field=None, nom=None, force=False):
    """Copies a file into the assets folder and DECLARES it in the spec.

    `pour` targets a seed row by one of its values; `cible` is 'logo' or
    'favicon'. Returns a report (dict) — display belongs to the CLI."""
    if bool(pour) == bool(cible):
        raise AssetsToolError(
            "Specify a destination: --for \"<value>\" for a seed row, "
            "or --logo / --favicon.")
    if not os.path.isfile(source):
        raise AssetsToolError(f"'{source}' does not exist or is not a file.")

    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    dossier = (normalized.get("assets") or {}).get("dir") or DEFAULT_ASSETS_DIR
    fichier = _nom_de_fichier(source, nom, pour, cible)

    with open(spec_path, encoding="utf-8") as fh:
        lignes = fh.readlines()

    if cible:
        # The logo is declared by its name ALONE: it is the frontend contract
        # that prefixes it with the folder (_assets_contract). Writing
        # 'assets/logo.svg' here would give '/site/assets/assets/logo.svg' to
        # the browser.
        valeur = fichier
        nouvelles, i_ligne, ancienne = _poser_prop_assets(lignes, cible, valeur, dossier)
        ou, entite, champ = f"assets.{cible}", None, None
    else:
        entite, champ, plage = _resoudre_seed(normalized, lignes, pour, entity, field)
        # A seed value is the URL the browser will request: it therefore
        # carries the folder.
        valeur = f"{dossier}/{fichier}"
        nouvelles, ancienne = _remplacer_entree(
            lignes, plage, lambda texte: _ecrire_paire(texte, champ, valeur))
        i_ligne = plage[0]
        ou = f"{entite}.{champ}"

    destination, sur_place, existait, identique = _etat_destination(
        project_dir, dossier, fichier, source, force)

    sauvegarde = None
    try:
        if not sur_place and not identique:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if existait:
                # Overwriting under --force stays reversible for the duration
                # of the revalidation: without this copy, a compiler refusal
                # would leave the old file destroyed for nothing.
                sauvegarde = destination + ".monl-precedent"
                shutil.copy2(destination, sauvegarde)
            shutil.copy2(source, destination)
        texte = "".join(nouvelles)
        apres = _revalider(texte, spec_path)
        # THE guarantee of layer 2, stated precisely: does what the tool has
        # just written resolve to a real file? Checked with the COMPILER's
        # resolver (resoudre_asset), not with a second implementation that
        # would end up diverging. This check targets our write and not the
        # whole spec: otherwise another missing asset would make the tool
        # unusable precisely where it serves to place one.
        if not resoudre_asset(project_dir, dossier, valeur):
            raise AssetsToolError(
                f"Write CANCELLED — '{valeur}' does not resolve to a file after "
                f"writing. This is exactly what layer 1 rejects during compilation, "
                f"and the tool must not produce it.")
        # Redeclaring what is already declared must write nothing: rewriting an
        # identical text would invalidate the 'monl run --check' fingerprint
        # for nothing.
        spec_changee = texte != "".join(lignes)
        if spec_changee:
            with open(spec_path, "w", encoding="utf-8") as fh:
                fh.write(texte)
    except Exception:
        _annuler_copie(sauvegarde, destination, existait, sur_place)
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
        **_drapeaux_du_rapport(existait, identique, sur_place, ancienne, valeur),
        "spec_changee": spec_changee,
        "orphelin": _orphelin(ancienne, valeur, apres, project_dir),
        "avertissements": _avertissements(project_dir, dossier, fichier, spec_changee,
                                          apres, valeur, seed=cible is None),
    }

def _orphelin(ancienne, valeur, normalized, project_dir):
    """Has the old file become an orphan? REPORTED, never deleted.

    A deliberate decision: a file dropped by the human is not erased on the
    deduction of a declaration tool. It may serve elsewhere — SneakerLab's
    frontend hard-codes three photos the spec ignores."""
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
    """What success does NOT imply. Traps actually met, not hypotheses."""
    messages = []
    # 0. Placing a photo does not make the project compilable: the OTHER
    # declared and missing assets still block it. The tool only checks what it
    # writes (see _valider) — so it must say what is still missing, otherwise
    # 'monl update' would fail without anyone knowing why.
    _dossier, declares = chemins_declares(normalized)
    manquants = [c for c in sorted(declares)
                 if c != valeur and not resoudre_asset(project_dir, dossier, c)]
    if manquants:
        messages.append(
            f"{len(manquants)} other declared asset(s) are still missing: "
            + ", ".join(manquants)
            + ". Compilation will reject them — 'monl assets list' shows their status.")
    # 1. The seed only feeds a FRESH database. SneakerLab's migration to layer
    # 1 showed it: 12 items kept the old path, and the site would have shown 12
    # empty frames with nothing reporting it. Concerns ONLY editing a seed:
    # saying it when placing a logo would be an off-topic warning, and an
    # off-topic warning teaches people to ignore all of them.
    if seed and spec_changee and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append(
            "The database already exists: the 'seed' block only populates a NEW "
            "database. Existing records keep their old values — update them via "
            "the API (PUT) or start with an empty database.")
    # 2. Credits: completeness, never truthfulness (point 83).
    for candidat in NOMS_DE_CREDITS:
        chemin = os.path.join(project_dir, dossier, candidat)
        if not os.path.exists(chemin):
            continue
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            if fichier not in fh.read():
                messages.append(
                    f"{dossier}/{candidat} does not mention '{fichier}'. monl cannot "
                    f"verify attribution; it can only report that it is missing.")
        break
    # 3. The spec changed: the artifacts did not follow it.
    if spec_changee:
        messages.append("Spec changed: run 'monl update' to resynchronize the "
                        "backend and contract.")
    return messages

# ----------------------------------------------------------------- list --
def lister_assets(spec_path, project_dir):
    """What the spec declares, what is present, what lies around undeclared."""
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
            # A logo is declared by its name alone: saying WHERE it was found
            # avoids suggesting it lives at the project root.
            "resolu": os.path.relpath(trouve, project_dir) if trouve else None,
            "taille": os.path.getsize(trouve) if trouve else None,
        })

    # "Orphan" is not a reproach: a credits file, or a photo hard-coded in a
    # frontend page, legitimately lives here without the spec declaring it. The
    # report observes, it does not judge.
    racine = os.path.join(project_dir, dossier)
    orphelins = []
    if os.path.isdir(racine):
        for base, _sous, fichiers in os.walk(racine):
            for nom in fichiers:
                chemin = os.path.join(base, nom)
                if os.path.realpath(chemin) not in resolus:
                    orphelins.append(os.path.relpath(chemin, project_dir))
    return {"dir": dossier, "declares": lignes, "orphelins": sorted(orphelins)}
