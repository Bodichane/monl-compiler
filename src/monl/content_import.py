"""Named steps of importing CSV content into the spec."""

import itertools
import os
import re


def _expected(tool, normalized, entity, types, infos, parent, columns):
    expected_ones = []
    blocks = [b for b in normalized.get("seeds", []) if b["entity"] == entity]
    for (_i, _ranges, parent_info), block in zip(infos, blocks, strict=True):
        for ast_row in block["rows"]:
            expected = {"_parent": parent_info[2]} if parent else {}
            for name in columns:
                if name != "_parent":
                    expected[name] = tool._value_csv(ast_row.get(name), types[name])
            expected_ones.append(expected)
    return expected_ones


def _text_seed_with_parent(tool, entity, rows, types, folder_assets, parent):
    chunks, precedent = [], object()
    for number, row in rows:
        parent_value = row.get("_parent")
        if parent_value != precedent:
            try:
                valeur = tool._literal(parent_value)
            except tool.AssetsToolError as err:
                raise tool.ContentToolError(
                    f"{entity}.csv row {number}, column _parent: {err}") from None
            chunks.append(f"seed {entity} for {parent[0]}.{parent[1]} {valeur}\n")
            precedent = parent_value
        chunks.append(tool._text_fiche(
            entity, row, number, types, folder_assets))
    return "".join(chunks)


def _new_seed(tool, entity, rows, types, folder_assets, parent):
    if parent:
        return _text_seed_with_parent(
            tool, entity, rows, types, folder_assets, parent)
    chunks, precedent = [], object()
    for number, row in rows:
        if precedent.__class__ is object:
            chunks.append(f"seed {entity}\n")
            precedent = None
        chunks.append(tool._text_fiche(
            entity, row, number, types, folder_assets))
    return "".join(chunks)


def _zone_des_seeds(tool, lines, entity):
    existing = [p for p in tool._ranges_blocks(lines) if p[0] == entity]
    if existing:
        for gauche, right in itertools.pairwise(existing):
            entre = "".join(lines[gauche[2] + 1:right[1]])
            if not tool._only_spaces_comments(entre):
                raise tool.ContentToolError(
                    f"The seed blocks for {entity} are not contiguous. "
                    "Group them by hand before importing.")
        return existing[0][1], existing[-1][2], True
    all_ = tool._ranges_blocks(lines)
    if all_:
        debut = fin = all_[-1][2] + 1
    else:
        debut = next((i for i, li in enumerate(lines)
                      if re.match(r"^workflow\s+", li)), len(lines))
        fin = debut
    return debut, fin, False


def _entity_import(tool, normalized, lines, blocks, entity, types,
                   folder_content, folder_assets):
    path = os.path.join(folder_content, f"{entity}.csv")
    if not os.path.isfile(path):
        return None
    infos, parent = tool._infos_parent(lines, blocks, entity)
    columns = tool._columns(normalized, entity, bool(parent))
    rows = tool._read_csv(path, columns)
    if "_parent" in columns and any(not row["_parent"] for _n, row in rows):
        number = next(n for n, row in rows if not row["_parent"])
        raise tool.ContentToolError(
            f"{entity}.csv row {number}: column _parent is empty.")
    expected_ones = _expected(
        tool, normalized, entity, types, infos, parent, columns)
    new = _new_seed(tool, entity, rows, types, folder_assets, parent)
    debut, fin, replaces = _zone_des_seeds(tool, lines, entity)
    operation = None
    if [row for _number, row in rows] != expected_ones:
        operation = (debut, fin, new, entity, rows, replaces)
    return operation, {"fiches": len(rows)}


def _images_imported(tool, project_dir, normalized, rapports,
                      lines, blocks, folder_content, folder_assets):
    for entity in rapports:
        path = os.path.join(folder_content, f"{entity}.csv")
        infos, parent = tool._infos_parent(lines, blocks, entity)
        rows = tool._read_csv(
            path, tool._columns(normalized, entity, bool(parent)))
        types = normalized["schema"]["entities"][entity]
        for number, row in rows:
            for name, type_ in types.items():
                valeur = row.get(name, "")
                if type_ == "Image" and valeur:
                    asset = f"{folder_assets}/{valeur}"
                    if not tool.resolve_asset(project_dir, folder_assets, asset):
                        raise tool.ContentToolError(
                            f"{entity}.csv row {number}: image file "
                            f"'{valeur}' was not found in {folder_assets}/.")


def importer_content(spec_path, project_dir, tool):
    normalized = tool._call(tool._charger, spec_path)
    with open(spec_path, encoding="utf-8") as fh:
        original = fh.read()
    lines = original.splitlines(keepends=True)
    blocks = tool._blocks_seed(lines)
    folder_content = os.path.join(project_dir, "content")
    folder_assets = (normalized.get("assets") or {}).get("dir") or tool.DEFAULT_ASSETS_DIR
    operations, rapports = [], {}
    for entity, types in normalized["schema"]["entities"].items():
        result = _entity_import(
            tool, normalized, lines, blocks, entity, types,
            folder_content, folder_assets)
        if result:
            operation, rapport = result
            if operation:
                operations.append(operation)
            rapports[entity] = rapport
    text_lines = list(lines)
    for debut, fin, new, _entity, _rows, replaces in sorted(
            operations, reverse=True):
        text_lines[debut:fin + 1 if replaces else debut] = (
            new.splitlines(keepends=True))
    text = "".join(text_lines)
    apres = tool._call(tool._revalidate, text, spec_path)
    _images_imported(
        tool, project_dir, normalized, rapports, lines, blocks,
        folder_content, folder_assets)
    changed = text != original
    if changed:
        with open(spec_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    warnings = tool._warnings(project_dir, apres, changed)
    for rapport in rapports.values():
        rapport.update({"spec_changee": changed, "avertissements": warnings})
    return {"entites": rapports, "spec_changee": changed}
