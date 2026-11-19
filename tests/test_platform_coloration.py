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
FOND_DARK = "#0f0e0c"

THRESHOLD_TEXT = 4.5       # WCAG 1.4.3 — code is read, it is not a graphic
GAP_HUE = 35       # degrees
GAP_CLARITY = 1.35     # rapport de contraste entre deux jetons
GAP_CHROMA = 40       # out of 255 — what separates a gray from a clear color
CHROMA_COLORED = 30      # below this, hue carries nothing any more


def _rgb(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def _chroma(color):
    channels = _rgb(color)
    return max(channels) - min(channels)


def _hue(color):
    return colorsys.rgb_to_hsv(*[v / 255 for v in _rgb(color)])[0] * 360


def _luminance(color):
    def linear(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, v, b = (c / 255 for c in _rgb(color))
    return 0.2126 * linear(r) + 0.7152 * linear(v) + 0.0722 * linear(b)


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
    ink = re.search(r"--code-ink:\s*(#[0-9a-fA-F]{6})", css)
    assert palette, "no --s-* color in the stylesheet: the test no longer guards anything"
    assert ink, "--code-ink introuvable"
    return palette, ink.group(1)


def test_keywords_are_derived_from_the_grammar():
    """No keyword is WRITTEN in the highlighting module.

    The witness is about words that arrived late in the project (points 90 to
    116). If they are colored WITHOUT appearing in the source, the derivation
    holds. Copying a list would make the names appear: the test fails.
    """
    late = ("publicWhen", "oncePer", "numbered", "releases",
               "writableAfterPayment", "requiresOwn", "derivedFrom", "sumOf")

    for word in late:
        assert coloration._class_of_word(word) == "s-kw", f"{word} is no longer highlighted"
        assert word not in SOURCE, (
            f"{word} is WRITTEN in coloration.py: the list became a copy again")


def test_a_word_missing_from_the_grammar_takes_no_color():
    """The counter-proof of the derivation.

    Without it, a function coloring EVERYTHING would make the previous test
    green without deriving anything at all.
    """
    assert coloration._class_of_word("entity") == "s-kw"
    assert coloration._class_of_word("courriel") is None
    assert coloration._class_of_word("libelle") is None
    assert coloration._class_of_word("Commande") == "s-nom", "a declared name"


def test_each_token_color_reads_on_both_code_backgrounds():
    palette, ink = _palette()

    for name, color in sorted(palette.items()):
        for fond in (FOND_CLAIR, FOND_DARK):
            measure = _contraste(color, fond)
            assert measure >= THRESHOLD_TEXT, (
                f"--{name} ({color}) drops to {measure:.2f}:1 on {fond} — "
                f"below the text threshold ({THRESHOLD_TEXT}:1)")


def test_no_color_pair_is_indistinguishable():
    """Two tokens are distinguished by hue, lightness OR vividness.

    Contrast BETWEEN two tokens is NOT WCAG's measure (which is about the
    background): two colors of the same lightness separated by hue read very
    well. What is refused is a pair close on all THREE axes — that is how the
    declared names in cream (#f0e6d8) could not be told from the block's ink,
    measured at 1.1:1 with 12 chroma apart. The ink enters the comparison: a
    token resembling bare text colors nothing.
    """
    palette, ink = _palette()
    all_ = dict(palette, encre=ink)
    confuses = []

    for (a, ca), (b, cb) in itertools.combinations(sorted(all_.items()), 2):
        gap_hue = min(abs(_hue(ca) - _hue(cb)),
                           360 - abs(_hue(ca) - _hue(cb)))
        colored = _chroma(ca) >= CHROMA_COLORED and _chroma(cb) >= CHROMA_COLORED
        distinct = (
            (colored and gap_hue >= GAP_HUE)
            or _contraste(ca, cb) >= GAP_CLARITY
            or abs(_chroma(ca) - _chroma(cb)) >= GAP_CHROMA
        )
        if not distinct:
            confuses.append(f"{a}/{b} : {gap_hue:.0f}°, "
                            f"{_contraste(ca, cb):.2f}:1, "
                            f"Δchroma {abs(_chroma(ca) - _chroma(cb))}")

    assert not confuses, "colors close on the three axes: " + " ; ".join(confuses)


def test_the_home_page_spec_really_uses_several_families():
    """Before, two classes in all — `.kw` in gold and `.cm` in gray.

    Without this count, replacing the highlighting with a `<span class="s-kw">`
    put on everything would leave the page "colored" and the site monochrome.
    """
    families = set(re.findall(r'class="(s-\w+)"', LANDING_HTML))
    tokens = len(re.findall(r'class="s-\w+"', LANDING_HTML))

    assert len(families) >= 5, f"only {sorted(families)} on the home page"
    assert tokens >= 40, f"{tokens} colored tokens: the spec is no longer highlighted"


# The classes that put a phrase BEFORE a title. Two and not one: the first pass
# had only removed `.eyebrow`, and the three positioning cards carried their
# overline under another name (`01 · INFRASTRUCTURE`). Looking for a single
# name kept half of the rule.
OVERLINES = ("eyebrow", "stage-no")


def test_no_section_carries_an_overline_any_more():
    """"The backend is compiled, not improvised" was read BEFORE the title.

    The only deliberate survivor is the error page, where the overline IS the
    title — "Error 404" does not announce a section, it names it.
    """
    pages = {"accueil": LANDING_HTML, "docs": DOCS_HTML, "mcp": MCP_HTML,
             "sécurité": SECURITY_HTML, "connexion": AUTH_HTML,
             "compte": ACCOUNT_HTML}

    for name, page in pages.items():
        assert "<section" in page or "<main" in page, (
            f"the {name} page no longer has a section: the test no longer guards anything")
        for class_ in OVERLINES:
            assert f'class="{class_}"' not in page, (
                f"an .{class_} overline came back on the {name} page")


def test_no_rule_dresses_a_vanished_overline():
    """An orphan CSS rule suggests the overline can come back.

    It is point 154's shape: a guarantee that no longer applies to anything makes
    no noise. `.flow-stage .stage-no` left with the markup it dressed; the
    deliberate exception is `.eyebrow`, still used by the error page.
    """
    sheet = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>",
                                   LANDING_HTML, re.S | re.I))
    assert sheet, "the stylesheet is no longer inlined"
    assert "stage-no" not in sheet, (
        "a rule still styles an overline that no longer exists")
