"""Fabrique `favicon.ico` DEPUIS le chemin de la marque, jamais depuis un PNG.

Un `.ico` recopié d'un fichier image dériverait le jour où la marque change,
sans que rien ne le dise — c'est la leçon du fichier de marque du point 156,
qui avait dérivé et qu'un test a rattrapé. Ici la source unique est
`brand.MARQUE_M` : le même chemin que sert `/favicon.svg`, rendu en pixels.

Pourquoi un `.ico` alors que le SVG existe : les navigateurs demandent
`/favicon.ico` d'office, et un 404 les laisse afficher ce qu'ils gardent en
cache — c'est-à-dire l'ANCIENNE icône, qui « réapparaît » sans que le serveur
y soit pour rien.

    python3 outils/fabriquer_favicon.py
"""

import pathlib
import re
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from monl_platform.brand import MARQUE_M

CADRE = 48          # le viewBox de MARQUE_M
RENDU = 512         # rendu large puis réduit : le lissage vient de la réduction
TAILLES = (16, 32, 48)
FOND = (46, 43, 37)      # --brand
ENCRE = (249, 244, 237)  # --on-brand
RAYON = 11               # le même que le <rect rx> de LOGO_SVG
SEGMENTS = 16            # découpe d'une quadratique en segments


def _points(chemin: str, echelle: float) -> list:
    """Aplatit le chemin en une liste de points.

    MARQUE_M n'emploie que M, L, Q et Z, et un seul sous-chemin — vérifié
    avant d'écrire cet outil. Toute autre commande fait échouer plutôt que
    d'être ignorée : un chemin à moitié rendu produirait une icône fausse mais
    plausible, ce qui est pire qu'une erreur.
    """
    points, position = [], (0.0, 0.0)
    for commande, corps in re.findall(r"([MLQZ])([^MLQZ]*)", chemin):
        nombres = [float(n) * echelle for n in re.findall(r"-?\d*\.?\d+", corps)]
        if commande == "Z":
            continue
        if commande in ("M", "L"):
            if len(nombres) != 2:
                raise ValueError(f"{commande} attend 2 nombres, reçu {len(nombres)}")
            position = (nombres[0], nombres[1])
            points.append(position)
        elif commande == "Q":
            if len(nombres) != 4:
                raise ValueError(f"Q attend 4 nombres, reçu {len(nombres)}")
            (x0, y0), (cx, cy), (x1, y1) = position, nombres[:2], nombres[2:]
            for pas in range(1, SEGMENTS + 1):
                t = pas / SEGMENTS
                u = 1 - t
                points.append((u * u * x0 + 2 * u * t * cx + t * t * x1,
                               u * u * y0 + 2 * u * t * cy + t * t * y1))
            position = (x1, y1)
    return points


def fabriquer(destination: pathlib.Path) -> pathlib.Path:
    echelle = RENDU / CADRE
    image = Image.new("RGBA", (RENDU, RENDU), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    dessin.rounded_rectangle((0, 0, RENDU - 1, RENDU - 1),
                             radius=int(RAYON * echelle), fill=FOND + (255,))
    dessin.polygon(_points(MARQUE_M, echelle), fill=ENCRE + (255,))

    tailles = [(t, t) for t in TAILLES]
    image.resize(tailles[-1], Image.LANCZOS).save(destination, sizes=tailles)
    return destination


if __name__ == "__main__":
    cible = (pathlib.Path(__file__).resolve().parent.parent
             / "src" / "monl_platform" / "static" / "favicon.ico")
    fabriquer(cible)
    print(f"{cible} écrit ({cible.stat().st_size} octets, tailles {TAILLES})")
