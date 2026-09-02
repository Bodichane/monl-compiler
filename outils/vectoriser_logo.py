#!/usr/bin/env python3
"""Vectorise le logo Monl monochrome depuis son PNG transparent.

    python3 outils/vectoriser_logo.py [artwork]

Le masque vient exclusivement du canal alpha. Le script extrait à la fois le
lockup horizontal et le signe situé à gauche, les normalise, puis écrit la
source Python et les deux SVG documentaires. Aucun nom de police n'entre dans
la chaîne : toutes les lettres restent des tracés.
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

#: La part de l'encre du dessin d'origine que le tracé a le droit de manquer.
#: Six pour cent, la valeur du point 157 — restaurée ici parce que la
#: réécriture de cet outil pour le logo monochrome l'avait fait disparaître, et
#: que rien ne l'avait remplacée : plus rien ne garantissait qu'un tracé
#: RESSEMBLE au dessin fourni. Les mesures relevées sur l'artwork courant sont
#: de 2,5 à 3,3 %, donc le seuil laisse la marge d'une simplification honnête
#: (EPSILON) sans laisser passer un signe visiblement faux.
TOLERANCE = 0.06


def _verifier(nom: str, reference: Image.Image, chemin: str) -> float:
    """Refuse d'ÉCRIRE un tracé qui ne ressemble pas à ce qu'on lui a donné.

    Le contrôle porte sur la FIDÉLITÉ au dessin fourni, ce qu'aucun autre
    témoin ne garde : ceux de la suite comparent les artefacts ENTRE EUX, donc
    ils resteraient verts sur un logo faux vectorisé de façon cohérente.
    """
    masque = reference.point(lambda a: 255 if a >= ALPHA_MIN else 0).convert("1")
    ecart = ecart_de_rendu(masque, chemin)
    if ecart > TOLERANCE:
        raise SystemExit(
            f"{nom} s'écarte de {ecart:.2%} du dessin d'origine "
            f"(tolérance {TOLERANCE:.0%}) — rien n'est écrit. "
            f"Vérifier l'artwork, le seuil alpha ou EPSILON.")
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
        raise SystemExit("aucun tracé trouvé dans le canal alpha")
    return "".join(lisser(simplifier(b, EPSILON)) for b in boucles)


def _separation(alpha: Image.Image) -> int:
    """Trouve le plus grand intervalle transparent entre signe et mot."""
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
        raise SystemExit("impossible de séparer le signe du mot")
    _, gauche, droite = max(candidats)
    return (gauche + droite) // 2


def _coupe_descripteur(alpha: Image.Image, separation: int) -> int:
    """Trouve le vide entre MONL et le mot COMPILER, côté lettres."""
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
        raise SystemExit("impossible de séparer MONL de COMPILER")
    _, haut, bas = max(intervalles)
    return (haut + bas) // 2


def _partie(alpha: Image.Image, garde) -> Image.Image:
    """Extrait une partie du lockup, en gardant son repère d'origine."""
    pixels = alpha.load()
    partie = Image.new("L", alpha.size)
    sortie = partie.load()
    for y in range(alpha.height):
        for x in range(alpha.width):
            if garde(x, y):
                sortie[x, y] = pixels[x, y]
    boite = partie.point(lambda a: 255 if a >= ALPHA_MIN else 0).getbbox()
    if not boite:
        raise SystemExit("partie de lockup vide")
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
        raise SystemExit("artwork transparent ou vide")
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
        raise SystemExit("signe introuvable à gauche du lockup")
    signe = normaliser(_chemin(signe_alpha.crop(signe_boite)), cible=48, marge=3)
    vue = alpha.size

    nav_mot = _chemin(nav_signe)
    nav_lettres = _chemin(nav_texte)
    # AVANT toute écriture : un contrôle placé après laisserait sur le disque
    # le tracé qu'il vient de déclarer faux.
    ecarts = {
        "WORDMARK_PATH": _verifier("WORDMARK_PATH", alpha, mot),
        "NAV_MARK_PATH": _verifier("NAV_MARK_PATH", nav_signe, nav_mot),
        "NAV_TEXT_PATH": _verifier("NAV_TEXT_PATH", nav_texte, nav_lettres),
    }

    cible = RACINE / "src" / "monl_platform" / "brand.py"
    cible.write_text(
        '''"""Tracés monochromes de la marque Monl, vectorisés depuis l'artwork.

La couleur appartient au thème ; ce module ne contient que la géométrie.
Généré par ``outils/vectoriser_logo.py`` — ne pas retoucher à la main.
"""\n\nfrom __future__ import annotations\n\n'''
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
    print(f"artwork : {source.name} {image.width}x{image.height}")
    print(f"emprise : {vue[0]}x{vue[1]} · séparation x={separation}, coupe y={coupe}")
    print("fidélité : " + " · ".join(f"{n} {e:.2%}" for n, e in ecarts.items())
          + f" (tolérance {TOLERANCE:.0%})")
    print(f"écrit : {cible.relative_to(RACINE)}, {marque.relative_to(RACINE)}, "
          f"{wordmark.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv))
