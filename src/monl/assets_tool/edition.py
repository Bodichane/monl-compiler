"""L'édition TEXTUELLE de la spec, ligne à ligne.

Jamais un aller-retour parse → regénère : la spec d'un projet réel est
plus qu'à moitié faite de commentaires, et ce sont eux qui expliquent les
briques employées."""

import re

from .fondations import DEBUTS_DE_BLOC, AssetsToolError


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
