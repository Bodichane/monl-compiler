#!/usr/bin/env python3
"""Vectoriser le logo À DEUX COULEURS, et PROUVER le tracé en le re-rendant.

    python3 outils/vectoriser_logo.py [artwork]

Le logo est fait de trois couches concentriques, mesurées sur l'artwork et non
supposées : un ANNEAU ORANGE (le grand « O »), un ANNEAU CRÈME niché dedans
(le vrai « o » du mot), et le fond qui se voit au centre. Les deux anneaux
sont donc des tracés à TROU — `fill-rule="evenodd"` — et le fond n'est jamais
peint : c'est la page qui se voit au travers, sans quoi le logo porterait un
rectangle sombre sur un thème clair (le défaut qui avait fait vectoriser la
bannière plutôt que la servir en `<img>`).

Les couches se séparent par la couleur la plus PROCHE parmi les trois relevées
dans l'artwork, jamais par un seuil sur un canal : le liseré antialiasé se
range alors du côté dont il est le plus près, au lieu de disparaître ou de
grossir les deux couches à la fois.

Ce fichier n'écrit AUCUNE couleur dans `brand.py` — c'est `theme.py` qui
compose, et un test l'exige.
"""

import pathlib
import re
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tracage import (  # noqa: E402
    RACINE, contours, envelopper, lisser, normaliser, redimensionner, simplifier,
)

FACTEUR = 4            # l'artwork fait déjà 2000 px : inutile de suréchantillonner plus
EPSILON = 3.0          # tolérance de simplification, en pixels du rendu agrandi
ECART_MAXIMAL = 6.0    # % de pixels discordants tolérés, comme pour la bannière
BOUCLE_MINIMALE = 40   # une boucle plus courte est du bruit de seuillage


def _releve(image, echantillon=4):
    """Les trois couleurs de l'artwork : fond, crème, orange.

    Relevées PLUTÔT que codées en dur — un artwork réexporté par l'outil de
    design change de quelques unités, et un seuil écrit à la main cesserait
    alors de séparer quoi que ce soit sans rien dire.
    """
    from collections import Counter
    petit = image.convert("RGB").resize(
        (image.width // echantillon, image.height // echantillon), Image.NEAREST)
    frequentes = [c for _, c in
                  sorted(((n, c) for c, n in Counter(petit.getdata()).items()),
                         reverse=True)]
    fond = frequentes[0]

    def eloignees(reference, mini):
        for couleur in frequentes:
            if sum((a - b) ** 2 for a, b in zip(couleur, reference)) ** .5 > mini:
                yield couleur

    encres = []
    for couleur in eloignees(fond, 60):
        if all(sum((a - b) ** 2 for a, b in zip(couleur, deja)) ** .5 > 60
               for deja in encres):
            encres.append(couleur)
        if len(encres) == 2:
            break
    if len(encres) != 2:
        raise SystemExit(f"deux encres attendues, {len(encres)} trouvée(s) : {encres}")
    # La plus claire est le texte, l'autre l'anneau.
    encres.sort(key=lambda c: sum(c), reverse=True)
    return fond, encres[0], encres[1]


def _boite(image, fond, marge=6):
    px = image.convert("RGB").load()
    xs, ys = [], []
    for y in range(0, image.height, 2):
        for x in range(0, image.width, 2):
            if sum((a - b) ** 2 for a, b in zip(px[x, y], fond)) ** .5 > 40:
                xs.append(x)
                ys.append(y)
    return (max(0, min(xs) - marge), max(0, min(ys) - marge),
            min(image.width, max(xs) + marge), min(image.height, max(ys) + marge))


def _sv(couleur):
    """Saturation et valeur, sans passer par colorsys (appelé des millions de fois)."""
    haut, bas = max(couleur), min(couleur)
    return (0.0 if haut == 0 else (haut - bas) / haut), haut / 255.0


def classer(image, boite, palette, facteur=FACTEUR):
    """Range chaque pixel en 0 = fond, 1 = crème, 2 = orange.

    PAS par la couleur la plus proche : mesuré, le bord antialiasé d'une lettre
    crème sur le fond sombre passe par des demi-tons qui sont, en distance RGB,
    plus près de l'orange que des deux couleurs dont ils viennent — chaque
    lettre récoltait donc un liseré orange, et la couche orange sortait en
    quatorze morceaux au lieu de deux.

    La saturation, elle, sépare franchement : le bord crème→fond tombe à 0,074
    quand le bord orange→fond tient 0,650. Les deux seuils sont DÉRIVÉS des
    couleurs relevées (moitié de la saturation de l'anneau, milieu des valeurs
    fond/crème), jamais écrits à la main : un artwork réexporté un peu
    différemment reste séparé sans qu'on y retouche.
    """
    fond, creme, orange = palette
    seuil_saturation = _sv(orange)[0] / 2
    seuil_valeur = (_sv(fond)[1] + _sv(creme)[1]) / 2

    # BILINEAR et surtout PAS Lanczos : mesuré, le dépassement de Lanczos aux
    # bords francs fabrique des pixels artificiellement saturés, et le seuil de
    # saturation les prenait pour de l'orange — la couche sortait en 52 morceaux
    # au lieu de 4, chaque lettre crème portant un liseré. Un filtre qui
    # « améliore » l'image invente de la matière que le tracé recopie ensuite.
    grand = image.crop(boite).convert("RGB")
    grand = grand.resize((grand.width * facteur, grand.height * facteur), Image.BILINEAR)
    px = grand.load()
    L, H = grand.size
    etiquettes = []
    for y in range(H):
        ligne = []
        for x in range(L):
            saturation, valeur = _sv(px[x, y])
            if saturation >= seuil_saturation:
                ligne.append(2)
            elif valeur >= seuil_valeur:
                ligne.append(1)
            else:
                ligne.append(0)
        etiquettes.append(ligne)
    return etiquettes, L, H


def masque_couleur(image, boite, palette, indice, facteur=FACTEUR):
    """Masque binaire d'une couche, par la classification ci-dessous."""
    etiquettes, L, H = classer(image, boite, palette, facteur)
    return [[1 if e == indice else 0 for e in ligne] for ligne in etiquettes], L, H


def tracer_couche(image, boite, palette, indice):
    masque, L, H = masque_couleur(image, boite, palette, indice)
    morceaux = [lisser(simplifier(boucle, EPSILON))
                for boucle in contours(masque, L, H)
                if len(boucle) > BOUCLE_MINIMALE]
    return "".join(morceaux), masque, L, H


def _rendre(chemins_et_couleurs, L, H, fond):
    """Rend le SVG obtenu, pour le comparer à l'artwork."""
    import io
    corps = "".join(
        f'<path d="{d}" fill="rgb{couleur}" fill-rule="evenodd"/>'
        for d, couleur in chemins_et_couleurs)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{L}" height="{H}" '
           f'viewBox="0 0 {L} {H}"><rect width="{L}" height="{H}" '
           f'fill="rgb{fond}"/>{corps}</svg>')
    try:
        import cairosvg
    except ImportError:
        return None, svg
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))), svg


