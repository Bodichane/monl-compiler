# ─────────────────────────────────────────────────────────────────────
# BRIQUE 13, COUCHE 2 (point 84) : l'OUTIL — 'monl assets add' / 'monl assets list'.
#
# Pourquoi cette couche vient EN SECOND, et pourquoi c'était la bonne
# décision : un outil qui écrit « assets/halo-rs.jpg » dans un seed automatise
# l'écriture d'une chaîne. Avant la couche 1 (point 83), personne ne vérifiait
# cette chaîne — l'outil aurait donc industrialisé la production d'images
# cassées, plus vite et plus proprement. La couche 1 d'abord, l'ergonomie
# ensuite.
#
# Le contrat de cet outil tient en une phrase : IL ÉCRIT, LE COMPILATEUR
# PROUVE. Chaque modification de la spec est reparsée et revalidée EN MÉMOIRE
# par le vrai parseur et le vrai validateur avant d'être écrite sur disque. Si
# la spec obtenue ne passe pas, rien n'est écrit et le fichier copié est retiré.
# C'est la même discipline que le dialogue guidé (« la spec produite est
# revalidée par le vrai parseur avant d'être écrite »), appliquée à une édition
# chirurgicale.
#
# La revalidation se fait SANS base_dir, et l'existence de ce que l'outil vient
# d'écrire est vérifiée à part, avec le résolveur du compilateur : c'est la
# portée juste, et elle a été trouvée en éprouvant l'outil, pas en le relisant
# (voir _valider). Valider toute la spec avec base_dir rendait `list` incapable
# de rapporter un asset manquant, et `add` inutilisable sur une spec à deux
# photos absentes.
#
# L'édition est TEXTUELLE, jamais un aller-retour parse → regénère : la spec
# d'un projet réel est plus qu'à moitié faite de commentaires, et ce sont eux
# qui expliquent les briques employées. Les perdre pour gagner trois lignes de
# code serait détruire la documentation du projet pour poser une photo.
#
# Ce que l'outil ne fait PAS, et pourquoi :
#   - il ne SUPPRIME rien. Remplacer la photo d'une fiche laisse l'ancien
#     fichier orphelin : il est SIGNALÉ, pas effacé. Effacer un fichier fourni
#     par l'humain n'est pas la décision d'un outil de déclaration.
#   - il n'écrit AUCUN crédit. « monl vérifie la complétude, jamais la
#     véracité » (point 83) : un champ d'attribution obligatoire et
#     invérifiable invite à l'inventer. En revanche, si le dossier porte déjà
#     un fichier de crédits, l'outil dit quand le nouveau fichier n'y figure
#     pas — c'est de la complétude, pas de la véracité.
#   - il ne recompile pas. 'monl update' reste le geste explicite qui propage
#     une évolution de spec, avec son rapport de delta à lire.
# ─────────────────────────────────────────────────────────────────────
import contextlib
import difflib
import hashlib
import io
import os
import re
import shutil
import unicodedata

from .ast_validator import DEFAULT_ASSETS_DIR, MonlAST, resoudre_asset
from .errors import ToolError
from .parser import parse_monl_string


class AssetsToolError(ToolError):
    pass


# Lettres que la décomposition Unicode NFKD ne sépare pas : sans cette table,
# « Sørlund » donne « srlund » et « Bæk » donne « bk » — un slug muet là où le
# nom était lisible. Le catalogue de SneakerLab porte déjà une maison nordique :
# le cas n'est pas théorique.
TRANSLITTERATIONS = {
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "þ": "th", "ð": "d",
    "đ": "d", "ł": "l", "ħ": "h", "ı": "i", "ŋ": "n", "ə": "e",
}

# Les mots qui ouvrent un bloc de premier niveau. Sert à placer un bloc
# 'assets' créé de toutes pièces : après l'en-tête du fichier (le nom de
# l'app et ses commentaires de tête), avant la première déclaration.
DEBUTS_DE_BLOC = ("entity", "relation", "actor", "rule", "workflow", "seed",
                  "landing", "ui", "capability", "custom", "assets")

# Noms de fichiers de crédits reconnus — convention de projet, pas format monl.
NOMS_DE_CREDITS = ("CREDITS.json", "CREDITS.md", "CREDITS.txt", "credits.json")


