"""Fabrique les images raster DEPUIS les tracés de la marque, jamais d'un PNG.

    python3 outils/fabriquer_images.py

Trois artefacts, une seule source :

  favicon.ico        16/32/48 px — les navigateurs le demandent d'office, et un
                     404 les laisse afficher l'ANCIENNE icône gardée en cache.
  monl-wordmark.png  le mot en raster, pour ce qui ne sait pas lire un SVG.
  monl-social.png    1200x630 — la carte Open Graph.

Recopiés d'un fichier image, ces trois-là dériveraient le jour où la marque
change, sans que rien ne le dise. Ici ils viennent de `brand.py`.
Aucun TEXTE n'y est rendu : il faudrait une police installée, et la plateforme
refuse cette dépendance partout ailleurs.
"""

import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from tracage import rendre as _masque

from monl_platform.brand import MARK_PATH, VUE, WORDMARK_PATH

STATIQUE = (pathlib.Path(__file__).resolve().parent.parent
            / "src" / "monl_platform" / "static")

CADRE = 48               # le viewBox des tracés d'icône
TAILLES_ICO = (16, 32, 48)
RENDU = 512              # rendu large puis réduit : le lissage vient de la réduction
FOND = (46, 43, 37)      # --brand
ENCRE = (249, 244, 237)  # --on-brand
PAPIER = (23, 21, 18)    # --bg sombre, pour la carte de partage
RAYON = 11               # le même que le <rect rx> de LOGO_SVG



def _poser_mot(image, echelle, decalage, encre):
    image.paste(encre, (0, 0), _masque(WORDMARK_PATH, image.size, echelle, decalage))


def fabriquer_ico(destination):
    echelle = RENDU / CADRE
    carre = (RENDU, RENDU)
    image = Image.new("RGB", carre, FOND)
    image.paste(ENCRE, (0, 0), _masque(MARK_PATH, carre, echelle))

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
    image.paste(ENCRE + (255,), (0, 0), _masque(WORDMARK_PATH, grand, echelle))
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
