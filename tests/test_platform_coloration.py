"""La coloration syntaxique des spécifications, et ce qui la garde honnête.

Trois garanties y vivent, chacune née d'un défaut mesuré :

1. **Les mots-clés sont DÉRIVÉS de la grammaire.** Une liste recopiée aurait
   divergé au premier point de journal — et une coloration qui manque ne
   ressemble pas à une panne, elle ressemble à un choix.
2. **Chaque couleur se lit, et aucune paire n'est confusable.** Les noms
   déclarés étaient crème, donc à 1,1:1 de l'encre du bloc : une classe qui ne
   distinguait rien. Le rose des mots-clés et l'olive des chaînes tombaient
   chacun à 32° de l'or.
3. **Aucune section ne porte plus de surtitre.** « Le backend est compilé, pas
   improvisé », « Voyez le résultat » : des phrases posées AVANT le titre,
   qu'il fallait lire pour arriver au titre.
"""

import colorsys
import itertools
import pathlib
import re

from monl_platform import coloration
from monl_platform.account import ACCOUNT_HTML, AUTH_HTML
from monl_platform.docs_page import DOCS_HTML
from monl_platform.landing import LANDING_HTML
from monl_platform.mcp_page import MCP_HTML
from monl_platform.security import SECURITY_HTML

SOURCE = pathlib.Path(coloration.__file__).read_text(encoding="utf-8")

# Les fonds de code, l'un par thème. Le CLAIR est le plus dur : c'est sur lui
# que les seuils sont tenus.
FOND_CLAIR = "#2e2b25"
FOND_SOMBRE = "#0f0e0c"

SEUIL_TEXTE = 4.5       # WCAG 1.4.3 — du code se lit, ce n'est pas un graphique
ECART_TEINTE = 35       # degrés
ECART_CLARTE = 1.35     # rapport de contraste entre deux jetons
ECART_CHROMA = 40       # sur 255 — ce qui sépare un gris d'une couleur franche
CHROMA_COLORE = 30      # en dessous, la teinte ne porte plus rien


def _rvb(couleur):
    return [int(couleur[i:i + 2], 16) for i in (1, 3, 5)]


def _chroma(couleur):
    canaux = _rvb(couleur)
    return max(canaux) - min(canaux)


def _teinte(couleur):
    return colorsys.rgb_to_hsv(*[v / 255 for v in _rvb(couleur)])[0] * 360


