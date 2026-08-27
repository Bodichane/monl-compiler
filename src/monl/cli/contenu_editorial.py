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

    verbe = "déjà en place" if rapport["deja_en_place"] else \
            ("remplacé" if rapport["ecrase"] else "copié")
    print(f" -> Fichier {verbe} : {rapport['fichier']}")
    print(f" -> Déclaré dans   : {rapport['ou']} "
          f"(ligne {rapport['ligne']} de {os.path.basename(spec_path)})")
    if rapport["remplace"]:
        print(f" -> Remplace la valeur précédente : {rapport['remplace']}")
    print(" ✅ Spec revalidée par le compilateur : le chemin écrit existe.")
    if rapport["orphelin"]:
        print(f" ⚠️  '{rapport['orphelin']}' n'est plus déclaré par la spec. Le fichier "
              "est laissé en place : monl ne supprime pas un fichier fourni par vous.")
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

    print(f"─── Assets déclarés — dossier '{rapport['dir']}/' ───")
    if not rapport["declares"]:
        print("  (la spec ne déclare aucun asset : aucun champ 'Image', ni logo, ni favicon)")
    for ligne in rapport["declares"]:
        marque = "✅" if ligne["present"] else "❌"
        octets = ligne["taille"]
        taille = "" if octets is None else (
            f" ({octets // 1024} ko)" if octets >= 1024 else f" ({octets} o)")
        ailleurs = (f" → {ligne['resolu']}"
                    if ligne["resolu"] and ligne["resolu"] != ligne["chemin"] else "")
        print(f"  {marque} {ligne['chemin']}{ailleurs}{taille}"
              f"   ← {', '.join(ligne['origines'])}")
    if rapport["orphelins"]:
        print(f"─── Présents mais non déclarés ({len(rapport['orphelins'])}) ───")
        for chemin in rapport["orphelins"]:
            print(f"  ·  {chemin}")
        print("  (légitime pour un fichier de crédits ou une image posée à la main "
              "dans une page : ce rapport constate, il ne reproche rien)")

def cmd_content_export(project_dir):
    from ..content_tool import ContentToolError, exporter_contenu
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = exporter_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite}.csv : {info['fiches']} fiche(s), "
              f"{len(info['colonnes'])} colonne(s)")
    for entite, raison in rapport["ignorees"].items():
        print(f" ⚠️  {entite} non exportée : {raison}.")
    print(" ✅ Contenu exporté dans content/ — lire content/LISEZMOI.txt.")

def cmd_content_import(project_dir):
    from ..content_tool import ContentToolError, importer_contenu
    spec_path = emplacement._spec_du_projet(project_dir)
    try:
        rapport = importer_contenu(spec_path, project_dir)
    except ContentToolError as err:
        print(f" ❌ {err}")
        sys.exit(1)
    for entite, info in rapport["entites"].items():
        print(f" -> {entite} : {info['fiches']} fiche(s) lue(s)")
    message = ("Spec revalidée par le compilateur et contenu remplacé."
               if rapport["spec_changee"]
               else "Contenu inchangé : la spec n'a pas été réécrite.")
    print(f" ✅ {message}")
    avertissements = next(iter(rapport["entites"].values()), {}).get(
        "avertissements", [])
    for message in avertissements:
        print(f" ⚠️  {message}")
