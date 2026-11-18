#!/usr/bin/env python3
"""Vectorizes the monochrome Monl logo from its transparent PNG.

    python3 outils/vectoriser_logo.py [artwork]

The mask comes exclusively from the alpha channel. The script extracts both
the horizontal lockup and the sign on its left, normalizes them, then writes
the Python source and the two documentation SVGs. No font name enters the
chain: every letter stays an outline.
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tracage import (
    RACINE,
    contours,
    ecart_de_rendu,
    envelopper,
    lisser,
    normaliser,
    simplifier,
)

ALPHA_MIN = 96
EPSILON = 2.2
BOUCLE_MINIMALE = 36

#: The share of the original drawing's ink the outline is allowed to miss.
#: Six percent, the value of point 157 — restored here because rewriting this
#: tool for the monochrome logo had made it disappear, and nothing had
#: replaced it: nothing guaranteed any more that an outline LOOKS LIKE the
#: supplied drawing. The measurements taken on the current artwork are 2.5 to
#: 3.3 %, so the threshold leaves room for an honest simplification (EPSILON)
#: without letting a visibly wrong sign through.
TOLERANCE = 0.06


def _verifier(nom: str, reference: Image.Image, chemin: str) -> float:
    """Refuses to WRITE an outline that does not look like what it was given.

    The check is about FIDELITY to the supplied drawing, which no other
    witness guards: the suite's witnesses compare the artifacts WITH EACH
    OTHER, so they would stay green on a wrong logo vectorized consistently.
    """
    masque = reference.point(lambda a: 255 if a >= ALPHA_MIN else 0).convert("1")
    ecart = ecart_de_rendu(masque, chemin)
    if ecart > TOLERANCE:
        raise SystemExit(
            f"{nom} departs {ecart:.2%} from the original drawing "
            f"(tolerance {TOLERANCE:.0%}) — nothing is written. "
            f"Check the artwork, the alpha threshold or EPSILON.")
    return ecart


def _masque(alpha: Image.Image) -> list[list[int]]:
    px = alpha.load()
    return [[1 if px[x, y] >= ALPHA_MIN else 0 for x in range(alpha.width)]
            for y in range(alpha.height)]


def _chemin(alpha: Image.Image) -> str:
    masque = _masque(alpha)
    boucles = [b for b in contours(masque, alpha.width, alpha.height)
               if len(b) > BOUCLE_MINIMALE]
    if not boucles:
        raise SystemExit("no outline found in the alpha channel")
    return "".join(lisser(simplifier(b, EPSILON)) for b in boucles)


def _separation(alpha: Image.Image) -> int:
    """Finds the widest transparent gap between sign and word."""
    colonnes = [alpha.crop((x, 0, x + 1, alpha.height)).getbbox() is not None
                for x in range(alpha.width)]
    intervalles, debut = [], None
    for x, pleine in enumerate(colonnes + [True]):
        if not pleine and debut is None:
            debut = x
        elif pleine and debut is not None:
            if debut > 0 and x < alpha.width:
                intervalles.append((x - debut, debut, x))
            debut = None
    candidats = [i for i in intervalles
                  if alpha.width * .15 < i[1] < alpha.width * .45]
    if not candidats:
        raise SystemExit("cannot separate the sign from the word")
    _, gauche, droite = max(candidats)
    return (gauche + droite) // 2


def _coupe_descripteur(alpha: Image.Image, separation: int) -> int:
    """Finds the gap between MONL and the word COMPILER, on the letters side."""
    lettres = alpha.crop((separation, 0, alpha.width, alpha.height))
    lignes = [lettres.crop((0, y, lettres.width, y + 1)).getbbox() is not None
              for y in range(lettres.height)]
    intervalles, debut = [], None
    for y, pleine in enumerate(lignes + [True]):
        if not pleine and debut is None:
            debut = y
        elif pleine and debut is not None:
            if debut > lettres.height * .15 and y < lettres.height * .85:
                intervalles.append((y - debut, debut, y))
            debut = None
    if not intervalles:
        raise SystemExit("cannot separate MONL from COMPILER")
    _, haut, bas = max(intervalles)
    return (haut + bas) // 2


def _partie(alpha: Image.Image, garde) -> Image.Image:
    """Extracts part of the lockup, keeping its original coordinates."""
    pixels = alpha.load()
    partie = Image.new("L", alpha.size)
    sortie = partie.load()
    for y in range(alpha.height):
        for x in range(alpha.width):
            if garde(x, y):
                sortie[x, y] = pixels[x, y]
    boite = partie.point(lambda a: 255 if a >= ALPHA_MIN else 0).getbbox()
    if not boite:
        raise SystemExit("empty lockup part")
    return partie


def _svg(viewbox: tuple[int, int], chemin: str, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
            f'{viewbox[0]} {viewbox[1]}" role="img" aria-label="{label}">\n'
            f'  <path d="{chemin}" fill="currentColor" fill-rule="evenodd"/>\n'
            '</svg>\n')


def principal(argv: list[str]) -> int:
    source = pathlib.Path(argv[1] if len(argv) > 1 else
                          RACINE / "docs" / "brand" / "monl-logo-source.png")
    image = Image.open(source).convert("RGBA")
    boite = image.getchannel("A").point(lambda a: 255 if a >= ALPHA_MIN else 0).getbbox()
    if not boite:
        raise SystemExit("artwork transparent or empty")
    alpha = image.getchannel("A").crop(boite)
    mot = _chemin(alpha)
    separation = _separation(alpha)
    coupe = _coupe_descripteur(alpha, separation)
    nav_signe = _partie(alpha, lambda x, _y: x < separation)
    nav_texte = _partie(alpha, lambda x, y: x >= separation and y < coupe)
    signe_boite_nav = nav_signe.getbbox()
    texte_boite_nav = nav_texte.getbbox()
    decalage_texte = round(
        ((signe_boite_nav[1] + signe_boite_nav[3]
         - texte_boite_nav[1] - texte_boite_nav[3]) / 2) * 2) / 2
    signe_alpha = alpha.crop((0, 0, separation, alpha.height))
    signe_boite = signe_alpha.getbbox()
    if not signe_boite:
        raise SystemExit("sign not found to the left of the lockup")
    signe = normaliser(_chemin(signe_alpha.crop(signe_boite)), cible=48, marge=3)
    vue = alpha.size

    nav_mot = _chemin(nav_signe)
    nav_lettres = _chemin(nav_texte)
    # BEFORE any write: a check placed afterwards would leave on disk the
    # outline it has just declared wrong.
    ecarts = {
        "WORDMARK_PATH": _verifier("WORDMARK_PATH", alpha, mot),
        "NAV_MARK_PATH": _verifier("NAV_MARK_PATH", nav_signe, nav_mot),
        "NAV_TEXT_PATH": _verifier("NAV_TEXT_PATH", nav_texte, nav_lettres),
    }

    cible = RACINE / "src" / "monl_platform" / "brand.py"
    cible.write_text(
        '''"""Monochrome paths of the Monl brand, vectorized from the artwork.