# ------------------------------------------------------------------ slug --
def sluggify(texte):
    """« Halo RS » → « halo-rs ». Un nom de fichier servi par un navigateur :
    minuscules, ASCII, tirets. Retourne "" si rien d'utilisable ne reste."""
    base = "".join(TRANSLITTERATIONS.get(c.lower(), c) for c in texte)
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


# ------------------------------------------------- lecture de la spec --
def _valider(texte, spec_path):
    """Le vrai parseur et le vrai validateur, SANS base_dir. Volontairement.

    C'est la portée exacte dont l'outil a besoin, et elle vient de la coupure
    forme/existence de la couche 1 : les contrôles de forme sont purs, donc ils
    s'appliquent ; la vérification d'EXISTENCE, non — et c'est ce qu'il faut.

    Deux raisons, toutes deux découvertes en éprouvant l'outil, pas en le
    relisant. `monl assets list` ne pouvait pas rapporter un asset manquant :
    charger la spec avec base_dir échouait sur ce manquant même, si bien que le
    rapport refusait de tourner dans le seul cas où il servait. Et `add` était
    inutilisable sur une spec qui déclare deux photos absentes — impossible
    d'en poser une, puisque l'autre faisait échouer la revalidation.

    L'existence de ce que l'outil ÉCRIT est vérifiée séparément, avec le même
    résolveur que le compilateur (`resoudre_asset`) : la garantie reste, elle
    est simplement énoncée juste. Le validateur affiche son audit de sécurité —
    déjà vu à la compilation : on l'étouffe."""
    with contextlib.redirect_stdout(io.StringIO()):
        raw = parse_monl_string(texte, file_path=spec_path)
        return MonlAST(raw).validate_and_audit()


def _charger(spec_path):
    """État de départ. Refuser tôt sur une spec déjà cassée n'est pas du zèle :
    sans ce contrôle, l'échec de la revalidation d'après édition ferait accuser
    l'outil d'un défaut qui existait avant lui."""
    with open(spec_path, encoding="utf-8") as fh:
        texte = fh.read()
    try:
        return _valider(texte, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"La spec ne compile pas en l'état : {err}\n"
            f"   L'outil refuse d'y écrire tant qu'elle est cassée — sinon "
            f"l'échec suivant semblerait venir de lui.") from None


def _revalider(texte, spec_path):
    """LE contrôle qui rend cet outil sûr : la spec obtenue est-elle valide ?

    Reparsée par le vrai parseur, revalidée par le vrai validateur — tous les
    refus du compilateur s'appliquent donc à ce que l'outil vient d'écrire.
    C'est ce qui fait que la couche 2 ne peut pas produire ce que la couche 1
    refuse."""
    try:
        return _valider(texte, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"Écriture ANNULÉE — la spec obtenue ne compilerait pas : {err}\n"
            f"   Ni la spec ni le dossier d'assets n'ont été modifiés.") from None


# ------------------------------------------- repérage dans le TEXTE --
def _chaine_ouverte(texte, ouvert):
    """Un littéral de chaîne reste-t-il ouvert à la fin de cette ligne ?

    `STRING_LITERAL` est compilé avec le drapeau /s et sa classe accepte le
    retour à la ligne : une valeur de seed PEUT donc tenir sur deux lignes, et
    le parseur l'accepte (vérifié, pas supposé). Hors chaîne, un « # » ouvre un
    commentaire : le reste de la ligne ne compte plus."""
    echap = False
    for c in texte:
        if ouvert:
            if echap:
                echap = False
            elif c == "\\":
                echap = True
            elif c == '"':
                ouvert = False
        elif c == '"':
            ouvert = True
        elif c == "#":
            break
    return ouvert