def _ecart(masque_attendu, chemin, L, H):
    """% de pixels où le tracé re-rasterisé s'écarte du masque d'origine.

    Les sous-chemins sont combinés en OU EXCLUSIF, jamais empilés : c'est la
    règle `evenodd`, celle avec laquelle le SVG sera rendu. Empilés, le trou
    d'un anneau se remplissait et la mesure accusait le tracé de 8 % d'écart
    alors qu'elle mesurait sa propre erreur.
    """
    from PIL import ImageDraw
    rendu = Image.new("1", (L, H), 0)
    for sous in chemin.split("M")[1:]:
        points = [float(n) for n in re.findall(r"-?\d+\.?\d*", "M" + sous)]
        if len(points) < 6:
            continue
        couche = Image.new("1", (L, H), 0)
        ImageDraw.Draw(couche).polygon(
            list(zip(points[0::2], points[1::2])), fill=1, outline=1)
        from PIL import ImageChops
        rendu = ImageChops.logical_xor(rendu, couche)
    px = rendu.load()
    discordants = sum(1 for y in range(H) for x in range(L)
                      if bool(px[x, y]) != bool(masque_attendu[y][x]))
    return 100.0 * discordants / (L * H)


def _bbox(boucle):
    xs = [p[0] for p in boucle]
    ys = [p[1] for p in boucle]
    return min(xs), min(ys), max(xs), max(ys)


def _boucles_du_o(etiquettes, L, H):
    """Les deux boucles crème du « o », reconnues par leur POSITION.

    Reconnues et non comptées : l'ordre des contours suit le balayage, il
    changerait au moindre recadrage. Le « o » est la seule lettre entièrement
    contenue dans l'emprise de l'anneau orange — c'est ce qui la désigne.
    """
    orange = [[1 if e == 2 else 0 for e in ligne] for ligne in etiquettes]
    creme = [[1 if e == 1 else 0 for e in ligne] for ligne in etiquettes]
    boucles_orange = [b for b in contours(orange, L, H) if len(b) > BOUCLE_MINIMALE]
    if not boucles_orange:
        raise SystemExit("aucun anneau orange : l'artwork a changé de nature")
    ox0, oy0, ox1, oy1 = _bbox(max(boucles_orange, key=len))

    dedans = [b for b in contours(creme, L, H)
              if len(b) > BOUCLE_MINIMALE
              and (lambda x0, y0, x1, y1: x0 >= ox0 and x1 <= ox1
                   and y0 >= oy0 and y1 <= oy1)(*_bbox(b))]
    if len(dedans) != 2:
        raise SystemExit(
            f"le « o » crème devrait donner 2 boucles, {len(dedans)} trouvée(s)")
    return dedans


