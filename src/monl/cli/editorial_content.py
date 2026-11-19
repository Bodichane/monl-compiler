"""Assets and editorial content, from the command line."""

import os
import sys

from . import location


def cmd_assets_add(project_dir, source, pour=None, target=None, entity=None,
                   field=None, name=None, force=False):
    from ..assets_tool import AssetsToolError, add_asset
    spec_path = location._spec_of_project(project_dir)
    try:
        rapport = add_asset(spec_path, project_dir, source, pour=pour,
                                target=target, entity=entity, field=field,
                                name=name, force=force)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    verb = "already in place" if rapport["deja_en_place"] else \
            ("replaced" if rapport["ecrase"] else "copied")
    print(f" -> File {verb}: {rapport['fichier']}")
    print(f" -> Declared in     : {rapport['ou']} "
          f"(line {rapport['ligne']} of {os.path.basename(spec_path)})")
    if rapport["remplace"]:
        print(f" -> Replaces previous value: {rapport['remplace']}")
    print(" ✅ Spec revalidated by the compiler: the written path exists.")
    if rapport["orphelin"]:
        print(f" ⚠️  '{rapport['orphelin']}' is no longer declared in the spec. The file "
              "is left in place: monl does not delete a file you provided.")
    for message in rapport["avertissements"]:
        print(f" ⚠️  {message}")

def cmd_assets_list(project_dir):
    from ..assets_tool import AssetsToolError, lister_assets
    spec_path = location._spec_of_project(project_dir)
    try:
        rapport = lister_assets(spec_path, project_dir)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    print(f"─── Declared assets — directory '{rapport['dir']}/' ───")
    if not rapport["declares"]:
        print("  (the spec declares no assets: no 'Image' field, logo, or favicon)")
    for line in rapport["declares"]:
        marque = "✅" if line["present"] else "❌"
        bytes_ = line["taille"]
        size = "" if bytes_ is None else (
            f" ({bytes_ // 1024} KB)" if bytes_ >= 1024 else f" ({bytes_} B)")
        elsewhere = (f" → {line['resolu']}"
                    if line["resolu"] and line["resolu"] != line["chemin"] else "")
        print(f"  {marque} {line['chemin']}{elsewhere}{size}"
              f"   ← {', '.join(line['origines'])}")
    if rapport["orphelins"]:
        print(f"─── Present but undeclared ({len(rapport['orphelins'])}) ───")
        for path in rapport["orphelins"]:
            print(f"  ·  {path}")
        print("  (this is fine for a credits file or an image added by hand "
              "to a page: this report is informational, not a warning)")

def cmd_content_export(project_dir):
    from ..content_tool import ContentToolError, exporter_content
    spec_path = location._spec_of_project(project_dir)
    try:
        rapport = exporter_content(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entity, info in rapport["entites"].items():
        print(f" -> {entity}.csv: {info['fiches']} record(s), "
              f"{len(info['colonnes'])} column(s)")
    for entity, reason in rapport["ignorees"].items():
        print(f" ⚠️  {entity} was not exported: {reason}.")
    print(" ✅ Content exported to content/ — see content/LISEZMOI.txt.")

def cmd_content_import(project_dir):
    from ..content_tool import ContentToolError, importer_content
    spec_path = location._spec_of_project(project_dir)
    try:
        rapport = importer_content(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entity, info in rapport["entites"].items():
        print(f" -> {entity}: {info['fiches']} record(s) read")
    message = ("Spec revalidated by the compiler and content replaced."
               if rapport["spec_changee"]
               else "Content unchanged: the spec was not rewritten.")
    print(f" ✅ {message}")
    warnings = next(iter(rapport["entites"].values()), {}).get(
        "avertissements", [])
    for message in warnings:
        print(f" ⚠️  {message}")