def _entrees_du_bloc(lignes, i_entete):
    """[(première ligne, dernière ligne)] par ENTRÉE du bloc indenté.

    Une plage, et pas un simple indice : une fiche de seed dont la description
    court sur deux lignes est UNE entrée. Compter les lignes aurait décalé
    toutes les fiches suivantes, et l'outil aurait écrit la photo sur la
    mauvaise — en silence, puisque la spec obtenue resterait compilable.

    Les lignes vides et les lignes de commentaire sont sautées, exactement
    comme le fait le parseur (`_strip_standalone_comment_lines`) : c'est ce qui
    permet de faire correspondre la n-ième entrée du fichier à la n-ième de
    l'AST. Une ligne non indentée termine le bloc — sauf en pleine chaîne, où
    l'indentation ne veut plus rien dire."""
    plages, debut, ouvert = [], None, False
    for j in range(i_entete + 1, len(lignes)):
        brute = lignes[j].rstrip("\n")
        if not ouvert:
            if not brute.strip():
                continue
            if not brute[:1].isspace():
                break
            if brute.lstrip().startswith("#"):
                continue
            debut = j
        ouvert = _chaine_ouverte(brute, ouvert)
        if not ouvert:
            plages.append((debut, j))
    return plages


def _remplacer_entree(lignes, plage, editeur):
    """Applique une édition à une entrée qui peut occuper PLUSIEURS lignes."""
    debut, fin = plage
    ancien = "".join(lignes[debut:fin + 1])
    nouveau, ancienne = editeur(ancien)
    return (lignes[:debut] + nouveau.splitlines(keepends=True) + lignes[fin + 1:],
            ancienne)


def _blocs_seed(lignes):
    """[(entité, [plages de lignes]), …] dans l'ordre du fichier.

    BRIQUE 21 (point 100) : l'en-tête accepte une désignation de parent
    (`seed Variant for Product.name "Chaise Ligne"`). Sans l'accepter ICI, cet
    outil sautait le bloc en silence alors que l'AST le contient : la
    correspondance fichier ↔ AST, sur laquelle repose tout l'écriture de photos,
    ne tenait plus. Toute brique qui change la FORME d'une ligne de spec
    contraint aussi les outils qui la lisent textuellement — c'est la leçon des
    points 95 et 96, appliquée hors du smoke test."""
    blocs = []
    for i, ligne in enumerate(lignes):
        m = re.match(
            r"^seed[ \t]+([A-Za-z_]\w*)"
            r"(?:[ \t]+for[ \t]+[A-Za-z_]\w*\.[A-Za-z_]\w*[ \t]+\"(?:[^\"\\]|\\.)*\")?"
            r"[ \t]*(#.*)?$",
            ligne.rstrip("\n"))
        if m:
            blocs.append((m.group(1), _entrees_du_bloc(lignes, i)))
    return blocs


def _bloc_assets(lignes):
    """(indice de l'en-tête, [plages des propriétés]) ou (None, [])."""
    for i, ligne in enumerate(lignes):
        if re.match(r"^assets[ \t]*(#.*)?$", ligne.rstrip("\n")):
            return i, _entrees_du_bloc(lignes, i)
    return None, []


def _separer_commentaire(corps):
    """Isole un commentaire de fin de ligne, en respectant les guillemets.

    La grammaire accepte `champ: "x"  # note`, et un descriptif peut contenir
    un « # ». Couper au premier dièse rencontré mutilerait le texte de
    l'humain — donc on suit l'état « dans une chaîne »."""
    dans_chaine = echap = False
    for i, c in enumerate(corps):
        if dans_chaine:
            if echap:
                echap = False
            elif c == "\\":
                echap = True
            elif c == '"':
                dans_chaine = False
        elif c == '"':
            dans_chaine = True
        elif c == "#":
            return corps[:i], corps[i:]
    return corps, ""


def _segments(corps):
    """Découpe une ligne de seed sur les virgules HORS chaîne.

    Un descriptif contient presque toujours une virgule : découper naïvement
    en ferait deux champs, et l'un des deux serait du texte libre."""
    parts, courant = [], ""
    dans_chaine = echap = False
    for c in corps:
        if dans_chaine:
            courant += c
            if echap:
                echap = False
            elif c == "\\":
                echap = True
            elif c == '"':
                dans_chaine = False
            continue
        if c == '"':
            dans_chaine = True
            courant += c
        elif c == ",":
            parts.append(courant)
            courant = ""
        else:
            courant += c
    parts.append(courant)
    return parts


