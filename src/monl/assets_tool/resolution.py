"""Où vit un asset déclaré, et sous quel nom on le range."""

import difflib
import os

from ..ast_validator import DEFAULT_ASSETS_DIR
from .edition import _blocs_seed
from .fondations import AssetsToolError, sluggify


# ------------------------------------------------- ce que la spec déclare --
def chemins_declares(normalized):
    """(dossier, {chemin déclaré: [origines lisibles]}).

    « Origine » sert aux messages : `assets.logo`, `Product[3].imageUrl`. Un
    même fichier peut être déclaré deux fois — c'est légitime (deux fiches, la
    même photo), et le rapport le montre plutôt que de le taire."""
    assets = normalized.get("assets") or {}
    dossier = assets.get("dir") or DEFAULT_ASSETS_DIR
    declares = {}
    for cle in ("logo", "favicon"):
        if assets.get(cle):
            declares.setdefault(assets[cle], []).append(f"assets.{cle}")
    entites = normalized.get("schema", {}).get("entities", {})
    for bloc in normalized.get("seeds") or []:
        champs = entites.get(bloc["entity"], {})
        for i, row in enumerate(bloc["rows"], 1):
            for nom, valeur in row.items():
                if champs.get(nom) == "Image" and isinstance(valeur, str):
                    declares.setdefault(valeur, []).append(f"{bloc['entity']}[{i}].{nom}")
    return dossier, declares

# ------------------------------------------------------------------ add --
def _resoudre_seed(normalized, lignes, pour, entity, field):
    """Quelle fiche de seed, et quel champ 'Image' de cette fiche.

    La fiche est désignée par une de ses VALEURS (« Halo RS ») et non par un
    numéro : c'est ce que l'humain a sous les yeux. Une désignation ambiguë est
    refusée en nommant les candidates — deviner écrirait la photo sur la
    mauvaise fiche, et personne ne le verrait avant la mise en ligne."""
    blocs_fichier = _blocs_seed(lignes)
    blocs_ast = normalized.get("seeds") or []
    if not blocs_ast:
        raise AssetsToolError(
            "Cette spec n'a aucun bloc 'seed' : rien à quoi rattacher une photo. "
            "Ajouter le bloc, ou viser --logo / --favicon.")
    # Filet : la correspondance fichier ↔ AST est ce sur quoi tout repose. Si
    # elle ne tient pas, s'arrêter vaut mieux qu'écrire sur une autre fiche —
    # une spec où la photo est sur la mauvaise ligne compile parfaitement.
    if (len(blocs_fichier) != len(blocs_ast)
            or any(f[0] != a["entity"] for f, a in zip(blocs_fichier, blocs_ast, strict=True))
            or any(len(f[1]) != len(a["rows"]) for f, a in zip(blocs_fichier, blocs_ast, strict=True))):
        raise AssetsToolError(
            "Les blocs 'seed' du fichier ne correspondent pas à ceux de la spec "
            "compilée (nombre de fiches différent). L'outil s'arrête plutôt que "
            "d'écrire sur une autre fiche que celle demandée.")

    candidats, toutes_valeurs = [], []
    for (ent, plages), bloc in zip(blocs_fichier, blocs_ast, strict=True):
        if entity and ent != entity:
            continue
        for k, row in enumerate(bloc["rows"]):
            textes = [v for v in row.values() if isinstance(v, str)]
            toutes_valeurs.extend(textes)
            if any(v.strip() == pour.strip() for v in textes):
                candidats.append((ent, plages[k], row))
    if not candidats:  # deuxième passe, insensible à la casse
        for (ent, plages), bloc in zip(blocs_fichier, blocs_ast, strict=True):
            if entity and ent != entity:
                continue
            for k, row in enumerate(bloc["rows"]):
                if any(isinstance(v, str) and v.strip().lower() == pour.strip().lower()
                       for v in row.values()):
                    candidats.append((ent, plages[k], row))

    if not candidats:
        proches = difflib.get_close_matches(pour, toutes_valeurs, n=3, cutoff=0.5)
        indice = (" Peut-être : " + ", ".join(f"'{p}'" for p in proches)) if proches else ""
        raise AssetsToolError(
            f"Aucune ligne de seed ne porte la valeur '{pour}'"
            + (f" dans l'entité {entity}" if entity else "") + f".{indice}")
    if len(candidats) > 1:
        ou = ", ".join(f"{e} ligne {plage[0] + 1}" for e, plage, _ in candidats)
        raise AssetsToolError(
            f"'{pour}' désigne {len(candidats)} lignes ({ou}) : préciser --entity, "
            f"ou viser une valeur qui n'appartient qu'à une seule fiche.")

    ent, plage, _row = candidats[0]
    champs = normalized["schema"]["entities"].get(ent, {})
    images = [nom for nom, type_ in champs.items() if type_ == "Image"]
    if field:
        if champs.get(field) == "Image":
            return ent, field, plage
        if field in champs:
            raise AssetsToolError(
                f"{ent}.{field} est de type '{champs[field]}', pas 'Image' — seul ce "
                f"type fait vérifier le fichier à la compilation. "
                + (f"Champs 'Image' de {ent} : {', '.join(images)}." if images
                   else f"{ent} n'a aucun champ 'Image'."))
        raise AssetsToolError(f"{ent} n'a pas de champ '{field}'.")
    if not images:
        raise AssetsToolError(
            f"L'entité {ent} n'a aucun champ de type 'Image' : déclarer par exemple "
            f"'photo: Image' dans son bloc 'entity'. C'est ce type qui fait vérifier "
            f"le fichier présent à la compilation — un champ 'String' accepterait "
            f"n'importe quel chemin en silence.")
    if len(images) > 1:
        raise AssetsToolError(
            f"{ent} a plusieurs champs 'Image' ({', '.join(images)}) : préciser --field.")
    return ent, images[0], plage

def _nom_de_fichier(source, nom, pour, cible):
    if nom:
        if os.sep in nom or "/" in nom or nom.strip(".") == "":
            raise AssetsToolError(
                f"--as attend un NOM de fichier, pas un chemin : '{nom}'.")
        return nom
    racine = sluggify(pour or cible)
    if not racine:
        raise AssetsToolError(
            f"'{pour or cible}' ne donne aucun nom de fichier utilisable "
            f"(ni lettre ni chiffre) — préciser --as <nom>.")
    extension = os.path.splitext(source)[1].lower()
    if not extension:
        raise AssetsToolError(
            f"'{source}' n'a pas d'extension : servi tel quel, le navigateur ne "
            f"saurait pas de quel type de fichier il s'agit. Renommer la source, "
            f"ou donner --as <nom.ext>.")
    return racine + extension
