#!/usr/bin/env python3
"""Vectoriser l'artwork de la marque, et PROUVER le tracé en le re-rendant.

    python3 outils/vectoriser_marque.py "Logo monl-selection.png"

Écrit `src/monl_platform/brand.py` (les tracés, sans aucune couleur — c'est
`theme.py` qui les compose) puis rend le SVG obtenu et le compare pixel à
pixel à l'artwork. Un tracé qui s'écarte trop fait ÉCHOUER le script : sans
cette mesure, « ça ressemble » remplacerait « ça correspond ».

Pourquoi vectoriser plutôt que servir le PNG :
  - le « m » de l'artwork fait 54 px de large et un favicon tire dessus
    jusqu'à 512 ;
  - en `<img>`, la bannière garde son fond sombre quel que soit le thème,
    soit 1,29:1 contre la page sombre — le logo disparaît de l'en-tête.

Pourquoi ne pas le REDESSINER : les empattements arrondis et l'attaque
inclinée du jambage sont le caractère du dessin. Les approximer produirait
une autre lettre.

Dépendances : Pillow (déjà dans l'extra `ai`) et ImageMagick pour la
vérification. Sans ImageMagick, le script trace mais REFUSE de conclure.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

RACINE = Path(__file__).resolve().parent.parent
FACTEUR = 12          # suréchantillonnage avant seuillage
ECART_MAXIMAL = 6.0   # % de pixels discordants tolérés (liseré antialiasé)

def masque(image, boite, facteur=FACTEUR):
    """Masque binaire de l'encre CLAIRE, suréchantillonné puis seuillé."""
    crop = image.crop(boite).convert("RGBA")
    l, h = crop.size
    grand = crop.resize((l * facteur, h * facteur), Image.LANCZOS)
    px = grand.load()
    L, H = grand.size
    return [[1 if (px[x, y][3] > 128 and px[x, y][0] > 190 and px[x, y][1] > 185)
             else 0 for x in range(L)] for y in range(H)], L, H


def contours(m, L, H):
    """Marching squares : les frontieres fermées entre encre et fond.

    On marche sur les ARÊTES de la grille, jamais sur les pixels : c'est ce
    qui garantit des boucles fermées, trous compris."""
    def dedans(x, y):
        return 0 <= x < L and 0 <= y < H and m[y][x]

    # Arêtes orientées : l'encre reste toujours à GAUCHE du sens de marche.
    aretes = {}
    for y in range(H):
        for x in range(L):
            if not m[y][x]:
                continue
            if not dedans(x, y - 1): aretes.setdefault((x, y), []).append((x + 1, y))
            if not dedans(x + 1, y): aretes.setdefault((x + 1, y), []).append((x + 1, y + 1))
            if not dedans(x, y + 1): aretes.setdefault((x + 1, y + 1), []).append((x, y + 1))
            if not dedans(x - 1, y): aretes.setdefault((x, y + 1), []).append((x, y))

    boucles = []
    restant = {a: list(b) for a, b in aretes.items()}
    while restant:
        depart = next(iter(restant))
        boucle, point = [depart], depart
        while True:
            suivants = restant.get(point)
            if not suivants:
                break
            prochain = suivants.pop()
            if not suivants:
                del restant[point]
            if prochain == depart:
                break
            boucle.append(prochain)
            point = prochain
        if len(boucle) > 8:
            boucles.append(boucle)
    return boucles


