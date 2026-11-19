"""Where a declared asset lives, and under which name it is filed."""

import difflib
import os

from ..ast_validator import DEFAULT_ASSETS_DIR
from .editing import _blocks_seed
from .foundations import AssetsToolError, slugify


# ------------------------------------------------- what the spec declares --
def paths_declares(normalized):
    """(folder, {declared path: [readable origins]}).

    "Origin" serves the messages: `assets.logo`, `Product[3].imageUrl`. The
    same file can be declared twice — it is legitimate (two items, the same
    photo), and the report shows it rather than hiding it."""
    assets = normalized.get("assets") or {}
    folder = assets.get("dir") or DEFAULT_ASSETS_DIR
    declares = {}
    for key in ("logo", "favicon"):
        if assets.get(key):
            declares.setdefault(assets[key], []).append(f"assets.{key}")
    entities = normalized.get("schema", {}).get("entities", {})
    for block in normalized.get("seeds") or []:
        fields = entities.get(block["entity"], {})
        for i, row in enumerate(block["rows"], 1):
            for name, valeur in row.items():
                if fields.get(name) == "Image" and isinstance(valeur, str):
                    declares.setdefault(valeur, []).append(f"{block['entity']}[{i}].{name}")
    return folder, declares

# ------------------------------------------------------------------ add --
def _resolve_seed(normalized, lines, pour, entity, field):
    """Which seed item, and which 'Image' field of that item.

    The item is designated by one of its VALUES ("Halo RS") and not by a
    number: it is what the human has in front of them. An ambiguous
    designation is refused, naming the candidates — guessing would write the
    photo on the wrong item, and nobody would see it before going live."""
    blocks_file = _blocks_seed(lines)
    blocks_ast = normalized.get("seeds") or []
    _check_match_seed(blocks_file, blocks_ast)
    candidates, all_values = _candidates_seed(blocks_file, blocks_ast, entity, pour)
    _refuse_designation(candidates, all_values, pour, entity)
    ent, range_, _row = candidates[0]
    return _field_image(normalized, ent, field, range_)

def _check_match_seed(blocks_file, blocks_ast):
    """The file and the AST list the same seed blocks, row for row."""
    if not blocks_ast:
        raise AssetsToolError(
            "This spec has no 'seed' block to attach a photo to. Add the block, "
            "or use --logo / --favicon.")
    # Safety net: the file ↔ AST match is what everything rests on. If it does
    # not hold, stopping is better than writing on another item — a spec where
    # the photo is on the wrong line compiles perfectly.
    if (len(blocks_file) != len(blocks_ast)
            or any(f[0] != a["entity"] for f, a in zip(blocks_file, blocks_ast, strict=True))
            or any(len(f[1]) != len(a["rows"]) for f, a in zip(blocks_file, blocks_ast, strict=True))):
        raise AssetsToolError(
            "The file's 'seed' blocks do not match those in the compiled spec "
            "(different number of rows). The tool stops rather than writing to "
            "a different row from the one requested.")


def _lines_seed(blocks_file, blocks_ast, entity):
    """Every seed row as (entity, line range, values), filtered by --entity."""
    for (ent, ranges), block in zip(blocks_file, blocks_ast, strict=True):
        if entity and ent != entity:
            continue
        for k, row in enumerate(block["rows"]):
            yield ent, ranges[k], row


def _candidates_seed(blocks_file, blocks_ast, entity, pour):
    """Rows carrying the value: exact first, case-insensitive second."""
    lines = list(_lines_seed(blocks_file, blocks_ast, entity))
    candidates, all_values = [], []
    for ent, range_, row in lines:
        texts = [v for v in row.values() if isinstance(v, str)]
        all_values.extend(texts)
        if any(v.strip() == pour.strip() for v in texts):
            candidates.append((ent, range_, row))
    if not candidates:  # second pass, case-insensitive
        candidates = [(ent, range_, row) for ent, range_, row in lines
                     if any(isinstance(v, str) and v.strip().lower() == pour.strip().lower()
                            for v in row.values())]
    return candidates, all_values


def _refuse_designation(candidates, all_values, pour, entity):
    """Exactly one row must match: none or several is refused, with help."""
    if not candidates:
        close = difflib.get_close_matches(pour, all_values, n=3, cutoff=0.5)
        index = (" Maybe: " + ", ".join(f"'{p}'" for p in close)) if close else ""
        raise AssetsToolError(
            f"No seed row has the value '{pour}'"
            + (f" in entity {entity}" if entity else "") + f".{index}")
    if len(candidates) > 1:
        ou = ", ".join(f"{e} row {range_[0] + 1}" for e, range_, _ in candidates)
        raise AssetsToolError(
            f"'{pour}' matches {len(candidates)} rows ({ou}): specify --entity, "
            f"or use a value that belongs to only one row.")


def _field_image(normalized, ent, field, range_):
    """The 'Image' field of the designated row: named, or the only one."""
    fields = normalized["schema"]["entities"].get(ent, {})
    images = [name for name, type_ in fields.items() if type_ == "Image"]
    if field:
        if fields.get(field) == "Image":
            return ent, field, range_
        if field in fields:
            raise AssetsToolError(
                f"{ent}.{field} has type '{fields[field]}', not 'Image' — only this "
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
    return ent, images[0], range_


def _name_of_file(source, name, pour, target):
    if name:
        if os.sep in name or "/" in name or name.strip(".") == "":
            raise AssetsToolError(
                f"--as expects a file NAME, not a path: '{name}'.")
        return name
    racine = slugify(pour or target)
    if not racine:
        raise AssetsToolError(
            f"'{pour or target}' does not produce a usable filename "
            f"(no letters or digits) — specify --as <name>.")
    extension = os.path.splitext(source)[1].lower()
    if not extension:
        raise AssetsToolError(
            f"'{source}' has no extension: served as-is, the browser cannot "
            f"determine the file type. Rename the source, or provide --as <name.ext>.")
    return racine + extension
