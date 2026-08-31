"""Export et import du contenu de démonstration sans édition manuelle du DSL."""
import csv
import os
import re
from types import SimpleNamespace

from . import content_import
from .assets_tool import (
    DEFAULT_ASSETS_DIR,
    AssetsToolError,
    _blocs_seed,
    _charger,
    _litteral,
    _revalider,
    chemins_declares,
    resoudre_asset,
)
from .errors import ToolError


class ContentToolError(ToolError):
    pass


NUMERIQUES = {"Integer", "Float", "Money"}
ENTETE_PARENT = re.compile(
    r'^seed\s+(\w+)\s+for\s+(\w+)\.(\w+)\s+"([^"\\]*)"\s*(?:#.*)?$')
NOMBRE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _appeler(fonction, *args):
    try:
        return fonction(*args)
    except AssetsToolError as err:
        raise ContentToolError(str(err)) from None


def _exclus(normalized, entite):
    security = normalized.get("security", {})
    exclus = set()
    for cle in ("generated_fields", "derived_fields", "aggregated_fields",
                "timestamp_fields", "numbered_fields"):
        for item in security.get(cle) or []:
            if item.get("entity") == entite:
                exclus.add(item.get("field"))
    post = security.get("writable_after_payment") or {}
    valeur = post.get(entite, {}) if isinstance(post, dict) else {}
    exclus.update(valeur.get("fields", []) if isinstance(valeur, dict) else [])
    return exclus


def _infos_parent(lignes, blocs, entite):
    infos = []
    curseur = 0
    for i, ligne in enumerate(lignes):
        if not ligne.startswith("seed"):
            continue
        if curseur >= len(blocs):
            break
        nom, plages = blocs[curseur]
        curseur += 1
        if nom != entite:
            continue
        match = ENTETE_PARENT.match(ligne.rstrip("\n"))
        infos.append((i, plages, match.groups()[1:] if match else None))
    parents = [info for _i, _p, info in infos if info]
    if parents and len(parents) != len(infos):
        raise ContentToolError(
            f"Les blocs seed de {entite} mélangent des formes avec et sans parent. "
            "Les uniformiser à la main avant d'utiliser content.")
    if parents and len({p[:2] for p in parents}) != 1:
        raise ContentToolError(
            f"Les blocs seed de {entite} ne désignent pas tous le parent de la "
            "même façon. Les uniformiser à la main d'abord.")
    return infos, (parents[0][:2] if parents else None)


def _colonnes(normalized, entite, parent=False):
    champs = normalized["schema"]["entities"][entite]
    exclus = _exclus(normalized, entite)
    colonnes = (["_parent"] if parent else []) + [
        nom for nom, type_ in champs.items()
        if nom not in exclus and type_ not in ("Boolean", "Upload")
    ]
    return colonnes


def _valeur_csv(valeur, type_):
    if valeur is None:
        return ""
    if type_ == "Image" and isinstance(valeur, str):
        return os.path.basename(valeur)
    return str(valeur)


def _lisez_moi(normalized, exports, ignores):
    security = normalized.get("security", {})
    contraintes = security.get("field_constraints") or {}
    choix = security.get("enumerated_fields") or {}
    lignes = [
        "MODIFIER LE CONTENU\n",
        "\n",
        "Un fichier CSV correspond à une sorte de fiche. Gardez les noms de "
        "colonnes tels quels, puis lancez `monl content import`. Une cellule "
        "vide est volontairement absente de la fiche : les champs obligatoires "
        "seront refusés avec une explication.\n",
    ]
    for entite, info in exports.items():
        lignes.extend(["\n", f"{entite}.csv\n"])
        champs = normalized["schema"]["entities"][entite]
        for colonne in info["colonnes"]:
            if colonne == "_parent":
                texte = "la valeur d'une fiche de l'entité parente à laquelle rattacher cette ligne"
            else:
                details = []
                enum = choix.get(entite, {}).get(colonne)
                if enum:
                    details.append("valeurs permises : " + ", ".join(enum))
                regles = contraintes.get((entite, colonne), {})
                if regles.get("required"):
                    details.append("obligatoire")
                for borne in ("min", "max"):
                    if borne in regles:
                        details.append(f"{borne} {regles[borne]['valeur']}")
                if champs[colonne] == "Image":
                    details.append("déposer le fichier dans `assets/`, écrire uniquement son nom ici")
                texte = "; ".join(details) if details else "texte libre"
            lignes.append(f"- {colonne} : {texte}.\n")
        booleens = [n for n, t in champs.items() if t == "Boolean"]
        if booleens:
            lignes.append("  Champs booléens non proposés (le seed n'a pas de "
                          "littéral vrai/faux) : " + ", ".join(booleens) + ".\n")
    if ignores:
        lignes.extend(["\n", "Entités non exportées\n"])
        for entite, raison in ignores.items():
            lignes.append(f"- {entite} : {raison}\n")
    return "".join(lignes)