def _litteral(valeur):
    """Un chemin d'asset en littéral de chaîne monl.

    Les caractères qui demanderaient un échappement sont REFUSÉS plutôt
    qu'échappés : un nom de fichier qui en contient n'a rien à faire dans une
    URL, et l'échappement entre couches de templating est exactement le piège
    déjà rencontré (surcharge de backslash, voir la méthode de travail)."""
    if any(c in valeur for c in '"\\\n\r'):
        raise AssetsToolError(
            f"'{valeur}' contient un guillemet, un backslash ou un retour à la "
            f"ligne : impossible à écrire dans la spec, et illisible dans une URL.")
    return f'"{valeur}"'


def _ecrire_paire(ligne, champ, valeur):
    """Remplace (ou ajoute en fin) `champ: "valeur"` dans une ligne de seed.

    Préserve l'indentation, l'ordre des autres champs, l'espacement d'origine
    et un éventuel commentaire de fin de ligne."""
    fin = "\n" if ligne.endswith("\n") else ""
    corps, commentaire = _separer_commentaire(ligne.rstrip("\n"))
    blancs = corps[len(corps.rstrip()):]
    corps = corps.rstrip()
    litteral = _litteral(valeur)
    segments = _segments(corps)
    ancienne = None
    for k, segment in enumerate(segments):
        cle, sep, val = segment.partition(":")
        if sep and cle.strip() == champ:
            prefixe = cle[:len(cle) - len(cle.lstrip())]
            ancienne = val.strip().strip('"') or None
            segments[k] = f"{prefixe}{champ}: {litteral}"
            break
    else:
        segments.append(f" {champ}: {litteral}")
    return ",".join(segments) + blancs + commentaire + fin, ancienne


def _poser_prop_assets(lignes, cle, valeur, dossier):
    """Écrit `logo:` ou `favicon:` dans le bloc 'assets', qu'il existe ou non.

    Créer le bloc absent fait partie du travail : renvoyer l'humain écrire
    quatre lignes à la main avant de pouvoir poser son logo, ce serait rendre
    l'outil inutile là où il sert le plus (un projet qui n'a pas encore
    d'assets)."""
    lignes = list(lignes)
    i_entete, proprietes = _bloc_assets(lignes)
    if i_entete is None:
        cible = next((i for i, ligne in enumerate(lignes)
                      if ligne[:1] and not ligne[:1].isspace()
                      and ligne.strip().split(" ")[0] in DEBUTS_DE_BLOC),
                     len(lignes))
        lignes[cible:cible] = [
            "# Fichiers fournis par l'humain (brique 13). Chaque chemin déclaré ici\n",
            "# est vérifié PRÉSENT à la compilation.\n",
            "assets\n",
            f'    dir: "{dossier}"\n',
            "\n",
        ]
        i_entete, proprietes = _bloc_assets(lignes)

    litteral = _litteral(valeur)
    for plage in proprietes:
        corps, commentaire = _separer_commentaire(
            "".join(lignes[plage[0]:plage[1] + 1]).rstrip("\n"))
        nom, sep, val = corps.partition(":")
        if sep and nom.strip() == cle:
            indent = nom[:len(nom) - len(nom.lstrip())]
            ancienne = val.strip().strip('"') or None
            remplacement = (f"{indent}{cle}: {litteral}"
                            + (f"  {commentaire}" if commentaire else "") + "\n")
            lignes[plage[0]:plage[1] + 1] = [remplacement]
            return lignes, plage[0], ancienne

    # Absente : posée à la fin du bloc, avec l'indentation de ses voisines.
    dernier = proprietes[-1][1] if proprietes else i_entete
    indent = "    "
    if proprietes:
        brute = lignes[proprietes[-1][0]]
        indent = brute[:len(brute) - len(brute.lstrip())]
    lignes.insert(dernier + 1, f"{indent}{cle}: {litteral}\n")
    return lignes, dernier + 1, None


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
            "Cette spec n'a aucun bloc 'seed' : rien à quoi rattacher une photo. "
            "Ajouter le bloc, ou viser --logo / --favicon.")
    # Filet : la correspondance fichier ↔ AST est ce sur quoi tout repose. Si
    # elle ne tient pas, s'arrêter vaut mieux qu'écrire sur une autre fiche —
    # une spec où la photo est sur la mauvaise ligne compile parfaitement.
    if (len(blocs_fichier) != len(blocs_ast)
            or any(f[0] != a["entity"] for f, a in zip(blocs_fichier, blocs_ast, strict=True))
            or any(len(f[1]) != len(a["rows"]) for f, a in zip(blocs_fichier, blocs_ast, strict=True))):
        raise AssetsToolError(
            "Les blocs 'seed' du fichier ne correspondent pas à ceux de la spec "
            "compilée (nombre de fiches différent). L'outil s'arrête plutôt que "
            "d'écrire sur une autre fiche que celle demandée.")

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
        indice = (" Peut-être : " + ", ".join(f"'{p}'" for p in proches)) if proches else ""
        raise AssetsToolError(
            f"Aucune ligne de seed ne porte la valeur '{pour}'"
            + (f" dans l'entité {entity}" if entity else "") + f".{indice}")
    if len(candidats) > 1:
        ou = ", ".join(f"{e} ligne {plage[0] + 1}" for e, plage, _ in candidats)
        raise AssetsToolError(
            f"'{pour}' désigne {len(candidats)} lignes ({ou}) : préciser --entity, "
            f"ou viser une valeur qui n'appartient qu'à une seule fiche.")

    ent, plage, _row = candidats[0]
    champs = normalized["schema"]["entities"].get(ent, {})
    images = [nom for nom, type_ in champs.items() if type_ == "Image"]
    if field:
        if champs.get(field) == "Image":
            return ent, field, plage
        if field in champs:
            raise AssetsToolError(
                f"{ent}.{field} est de type '{champs[field]}', pas 'Image' — seul ce "
                f"type fait vérifier le fichier à la compilation. "
                + (f"Champs 'Image' de {ent} : {', '.join(images)}." if images
                   else f"{ent} n'a aucun champ 'Image'."))
        raise AssetsToolError(f"{ent} n'a pas de champ '{field}'.")
    if not images:
        raise AssetsToolError(
            f"L'entité {ent} n'a aucun champ de type 'Image' : déclarer par exemple "
            f"'photo: Image' dans son bloc 'entity'. C'est ce type qui fait vérifier "
            f"le fichier présent à la compilation — un champ 'String' accepterait "
            f"n'importe quel chemin en silence.")
    if len(images) > 1:
        raise AssetsToolError(
            f"{ent} a plusieurs champs 'Image' ({', '.join(images)}) : préciser --field.")
    return ent, images[0], plage