def _luminance(couleur):
    def lineaire(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, v, b = (c / 255 for c in _rvb(couleur))
    return 0.2126 * lineaire(r) + 0.7152 * lineaire(v) + 0.0722 * lineaire(b)


def _contraste(a, b):
    haut, bas = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (haut + 0.05) / (bas + 0.05)


def _palette():
    """Les couleurs LIVRÉES, relues dans la feuille inlinée de la page.

    Relire le source Python passerait à côté d'une surcharge écrite plus bas
    dans la feuille : ce que le test doit juger est ce que le navigateur reçoit.
    """
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", LANDING_HTML, re.S | re.I))
    palette = dict(re.findall(r"--(s-\w+):\s*(#[0-9a-fA-F]{6})", css))
    encre = re.search(r"--code-ink:\s*(#[0-9a-fA-F]{6})", css)
    assert palette, "aucune couleur --s-* dans la feuille : le test ne garde plus rien"
    assert encre, "--code-ink introuvable"
    return palette, encre.group(1)


def test_les_mots_cles_sont_derives_de_la_grammaire():
    """Aucun mot-clé n'est ÉCRIT dans le module de coloration.

    Le témoin porte sur des mots arrivés tard dans le projet (points 90 à 116).
    S'ils sont colorés SANS figurer dans le source, c'est que la dérivation
    tient. Recopier une liste ferait apparaître les noms : le test tombe.
    """
    tardifs = ("publicWhen", "oncePer", "numbered", "releases",
               "writableAfterPayment", "requiresOwn", "derivedFrom", "sumOf")

    for mot in tardifs:
        assert coloration._classe_du_mot(mot) == "s-kw", f"{mot} n'est plus coloré"
        assert mot not in SOURCE, (
            f"{mot} est ÉCRIT dans coloration.py : la liste est redevenue une copie")


def test_un_mot_absent_de_la_grammaire_ne_prend_aucune_couleur():
    """La contre-épreuve de la dérivation.

    Sans elle, une fonction qui colorerait TOUT rendrait le test précédent vert
    sans rien dériver du tout.
    """
    assert coloration._classe_du_mot("entity") == "s-kw"
    assert coloration._classe_du_mot("courriel") is None
    assert coloration._classe_du_mot("libelle") is None
    assert coloration._classe_du_mot("Commande") == "s-nom", "un nom déclaré"


def test_chaque_couleur_de_jeton_se_lit_sur_les_deux_fonds_de_code():
    palette, encre = _palette()

    for nom, couleur in sorted(palette.items()):
        for fond in (FOND_CLAIR, FOND_SOMBRE):
            mesure = _contraste(couleur, fond)
            assert mesure >= SEUIL_TEXTE, (
                f"--{nom} ({couleur}) tombe à {mesure:.2f}:1 sur {fond} — "
                f"sous le seuil du texte ({SEUIL_TEXTE}:1)")


def test_aucune_paire_de_couleurs_n_est_indistinguable():
    """Deux jetons se distinguent par la teinte, la clarté OU la franchise.

    Le contraste ENTRE deux jetons n'est PAS la mesure de WCAG (qui parle du
    fond) : deux couleurs de même clarté séparées par la teinte se lisent très
    bien. Ce qu'on refuse est qu'une paire soit proche sur les TROIS axes —
    c'est ainsi que les noms déclarés en crème (#f0e6d8) ne se distinguaient
    pas de l'encre du bloc, mesurés à 1,1:1 pour 12 de chroma d'écart.
    L'encre entre dans la comparaison : un jeton qui ressemble au texte nu ne
    colore rien.
    """
    palette, encre = _palette()
    toutes = dict(palette, encre=encre)
    confuses = []

    for (a, ca), (b, cb) in itertools.combinations(sorted(toutes.items()), 2):
        ecart_teinte = min(abs(_teinte(ca) - _teinte(cb)),
                           360 - abs(_teinte(ca) - _teinte(cb)))
        colorees = _chroma(ca) >= CHROMA_COLORE and _chroma(cb) >= CHROMA_COLORE
        distincts = (
            (colorees and ecart_teinte >= ECART_TEINTE)
            or _contraste(ca, cb) >= ECART_CLARTE
            or abs(_chroma(ca) - _chroma(cb)) >= ECART_CHROMA
        )
        if not distincts:
            confuses.append(f"{a}/{b} : {ecart_teinte:.0f}°, "
                            f"{_contraste(ca, cb):.2f}:1, "
                            f"Δchroma {abs(_chroma(ca) - _chroma(cb))}")

    assert not confuses, "couleurs proches sur les trois axes : " + " ; ".join(confuses)


def test_la_spec_de_l_accueil_emploie_vraiment_plusieurs_familles():
    """Avant, deux classes en tout — `.kw` en or et `.cm` en gris.

    Sans ce compte, remplacer la coloration par un `<span class="s-kw">` posé
    sur tout laisserait la page « colorée » et le site monochrome.
    """
    familles = set(re.findall(r'class="(s-\w+)"', LANDING_HTML))
    jetons = len(re.findall(r'class="s-\w+"', LANDING_HTML))

    assert len(familles) >= 5, f"seulement {sorted(familles)} sur la page d'accueil"
    assert jetons >= 40, f"{jetons} jetons colorés : la spec n'est plus colorée"


# Les classes qui posent une phrase AVANT un titre. Deux et non une : le
# premier passage n'avait retiré que `.eyebrow`, et les trois cartes de
# positionnement portaient leur surtitre sous un autre nom (`01 ·
# INFRASTRUCTURE`). Chercher un seul nom, c'était garder la moitié de la règle.
SURTITRES = ("eyebrow", "stage-no")


def test_aucune_section_ne_porte_plus_de_surtitre():
    """« Le backend est compilé, pas improvisé » se lisait AVANT le titre.

    Le seul survivant assumé est la page d'erreur, où le surtitre EST le
    titre — « Erreur 404 » n'annonce pas une section, il la nomme.
    """
    pages = {"accueil": LANDING_HTML, "docs": DOCS_HTML, "mcp": MCP_HTML,
             "sécurité": SECURITY_HTML, "connexion": AUTH_HTML,
             "compte": ACCOUNT_HTML}

    for nom, page in pages.items():
        assert "<section" in page or "<main" in page, (
            f"la page {nom} n'a plus de section : le test ne garde plus rien")
        for classe in SURTITRES:
            assert f'class="{classe}"' not in page, (
                f"un surtitre .{classe} est revenu sur la page {nom}")


def test_aucune_regle_n_habille_un_surtitre_disparu():
    """Une règle CSS orpheline fait croire que le surtitre peut revenir.

    C'est la forme du point 154 : une garantie qui ne porte plus sur rien ne
    fait aucun bruit. `.flow-stage .stage-no` est partie avec le balisage
    qu'elle habillait ; l'exception assumée est `.eyebrow`, qui sert encore à
    la page d'erreur.
    """
    feuille = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>",
                                   LANDING_HTML, re.S | re.I))
    assert feuille, "la feuille n'est plus inlinée"
    assert "stage-no" not in feuille, (
        "une règle habille encore un surtitre qui n'existe plus")
