"""Syntax highlighting of specifications, and what keeps it honest.

Three guarantees live here, each born from a measured defect:

1. **Keywords are DERIVED from the grammar.** A copied list would have
   diverged at the first journal point — and missing highlighting does not
   look like a failure, it looks like a choice.
2. **Every color is readable, and no pair is confusable.** Declared names
   were cream, hence at 1.1:1 from the block's ink: a class that
   distinguished nothing. The keywords' pink and the strings' olive each fell
   32° from gold.
3. **No section carries an overline any more.** "The backend is compiled,
   not improvised", "See the result": phrases put BEFORE the title, which had
   to be read to reach the title.
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

# The code backgrounds, one per theme. The LIGHT one is the hardest: the
# thresholds are held on it.
FOND_CLAIR = "#2e2b25"
FOND_SOMBRE = "#0f0e0c"

SEUIL_TEXTE = 4.5       # WCAG 1.4.3 — code is read, it is not a graphic
ECART_TEINTE = 35       # degrees
ECART_CLARTE = 1.35     # rapport de contraste entre deux jetons
ECART_CHROMA = 40       # out of 255 — what separates a gray from a clear color
CHROMA_COLORE = 30      # below this, hue carries nothing any more


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
    """The SHIPPED colors, reread in the page's inlined sheet.

    Rereading the Python source would miss an override written further down in
    the sheet: what the test must judge is what the browser receives.
    """
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", LANDING_HTML, re.S | re.I))
    palette = dict(re.findall(r"--(s-\w+):\s*(#[0-9a-fA-F]{6})", css))
    encre = re.search(r"--code-ink:\s*(#[0-9a-fA-F]{6})", css)
    assert palette, "no --s-* color in the stylesheet: the test no longer guards anything"
    assert encre, "--code-ink introuvable"
    return palette, encre.group(1)


def test_keywords_are_derived_from_the_grammar():
    """No keyword is WRITTEN in the highlighting module.

    The witness is about words that arrived late in the project (points 90 to
    116). If they are colored WITHOUT appearing in the source, the derivation
    holds. Copying a list would make the names appear: the test fails.
    """
    tardifs = ("publicWhen", "oncePer", "numbered", "releases",
               "writableAfterPayment", "requiresOwn", "derivedFrom", "sumOf")

    for mot in tardifs:
        assert coloration._classe_du_mot(mot) == "s-kw", f"{mot} is no longer highlighted"
        assert mot not in SOURCE, (
            f"{mot} is WRITTEN in coloration.py: the list became a copy again")


def test_a_word_absent_from_the_grammar_takes_no_color():
    """The counter-proof of the derivation.

    Without it, a function coloring EVERYTHING would make the previous test
    green without deriving anything at all.
    """
    assert coloration._classe_du_mot("entity") == "s-kw"
    assert coloration._classe_du_mot("courriel") is None
    assert coloration._classe_du_mot("libelle") is None
    assert coloration._classe_du_mot("Commande") == "s-nom", "a declared name"


def test_each_token_color_reads_on_both_code_backgrounds():
    palette, encre = _palette()

    for nom, couleur in sorted(palette.items()):
        for fond in (FOND_CLAIR, FOND_SOMBRE):
            mesure = _contraste(couleur, fond)
            assert mesure >= SEUIL_TEXTE, (
                f"--{nom} ({couleur}) drops to {mesure:.2f}:1 on {fond} — "
                f"below the text threshold ({SEUIL_TEXTE}:1)")


def test_no_color_pair_is_indistinguishable():
    """Two tokens are distinguished by hue, lightness OR vividness.

    Contrast BETWEEN two tokens is NOT WCAG's measure (which is about the
    background): two colors of the same lightness separated by hue read very
    well. What is refused is a pair close on all THREE axes — that is how the
    declared names in cream (#f0e6d8) could not be told from the block's ink,
    measured at 1.1:1 with 12 chroma apart. The ink enters the comparison: a
    token resembling bare text colors nothing.
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

    assert not confuses, "colors close on the three axes: " + " ; ".join(confuses)


def test_the_home_page_spec_really_uses_several_families():
    """Before, two classes in all — `.kw` in gold and `.cm` in gray.

    Without this count, replacing the highlighting with a `<span class="s-kw">`
    put on everything would leave the page "colored" and the site monochrome.
    """
    familles = set(re.findall(r'class="(s-\w+)"', LANDING_HTML))
    jetons = len(re.findall(r'class="s-\w+"', LANDING_HTML))

    assert len(familles) >= 5, f"only {sorted(familles)} on the home page"
    assert jetons >= 40, f"{jetons} colored tokens: the spec is no longer highlighted"


# The classes that put a phrase BEFORE a title. Two and not one: the first pass
# had only removed `.eyebrow`, and the three positioning cards carried their
# overline under another name (`01 · INFRASTRUCTURE`). Looking for a single
# name kept half of the rule.
SURTITRES = ("eyebrow", "stage-no")


def test_no_section_carries_an_overline_any_more():
    """"The backend is compiled, not improvised" was read BEFORE the title.

    The only deliberate survivor is the error page, where the overline IS the
    title — "Error 404" does not announce a section, it names it.
    """
    pages = {"accueil": LANDING_HTML, "docs": DOCS_HTML, "mcp": MCP_HTML,
             "sécurité": SECURITY_HTML, "connexion": AUTH_HTML,
             "compte": ACCOUNT_HTML}

    for nom, page in pages.items():
        assert "<section" in page or "<main" in page, (
            f"the {nom} page no longer has a section: the test no longer guards anything")
        for classe in SURTITRES:
            assert f'class="{classe}"' not in page, (
                f"an .{classe} overline came back on the {nom} page")


def test_no_rule_dresses_a_vanished_overline():
    """An orphan CSS rule suggests the overline can come back.

    It is point 154's shape: a guarantee that no longer applies to anything makes
    no noise. `.flow-stage .stage-no` left with the markup it dressed; the
    deliberate exception is `.eyebrow`, still used by the error page.
    """
    feuille = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>",
                                   LANDING_HTML, re.S | re.I))
    assert feuille, "the stylesheet is no longer inlined"
    assert "stage-no" not in feuille, (
        "a rule still styles an overline that no longer exists")
