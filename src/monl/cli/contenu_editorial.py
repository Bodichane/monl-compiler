"""Les assets et le contenu éditorial, en ligne de commande."""

import os
import sys

from . import emplacement


def cmd_assets_add(project_dir, source, pour=None, cible=None, entity=None,
                   field=None, nom=None, force=False):
    from ..assets_tool import AssetsToolError, ajouter_asset
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = ajouter_asset(spec_path, project_dir, source, pour=pour,
                                cible=cible, entity=entity, field=field,
                                nom=nom, force=force)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    verbe = "already in place" if rapport["deja_en_place"] else \
            ("replaced" if rapport["ecrase"] else "copied")
    print(f" -> File {verbe}: {rapport['fichier']}")
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
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = lister_assets(spec_path, project_dir)
    except AssetsToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)

    print(f"─── Declared assets — directory '{rapport['dir']}/' ───")
    if not rapport["declares"]:
        print("  (the spec declares no assets: no 'Image' field, logo, or favicon)")
    for ligne in rapport["declares"]:
        marque = "✅" if ligne["present"] else "❌"
        octets = ligne["taille"]
        taille = "" if octets is None else (
            f" ({octets // 1024} KB)" if octets >= 1024 else f" ({octets} B)")
        ailleurs = (f" → {ligne['resolu']}"
                    if ligne["resolu"] and ligne["resolu"] != ligne["chemin"] else "")
        print(f"  {marque} {ligne['chemin']}{ailleurs}{taille}"
              f"   ← {', '.join(ligne['origines'])}")
    if rapport["orphelins"]:
        print(f"─── Present but undeclared ({len(rapport['orphelins'])}) ───")
        for chemin in rapport["orphelins"]:
            print(f"  ·  {chemin}")
        print("  (this is fine for a credits file or an image added by hand "
              "to a page: this report is informational, not a warning)")

def cmd_content_export(project_dir):
    from ..content_tool import ContentToolError, exporter_contenu
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = exporter_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite}.csv: {info['fiches']} record(s), "
              f"{len(info['colonnes'])} column(s)")
    for entite, raison in rapport["ignorees"].items():
        print(f" ⚠️  {entite} was not exported: {raison}.")
    print(" ✅ Content exported to content/ — see content/LISEZMOI.txt.")

def cmd_content_import(project_dir):
    from ..content_tool import ContentToolError, importer_contenu
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = importer_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite}: {info['fiches']} record(s) read")
    message = ("Spec revalidated by the compiler and content replaced."
               if rapport["spec_changee"]
               else "Content unchanged: the spec was not rewritten.")
    print(f" ✅ {message}")
    avertissements = next(iter(rapport["entites"].values()), {}).get(
        "avertissements", [])
    for message in avertissements:
        print(f" ⚠️  {message}")