def _nom_de_fichier(source, nom, pour, cible):
    if nom:
        if os.sep in nom or "/" in nom or nom.strip(".") == "":
            raise AssetsToolError(
                f"--as attend un NOM de fichier, pas un chemin : '{nom}'.")
        return nom
    racine = sluggify(pour or cible)
    if not racine:
        raise AssetsToolError(
            f"'{pour or cible}' ne donne aucun nom de fichier utilisable "
            f"(ni lettre ni chiffre) — préciser --as <nom>.")
    extension = os.path.splitext(source)[1].lower()
    if not extension:
        raise AssetsToolError(
            f"'{source}' n'a pas d'extension : servi tel quel, le navigateur ne "
            f"saurait pas de quel type de fichier il s'agit. Renommer la source, "
            f"ou donner --as <nom.ext>.")
    return racine + extension


def ajouter_asset(spec_path, project_dir, source, pour=None, cible=None,
                  entity=None, field=None, nom=None, force=False):
    """Copie un fichier dans le dossier d'assets et le DÉCLARE dans la spec.

    `pour` vise une ligne de seed par une de ses valeurs ; `cible` vaut 'logo'
    ou 'favicon'. Retourne un rapport (dict) — l'affichage appartient au CLI."""
    if bool(pour) == bool(cible):
        raise AssetsToolError(
            "Préciser la destination : --for \"<valeur>\" pour une fiche de seed, "
            "ou --logo / --favicon.")
    if not os.path.isfile(source):
        raise AssetsToolError(f"'{source}' n'existe pas, ou n'est pas un fichier.")

    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    dossier = (normalized.get("assets") or {}).get("dir") or DEFAULT_ASSETS_DIR
    fichier = _nom_de_fichier(source, nom, pour, cible)

    with open(spec_path, encoding="utf-8") as fh:
        lignes = fh.readlines()

    if cible:
        # Le logo se déclare par son SEUL nom : c'est le contrat frontend qui
        # préfixe par le dossier (_assets_contract). Écrire 'assets/logo.svg'
        # ici donnerait '/site/assets/assets/logo.svg' au navigateur.
        valeur = fichier
        nouvelles, i_ligne, ancienne = _poser_prop_assets(lignes, cible, valeur, dossier)
        ou, entite, champ = f"assets.{cible}", None, None
    else:
        entite, champ, plage = _resoudre_seed(normalized, lignes, pour, entity, field)
        # Une valeur de seed est l'URL que le navigateur demandera : elle porte
        # donc le dossier.
        valeur = f"{dossier}/{fichier}"
        nouvelles, ancienne = _remplacer_entree(
            lignes, plage, lambda texte: _ecrire_paire(texte, champ, valeur))
        i_ligne = plage[0]
        ou = f"{entite}.{champ}"

    destination = os.path.join(project_dir, dossier, fichier)
    sur_place = os.path.abspath(destination) == os.path.abspath(source)
    existait = os.path.exists(destination)
    identique = existait and _sha256(destination) == _sha256(source)
    if existait and not identique and not sur_place and not force:
        raise AssetsToolError(
            f"'{dossier}/{fichier}' existe déjà avec un contenu DIFFÉRENT. "
            f"Relancer avec --force pour l'écraser, ou choisir --as <autre-nom>.")

    sauvegarde = None
    try:
        if not sur_place and not identique:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if existait:
                # Écraser sous --force reste réversible le temps de la
                # revalidation : sans cette copie, un refus du compilateur
                # laisserait l'ancien fichier détruit pour rien.
                sauvegarde = destination + ".monl-precedent"
                shutil.copy2(destination, sauvegarde)
            shutil.copy2(source, destination)
        texte = "".join(nouvelles)
        apres = _revalider(texte, spec_path)
        # LA garantie de la couche 2, énoncée précisément : ce que l'outil vient
        # d'écrire résout-il vers un vrai fichier ? Vérifié avec le résolveur du
        # COMPILATEUR (resoudre_asset), pas avec une seconde implémentation qui
        # finirait par diverger. Cette vérification est ciblée sur notre écriture
        # et non sur toute la spec : sinon un autre asset manquant rendrait
        # l'outil inutilisable là où il sert justement à en poser un.
        if not resoudre_asset(project_dir, dossier, valeur):
            raise AssetsToolError(
                f"Écriture ANNULÉE — '{valeur}' ne résout vers aucun fichier une "
                f"fois écrit. C'est exactement ce que la couche 1 refuse à la "
                f"compilation, et l'outil ne doit pas le produire.")
        # Redéclarer ce qui l'est déjà ne doit rien écrire : réécrire un texte
        # identique invaliderait l'empreinte de 'monl run --check' pour rien.
        spec_changee = texte != "".join(lignes)
        if spec_changee:
            with open(spec_path, "w", encoding="utf-8") as fh:
                fh.write(texte)
    except Exception:
        if sauvegarde and os.path.exists(sauvegarde):
            shutil.move(sauvegarde, destination)
            sauvegarde = None
        elif not existait and not sur_place and os.path.exists(destination):
            os.remove(destination)
        raise
    finally:
        if sauvegarde and os.path.exists(sauvegarde):
            os.remove(sauvegarde)

    return {
        "fichier": f"{dossier}/{fichier}",
        "valeur": valeur,
        "ou": ou,
        "entite": entite,
        "champ": champ,
        "ligne": i_ligne + 1,
        "ecrase": bool(existait and not identique and not sur_place),
        "deja_en_place": sur_place or identique,
        "remplace": ancienne if ancienne and ancienne != valeur else None,
        "spec_changee": spec_changee,
        "orphelin": _orphelin(ancienne, valeur, apres, project_dir),
        "avertissements": _avertissements(project_dir, dossier, fichier, spec_changee,
                                          apres, valeur, seed=cible is None),
    }


