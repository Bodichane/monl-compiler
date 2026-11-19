"""Where a declared asset lives, and under which name it is filed."""

import difflib
import os

from ..ast_validator import DEFAULT_ASSETS_DIR
from .editing import _blocs_seed
from .foundations import AssetsToolError, sluggify


# ------------------------------------------------- what the spec declares --
def chemins_declares(normalized):
    """(folder, {declared path: [readable origins]}).

    "Origin" serves the messages: `assets.logo`, `Product[3].imageUrl`. The
    same file can be declared twice — it is legitimate (two items, the same
    photo), and the report shows it rather than hiding it."""
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
    """Which seed item, and which 'Image' field of that item.

    The item is designated by one of its VALUES ("Halo RS") and not by a
    number: it is what the human has in front of them. An ambiguous
    designation is refused, naming the candidates — guessing would write the
    photo on the wrong item, and nobody would see it before going live."""
    blocs_fichier = _blocs_seed(lignes)
    blocs_ast = normalized.get("seeds") or []
    _verifier_correspondance_seed(blocs_fichier, blocs_ast)
    candidats, toutes_valeurs = _candidats_seed(blocs_fichier, blocs_ast, entity, pour)
    _refuser_designation(candidats, toutes_valeurs, pour, entity)
    ent, plage, _row = candidats[0]
    return _champ_image(normalized, ent, field, plage)

def _verifier_correspondance_seed(blocs_fichier, blocs_ast):
    """The file and the AST list the same seed blocks, row for row."""
    if not blocs_ast:
        raise AssetsToolError(
            "This spec has no 'seed' block to attach a photo to. Add the block, "
            "or use --logo / --favicon.")
    # Safety net: the file ↔ AST match is what everything rests on. If it does
    # not hold, stopping is better than writing on another item — a spec where
    # the photo is on the wrong line compiles perfectly.
    if (len(blocs_fichier) != len(blocs_ast)
            or any(f[0] != a["entity"] for f, a in zip(blocs_fichier, blocs_ast, strict=True))
            or any(len(f[1]) != len(a["rows"]) for f, a in zip(blocs_fichier, blocs_ast, strict=True))):
        raise AssetsToolError(
            "The file's 'seed' blocks do not match those in the compiled spec "
            "(different number of rows). The tool stops rather than writing to "
            "a different row from the one requested.")


def _lignes_seed(blocs_fichier, blocs_ast, entity):
    """Every seed row as (entity, line range, values), filtered by --entity."""
    for (ent, plages), bloc in zip(blocs_fichier, blocs_ast, strict=True):
        if entity and ent != entity:
            continue
        for k, row in enumerate(bloc["rows"]):
            yield ent, plages[k], row


def _candidats_seed(blocs_fichier, blocs_ast, entity, pour):
    """Rows carrying the value: exact first, case-insensitive second."""
    lignes = list(_lignes_seed(blocs_fichier, blocs_ast, entity))
    candidats, toutes_valeurs = [], []
    for ent, plage, row in lignes:
        textes = [v for v in row.values() if isinstance(v, str)]
        toutes_valeurs.extend(textes)
        if any(v.strip() == pour.strip() for v in textes):
            candidats.append((ent, plage, row))
    if not candidats:  # second pass, case-insensitive
        candidats = [(ent, plage, row) for ent, plage, row in lignes
                     if any(isinstance(v, str) and v.strip().lower() == pour.strip().lower()
                            for v in row.values())]
    return candidats, toutes_valeurs


def _refuser_designation(candidats, toutes_valeurs, pour, entity):
    """Exactly one row must match: none or several is refused, with help."""
    if not candidats:
        proches = difflib.get_close_matches(pour, toutes_valeurs, n=3, cutoff=0.5)
        indice = (" Maybe: " + ", ".join(f"'{p}'" for p in proches)) if proches else ""
        raise AssetsToolError(
            f"No seed row has the value '{pour}'"
            + (f" in entity {entity}" if entity else "") + f".{indice}")
    if len(candidats) > 1:
        ou = ", ".join(f"{e} row {plage[0] + 1}" for e, plage, _ in candidats)
        raise AssetsToolError(
            f"'{pour}' matches {len(candidats)} rows ({ou}): specify --entity, "
            f"or use a value that belongs to only one row.")


def _champ_image(normalized, ent, field, plage):
    """The 'Image' field of the designated row: named, or the only one."""
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
