#!/usr/bin/env python3
"""Boîte à outils du tracé : contours, simplification, lissage, émission.

Extraite de `vectoriser_marque.py`, qui vectorisait la bannière retirée au
profit du logo au « o » orange. Ces fonctions-là ne dépendaient d'aucun
artwork : ce sont elles qu'on garde, et l'outil qui visait l'ancien dessin est
parti avec lui plutôt que de rester en place à pouvoir réécrire `brand.py`
avec une marque qui n'existe plus.

Deux choses à ne pas défaire. `contours` marche sur les ARÊTES de la grille et
jamais sur les pixels : c'est ce qui garantit des boucles fermées, trous
compris. Et `envelopper` coupe le tracé sur les marqueurs `MLQZ`, jamais au
milieu d'un nombre.
"""

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


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
