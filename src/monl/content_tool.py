"""Export and import of demo content without hand-editing the DSL."""
import csv
import os
import re
from types import SimpleNamespace

from . import content_import
from .assets_tool import (
    DEFAULT_ASSETS_DIR,
    AssetsToolError,
    _blocks_seed,
    _charger,
    _literal,
    _revalidate,
    paths_declares,
    resolve_asset,
)
from .errors import ToolError
from .policies import event_counter_fields


class ContentToolError(ToolError):
    pass


NUMERIC = {"Integer", "Float", "Money"}
HEADER_PARENT = re.compile(
    r'^seed\s+(\w+)\s+for\s+(\w+)\.(\w+)\s+"([^"\\]*)"\s*(?:#.*)?$')
NUMBER = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _call(function, *args):
    try:
        return function(*args)
    except AssetsToolError as err:
        raise ContentToolError(str(err)) from None


def _excluded(normalized, entity_name):
    security = normalized.get("security", {})
    excluded = {field for entity, field in event_counter_fields(security)
              if entity == entity_name}
    for key in ("generated_fields", "derived_fields", "aggregated_fields",
                "timestamp_fields", "numbered_fields"):
        for item in security.get(key) or []:
            if item.get("entity") == entity_name:
                excluded.add(item.get("field"))
    post = security.get("writable_after_payment") or {}
    valeur = post.get(entity_name, {}) if isinstance(post, dict) else {}
    excluded.update(valeur.get("fields", []) if isinstance(valeur, dict) else [])
    return excluded


def _infos_parent(lines, blocks, entity_name):
    infos = []
    cursor = 0
    for i, line in enumerate(lines):
        if not line.startswith("seed"):
            continue
        if cursor >= len(blocks):
            break
        name, ranges = blocks[cursor]
        cursor += 1
        if name != entity_name:
            continue
        match = HEADER_PARENT.match(line.rstrip("\n"))
        infos.append((i, ranges, match.groups()[1:] if match else None))
    parents = [info for _i, _p, info in infos if info]
    if parents and len(parents) != len(infos):
        raise ContentToolError(
            f"The seed blocks for {entity_name} mix forms with and without a parent. "
            "Make them consistent by hand before using content.")
    if parents and len({p[:2] for p in parents}) != 1:
        raise ContentToolError(
            f"The seed blocks for {entity_name} do not all identify the parent in the "
            "same way. Make them consistent by hand first.")
    return infos, (parents[0][:2] if parents else None)


def _columns(normalized, entity_name, parent=False):
    fields = normalized["schema"]["entities"][entity_name]
    excluded = _excluded(normalized, entity_name)
    columns = (["_parent"] if parent else []) + [
        name for name, type_ in fields.items()
        if name not in excluded and type_ not in ("Boolean", "Upload")
    ]
    return columns


def _value_csv(valeur, type_):
    if valeur is None:
        return ""
    if type_ == "Image" and isinstance(valeur, str):
        return os.path.basename(valeur)
    return str(valeur)


def _help_of_column(entity_name, column, fields, choice, constraints):
    """What LISEZMOI says about a column. Extracted from `_lisez_moi`
    (complexity ceiling); text unchanged."""
    if column == "_parent":
        return "the value of a record in the parent entity to which this row should be linked"
    details = []
    enum = choice.get(entity_name, {}).get(column)
    if enum:
        details.append("allowed values: " + ", ".join(enum))
    rules = constraints.get((entity_name, column), {})
    if rules.get("required"):
        details.append("required")
    for bound in ("min", "max"):
        if bound in rules:
            details.append(f"{bound} {rules[bound]['valeur']}")
    if fields[column] == "Image":
        details.append("put the file in `assets/` and enter only its name here")
    return "; ".join(details) if details else "free text"


def _read_moi(normalized, exports, ignores):
    security = normalized.get("security", {})
    constraints = security.get("field_constraints") or {}
    choice = security.get("enumerated_fields") or {}
    lines = [
        "EDIT CONTENT\n",
        "\n",
        "Each CSV file represents a type of record. Keep the column names as "
        "they are, then run `monl content import`. An empty cell is intentionally "
        "omitted from the record: required fields will be rejected with an explanation.\n",
    ]
    for entity_name, info in exports.items():
        lines.extend(["\n", f"{entity_name}.csv\n"])
        fields = normalized["schema"]["entities"][entity_name]
        for column in info["colonnes"]:
            text = _help_of_column(entity_name, column, fields, choice, constraints)
            lines.append(f"- {column}: {text}.\n")
        booleans = [n for n, t in fields.items() if t == "Boolean"]
        if booleans:
            lines.append("  Boolean fields are not offered (the seed has no "
                          "true/false literal): " + ", ".join(booleans) + ".\n")
    if ignores:
        lines.extend(["\n", "Entities not exported\n"])
        for entity_name, reason in ignores.items():
            lines.append(f"- {entity_name}: {reason}\n")
    return "".join(lines)