def exporter_contenu(spec_path, project_dir):
    normalized = _appeler(_charger, spec_path)
    with open(spec_path, encoding="utf-8") as fh:
        lignes = fh.readlines()
    blocs = _blocs_seed(lignes)
    entites_seedees = {entite for entite, _ in blocs}
    exports, ignores = {}, {}
    dossier = os.path.join(project_dir, "content")
    os.makedirs(dossier, exist_ok=True)
    for entite in normalized["schema"]["entities"]:
        if entite not in entites_seedees:
            ignores[entite] = ("aucun exemple seed ne fixe encore la forme du "
                                "contenu; écrire d'abord un exemple à la main")
            continue
        infos, parent = _infos_parent(lignes, blocs, entite)
        colonnes = _colonnes(normalized, entite, bool(parent))
        blocs_ast = [b for b in normalized.get("seeds", []) if b["entity"] == entite]
        if len(infos) != len(blocs_ast):
            raise ContentToolError(
                f"Les blocs seed de {entite} ne correspondent pas à la spec compilée.")
        chemin = os.path.join(dossier, f"{entite}.csv")
        fiches = 0
        with open(chemin, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=colonnes)
            writer.writeheader()
            for (_i, _plages, parent_info), bloc in zip(infos, blocs_ast, strict=True):
                for row in bloc["rows"]:
                    sortie = {}
                    if parent:
                        sortie["_parent"] = parent_info[2]
                    for nom in colonnes:
                        if nom != "_parent":
                            sortie[nom] = _valeur_csv(
                                row.get(nom), normalized["schema"]["entities"][entite][nom])
                    writer.writerow(sortie)
                    fiches += 1
        exports[entite] = {"fichier": chemin, "colonnes": colonnes, "fiches": fiches,
                            "parent": parent}
    readme = os.path.join(dossier, "LISEZMOI.txt")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write(_lisez_moi(normalized, exports, ignores))
    return {"entites": exports, "ignorees": ignores, "lisez_moi": readme}


def _lire_csv(chemin, colonnes):
    with open(chemin, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != colonnes:
            raise ContentToolError(
                f"{os.path.basename(chemin)} : colonnes attendues : {', '.join(colonnes)}; "
                f"colonnes reçues : {', '.join(reader.fieldnames or [])}.")
        return [(numero, dict(row)) for numero, row in enumerate(reader, 2)]


def _texte_fiche(entite, row, numero, types, dossier_assets):
    morceaux = []
    for nom, valeur in row.items():
        if nom == "_parent" or valeur == "":
            continue
        type_ = types[nom]
        if type_ in NUMERIQUES:
            if not NOMBRE.fullmatch(valeur):
                raise ContentToolError(
                    f"{entite}.csv ligne {numero} : '{valeur}' n'est pas un nombre "
                    f"valide pour la colonne {nom}.")
            literal = valeur
        else:
            if type_ == "Image" and (
                    os.path.basename(valeur) != valeur
                    or valeur in (".", "..")
                    or "/" in valeur
                    or "\\" in valeur):
                raise ContentToolError(
                    f"{entite}.csv ligne {numero} : la colonne {nom} attend un "
                    f"NOM de fichier seul, pas le chemin '{valeur}'.")
            try:
                literal = _litteral(
                    f"{dossier_assets}/{valeur}" if type_ == "Image" else valeur)
            except AssetsToolError as err:
                raise ContentToolError(
                    f"{entite}.csv ligne {numero}, colonne {nom} : {err}") from None
        morceaux.append(f"{nom}: {literal}")
    return "    " + ", ".join(morceaux) + "\n"


def _plages_blocs(lignes):
    resultat = []
    blocs = _blocs_seed(lignes)
    curseur = 0
    for i, ligne in enumerate(lignes):
        if curseur >= len(blocs):
            break
        if re.match(r"^seed\s+", ligne):
            entite, entrees = blocs[curseur]
            fin = entrees[-1][1] if entrees else i
            resultat.append((entite, i, fin))
            curseur += 1
    return resultat


def _seulement_espaces_commentaires(texte):
    return all(not ligne.strip() or ligne.lstrip().startswith("#")
               for ligne in texte.splitlines())


def _avertissements(project_dir, normalized, spec_changee):
    messages = []
    dossier, declares = chemins_declares(normalized)
    manquants = [c for c in sorted(declares)
                 if not resoudre_asset(project_dir, dossier, c)]
    if manquants:
        messages.append(f"{len(manquants)} asset(s) déclaré(s) reste(nt) absent(s) : "
                        + ", ".join(manquants) + ". 'monl assets list' fait le point.")
    if spec_changee and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append("La base existe déjà : le seed ne nourrit qu'une base NEUVE.")
    if spec_changee:
        messages.append("Spec modifiée : lancer 'monl update' pour resynchroniser backend et contrat.")
    return messages


def importer_contenu(spec_path, project_dir):
    return content_import.importer_contenu(
        spec_path, project_dir, SimpleNamespace(
            _appeler=_appeler,
            _charger=_charger,
            _blocs_seed=_blocs_seed,
            _infos_parent=_infos_parent,
            _colonnes=_colonnes,
            _lire_csv=_lire_csv,
            _revalider=_revalider,
            _seulement_espaces_commentaires=_seulement_espaces_commentaires,
            _plages_blocs=_plages_blocs,
            _litteral=_litteral,
            _valeur_csv=_valeur_csv,
            _texte_fiche=_texte_fiche,
            _avertissements=_avertissements,
            resoudre_asset=resoudre_asset,
            ContentToolError=ContentToolError,
            AssetsToolError=AssetsToolError,
            DEFAULT_ASSETS_DIR=DEFAULT_ASSETS_DIR,
        ))