def _orphelin(ancienne, valeur, normalized, project_dir):
    """L'ancien fichier est-il devenu orphelin ? SIGNALÉ, jamais supprimé.

    Décision assumée : un fichier déposé par l'humain ne s'efface pas sur la
    déduction d'un outil de déclaration. Il peut servir ailleurs — le frontend
    de SneakerLab référence en dur trois photos que la spec ignore."""
    if not ancienne or ancienne == valeur:
        return None
    dossier, declares = chemins_declares(normalized)
    if ancienne in declares:
        return None
    if not resoudre_asset(project_dir, dossier, ancienne):
        return None
    return ancienne


def _avertissements(project_dir, dossier, fichier, spec_changee, normalized,
                    valeur, seed):
    """Ce que la réussite n'implique PAS. Des pièges vécus, pas des hypothèses."""
    messages = []
    # 0. Poser une photo ne rend pas le projet compilable : les AUTRES assets
    # déclarés et absents le bloquent toujours. L'outil ne vérifie que ce qu'il
    # écrit (voir _valider) — il doit donc dire ce qui manque encore, sinon
    # 'monl update' échouerait sans qu'on sache pourquoi.
    _dossier, declares = chemins_declares(normalized)
    manquants = [c for c in sorted(declares)
                 if c != valeur and not resoudre_asset(project_dir, dossier, c)]
    if manquants:
        messages.append(
            f"{len(manquants)} autre(s) asset déclaré(s) reste(nt) absent(s) : "
            + ", ".join(manquants)
            + ". La compilation les refusera — 'monl assets list' fait le point.")
    # 1. Le seed ne nourrit qu'une base NEUVE. La migration de SneakerLab à la
    # couche 1 l'a montré : 12 fiches gardaient l'ancien chemin, et le site
    # aurait affiché 12 cadres vides sans que rien ne le signale. Ne concerne
    # QUE l'édition d'un seed : le dire en posant un logo serait un
    # avertissement hors sujet, et un avertissement hors sujet apprend à les
    # ignorer tous.
    if seed and spec_changee and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append(
            "La base existe déjà : le bloc 'seed' ne nourrit qu'une base NEUVE. "
            "Les fiches déjà enregistrées gardent leur ancienne valeur — les "
            "corriger via l'API (PUT) ou repartir d'une base vide.")
    # 2. Crédits : complétude, jamais véracité (point 83).
    for candidat in NOMS_DE_CREDITS:
        chemin = os.path.join(project_dir, dossier, candidat)
        if not os.path.exists(chemin):
            continue
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            if fichier not in fh.read():
                messages.append(
                    f"{dossier}/{candidat} ne mentionne pas '{fichier}'. monl ne "
                    f"peut pas vérifier une attribution, seulement constater "
                    f"qu'elle manque.")
        break
    # 3. La spec a changé : les artefacts ne l'ont pas suivie.
    if spec_changee:
        messages.append("Spec modifiée : lancer 'monl update' pour resynchroniser "
                        "backend et contrat.")
    return messages


