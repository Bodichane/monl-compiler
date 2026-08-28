"""Fabrique les images raster DEPUIS les tracés de la marque, jamais d'un PNG.

    python3 outils/fabriquer_images.py

Trois artefacts, une seule source :

  favicon.ico        16/32/48 px — les navigateurs le demandent d'office, et un
                     404 les laisse afficher l'ANCIENNE icône gardée en cache.
  monl-wordmark.png  le mot en raster, pour ce qui ne sait pas lire un SVG.
  monl-social.png    1200x630 — la carte Open Graph.

Recopiés d'un fichier image, ces trois-là dériveraient le jour où la marque
change, sans que rien ne le dise. Ici ils viennent de `brand.py` pour la forme
et de `theme.ORANGE` pour la couleur, qui n'existe donc qu'à un seul endroit.
Aucun TEXTE n'y est rendu : il faudrait une police installée, et la plateforme
refuse cette dépendance partout ailleurs.
"""

import pathlib
import re
import sys

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from monl_platform.brand import ANNEAU, LETTRES, MARQUE_ANNEAU, MARQUE_O, VUE
from monl_platform.theme import ORANGE

STATIQUE = (pathlib.Path(__file__).resolve().parent.parent
            / "src" / "monl_platform" / "static")

CADRE = 48               # le viewBox des tracés d'icône
TAILLES_ICO = (16, 32, 48)
RENDU = 512              # rendu large puis réduit : le lissage vient de la réduction
FOND = (46, 43, 37)      # --brand
ENCRE = (249, 244, 237)  # --on-brand
PAPIER = (23, 21, 18)    # --bg sombre, pour la carte de partage
RAYON = 11               # le même que le <rect rx> de LOGO_SVG
SEGMENTS = 16            # découpe d'une quadratique en segments

ORANGE_RVB = tuple(int(ORANGE[i:i + 2], 16) for i in (1, 3, 5))


def _sous_chemins(chemin, echelle, decalage=(0, 0)):
    """Aplatit chaque sous-chemin en une liste de points.

    Les tracés n'emploient que M, L, Q et Z. Toute autre commande fait échouer
    plutôt que d'être ignorée : un chemin à moitié rendu produirait une image
    fausse mais plausible, ce qui est pire qu'une erreur.
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
                raise ValueError(f"{commande} attend 2 nombres, reçu {len(valeurs)}")
            position = (valeurs[0], valeurs[1])
            courant.append((position[0] + dx, position[1] + dy))
        elif commande == "Q":
            if len(valeurs) != 4:
                raise ValueError(f"Q attend 4 nombres, reçu {len(valeurs)}")
            (x0, y0), (cx, cy), (x1, y1) = position, valeurs[:2], valeurs[2:]
            for pas in range(1, SEGMENTS + 1):
                t = pas / SEGMENTS
                u = 1 - t
                courant.append((u * u * x0 + 2 * u * t * cx + t * t * x1 + dx,
                                u * u * y0 + 2 * u * t * cy + t * t * y1 + dy))
            position = (x1, y1)
    if courant:
        yield courant


def _masque(chemin, taille, echelle, decalage=(0, 0)):
    """Rend un tracé en OU EXCLUSIF : c'est la règle `evenodd`.

    Empilés, les sous-chemins rempliraient le trou de l'anneau — et le signe
    sortirait en pastille pleine au lieu d'un « o ».
    """
    rendu = Image.new("1", taille, 0)
    for points in _sous_chemins(chemin, echelle, decalage):
        if len(points) < 3:
            continue
        couche = Image.new("1", taille, 0)
        ImageDraw.Draw(couche).polygon(points, fill=1, outline=1)
        rendu = ImageChops.logical_xor(rendu, couche)
    return rendu


def _poser_mot(image, echelle, decalage, encre):
    image.paste(ORANGE_RVB, (0, 0), _masque(ANNEAU, image.size, echelle, decalage))
    image.paste(encre, (0, 0), _masque(LETTRES, image.size, echelle, decalage))


def fabriquer_ico(destination):
    echelle = RENDU / CADRE
    carre = (RENDU, RENDU)
    image = Image.new("RGB", carre, FOND)
    image.paste(ORANGE_RVB, (0, 0), _masque(MARQUE_ANNEAU, carre, echelle))
    image.paste(ENCRE, (0, 0), _masque(MARQUE_O, carre, echelle))

    plaque = Image.new("1", carre, 0)
    ImageDraw.Draw(plaque).rounded_rectangle(
        (0, 0, RENDU - 1, RENDU - 1), radius=int(RAYON * echelle), fill=1)
    fini = Image.new("RGBA", carre, (0, 0, 0, 0))
    fini.paste(image, (0, 0), plaque)

    tailles = [(t, t) for t in TAILLES_ICO]
    fini.resize(tailles[-1], Image.LANCZOS).save(destination, sizes=tailles)
    return destination


def fabriquer_wordmark(destination, largeur=1024):
    """Le mot sur fond TRANSPARENT : posé sur un fond en dur, il ne conviendrait
    qu'à un seul thème. Les lettres prennent l'encre claire, le seul choix qui
    tienne sur les supports sombres où un raster finit."""
    echelle = largeur / VUE[0] * 4
    grand = (largeur * 4, int(VUE[1] * echelle))
    image = Image.new("RGBA", grand, (0, 0, 0, 0))
    image.paste(ORANGE_RVB + (255,), (0, 0), _masque(ANNEAU, grand, echelle))
    image.paste(ENCRE + (255,), (0, 0), _masque(LETTRES, grand, echelle))
    image.resize((largeur, grand[1] // 4), Image.LANCZOS).save(destination)
    return destination


def fabriquer_social(destination, taille=(1200, 630)):
    """La carte Open Graph : le mot centré sur le papier sombre, rien d'autre.

    Pas de baseline rendue : il faudrait une police installée, et la plateforme
    refuse cette dépendance partout ailleurs. Le titre de la page porte déjà le
    texte, et c'est lui que les réseaux affichent à côté de l'image.
    """
    facteur = 3
    grand = (taille[0] * facteur, taille[1] * facteur)
    image = Image.new("RGB", grand, PAPIER)
    largeur_mot = grand[0] * 0.56
    echelle = largeur_mot / VUE[0]
    decalage = ((grand[0] - largeur_mot) / 2,
                (grand[1] - VUE[1] * echelle) / 2)
    _poser_mot(image, echelle, decalage, ENCRE)
    image.resize(taille, Image.LANCZOS).save(destination, optimize=True)
    return destination


if __name__ == "__main__":
    for nom, fabrique in (("favicon.ico", fabriquer_ico),
                          ("monl-wordmark.png", fabriquer_wordmark),
                          ("monl-social.png", fabriquer_social)):
        cible = fabrique(STATIQUE / nom)
        print(f"{cible.name:20} {cible.stat().st_size:>8} octets")