Color belongs to the theme; this module contains only the geometry.
Generated by ``outils/vectoriser_logo.py`` — do not edit by hand."""\n\nfrom __future__ import annotations\n\n'''
        + envelopper("WORDMARK_PATH", mot)
        + envelopper("NAV_MARK_PATH", nav_mot)
        + envelopper("NAV_TEXT_PATH", nav_lettres)
        + envelopper("MARK_PATH", signe)
        + f"VUE = ({vue[0]}, {vue[1]})\n"
        + f"NAV_VUE = ({vue[0]}, {vue[1]})\n"
        + f"NAV_TEXT_OFFSET_Y = {decalage_texte}\n",
        encoding="utf-8")

    marque = RACINE / "docs" / "brand" / "monl-mark.svg"
    wordmark = RACINE / "docs" / "brand" / "monl-wordmark.svg"
    marque.write_text(_svg((48, 48), signe, "Monl"), encoding="utf-8")
    wordmark.write_text(_svg(vue, mot, "Monl Compiler"), encoding="utf-8")
    print(f"artwork: {source.name} {image.width}x{image.height}")
    print(f"extent: {vue[0]}x{vue[1]} · split x={separation}, cut y={coupe}")
    print("fidelity: " + " · ".join(f"{n} {e:.2%}" for n, e in ecarts.items())
          + f" (tolerance {TOLERANCE:.0%})")
    print(f"written: {cible.relative_to(RACINE)}, {marque.relative_to(RACINE)}, "
          f"{wordmark.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv))
