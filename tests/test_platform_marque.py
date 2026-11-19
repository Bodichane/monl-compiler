"""The identity, verified rather than hoped for.

`theme.py` claims in its own docstring that the contrasts meet WCAG AA. A claim
in a comment protects from nothing: it is exactly what point 85 holds against
rules that produce nothing. This file computes the ratios from the variables
really declared, and refuses colors hard-coded anywhere but the stylesheet.

What it took to write it: the previous identity overhaul had left FIVE greens
from the old palette in `console.py` (terminal border, dots, comment text,
input field border). They went through a complete palette change without
anything saying so, because a hard-coded color belongs to no theme and never
breaks.
"""

import pathlib
import re
import sys

from PIL import Image

from monl_platform import brand, theme, theme_fragments
from tests.support.cas import verifier_chaque_cas

PAQUET = pathlib.Path(theme.__file__).parent
COULEUR = re.compile(r"#[0-9a-fA-F]{6}\b")


def _luminance(hexa: str) -> float:
    hexa = hexa.lstrip("#")
    canaux = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineaire = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lineaire[0] + 0.7152 * lineaire[1] + 0.0722 * lineaire[2]


def contraste(avant: str, arriere: str) -> float:
    clair, sombre = sorted((_luminance(avant), _luminance(arriere)), reverse=True)
    return (clair + 0.05) / (sombre + 0.05)