# ----------------------------------------------------------------- list --
def lister_assets(spec_path, project_dir):
    """Ce que la spec déclare, ce qui est présent, ce qui traîne sans être déclaré."""
    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    dossier, declares = chemins_declares(normalized)

    lignes, resolus = [], set()
    for chemin in sorted(declares):
        trouve = resoudre_asset(project_dir, dossier, chemin)
        if trouve:
            resolus.add(os.path.realpath(trouve))
        lignes.append({
            "chemin": chemin,
            "origines": declares[chemin],
            "present": bool(trouve),
            # Un logo est déclaré par son seul nom : dire OÙ il a été trouvé
            # évite de laisser croire qu'il vit à la racine du projet.
            "resolu": os.path.relpath(trouve, project_dir) if trouve else None,
            "taille": os.path.getsize(trouve) if trouve else None,
        })

    # « Orphelin » n'est pas un reproche : un fichier de crédits, ou une photo
    # posée en dur dans une page du frontend, vit légitimement ici sans que la
    # spec la déclare. Le rapport constate, il ne juge pas.
    racine = os.path.join(project_dir, dossier)
    orphelins = []
    if os.path.isdir(racine):
        for base, _sous, fichiers in os.walk(racine):
            for nom in fichiers:
                chemin = os.path.join(base, nom)
                if os.path.realpath(chemin) not in resolus:
                    orphelins.append(os.path.relpath(chemin, project_dir))
    return {"dir": dossier, "declares": lignes, "orphelins": sorted(orphelins)}


def _sha256(chemin):
    with open(chemin, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
