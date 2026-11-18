"""TEXTUAL editing of the spec, line by line.

Never a parse → regenerate round trip: a real project's spec is more than
half comments, and they are what explains the bricks used."""

import re

from .fondations import DEBUTS_DE_BLOC, AssetsToolError


# ------------------------------------------- locating in the TEXT --
def _chaine_ouverte(texte, ouvert):
    """Is a string literal still open at the end of this line?

    `STRING_LITERAL` is compiled with the /s flag and its class accepts line
    breaks: a seed value CAN therefore span two lines, and the parser accepts
    it (checked, not assumed). Outside a string, a "#" opens a comment: the
    rest of the line no longer counts."""
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
    """[(first line, last line)] per ENTRY of the indented block.

    A range, not a plain index: a seed item whose description runs over two
    lines is ONE entry. Counting lines would have shifted every following
    item, and the tool would have written the photo on the wrong one —
    silently, since the resulting spec would stay compilable.

    Empty lines and comment lines are skipped, exactly as the parser does
    (`_strip_standalone_comment_lines`): that is what lets the file's n-th
    entry match the AST's n-th. A non-indented line ends the block — except
    in the middle of a string, where indentation no longer means anything."""
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
    """Applies an edit to an entry that may span SEVERAL lines."""
    debut, fin = plage
    ancien = "".join(lignes[debut:fin + 1])
    nouveau, ancienne = editeur(ancien)
    return (lignes[:debut] + nouveau.splitlines(keepends=True) + lignes[fin + 1:],
            ancienne)

def _blocs_seed(lignes):
    """[(entity, [line ranges]), …] in file order.

    BRICK 21 (point 100): the header accepts a parent designation (`seed
    Variant for Product.name "Chaise Ligne"`). Without accepting it HERE, this
    tool silently skipped the block while the AST contains it: the file ↔ AST
    match, on which all photo writing rests, no longer held. Any brick that
    changes the SHAPE of a spec line also constrains the tools that read it
    textually — the lesson of points 95 and 96, applied outside the smoke
    test."""
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
    """(header index, [property ranges]) or (None, [])."""
    for i, ligne in enumerate(lignes):
        if re.match(r"^assets[ \t]*(#.*)?$", ligne.rstrip("\n")):
            return i, _entrees_du_bloc(lignes, i)
    return None, []

def _separer_commentaire(corps):
    """Isolates an end-of-line comment, respecting quotes.

    The grammar accepts `field: "x"  # note`, and a description can contain a
    "#". Cutting at the first hash met would mutilate the human's text — so
    the "inside a string" state is tracked."""
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
    """Splits a seed line on the commas OUTSIDE strings.

    A description almost always contains a comma: splitting naively would
    make two fields of it, and one of the two would be free text."""
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
    """An asset path as a monl string literal.

    Characters that would require escaping are REFUSED rather than escaped: a
    file name containing them has no business in a URL, and escaping across
    templating layers is exactly the trap already met (backslash
    over-escaping, see the working method)."""
    if any(c in valeur for c in '"\\\n\r'):
        raise AssetsToolError(
            f"'{valeur}' contains a quote, backslash, or newline: it cannot be "
            f"written to the spec and would be unreadable in a URL.")
    return f'"{valeur}"'

def _ecrire_paire(ligne, champ, valeur):
    """Replaces (or appends) `field: "value"` in a seed line.

    Preserves the indentation, the order of the other fields, the original
    spacing and any end-of-line comment."""
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
    """Writes `logo:` or `favicon:` in the 'assets' block, whether it exists or
    not.

    Creating the missing block is part of the job: sending the human to write
    four lines by hand before they can place their logo would make the tool
    useless where it serves most (a project that has no assets yet)."""
    lignes = list(lignes)
    i_entete, proprietes = _bloc_assets(lignes)
    if i_entete is None:
        cible = next((i for i, ligne in enumerate(lignes)
                      if ligne[:1] and not ligne[:1].isspace()
                      and ligne.strip().split(" ")[0] in DEBUTS_DE_BLOC),
                     len(lignes))
        lignes[cible:cible] = [
            "# Files supplied by the human (brick 13). Each path declared here\n",
            "# is checked PRESENT at compilation.\n",
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

    # Missing: placed at the end of the block, with its neighbors' indentation.
    dernier = proprietes[-1][1] if proprietes else i_entete
    indent = "    "
    if proprietes:
        brute = lignes[proprietes[-1][0]]
        indent = brute[:len(brute) - len(brute.lstrip())]
    lignes.insert(dernier + 1, f"{indent}{cle}: {litteral}\n")
    return lignes, dernier + 1, None
