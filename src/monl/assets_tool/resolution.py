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
            "This spec has no 'seed' block to attach a photo to. Add the block, "
            "or use --logo / --favicon.")
    # Filet : la correspondance fichier ↔ AST est ce sur quoi tout repose. Si
    # elle ne tient pas, s'arrêter vaut mieux qu'écrire sur une autre fiche —
    # une spec où la photo est sur la mauvaise ligne compile parfaitement.
    if (len(blocs_fichier) != len(blocs_ast)
            or any(f[0] != a["entity"] for f, a in zip(blocs_fichier, blocs_ast, strict=True))
            or any(len(f[1]) != len(a["rows"]) for f, a in zip(blocs_fichier, blocs_ast, strict=True))):
        raise AssetsToolError(
            "The file's 'seed' blocks do not match those in the compiled spec "
            "(different number of rows). The tool stops rather than writing to "
            "a different row from the one requested.")

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
        indice = (" Maybe: " + ", ".join(f"'{p}'" for p in proches)) if proches else ""
        raise AssetsToolError(
            f"No seed row has the value '{pour}'"
            + (f" in entity {entity}" if entity else "") + f".{indice}")
    if len(candidats) > 1:
        ou = ", ".join(f"{e} ligne {plage[0] + 1}" for e, plage, _ in candidats)
        raise AssetsToolError(
            f"'{pour}' matches {len(candidats)} rows ({ou}): specify --entity, "
            f"or use a value that belongs to only one row.")

    ent, plage, _row = candidats[0]
    champs = normalized["schema"]["entities"].get(ent, {})
    images = [nom for nom, type_ in champs.items() if type_ == "Image"]
    if field:
        if champs.get(field) == "Image":
            return ent, field, plage
        if field in champs:
            raise AssetsToolError(
                f"{ent}.{field} has type '{champs[field]}', not 'Image' — only this "
                f"type makes compilation check the file. "
                + (f"'Image' fields in {ent}: {', '.join(images)}." if images
                   else f"{ent} has no 'Image' field."))
        raise AssetsToolError(f"{ent} has no '{field}' field.")
    if not images:
        raise AssetsToolError(
            f"Entity {ent} has no field of type 'Image': declare, for example, "
            f"'photo: Image' in its 'entity' block. This type makes compilation "
            f"check that the file exists — a 'String' field would silently accept "
            f"any path.")
    if len(images) > 1:
        raise AssetsToolError(
            f"{ent} has multiple 'Image' fields ({', '.join(images)}): specify --field.")
    return ent, images[0], plage

def _nom_de_fichier(source, nom, pour, cible):
    if nom:
        if os.sep in nom or "/" in nom or nom.strip(".") == "":
            raise AssetsToolError(
                f"--as expects a file NAME, not a path: '{nom}'.")
        return nom
    racine = sluggify(pour or cible)
    if not racine:
        raise AssetsToolError(
            f"'{pour or cible}' does not produce a usable filename "
            f"(no letters or digits) — specify --as <name>.")
    extension = os.path.splitext(source)[1].lower()
    if not extension:
        raise AssetsToolError(
            f"'{source}' has no extension: served as-is, the browser cannot "
            f"determine the file type. Rename the source, or provide --as <name.ext>.")
    return racine + extension
