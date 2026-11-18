#!/usr/bin/env python3
"""Outline toolbox: contours, simplification, smoothing, emission.

Extracted from `vectoriser_marque.py`, which vectorized the banner retired in
favor of the logo with the orange "o". These functions depended on no
artwork: they are what is kept, and the tool aimed at the old drawing left
with it rather than staying in place, able to rewrite `brand.py` with a brand
that no longer exists.

Two things not to undo. `contours` walks the grid's EDGES and never the
pixels: that is what guarantees closed loops, holes included. And
`envelopper` wraps the outline at the `MLQZ` markers, never in the middle of
a number.
"""

import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

RACINE = Path(__file__).resolve().parent.parent


def contours(m, L, H):
    """Marching squares: the closed boundaries between ink and background.

    It walks the grid's EDGES, never the pixels: that is what guarantees
    closed loops, holes included."""
    def dedans(x, y):
        return 0 <= x < L and 0 <= y < H and m[y][x]

    # Oriented edges: ink always stays on the LEFT of the direction of
    # travel.
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
    """Douglas-Peucker. Removes the vertices a straight line already replaces."""
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
    """SVG path: quadratic curves, except at REAL corners.

    Without the angle threshold, the glyph's serifs — which are sharp corners
    — would round off and the letter would change character."""
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
        if angle(a, b, c) > seuil_angle:          # corner: go straight there
            segments.append(f"L{b[0]:.2f} {b[1]:.2f}")
            m = milieu(b, c)
            segments.append(f"L{m[0]:.2f} {m[1]:.2f}")
        else:
            m = milieu(b, c)
            segments.append(f"Q{b[0]:.2f} {b[1]:.2f} {m[0]:.2f} {m[1]:.2f}")
    return "".join(segments) + "Z"


def chemins_de(m, L, H, epsilon):
    return "".join(lisser(simplifier(b, epsilon))
                   for b in contours(m, L, H) if len(b) > 40)


def redimensionner(chemin, k):
    return re.sub(r"-?\d+\.?\d*", lambda m: f"{float(m.group(0)) / k:.1f}", chemin)


def normaliser(chemin, cible, marge):
    """Brings an outline into a `cible` square, centered."""
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


SEGMENTS = 16  # how many segments a quadratic is cut into


def sous_chemins(chemin, echelle, decalage=(0, 0)):
    """Flattens each subpath into a list of points.

    The outlines only use M, L, Q and Z. Any other command fails rather than
    being ignored: a half-rendered path would produce a wrong but plausible
    image, which is worse than an error.
    """
    dx, dy = decalage
    courant, position = [], (0.0, 0.0)
    for commande, corps in re.findall(r"([MLQZ])([^MLQZ]*)", chemin):
        valeurs = [float(n) * echelle for n in re.findall(r"-?\d*\.?\d+", corps)]
        if commande == "Z":
            continue
        if commande == "M":
            if courant:
                yield courant
            courant = []
        if commande in ("M", "L"):
            if len(valeurs) != 2:
                raise ValueError(f"{commande} expects 2 numbers, got {len(valeurs)}")
            position = (valeurs[0], valeurs[1])
            courant.append((position[0] + dx, position[1] + dy))
        elif commande == "Q":
            if len(valeurs) != 4:
                raise ValueError(f"Q expects 4 numbers, got {len(valeurs)}")
            (x0, y0), (cx, cy), (x1, y1) = position, valeurs[:2], valeurs[2:]
            for pas in range(1, SEGMENTS + 1):
                t = pas / SEGMENTS
                u = 1 - t
                courant.append((u * u * x0 + 2 * u * t * cx + t * t * x1 + dx,
                                u * u * y0 + 2 * u * t * cy + t * t * y1 + dy))
            position = (x1, y1)
    if courant:
        yield courant


def rendre(chemin, taille, echelle, decalage=(0, 0)):
    """Renders an outline in EXCLUSIVE OR: that is the `evenodd` rule.

    Stacked, the subpaths would fill the letters' counters and the sign's
    openings. Point 157 had measured this trap: a check that STACKS reported
    an 8.08 % gap for 0.49 % in reality.

    This function lives in the package's leaf because TWO tools depend on it
    — the one that makes the images and the one that vectorizes. Two
    rasterizers would end up diverging, and the second serves to CHECK the
    first one's work: they must render exactly the same thing.
    """
    rendu = Image.new("1", taille, 0)
    for points in sous_chemins(chemin, echelle, decalage):
        if len(points) < 3:
            continue
        couche = Image.new("1", taille, 0)
        ImageDraw.Draw(couche).polygon(points, fill=1, outline=1)
        rendu = ImageChops.logical_xor(rendu, couche)
    return rendu


def ecart_de_rendu(reference, chemin, echelle=1.0, decalage=(0, 0)):
    """The share of the ORIGINAL drawing's ink the outline does not recover.

    Relative to the reference's ink and not to the total pixel count: a very
    empty image would make any gap negligible, and the measurement would stop
    biting exactly on the finest signs.
    """
    encre = sum(1 for p in reference.get_flattened_data() if p)
    if not encre:
        raise ValueError("empty reference: the measurement would be about nothing")
    divergents = ImageChops.logical_xor(reference, rendre(chemin, reference.size,
                                                          echelle, decalage))
    return sum(1 for p in divergents.get_flattened_data() if p) / encre