def _normaliser_ensemble(chemins, cible, marge):
    """Normalise plusieurs tracés avec UNE SEULE transformation.

    Normalisés séparément, chacun serait centré sur sa propre emprise et les
    deux anneaux cesseraient d'être concentriques.
    """
    # Séparateur « | » et surtout pas l'espace : les tracés en contiennent
    # partout, et couper à la première espace tranchait au milieu du premier
    # chemin. `normaliser` ne réécrit que les NOMBRES, donc la barre traverse
    # intacte. Chaque commande porte un nombre PAIR de coordonnées (M et L en
    # prennent 2, Q en prend 4), ce qui garde l'alternance x/y d'un tracé au
    # suivant.
    joint = normaliser("|".join(chemins), cible, marge)
    morceaux = joint.split("|")
    if len(morceaux) != len(chemins):
        raise SystemExit("la normalisation conjointe a perdu un tracé")
    return morceaux


def principal(argv):
    source = pathlib.Path(argv[1] if len(argv) > 1
                          else RACINE / "docs" / "brand" / "monl-logo-source.png")
    if not source.exists():
        raise SystemExit(f"artwork introuvable : {source}")
    image = Image.open(source)
    fond, creme, orange = _releve(image)
    boite = _boite(image, fond)
    largeur, hauteur = boite[2] - boite[0], boite[3] - boite[1]
    print(f"artwork : {source.name} {image.width}x{image.height}")
    print(f"fond #{fond[0]:02x}{fond[1]:02x}{fond[2]:02x}  "
          f"crème #{creme[0]:02x}{creme[1]:02x}{creme[2]:02x}  "
          f"orange #{orange[0]:02x}{orange[1]:02x}{orange[2]:02x}")

    etiquettes, L, H = classer(image, boite, [fond, creme, orange])
    tracas = {}
    for nom, indice in (("lettres", 1), ("anneau", 2)):
        masque = [[1 if e == indice else 0 for e in ligne] for ligne in etiquettes]
        boucles = [b for b in contours(masque, L, H) if len(b) > BOUCLE_MINIMALE]
        chemin = "".join(lisser(simplifier(b, EPSILON)) for b in boucles)
        ecart = _ecart(masque, chemin, L, H)
        print(f"{nom:8} : {len(boucles)} boucles, {len(chemin):>6} car., "
              f"écart {ecart:.2f} % (plafond {ECART_MAXIMAL} %)")
        if ecart > ECART_MAXIMAL:
            raise SystemExit(f"tracé « {nom} » REFUSÉ — rien n'est écrit")
        tracas[nom] = redimensionner(chemin, FACTEUR)

    # L'ICÔNE est le « o » ENTIER — anneau orange ET anneau crème — jamais
    # l'anneau seul : dans l'artwork, le « m » et le « n » sont dessinés PAR
    # DESSUS l'orange, donc la couche orange isolée porte leurs encoches. Sur le
    # mot on ne les voit pas (les lettres les recouvrent) ; sur l'icône, si.
    boucles_o = _boucles_du_o(etiquettes, L, H)
    o_creme = redimensionner("".join(lisser(simplifier(b, EPSILON))
                                     for b in boucles_o), FACTEUR)
    marque_anneau, marque_o = _normaliser_ensemble(
        [tracas["anneau"], o_creme], cible=48, marge=3)

    cible = RACINE / "src" / "monl_platform" / "brand.py"
    cible.write_text(
        '''"""Les tracés de la marque, SANS aucune couleur.

C'est `theme.py` qui compose — un test l'exige, et c'est ce qui permet au mot
de suivre le thème de la page au lieu de porter son propre fond.

Le logo est fait de trois couches concentriques : l'ANNEAU orange (le grand
« O »), les LETTRES crème dont le « o » est un anneau niché dedans, et le fond
qui se voit au centre. Les deux tracés sont donc refermés en `evenodd` : en
chemins séparés, les trous se peindraient.

Écrit par `outils/vectoriser_logo.py`, qui refuse d'écrire si le tracé
re-rasterisé s'écarte trop de l'artwork. Ne pas retoucher à la main.
"""'''
        "\n\nfrom __future__ import annotations\n\n"
        f"# Les quatre lettres, contre-forme du « o » comprise. viewBox {largeur}x{hauteur}.\n"
        + envelopper("LETTRES", tracas["lettres"]) + "\n"
        f"# L'anneau orange qui entoure le « o ». Même viewBox {largeur}x{hauteur}.\n"
        + envelopper("ANNEAU", tracas["anneau"]) + "\n"
        "# Le « o » entier ramené dans un carré de 48 : l'icône d'application.\n"
        "# Les deux tracés partagent la MÊME transformation, sinon ils se\n"
        "# décalent l'un par rapport à l'autre.\n"
        + envelopper("MARQUE_ANNEAU", marque_anneau) + "\n"
        + envelopper("MARQUE_O", marque_o) + "\n"
        f"VUE = ({largeur}, {hauteur})\n",
        encoding="utf-8")
    print(f"écrit : {cible.relative_to(RACINE)}  (viewBox {largeur}x{hauteur})")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv))