def _palette(bloc: str) -> dict[str, str]:
    """The variables of a CSS declaration block."""
    return {nom: valeur for nom, valeur in
            re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", bloc)}


def _blocs() -> dict[str, dict[str, str]]:
    css = theme_fragments.CSS
    racine = css[css.index(":root {"):css.index("@media (prefers-color-scheme: dark)")]
    sombre_debut = css.index(':root[data-theme="dark"] {')
    sombre = css[sombre_debut:css.index("}", sombre_debut)]
    clair = _palette(racine)
    # The dark theme only redeclares what changes: the rest is inherited.
    return {"clair": clair, "sombre": {**clair, **_palette(sombre)}}


# The pairs that carry text or delimit a control. A pair absent from this list
# is not "safe", it is not measured — adding it is the expected gesture when
# adding a color role.
COUPLES_TEXTE = [
    ("ink", "bg"), ("ink", "surface"), ("ink", "surface-2"),
    ("muted", "bg"), ("muted", "surface"), ("muted", "surface-2"),
    ("brand", "bg"), ("brand", "surface"), ("brand", "soft"),
    ("on-brand", "brand"),
    ("code-ink", "code-bg"), ("code-accent", "code-bg"), ("code-muted", "code-bg"),
    ("danger", "danger-bg"),
]
COUPLES_CONTROLE = [("line-strong", "bg"), ("line-strong", "surface")]


def test_the_text_palette_holds_on_the_three_surfaces():
    """The darkened palette's witness reads the stylesheet, never a copy."""
    table = ["clair", "sombre"]

    def cas(theme_nom):
        palette = _blocs()[theme_nom]
        for avant in ("ink", "muted", "accent", "danger"):
            for arriere in ("bg", "surface", "surface-2"):
                ratio = contraste(palette[avant], palette[arriere])
                assert ratio >= 4.5, (
                    f"[{theme_nom}] {avant} ({palette[avant]}) sur {arriere} "
                f"({palette[arriere]}) : {ratio:.2f}:1, il faut 4.5")

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_the_text_meets_wcag_aa_contrast():
    table = ["clair", "sombre"]

    def cas(theme_nom):
        palette = _blocs()[theme_nom]
        for avant, arriere in COUPLES_TEXTE:
            assert avant in palette and arriere in palette, f"{avant}/{arriere} absent"
            ratio = contraste(palette[avant], palette[arriere])
            assert ratio >= 4.5, (
                f"[{theme_nom}] {avant} ({palette[avant]}) sur {arriere} "
            f"({palette[arriere]}) : {ratio:.2f}:1, il faut 4.5")

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_controls_stand_out_from_the_background():
    """WCAG 1.4.11: an interface component is delimited at 3:1. It is
    `--line-strong`'s reason for being — `--line` only separates cards and need
    not meet this threshold."""
    table = ["clair", "sombre"]

    def cas(theme_nom):
        palette = _blocs()[theme_nom]
        for avant, arriere in COUPLES_CONTROLE:
            ratio = contraste(palette[avant], palette[arriere])
            assert ratio >= 3.0, (
                f"[{theme_nom}] bordure de contrôle {palette[avant]} sur "
            f"{palette[arriere]} : {ratio:.2f}:1, il faut 3.0")

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_both_themes_declare_the_same_roles():
    """A role defined on one side only lets the other theme inherit a color
    designed for the first — that is how a light background ends up on a dark
    page."""
    table = ["clair", "sombre"]

    def cas(theme_nom):
        blocs = _blocs()
        manquants = set(blocs["clair"]) - set(blocs["sombre"])
        assert not manquants, f"rôles absents du thème sombre : {sorted(manquants)}"

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_no_hard_coded_color_outside_the_stylesheet():
    """The previous overhaul left five greens in `console.py`. A hard-coded color
    belongs to no theme: it survives any palette change without ever failing."""
    fautifs = {}
    for module in sorted(PAQUET.glob("*.py")):
        if module.name in {"theme.py", "theme_fragments.py"}:
            continue
        trouvees = COULEUR.findall(module.read_text(encoding="utf-8"))
        if trouvees:
            fautifs[module.name] = sorted(set(trouvees))
    assert not fautifs, (
        f"couleurs écrites en dur hors de theme.py : {fautifs} — "
        "employez une variable CSS (var(--brand), var(--code-muted)…)")


def test_the_page_mark_follows_the_text_color():
    """The original defect: a mark carrying its own background disappeared on the
    dark theme. In `currentColor`, it no longer can."""
    assert "currentColor" in theme.LOGO_MARK
    assert "<text" not in theme.LOGO_MARK, "un tracé ne dépend d'aucune police"
    # The mark is now entirely monochrome: no fixed color, and no background
    # that would make it disappear in one of the two themes.
    assert "<rect" not in theme.LOGO_MARK, "le signe s'est remis un fond"
    figees = set(COULEUR.findall(theme.LOGO_MARK))
    assert not figees, f"couleur figée inattendue : {figees}"


def test_the_favicon_carries_its_colors_as_it_has_nothing_to_inherit():
    """The only exception, and it is justified: a browser tab offers no inherited
    color, and expects a background."""
    assert "<text" not in theme.FAVICON
    assert "currentColor" not in theme.FAVICON
    # Written WITHOUT citing a color: the previous version expected a
    # hard-coded `#ffb020` and would have seen nothing of a favicon repainted
    # in an unreadable tint, as long as that literal appeared in it. What
    # counts is the CONTRAST between the badge and its strokes — that holds for
    # any palette.
    couleurs = COULEUR.findall(theme.FAVICON)
    assert len(couleurs) >= 2, f"il faut un fond et au moins un tracé : {couleurs}"
    fond, traces = couleurs[0], couleurs[1:]
    ratios = [contraste(trace, fond) for trace in traces]
    # 3:1 is WCAG 2.2's threshold for a GRAPHICAL object (1.4.11) — an icon is
    # not text, and the standard even explicitly exempts logotypes. The 4.5
    # threshold applied when the mark was a LETTER. But a floor alone would let
    # the icon become a low-contrast mush: we therefore ALSO require at least
    # one stroke to hold 4.5, the one carrying the reading.
    for trace, ratio in zip(traces, ratios, strict=True):
        assert ratio >= 3.0, f"tracé {trace} sur {fond} : {ratio:.2f}:1"
    assert max(ratios) >= 4.5, (
        f"aucun tracé ne porte l'icône : {[f'{r:.2f}' for r in ratios]}")


def test_the_mark_file_and_the_stylesheet_draw_the_same_sign():
    """Two sources would end up diverging, and `docs/BRAND.md` points to the file:
    it must show what the page really serves."""
    svg = (pathlib.Path(theme.__file__).parents[2] / "docs/brand/monl-mark.svg"
           ).read_text(encoding="utf-8")
    traces = re.findall(r'd="([^"]+)"', theme.LOGO_MARK)
    assert traces, "le signe ne contient plus aucun tracé"
    for trace in traces:
        assert trace in svg, f"tracé absent de docs/brand/monl-mark.svg : {trace}"


# ---------------------------------------------------------------------------
# Cibles tactiles
# ---------------------------------------------------------------------------

# Selector → module declaring it. The list is explicit rather than guessed: a
# test looking for "everything that looks like a button" ends up measuring
# containers, and a test wrong about a correct page teaches people to stop
# reading tests (point 57).
CIBLES = [
    (".navlinks a", "theme_fragments.py"),
    (".primary, .secondary, .ghost, .nav-cta", "theme_fragments.py"),
    (".icon-btn", "theme_fragments.py"),
    (".copy", "theme_fragments.py"),
    (".brand", "theme_fragments.py"),
    (".toc a", "guide_template.py"),
    (".rail button", "console_template.py"),
    (".auth-tabs button", "account.py"),
    # Added AFTER measuring in the browser: the list did not contain them, so
    # the test was green while thirteen footer links rendered at 22.4 px on
    # EVERY page. A guarantee only covers what is written into it.
    (".footer nav a", "theme_fragments.py"),
    (".service-status", "theme_fragments.py"),
    (".docs-nav a", "docs_page.py"),
]
MINIMUM = 44


def _hauteur_declaree(source: str, selecteur: str) -> int | None:
    """The `min-height` (or `height`) of the block following this selector."""
    debut = source.find(selecteur + " {")
    if debut == -1:
        debut = source.find(selecteur + "{")
    if debut == -1:
        return None
    bloc = source[debut:source.find("}", debut)]
    trouve = re.search(r"(?:min-)?height:\s*(\d+)px", bloc)
    return int(trouve.group(1)) if trouve else None


def test_touch_targets_are_at_least_44px():
    """WCAG 2.5.5: a target is missed by finger under 44 px. A missed navigation
    link does not fail — it opens the neighboring page, which is worse than a
    click without effect."""
    table = CIBLES

    def cas(selecteur, module):
        source = (PAQUET / module).read_text(encoding="utf-8")
        hauteur = _hauteur_declaree(source, selecteur)
        assert hauteur is not None, (
            f"`{selecteur}` ne déclare plus de hauteur dans {module} — "
        "si la règle a été renommée, mettez CIBLES à jour plutôt que de "
        "supprimer la garantie")
        assert hauteur >= MINIMUM, (
            f"`{selecteur}` ({module}) : {hauteur}px, il en faut {MINIMUM}")

    verifier_chaque_cas(table, cas)


def test_the_wordmark_follows_the_theme_instead_of_carrying_its_background():
    """The measured defect: as an `<img>`, the logo banner keeps its background
    #2e2b25 whatever the theme — that is 1.29:1 against the dark page, a logo
    literally invisible in the header. A raster cannot follow a theme; that is
    the reason for inline SVG, not a preference.

    The test is therefore about the MEANS as much as the result: going back to an
    `<img>` tag would lose the guarantee again without any color changing."""
    assert "<img" not in theme.WORDMARK, (
        "un raster ne suit aucun thème — le wordmark doit rester en SVG inline")
    assert "currentColor" in theme.WORDMARK, "les lettres doivent hériter du texte"
    # No plate at all any more: the lockup is painted directly and the page
    # background shows through its openings. It is stronger than the old
    # guarantee, which hollowed the letters out of a banner.
    assert "<rect" not in theme.WORDMARK, "le wordmark s'est remis un fond"
    figees = set(COULEUR.findall(theme.WORDMARK))
    assert not figees, f"couleur figée dans le wordmark : {figees}"
    assert theme.NAV_WORDMARK in theme.page(title="t", description="d", body=""), (
        "le wordmark compact n'est pas servi dans la page")


def test_the_wordmark_stays_readable_in_both_themes():
    """The lockup takes `--ink` on the page: this pair carries the reading of the
    word. It must therefore hold in BOTH themes, otherwise the logo fades on one
    side."""
    table = ["clair", "sombre"]

    def cas(theme_nom):
        palette = _blocs()[theme_nom]
        lettres = contraste(palette["ink"], palette["bg"])
        assert lettres >= 4.5, (
            f"[{theme_nom}] lettres {palette['ink']} sur page {palette['bg']} : "
        f"{lettres:.2f}:1")

    verifier_chaque_cas([(valeur,) for valeur in table], cas)


def test_mark_strokes_carry_no_color():
    """`brand.py` is DATA: colors are composed in theme.py.

    Exempting one more file from the "no hard-coded color" rule would widen the
    door `test_no_hard_coded_color_outside_the_stylesheet` closes — which is why
    the strokes leave it instead of entering it."""
    from monl_platform import brand
    source = pathlib.Path(brand.__file__).read_text(encoding="utf-8")
    assert not COULEUR.findall(source), COULEUR.findall(source)
    for nom in ("WORDMARK_PATH", "NAV_MARK_PATH", "NAV_TEXT_PATH", "MARK_PATH"):
        assert getattr(brand, nom).startswith("M"), f"{nom} n'est pas un tracé"
    assert isinstance(brand.VUE, tuple) and len(brand.VUE) == 2, (
        "VUE porte le viewBox du mot : sans elle, theme.py le devinerait")


def test_the_share_tags_invent_no_address(monkeypatch):
    """A share image must be ABSOLUTE for a robot to fetch it. Deducing it from
    the `Host` header would make it point wherever a third party wants — same
    boundary as at point 145 for the OAuth return address. Without a declared
    public URL, monl stays silent rather than guessing."""
    monkeypatch.delenv("MONL_PLATFORM_PUBLIC_URL", raising=False)
    muet = theme.page(title="t", description="d", body="")
    assert "og:image" not in muet, "une image de partage a été inventée"
    assert 'name="twitter:card" content="summary"' in muet

    monkeypatch.setenv("MONL_PLATFORM_PUBLIC_URL", "https://exemple.test/")
    parlant = theme.page(title="t", description="d", body="")
    assert 'content="https://exemple.test/brand/monl-social.png"' in parlant
    assert 'content="summary_large_image"' in parlant


def test_raster_images_do_not_drift_from_the_mark():
    """`/favicon.ico` must exist, and say the SAME thing as `/favicon.svg`.

    Browsers request this path by default, even when the page declares an SVG. It
    answered 404 — and a 404 replaces nothing: the browser kept the old icon from
    its cache, which "reappeared" through no fault of the server.

    Made FROM `brand.MARK_PATH`, never copied from a PNG: a copied `.ico` would
    drift the day the mark changes, silently. The test regenerates and compares,
    like point 156's mark file — which had drifted, and which a test caught.

    **The comparison is about PIXELS, never bytes.** The first try compared the
    files byte for byte: green locally, red on CI's three Python versions. An
    `.ico` and a `.png` carry COMPRESSED pixels, and the same Pillow 12.3 linked
    to different zlib versions does not write the same byte sequence for the same
    image. The test therefore measured the ENCODER and not the DRAWING — it would
    have denounced a dependency update as loudly as a drift of the mark. Decoding,
    however, is lossless.
    """
    import importlib.util
    import tempfile

    from PIL import Image

    outil = pathlib.Path(theme.__file__).parents[2] / "outils" / "fabriquer_images.py"
    assert outil.exists(), "l'outil qui fabrique les images a disparu"
    spec = importlib.util.spec_from_file_location("fabriquer_images", outil)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _pixels(chemin):
        """The decoded pixels: every size of an ICO, a PNG's image."""
        with Image.open(chemin) as image:
            if getattr(image, "format", "") != "ICO":
                return [(image.size, image.convert("RGBA").tobytes())]
            rendus = []
            for taille in sorted(image.ico.sizes()):
                image.size = taille
                rendus.append((taille, image.convert("RGBA").tobytes()))
            return rendus

    # The THREE raster artifacts come from the same tool and the same source.
    # Keeping only one would let the other two drift silently — and the share
    # card is precisely the one nobody looks at.
    with tempfile.TemporaryDirectory() as dossier:
        temporaire = pathlib.Path(dossier)
        for nom, fabrique in (("favicon.ico", module.fabriquer_ico),
                              ("monl-wordmark.png", module.fabriquer_wordmark),
                              ("monl-social.png", module.fabriquer_social)):
            servi = PAQUET / "static" / nom
            assert servi.exists(), f"{nom} n'existe pas"
            refait = fabrique(temporaire / nom)

            attendu, obtenu = _pixels(refait), _pixels(servi)
            assert [t for t, _ in attendu] == [t for t, _ in obtenu], (
                f"{nom} n'a plus les mêmes tailles d'image")
            for (taille, a), (_, b) in zip(attendu, obtenu, strict=True):
                assert a == b, (
                    f"{nom} en {taille[0]}x{taille[1]} ne correspond plus aux "
                    "tracés de la marque — relancer outils/fabriquer_images.py")


def test_pages_declare_both_icons():
    """The SVG stays preferred, the `.ico` is the fallback preventing the 404.

    Declaring the SVG alone let browsers request `/favicon.ico` and receive
    nothing.
    """
    from monl_platform.theme import page

    html = page(title="t", description="d", body="<main></main>", active="home")
    assert '<link rel="icon" href="/favicon.ico?v=' in html
    assert '<link rel="icon" href="/favicon.svg?v=' in html
    assert html.index("/favicon.ico") < html.index("/favicon.svg"), (
        "le SVG doit être déclaré APRÈS le .ico pour rester préféré")


def test_the_icon_address_changes_with_its_content():
    """The declared fingerprint is the served byte's, not a hand-written number.

    `/favicon.ico` is an address that never changes: the browser keeps the icon it
    already has, and the OLD one reappears through no fault of the server — the
    defect reported when the logo changed. A CONTENT fingerprint changes exactly
    when the image changes; a hand-written number would have the same defect the
    day someone forgets to increment it.
    """
    import hashlib

    from monl_platform.theme import FAVICON, ICONE_ICO, VERSION_ICO, VERSION_SVG, page

    assert hashlib.sha256(ICONE_ICO.read_bytes()).hexdigest()[:8] == VERSION_ICO
    assert hashlib.sha256(FAVICON.encode()).hexdigest()[:8] == VERSION_SVG
    assert VERSION_ICO != VERSION_SVG, "deux fichiers, deux empreintes"

    html = page(title="t", description="d", body="<main></main>", active="home")
    assert f"/favicon.ico?v={VERSION_ICO}" in html
    assert f"/favicon.svg?v={VERSION_SVG}" in html


def test_only_the_versioned_address_is_kept_long():
    """A bare URL cannot be versioned: it is kept briefly.

    It is the one the browser requests BY DEFAULT without reading the page. Keeping
    it a year, as before, made a stale icon survive long after its replacement —
    and that is what made the defect so persistent.
    """
    from monl_platform.theme import VERSION_ICO, cache_icone

    versionnee = cache_icone(VERSION_ICO, VERSION_ICO)["Cache-Control"]
    nue = cache_icone("", VERSION_ICO)["Cache-Control"]
    perimee = cache_icone("vieille-empreinte", VERSION_ICO)["Cache-Control"]

    assert "immutable" in versionnee and "max-age=31536000" in versionnee
    assert "immutable" not in nue, "une adresse nue ne peut pas être immuable"
    assert nue == perimee, "une empreinte fausse vaut une absence d'empreinte"
    assert int(nue.rsplit("=", 1)[1]) <= 3600, (
        f"l'adresse nue se garde {nue} — une icône périmée survivrait")


def test_the_account_form_never_refuses_silently():
    """A refusal must be written IN the page, never in a browser bubble.

    Measured: with "joe" as address, no request went out, the `#auth-error`
    banner stayed EMPTY, and the only message was the native bubble — the one a
    password manager window covers. The button seemed to do nothing.

    `novalidate` is what hands control to the script: without it, the browser
    blocks the submission and `onsubmit` is never called. The message is not
    rewritten — we reuse `validationMessage`, already translated by the browser.
    """
    from monl_platform import account

    assert '<form id="auth-form" novalidate>' in account.AUTH_HTML, (
        "sans novalidate, le navigateur bloque l'envoi et la bannière reste vide")
    assert "validationMessage" in account.AUTH_HTML, (
        "le refus client n'atteint pas la bannière de la page")
    assert "error.className='form-error show'" in account.AUTH_HTML


def test_the_strokes_look_like_the_provided_drawing():
    """FIDELITY, which nothing else guards.

    All the other witnesses of this file compare the artifacts WITH EACH OTHER —
    the rasters do not drift from the mark, the stylesheet draws the same sign as
    the file. They would therefore stay GREEN on a wrong logo, as long as it is
    wrong everywhere in the same way. Only the comparison with the PNG provided by
    the human says whether the stroke looks like what was asked for.

    The safeguard also exists in `outils/vectoriser_logo.py`, which REFUSES to
    write beyond the tolerance. It is not a duplicate: the tool only runs the day
    someone re-vectorizes, this witness runs on every run of the suite. One
    prevents writing a bad stroke, the other prevents keeping one.

    THE FRAMING TRAP, measured by falling into it: the tool thresholds the alpha
    channel at `ALPHA_MIN` before cropping. Comparing on a bare `getbbox()` —
    which keeps the slightest antialiasing pixel — gives a footprint of 1676 x 492
    instead of 1667 x 438, two different framings, and an announced gap of 234 %
    on a perfectly faithful logo. The threshold is part of the measurement.
    """
    outils = pathlib.Path(__file__).resolve().parent.parent / "outils"
    sys.path.insert(0, str(outils))
    try:
        import vectoriser_logo
        from tracage import ecart_de_rendu
    finally:
        sys.path.remove(str(outils))

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "docs" / "brand" / "monl-logo-source.png")
    alpha = Image.open(source).convert("RGBA").getchannel("A")
    seuil = alpha.point(lambda a: 255 if a >= vectoriser_logo.ALPHA_MIN else 0)
    alpha = alpha.crop(seuil.getbbox())

    separation = vectoriser_logo._separation(alpha)
    coupe = vectoriser_logo._coupe_descripteur(alpha, separation)
    parties = {
        "WORDMARK_PATH": (alpha, brand.WORDMARK_PATH),
        "NAV_MARK_PATH": (vectoriser_logo._partie(alpha, lambda x, _y: x < separation),
                          brand.NAV_MARK_PATH),
        "NAV_TEXT_PATH": (vectoriser_logo._partie(
            alpha, lambda x, y: x >= separation and y < coupe), brand.NAV_TEXT_PATH),
    }

    mesures = {}
    for nom, (reference, trace) in parties.items():
        masque = reference.point(
            lambda a: 255 if a >= vectoriser_logo.ALPHA_MIN else 0).convert("1")
        mesures[nom] = ecart_de_rendu(masque, trace)

    trop_loin = {n: f"{e:.2%}" for n, e in mesures.items()
                 if e > vectoriser_logo.TOLERANCE}
    assert not trop_loin, (
        f"le tracé ne ressemble plus au dessin fourni : {trop_loin} "
        f"(tolérance {vectoriser_logo.TOLERANCE:.0%})")
    # The counterpart: a tolerance far above what we measure no longer refuses
    # anything. If the real gaps fell to zero, the MEASUREMENT would be suspect
    # — a pixel-identical rendering would assume the stroke is compared with
    # itself.
    assert max(mesures.values()) > 0, (
        "écart nul : la mesure compare probablement le tracé avec lui-même")