def exporter_content(spec_path, project_dir):
    normalized = _call(_charger, spec_path)
    with open(spec_path, encoding="utf-8") as fh:
        lines = fh.readlines()
    blocks = _blocks_seed(lines)
    entities_seeded = {entity_name for entity_name, _ in blocks}
    exports, ignores = {}, {}
    folder = os.path.join(project_dir, "content")
    os.makedirs(folder, exist_ok=True)
    for entity_name in normalized["schema"]["entities"]:
        if entity_name not in entities_seeded:
            ignores[entity_name] = ("no seed example defines the content shape yet; "
                                "write an example by hand first")
            continue
        infos, parent = _infos_parent(lines, blocks, entity_name)
        columns = _columns(normalized, entity_name, bool(parent))
        blocks_ast = [b for b in normalized.get("seeds", []) if b["entity"] == entity_name]
        if len(infos) != len(blocks_ast):
            raise ContentToolError(
                f"The seed blocks for {entity_name} do not match the compiled spec.")
        path = os.path.join(folder, f"{entity_name}.csv")
        fiches = 0
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for (_i, _ranges, parent_info), block in zip(infos, blocks_ast, strict=True):
                for row in block["rows"]:
                    output = {}
                    if parent:
                        output["_parent"] = parent_info[2]
                    for name in columns:
                        if name != "_parent":
                            output[name] = _value_csv(
                                row.get(name), normalized["schema"]["entities"][entity_name][name])
                    writer.writerow(output)
                    fiches += 1
        exports[entity_name] = {"fichier": path, "colonnes": columns, "fiches": fiches,
                            "parent": parent}
    readme = os.path.join(folder, "LISEZMOI.txt")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write(_read_moi(normalized, exports, ignores))
    return {"entites": exports, "ignorees": ignores, "lisez_moi": readme}


def _read_csv(path, columns):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != columns:
            raise ContentToolError(
                f"{os.path.basename(path)}: expected columns: {', '.join(columns)}; "
                f"received columns: {', '.join(reader.fieldnames or [])}.")
        return [(number, dict(row)) for number, row in enumerate(reader, 2)]


def _text_fiche(entity_name, row, number, types, folder_assets):
    chunks = []
    for name, valeur in row.items():
        if name == "_parent" or valeur == "":
            continue
        type_ = types[name]
        if type_ in NUMERIC:
            if not NUMBER.fullmatch(valeur):
                raise ContentToolError(
                    f"{entity_name}.csv row {number}: '{valeur}' is not a valid number "
                    f"for column {name}.")
            literal = valeur
        else:
            if type_ == "Image" and (
                    os.path.basename(valeur) != valeur
                    or valeur in (".", "..")
                    or "/" in valeur
                    or "\\" in valeur):
                raise ContentToolError(
                    f"{entity_name}.csv row {number}: column {name} expects a filename "
                    f"only, not the path '{valeur}'.")
            try:
                literal = _literal(
                    f"{folder_assets}/{valeur}" if type_ == "Image" else valeur)
            except AssetsToolError as err:
                raise ContentToolError(
                f"{entity_name}.csv row {number}, column {name}: {err}") from None
        chunks.append(f"{name}: {literal}")
    return "    " + ", ".join(chunks) + "\n"


def _ranges_blocks(lines):
    result = []
    blocks = _blocks_seed(lines)
    cursor = 0
    for i, line in enumerate(lines):
        if cursor >= len(blocks):
            break
        if re.match(r"^seed\s+", line):
            entity_name, entrees = blocks[cursor]
            fin = entrees[-1][1] if entrees else i
            result.append((entity_name, i, fin))
            cursor += 1
    return result


def _only_spaces_comments(text):
    return all(not line.strip() or line.lstrip().startswith("#")
               for line in text.splitlines())


def _warnings(project_dir, normalized, spec_changed):
    messages = []
    folder, declares = paths_declares(normalized)
    missing = [c for c in sorted(declares)
                 if not resolve_asset(project_dir, folder, c)]
    if missing:
        messages.append(f"{len(missing)} declared asset(s) are still missing: "
                        + ", ".join(missing) + ". Run 'monl assets list' for details.")
    if spec_changed and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append("The database already exists: seed data only populates a NEW database.")
    if spec_changed:
        messages.append("Spec changed: run 'monl update' to resynchronize the backend and contract.")
    return messages


def importer_content(spec_path, project_dir):
    return content_import.importer_content(
        spec_path, project_dir, SimpleNamespace(
            _call=_call,
            _charger=_charger,
            _blocks_seed=_blocks_seed,
            _infos_parent=_infos_parent,
            _columns=_columns,
            _read_csv=_read_csv,
            _revalidate=_revalidate,
            _only_spaces_comments=_only_spaces_comments,
            _ranges_blocks=_ranges_blocks,
            _literal=_literal,
            _value_csv=_value_csv,
            _text_fiche=_text_fiche,
            _warnings=_warnings,
            resolve_asset=resolve_asset,
            ContentToolError=ContentToolError,
            AssetsToolError=AssetsToolError,
            DEFAULT_ASSETS_DIR=DEFAULT_ASSETS_DIR,
        ))