def _distance(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** .5
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** .5


def simplifier(points, epsilon):
    """Douglas-Peucker. Retire les sommets qu'une droite remplace déjà."""
    if len(points) < 3:
        return points
    pire, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _distance(points[i], points[0], points[-1])
        if d > pire:
            pire, index = d, i
    if pire <= epsilon:
        return [points[0], points[-1]]
    return (simplifier(points[:index + 1], epsilon)[:-1]
            + simplifier(points[index:], epsilon))


def lisser(points, seuil_angle=0.55):
    """Chemin SVG : courbes quadratiques, sauf aux VRAIS coins.

    Sans le seuil d'angle, les empattements du glyphe — qui sont des coins
    nets — s'arrondiraient et la lettre changerait de caractere."""
    import math
    n = len(points)
    def milieu(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    def angle(a, b, c):
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        n1 = math.hypot(*v1); n2 = math.hypot(*v2)
        if n1 == 0 or n2 == 0:
            return 0.0
        cos = max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        return math.acos(cos)

    segments = []
    depart = milieu(points[-1], points[0])
    segments.append(f"M{depart[0]:.2f} {depart[1]:.2f}")
    for i in range(n):
        a, b, c = points[i - 1], points[i], points[(i + 1) % n]
        if angle(a, b, c) > seuil_angle:          # coin : on y va tout droit
            segments.append(f"L{b[0]:.2f} {b[1]:.2f}")
            m = milieu(b, c)
            segments.append(f"L{m[0]:.2f} {m[1]:.2f}")
        else:
            m = milieu(b, c)
            segments.append(f"Q{b[0]:.2f} {b[1]:.2f} {m[0]:.2f} {m[1]:.2f}")
    return "".join(segments) + "Z"


def tracer(image, boite, epsilon=1.4, echelle=None):
    m, L, H = masque(image, boite)
    chemins = []
    for boucle in contours(m, L, H):
        simple = simplifier(boucle, epsilon)
        if len(simple) > 4:
            chemins.append(lisser(simple))
    return chemins, L, H


# ---------------------------------------------------------------------------
# Émission
# ---------------------------------------------------------------------------

def masque_alpha(image, boite, facteur=FACTEUR):
    crop = image.crop(boite)
    l, h = crop.size
    grand = crop.resize((l * facteur, h * facteur), Image.LANCZOS)
    px = grand.load()
    L, H = grand.size
    return [[1 if px[x, y][3] > 128 else 0 for x in range(L)] for y in range(H)], L, H


def chemins_de(m, L, H, epsilon):
    return "".join(lisser(simplifier(b, epsilon))
                   for b in contours(m, L, H) if len(b) > 40)


def redimensionner(chemin, k):
    return re.sub(r"-?\d+\.?\d*", lambda m: f"{float(m.group(0)) / k:.1f}", chemin)


def normaliser(chemin, cible, marge):
    """Ramener un tracé dans un carré `cible`, centré."""
    nombres = [float(v) for v in re.findall(r"-?\d+\.?\d*", chemin)]
    xs, ys = nombres[0::2], nombres[1::2]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = (cible - 2 * marge) / max(x1 - x0, y1 - y0)
    dx = marge + (cible - 2 * marge - (x1 - x0) * k) / 2 - x0 * k
    dy = marge + (cible - 2 * marge - (y1 - y0) * k) / 2 - y0 * k
    compteur = iter(range(10 ** 9))

    def remplace(m):
        n = float(m.group(0))
        return f"{n * k + (dx if next(compteur) % 2 == 0 else dy):.1f}"

    return re.sub(r"-?\d+\.?\d*", remplace, chemin)


def envelopper(nom, chemin, largeur=76):
    morceaux, courant = [], ""
    for marqueur in "MLQZ":
        chemin = chemin.replace(marqueur, "\x00" + marqueur)
    for token in chemin.split("\x00"):
        if not token:
            continue
        if len(courant) + len(token) > largeur:
            morceaux.append(courant)
            courant = token
        else:
            courant += token
    if courant:
        morceaux.append(courant)
    corps = "\n".join(f'    "{m}"' for m in morceaux)
    return f"{nom} = (\n{corps}\n)\n"


def verifier(svg_texte, artwork, boite):
    """Rendre le SVG et le comparer à l'artwork. Rend le % de discordance."""
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        print("  ImageMagick absent : tracé écrit, NON vérifié.", file=sys.stderr)
        return None
    with tempfile.TemporaryDirectory() as tmp:
        chemin_svg = Path(tmp) / "rendu.svg"
        chemin_png = Path(tmp) / "rendu.png"
        chemin_svg.write_text(svg_texte, encoding="utf-8")
        largeur = boite[2] - boite[0]
        hauteur = boite[3] - boite[1]
        subprocess.run([magick, "-background", "none", str(chemin_svg),
                        "-resize", f"{largeur}x{hauteur}", str(chemin_png)],
                       check=True, capture_output=True)
        rendu = Image.open(chemin_png).convert("RGB")
        origine = artwork.crop(boite).convert("RGB")
        if rendu.size != origine.size:
            rendu = rendu.resize(origine.size)
        a = list(origine.get_flattened_data())
        b = list(rendu.get_flattened_data())
        ecarts = sum(1 for x, y in zip(a, b)
                     if sum(abs(i - j) for i, j in zip(x, y)) >= 90)
        return 100 * ecarts / len(a)


def principal(argv):
    source = Path(argv[1] if len(argv) > 1 else RACINE / "Logo monl-selection.png")
    if not source.exists():
        print(f"artwork introuvable : {source}", file=sys.stderr)
        return 1
    image = Image.open(source).convert("RGBA")
    boite = (0, 0, *image.size)

    alpha, LA, HA = masque_alpha(image, boite)
    banniere = redimensionner(chemins_de(alpha, LA, HA, 3.0), FACTEUR)
    encre, LB, HB = masque(image, boite)
    lettres = redimensionner(chemins_de(encre, LB, HB, 2.4), FACTEUR)

    # Le « m » seul : premier groupe de colonnes encrées.
    largeur, hauteur = image.size
    def claire(x, y):
        r, g, b, a = image.getpixel((x, y))
        return a > 128 and r > 200 and g > 200 and b > 190
    colonnes = [x for x in range(largeur)
                if any(claire(x, y) for y in range(hauteur))]
    fin = colonnes[0]
    for a, b in zip(colonnes, colonnes[1:]):
        if b - a > 1:
            break
        fin = b
    lignes = [y for y in range(hauteur)
              for x in range(colonnes[0], fin + 1) if claire(x, y)]
    coupe = (colonnes[0] - 1, min(lignes) - 1, fin + 2, max(lignes) + 2)
    tailles, LM, HM = masque(image, coupe)
    m_seul = normaliser(chemins_de(tailles, LM, HM, 3.2), cible=48, marge=9.5)

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {largeur} {hauteur}">'
           f'<path d="{banniere}" fill="#2e2b25"/>'
           f'<path d="{lettres}" fill="#f9f4ed" fill-rule="evenodd"/></svg>')
    ecart = verifier(svg, image, boite)
    if ecart is None:
        return 2
    print(f"  discordance au rendu : {ecart:.2f} % (plafond {ECART_MAXIMAL} %)")
    if ecart > ECART_MAXIMAL:
        print("  tracé REFUSÉ : trop loin de l'artwork.", file=sys.stderr)
        return 1

    cible = RACINE / "src" / "monl_platform" / "brand.py"
    entete = cible.read_text(encoding="utf-8").split('"""')[1]
    cible.write_text(
        f'"""{entete}"""\n\nfrom __future__ import annotations\n\n'
        "# La bannière : encoche à gauche, pointe à droite. viewBox 256x100.\n"
        + envelopper("BANNIERE", banniere) + "\n"
        "# Les quatre lettres, contre-forme du « o » comprise : UN seul chemin,\n"
        "# refermé en `evenodd`. En chemins séparés, le trou du « o » se peint.\n"
        + envelopper("LETTRES", lettres) + "\n"
        "# Le « m » seul, ramené dans un carré de 48 : l'icône d'application.\n"
        + envelopper("MARQUE_M", m_seul),
        encoding="utf-8")
    print(f"  écrit : {cible.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv))
