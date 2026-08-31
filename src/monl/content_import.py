"""Étapes nommées de l'import du contenu CSV dans la spec."""

import itertools
import os
import re


def _attendues(tool, normalized, entite, types, infos, parent, colonnes):
    attendues = []
    blocs = [b for b in normalized.get("seeds", []) if b["entity"] == entite]
    for (_i, _plages, parent_info), bloc in zip(infos, blocs, strict=True):
        for ast_row in bloc["rows"]:
            attendu = {"_parent": parent_info[2]} if parent else {}
            for nom in colonnes:
                if nom != "_parent":
                    attendu[nom] = tool._valeur_csv(ast_row.get(nom), types[nom])
            attendues.append(attendu)
    return attendues


def _texte_seed_avec_parent(tool, entite, rows, types, dossier_assets, parent):
    morceaux, precedent = [], object()
    for numero, row in rows:
        parent_value = row.get("_parent")
        if parent_value != precedent:
            try:
                valeur = tool._litteral(parent_value)
            except tool.AssetsToolError as err:
                raise tool.ContentToolError(
                    f"{entite}.csv ligne {numero}, colonne _parent : {err}") from None
            morceaux.append(f"seed {entite} for {parent[0]}.{parent[1]} {valeur}\n")
            precedent = parent_value
        morceaux.append(tool._texte_fiche(
            entite, row, numero, types, dossier_assets))
    return "".join(morceaux)


def _nouveau_seed(tool, entite, rows, types, dossier_assets, parent):
    if parent:
        return _texte_seed_avec_parent(
            tool, entite, rows, types, dossier_assets, parent)
    morceaux, precedent = [], object()
    for numero, row in rows:
        if precedent.__class__ is object:
            morceaux.append(f"seed {entite}\n")
            precedent = None
        morceaux.append(tool._texte_fiche(
            entite, row, numero, types, dossier_assets))
    return "".join(morceaux)


def _zone_des_seeds(tool, lignes, entite):
    existants = [p for p in tool._plages_blocs(lignes) if p[0] == entite]
    if existants:
        for gauche, droite in itertools.pairwise(existants):
            entre = "".join(lignes[gauche[2] + 1:droite[1]])
            if not tool._seulement_espaces_commentaires(entre):
                raise tool.ContentToolError(
                    f"Les blocs seed de {entite} ne sont pas contigus. Les "
                    "regrouper à la main avant l'import.")
        return existants[0][1], existants[-1][2], True
    tous = tool._plages_blocs(lignes)
    if tous:
        debut = fin = tous[-1][2] + 1
    else:
        debut = next((i for i, li in enumerate(lignes)
                      if re.match(r"^workflow\s+", li)), len(lignes))
        fin = debut
    return debut, fin, False


def _entite_import(tool, normalized, lignes, blocs, entite, types,
                   dossier_content, dossier_assets):
    chemin = os.path.join(dossier_content, f"{entite}.csv")
    if not os.path.isfile(chemin):
        return None
    infos, parent = tool._infos_parent(lignes, blocs, entite)
    colonnes = tool._colonnes(normalized, entite, bool(parent))
    rows = tool._lire_csv(chemin, colonnes)
    if "_parent" in colonnes and any(not row["_parent"] for _n, row in rows):
        numero = next(n for n, row in rows if not row["_parent"])
        raise tool.ContentToolError(
            f"{entite}.csv ligne {numero} : la colonne _parent est vide.")
    attendues = _attendues(
        tool, normalized, entite, types, infos, parent, colonnes)
    nouveau = _nouveau_seed(tool, entite, rows, types, dossier_assets, parent)
    debut, fin, remplace = _zone_des_seeds(tool, lignes, entite)
    operation = None
    if [row for _numero, row in rows] != attendues:
        operation = (debut, fin, nouveau, entite, rows, remplace)
    return operation, {"fiches": len(rows)}


def _images_importees(tool, project_dir, normalized, rapports,
                      lignes, blocs, dossier_content, dossier_assets):
    for entite in rapports:
        chemin = os.path.join(dossier_content, f"{entite}.csv")
        infos, parent = tool._infos_parent(lignes, blocs, entite)
        rows = tool._lire_csv(
            chemin, tool._colonnes(normalized, entite, bool(parent)))
        types = normalized["schema"]["entities"][entite]
        for numero, row in rows:
            for nom, type_ in types.items():
                valeur = row.get(nom, "")
                if type_ == "Image" and valeur:
                    asset = f"{dossier_assets}/{valeur}"
                    if not tool.resoudre_asset(project_dir, dossier_assets, asset):
                        raise tool.ContentToolError(
                            f"{entite}.csv ligne {numero} : le fichier image "
                            f"'{valeur}' est introuvable dans {dossier_assets}/.")


def importer_contenu(spec_path, project_dir, tool):
    normalized = tool._appeler(tool._charger, spec_path)
    with open(spec_path, encoding="utf-8") as fh:
        original = fh.read()
    lignes = original.splitlines(keepends=True)
    blocs = tool._blocs_seed(lignes)
    dossier_content = os.path.join(project_dir, "content")
    dossier_assets = (normalized.get("assets") or {}).get("dir") or tool.DEFAULT_ASSETS_DIR
    operations, rapports = [], {}
    for entite, types in normalized["schema"]["entities"].items():
        resultat = _entite_import(
            tool, normalized, lignes, blocs, entite, types,
            dossier_content, dossier_assets)
        if resultat:
            operation, rapport = resultat
            if operation:
                operations.append(operation)
            rapports[entite] = rapport
    texte_lignes = list(lignes)
    for debut, fin, nouveau, _entite, _rows, remplace in sorted(
            operations, reverse=True):
        texte_lignes[debut:fin + 1 if remplace else debut] = (
            nouveau.splitlines(keepends=True))
    texte = "".join(texte_lignes)
    apres = tool._appeler(tool._revalider, texte, spec_path)
    _images_importees(
        tool, project_dir, normalized, rapports, lignes, blocs,
        dossier_content, dossier_assets)
    changee = texte != original
    if changee:
        with open(spec_path, "w", encoding="utf-8") as fh:
            fh.write(texte)
    avertissements = tool._avertissements(project_dir, apres, changee)
    for rapport in rapports.values():
        rapport.update({"spec_changee": changee, "avertissements": avertissements})
    return {"entites": rapports, "spec_changee": changee}
