"""Makes the raster images FROM the brand's outlines, never from a PNG.

    python3 outils/fabriquer_images.py

Three artifacts, one source:

  favicon.ico        16/32/48 px — browsers ask for it unprompted, and a 404
                     leaves them showing the OLD icon kept in cache.
  monl-wordmark.png  the word as raster, for what cannot read an SVG.
  monl-social.png    1200x630 — the Open Graph card.

Copied from an image file, these three would drift the day the brand
changes, without anything saying so. Here they come from `brand.py`.
No TEXT is rendered: it would need an installed font, and the platform
refuses that dependency everywhere else.
"""

import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from tracage import rendre as _masque

from monl_platform.brand import MARK_PATH, VIEW, WORDMARK_PATH

STATIQUE = (pathlib.Path(__file__).resolve().parent.parent
            / "src" / "monl_platform" / "static")

CADRE = 48               # the icon outlines' viewBox
TAILLES_ICO = (16, 32, 48)
RENDU = 512              # rendered large then reduced: smoothing comes from the reduction
FOND = (46, 43, 37)      # --brand
ENCRE = (249, 244, 237)  # --on-brand
PAPIER = (23, 21, 18)    # dark --bg, for the share card
RAYON = 11               # the same as LOGO_SVG's <rect rx>



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
    """The word on a TRANSPARENT background: set on a hard background, it would
    only suit one theme. The letters take the light ink, the only choice that
    holds on the dark surfaces where a raster ends up."""
    echelle = largeur / VIEW[0] * 4
    grand = (largeur * 4, int(VIEW[1] * echelle))
    image = Image.new("RGBA", grand, (0, 0, 0, 0))
    image.paste(ENCRE + (255,), (0, 0), _masque(WORDMARK_PATH, grand, echelle))
    image.resize((largeur, grand[1] // 4), Image.LANCZOS).save(destination)
    return destination


def fabriquer_social(destination, taille=(1200, 630)):
    """The Open Graph card: the word centered on the dark paper, nothing else.

    No tagline rendered: it would need an installed font, and the platform
    refuses that dependency everywhere else. The page title already carries
    the text, and it is what networks display next to the image.
    """
    facteur = 3
    grand = (taille[0] * facteur, taille[1] * facteur)
    image = Image.new("RGB", grand, PAPIER)
    largeur_mot = grand[0] * 0.56
    echelle = largeur_mot / VIEW[0]
    decalage = ((grand[0] - largeur_mot) / 2,
                (grand[1] - VIEW[1] * echelle) / 2)
    _poser_mot(image, echelle, decalage, ENCRE)
    image.resize(taille, Image.LANCZOS).save(destination, optimize=True)
    return destination


if __name__ == "__main__":
    for nom, fabrique in (("favicon.ico", fabriquer_ico),
                          ("monl-wordmark.png", fabriquer_wordmark),
                          ("monl-social.png", fabriquer_social)):
        cible = fabrique(STATIQUE / nom)
        print(f"{cible.name:20} {cible.stat().st_size:>8} bytes")
