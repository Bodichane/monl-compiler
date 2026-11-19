"""The root carries the presentation page, the console lives on /console.

The console is a TOOL: it assumes one already knows what monl does. Someone
who did not got the console in their face, without a word about the product
nor any way to install it.
"""

import json
import pathlib
import re
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform import brand, landing_vitrine
from monl_platform.app import create_app
from monl_platform.landing import LANDING_HTML

RESSOURCE_EXTERNE = re.compile(
    r"<(?:link|script|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - never called here
        raise AssertionError("la page de présentation n'appelle aucune IA")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path):
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("le serveur n'a pas démarré")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_root_presents_the_product(platform):
    reponse = requests.get(platform, timeout=10)

    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]
    assert '<html lang="en">' in reponse.text
    # What a product page must say: what it is, and how to get it.
    assert "compiler" in reponse.text.lower()
    assert "Try it in the console" in reponse.text


def test_the_page_leads_to_the_console(platform):
    reponse = requests.get(platform, timeout=10)

    assert 'href="/console"' in reponse.text
    console = requests.get(f"{platform}/console", timeout=10, allow_redirects=False)
    assert console.status_code == 303
    assert console.headers["location"].startswith("/login")


def test_the_page_loads_no_remote_resource(platform):
    """Served locally, it must work without any network."""
    reponse = requests.get(platform, timeout=10)

    faute = RESSOURCE_EXTERNE.search(reponse.text)
    assert faute is None, f"ressource distante dans la page : {faute.group(0)}"


def test_every_outgoing_url_is_a_link_and_nothing_else(platform):
    """The safeguard above was widened: this one closes it again.

    Allowing outgoing links must not allow a URL anywhere. Every `https://` of the
    page must be the target of an `<a href>` — not of an `<img>`, a `fetch`, or a
    font.
    """
    page = requests.get(platform, timeout=10).text
    sans_commentaires = re.sub(r"/\*.*?\*/", "", page, flags=re.DOTALL)
    sans_commentaires = re.sub(r"<!--.*?-->", "", sans_commentaires, flags=re.DOTALL)

    for position in (m.start() for m in re.finditer(r"https?://", sans_commentaires)):
        debut = sans_commentaires.rfind("<", 0, position)
        balise = sans_commentaires[debut:position]
        # ONE exemption, and a narrow one: an inline SVG's `xmlns` is a
        # NAMESPACE, not an address — no browser fetches it. The exemption is
        # about the attribute, never the domain: writing "except w3.org" would
        # let a real request to w3.org through.
        if re.search(r"\bxmlns(:\w+)?\s*=\s*['\"]$", balise):
            continue
        assert re.match(r"<a\b[^>]*\bhref\s*=\s*['\"]$", balise), (
            "URL sortante hors d'un lien : "
            + sans_commentaires[position:position + 60]
        )


def test_the_page_respects_reduced_motion():
    """The hero terminal is animated: it must be able to stop."""
    assert "prefers-reduced-motion" in LANDING_HTML


def test_the_console_is_no_longer_at_the_root(platform):
    """The root and the console are two distinct pages, not the same one."""
    racine = requests.get(platform, timeout=10).text
    session = requests.Session()
    inscrit = session.post(f"{platform}/api/auth/register", json={
        "email": "landing-console@example.test", "password": "MotDePasse-123"
    }, timeout=10)
    assert inscrit.status_code == 201, inscrit.text
    console = session.get(f"{platform}/console", timeout=10).text

    assert racine != console
    assert "Compilation console" in console
    assert "Compilation console" not in racine


def test_the_brand_badge_keeps_its_ink_color():
    """The same defect twice: a BROAD rule overrides a precise one.

    `.logo span` (0,1,1) beats `.logo-mark` (0,1,0) and repainted the "m" in
    muted gray on clay — 1.35:1, that is invisible. The same trap had already
    eaten the call-to-action button at the other end of the bar. What is fixed is
    not the precise rule that would need strengthening, it is the broad rule that
    must be narrowed: we therefore forbid the catch-all selector, not a
    particular color.
    """
    assert ".logo span {" not in LANDING_HTML
    assert "brand-wordmark" in LANDING_HTML


def _bande_verticale(trace):
    """The top and bottom really drawn by a path.

    A path on TWO lines goes down to the bottom of its view; a single-line path,
    centered, leaves space above and below. It is the only way to check the
    presence of a second word without reading the drawing by eye.
    """
    nombres = [float(n) for n in re.findall(r"-?\d+\.?\d*", trace)]
    ordonnees = nombres[1::2]
    assert ordonnees, "tracé illisible : la mesure porterait sur du vide"
    return min(ordonnees), max(ordonnees)


def test_the_bar_carries_the_short_form_and_its_label_says_so(platform):
    """The label read aloud must be what is DRAWN.

    This witness was called `test_la_marque_se_lit_monl_compiler` and checked
    `aria-label="MONL"`: its NAME promised the full lockup, its assertion was
    about the short form. Point 167bis — a witness whose name announces a
    guarantee it does not hold makes it look guarded. Measured by rendering both
    marks: the bar draws "MONL" alone, so the label is RIGHT and it was the name
    that lied.

    The full lockup — the one carrying COMPILER — stays used elsewhere (the share
    image, the brand files). Keeping it HERE would be wrong; keeping it NOWHERE
    would let it disappear silently, hence the witness's second half.
    """
    reponse = requests.get(platform, timeout=10)
    assert 'aria-label="MONL"' in reponse.text
    # We do NOT look for "COMPILER" in the page to prove the bar does not
    # announce it: the word legitimately appears there in full ("un réseau pour
    # compiler"), and the witness then measured the PROSE instead of the label.
    # The label is the `aria-label` above — nothing else is read in its place.
    # Checked by measuring it: the broad assertion turned red on a correct
    # page.

    haut_court, bas_court = _bande_verticale(brand.NAV_TEXT_PATH)
    haut_long, bas_long = _bande_verticale(brand.WORDMARK_PATH)
    hauteur = brand.VUE[1]

    assert (bas_court - haut_court) < 0.5 * hauteur, (
        "le texte de la barre occupe deux lignes : ce n'est plus la forme "
        "courte que son intitulé annonce")
    assert (bas_long - haut_long) > 0.9 * hauteur, (
        "le lockup a perdu sa seconde ligne — le logo choisi ne porte plus "
        "COMPILER, et rien d'autre ne le garde")


def test_no_color_is_written_outside_the_theme():
    """A hard-coded color escapes the theme, and only the theme moves.

    The console bar carried `rgba(16, 14, 12, .9)`: when the palette went from
    dark to paper, everything followed the variables EXCEPT it — the bar stayed
    black while its text became black too. Dark on dark, unreadable, and
    invisible to a search for hexadecimal colors. Drop shadows stay allowed: a
    shadow is not a surface color, it darkens whatever is beneath it.
    """
    from monl_platform import theme

    assert "rgba(" in LANDING_HTML  # shadows and separators stay local
    assert "--brand" in theme.CSS and "--on-brand" in theme.CSS


def test_the_demo_shows_real_compilation_outputs(platform):
    """What is shown must come from the compiler, not from a hand.

    A product page inventing its own figures would be exactly what monl forbids
    the sites it produces — and what the substance barrier refuses since point
    143.
    """
    page = requests.get(platform, timeout=10).text

    assert "verified specification" in page
    # The four examples really compiled by the platform tests.
    for modele in ("Public showcase", "Appointment book",
                   "Shop and payment", "Community feed"):
        assert modele in page
    assert "frontend_contract.json" in page


def test_a_reveal_is_never_hidden_by_an_inline_style():
    """An INLINE style is not undone by a class.

    The page set `element.style.opacity = "0"` on each block to reveal, then
    relied on `.rise.seen { opacity: 1 }` to show it. But an inline style beats
    any class selector: the sections NEVER reappeared. Measured on the served page,
    outside reduced motion: 43.3 % blank, including a 993 px band — the refusals,
    the figures and the final call entirely invisible.

    The hidden state must therefore live in a RULE. Comments are removed before
    the search: they talk about the defect, they do not commit it.
    """
    from monl_platform.console import CONSOLE_HTML

    sans_commentaires = re.compile(r"/\*.*?\*/", re.DOTALL)
    for nom, page in (("accueil", LANDING_HTML), ("console", CONSOLE_HTML)):
        propre = sans_commentaires.sub("", page)
        assert not re.search(r"\.style\.opacity\s*=", propre), (
            f"la page {nom} cache un bloc par un style en ligne : une classe "
            "ne pourra pas le défaire"
        )


def test_animated_content_stays_showable_if_the_observer_stays_silent():
    """Invisible content is worse than non-animated content.

    Very tall screen, exotic browser, upstream error: if the IntersectionObserver
    never fires, the page must not stay blank anyway.
    """
    assert "data-reveal" in LANDING_HTML
    assert "IntersectionObserver" in LANDING_HTML
    assert "is-visible" in LANDING_HTML


# ---------------------------------------------------------------------------
# Les trois sections de positionnement (« pourquoi », « vs », « ensemble »)
# ---------------------------------------------------------------------------

def test_the_visitors_three_questions_have_their_section():
    """The site said WHAT monl does without ever saying why this one, how it
    differs from what one knows, nor whether one must choose."""
    for ancre in ("pourquoi-title", "compare-title", "ensemble-title"):
        assert f'id="{ancre}"' in LANDING_HTML, f"section absente : {ancre}"


def test_the_comparison_also_says_what_monl_does_not_bring():
    """A comparison listing only its victories is a comparison one stops
    believing at the first check. The limits line is not politeness: it is what
    makes the rest readable."""
    from monl_platform.landing_pourquoi import COMPARAISON
    axes = [axe for axe, _eux, _nous in COMPARAISON]
    assert "What it does not provide" in axes, axes
    limites = next(nous for axe, _e, nous in COMPARAISON
                   if axe == "What it does not provide")
    for absent in ("hosting", "real-time", "storage"):
        assert absent in limites, f"limite non énoncée : {absent}"
    assert limites in LANDING_HTML, "la ligne des limites n'est pas servie"


def test_no_value_judgment_in_the_comparison():
    """Each line must be a FACT checkable on both sides. "Simpler", "more
    modern", "safer" cannot be checked and do not survive a reader who knows the
    other product."""
    from monl_platform.landing_pourquoi import COMPARAISON
    interdits = ("simpler", "more modern", "safer", "more secure", "faster",
                 "better", "superior", "obsolete")
    texte = " ".join(f"{a} {b} {c}".lower() for a, b, c in COMPARAISON)
    fautifs = [mot for mot in interdits if mot in texte]
    assert not fautifs, f"jugement de valeur dans la comparaison : {fautifs}"


def test_the_sites_postgresql_promise_is_covered_by_a_test():
    """The site claims a generated backend runs on a managed provider's Postgres.
    A document is maintained like code (point 141): the promise must point to a
    test that exists, otherwise it ages silently until it becomes false."""
    from monl_platform.landing_pourquoi import MONTAGES
    montage = next(m for m in MONTAGES if m["etat"] == "verifie"
                   and "MONL_DATABASE_URL" in m["texte"])
    assert "postgresql://" in "\n".join(montage["code"])

    epreuve = pathlib.Path(__file__).with_name("test_postgresql.py")
    assert epreuve.exists(), "la promesse ne pointe sur aucune épreuve"
    source = epreuve.read_text(encoding="utf-8")
    assert "MONL_DATABASE_URL" in source, (
        "l'épreuve ne démarre pas les artefacts avec la variable annoncée")


def test_each_exploit_cites_the_point_documenting_it():
    """The three displayed refusals are REAL defects. Each points to its journal
    entry: a page telling of attacks without a source is a marketing page, not a
    proof."""
    import re as _re

    from monl_platform.landing_pourquoi import REFUS
    journal = (pathlib.Path(__file__).parents[1]
               / "docs" / "design_decisions.md").read_text(encoding="utf-8")
    for refus in REFUS:
        numeros = _re.findall(r"\d+", refus["point"])
        assert numeros, refus["point"]
        for numero in numeros:
            assert f"\n## {numero}." in journal, (
                f"point {numero} cité par « {refus['titre']} » absent du journal")
        assert refus["titre"] in LANDING_HTML


def _specificite(selecteur: str) -> tuple:
    """Returns (id, class/attribute/pseudo-class, type) of a selector.

    Deliberately modest: it can only count sequences of classes, attributes and
    types. `:is()`, `:not()` and `:where()` delegate their weight to their
    content, so their presence would miscount — the shape assertion refuses them
    rather than returning a wrong figure.
    """
    for delegue in (":is(", ":not(", ":where(", ":has("):
        assert delegue not in selecteur, f"poids délégué non calculé : {delegue}"
    reste, attributs = re.subn(r"\[[^\]]*\]", " ", selecteur)
    identifiants = len(re.findall(r"#[-\w]+", reste))
    classes = len(re.findall(r"\.[-\w]+", reste))
    pseudo_classes = len(re.findall(r"(?<!:):[-\w]+", reste))
    types = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][-\w]*)", reste))
    return (identifiants, classes + attributs + pseudo_classes, types)


def test_the_sliding_marker_takes_the_tab_background():
    """The active tab's background is HANDED to the moving marker.

    This cascade could not be measured in the browser — the hidden pane does not
    recalculate style, and reads the same value with and without the class. It is
    therefore computed: the selector handing over the background must be STRONGER
    and written AFTER the one setting it. Without both, the tab left fades in .18s
    while the marker takes .34s to arrive, and the two motions contradict each
    other to the eye.
    """
    pose = '.case-tab[aria-selected="true"]'
    cede = '.case-tabs.glisse .case-tab[aria-selected="true"]'

    assert LANDING_HTML.count(cede) == 1, "la règle qui cède le fond a disparu"
    assert _specificite(cede) > _specificite(pose), (
        f"{cede} ne l'emporte plus sur {pose}")
    assert LANDING_HTML.index(cede) > LANDING_HTML.index(pose), (
        "la règle qui cède le fond est passée AVANT celle qui le pose")


def test_the_marker_is_never_served_in_the_html(platform):
    """The marker is SET by the script, never delivered in the markup.

    Delivered in advance, it would show in the list's corner for whoever does not
    run the script — a rectangle placed on nothing — and the active tab would have
    handed over its background with nothing replacing it.
    """
    page = requests.get(platform, timeout=10).text
    # Remove ALL scripts and ALL stylesheets, not stop at the first script: the
    # theme one lives in the <head>, so cutting there left the tab markup
    # entirely out of reach — the test stayed green while serving the marker.
    balisage = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)

    assert "case-explorer" in balisage, "le découpage a emporté les onglets"
    assert "case-repere" not in balisage, "le repère est servi dans le balisage"
    assert "glisse" not in balisage, "la classe qui cède le fond est servie"
    assert "case-repere" in page, "plus personne ne pose le repère"


def test_the_theme_toggle_does_not_animate_for_reduced_motion():
    """Motion refusal is held in JavaScript, since it cannot be in CSS: the
    @media block applies to `*`, which reaches no `::view-transition-*`. The
    toggle must also stay functional where the API does not exist — otherwise the
    theme stops toggling.
    """
    garde = re.search(
        r"if\s*\(\s*!document\.startViewTransition\s*\|\|\s*(\w+)\.matches\s*\)"
        r"\s*\{\s*basculer\(\)\s*;\s*return\s*;\s*\}",
        LANDING_HTML,
    )
    assert garde, "la bascule s'anime sans vérifier l'API ni le mouvement réduit"

    nom = garde.group(1)
    assert re.search(
        rf"var\s+{nom}\s*=\s*window\.matchMedia\(\s*'\(prefers-reduced-motion: reduce\)'\s*\)",
        LANDING_HTML,
    ), f"« {nom} » n'interroge pas le mouvement réduit"


def _feuille(html: str) -> str:
    """Returns the page's inlined CSS, stylesheets concatenated."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))


def _declarations(css: str, selecteur: str) -> list:
    """Returns the blocks written for this selector alone, at rule start.

    Cannot read a grouped selector (".a, .band { … }"): the existence assertion
    below refuses silence rather than leaving the test green on a rule it could
    not find.
    """
    motif = re.compile(r"(?:^|[};])\s*" + re.escape(selecteur) + r"\s*\{([^}]*)\}", re.M)
    return [m.group(1) for m in motif.finditer(css)]


def test_the_site_holds_on_a_single_background():
    """A single background color from the top of the page to the footer.

    The bands carried --surface-2, the rail --surface and the footer --surface:
    three backgrounds on top of the page's --bg, hence a color change at almost
    every section. The rule line now marks the same break without repainting.
    CARDS keep their own background — a card that does not stand out from the
    background stops being a card — and the final block is one, rounded and
    detached, not a band.
    """
    css = _feuille(LANDING_HTML)
    assert css, "la feuille n'est plus inlinée dans la page"

    for bande in (".band", ".proof-rail", ".footer-wrap"):
        blocs = _declarations(css, bande)
        assert blocs, f"la règle {bande} est introuvable : le test ne garde plus rien"
        for bloc in blocs:
            assert "background" not in bloc, (
                f"{bande} repeint le fond — l'alternance de couleurs est revenue")


def test_favicon_ico_really_answers(platform):
    """The file can exist without the route serving it.

    The tests of `test_platform_marque.py` guard the icon's CONTENT; this one
    guards the fact that it can be obtained. Without it, removing the route would
    leave the suite entirely green while browsers again receive a 404 — and keep
    the old icon.
    """
    reponse = requests.get(platform + "/favicon.ico", timeout=10)

    assert reponse.status_code == 200, "/favicon.ico ne répond plus"
    assert reponse.content[:4] == b"\x00\x00\x01\x00", "ce n'est pas un vrai ICO"
    assert reponse.headers["content-type"] == "image/x-icon"

    # And the ROUTE does read the fingerprint: without the `v` parameter,
    # theme.py's cache policy would stay right without ever being applied.
    from monl_platform.theme import VERSION_ICO

    versionnee = requests.get(
        f"{platform}/favicon.ico?v={VERSION_ICO}", timeout=10)
    assert "immutable" in versionnee.headers["cache-control"]
    assert "immutable" not in reponse.headers["cache-control"], (
        "l'adresse nue se garde comme une adresse versionnée")
    assert versionnee.content == reponse.content, "deux icônes différentes"


def test_no_command_overflows_its_card():
    """A crammed command leaves the frame and gets cut — silently.

    Measured: "MONL_DATABASE_URL=postgresql://…  python3 -m uvicorn app:app" fit
    on ONE line in a card with 309 usable px, one read the start and nothing of
    the end, and two commands separated by a middle dot could not be copied. The
    limit is not chosen: it is MEASURED against a real server — 309 usable px at
    7.5 px per character of the block's mono font, at the desktop width where the
    three cards fit side by side, that is the narrowest of the layouts.

    Length is a PROXY for overflow, and it says so: it is the only measurement a
    static test can make. The CSS fallback (`pre-wrap`) is checked separately
    below — without it, a too long line would be cut instead of wrapped, and the
    card would lie about its content.
    """
    from monl_platform.landing_pourquoi import SECTIONS

    blocs = re.findall(r"<pre><code>(.*?)</code></pre>", SECTIONS, re.S)
    assert blocs, "plus aucun bloc de commande : le test ne garde plus rien"

    for bloc in blocs:
        for ligne in bloc.split("\n"):
            assert len(ligne) <= 41, (
                f"{len(ligne)} caractères — la carte en tient 41 :\n  {ligne}")
            assert " · " not in ligne, (
                "deux commandes sur une ligne, séparées par un point médian : "
                "elles ne se copient pas")


def test_a_command_block_wraps_instead_of_being_cut():
    """The safety net under the limit above.

    `overflow-x: auto` alone lets the line scroll OUTSIDE the frame: on a card,
    nobody goes looking for it. `pre-wrap` wraps it.
    """
    from monl_platform.landing_pourquoi import EXTRA_CSS

    regle = _declarations(EXTRA_CSS, ".montage pre")
    assert regle, "la règle .montage pre est introuvable"
    assert "pre-wrap" in regle[0], (
        "une commande trop longue serait coupée au lieu d'être repliée")


def test_the_three_position_cards_align_their_titles():
    """The overline hid a misalignment, and removing it revealed it.

    `margin-top: auto` on the title pushed it by a free space depending on the
    paragraph's LENGTH: the three titles therefore sat at three different heights
    (measured 282, 301 and 321 px). As long as the overline, itself aligned,
    occupied the top of each card, the eye hooked onto it.

    The check is CSS and not geometric — a static test cannot measure a layout.
    It is a proxy, and it says so: the geometric check was done against a real
    browser (0 px gap on the titles as on the bottom of the labels).
    """
    from monl_platform.landing import EXTRA_CSS

    titre = _declarations(EXTRA_CSS, ".flow-stage h3")
    tags = _declarations(EXTRA_CSS, ".flow-stage .stage-tags")
    assert titre and tags, "les règles des cartes sont introuvables"

    assert "auto" not in titre[0], (
        "le titre repousse encore : les trois cartes se désalignent")
    assert "margin-top:auto" in tags[0].replace(" ", ""), (
        "rien ne pousse les étiquettes en bas : elles suivent le paragraphe")


def _css_rules(css: str) -> list:
    """Returns [(rank, media, selector, {properties})] for all the served CSS.

    `@keyframes` blocks are SKIPPED entirely: their "0%" and "to" are not
    selectors, and counting them would compare animation steps with layout
    rules.

    COMMENTS are removed first: those of this repository readily quote the rule
    they explain, braces included (point 156 — a CSS comment is page content), and
    a naive extractor would read them as real rules.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    regles, i, rang = [], 0, 0
    fins_de_media = []
    while i < len(css):
        while fins_de_media and i >= fins_de_media[-1]:
            fins_de_media.pop()
        saut = re.compile(r"@(keyframes|font-face|supports)[^{]*\{").match(css, i)
        if saut:
            profondeur, j = 1, saut.end()
            while j < len(css) and profondeur:
                profondeur += (css[j] == "{") - (css[j] == "}")
                j += 1
            i = j
            continue
        ouverture = re.compile(r"@media([^{]*)\{").match(css, i)
        if ouverture:
            profondeur, j = 1, ouverture.end()
            while j < len(css) and profondeur:
                profondeur += (css[j] == "{") - (css[j] == "}")
                j += 1
            fins_de_media.append(j - 1)
            i = ouverture.end()
            continue
        regle = re.compile(r"([^{}@]+)\{([^{}]*)\}").match(css, i)
        if regle:
            proprietes = {
                declaration.split(":", 1)[0].strip()
                for declaration in regle.group(2).split(";")
                if ":" in declaration
            }
            for selecteur in regle.group(1).split(","):
                regles.append(
                    (rang, bool(fins_de_media), selecteur.strip(), proprietes))
                rang += 1
            i = regle.end()
            continue
        i += 1
    return regles


def test_no_responsive_rule_is_overridden_by_a_bare_rule(platform):
    """A `@media` adds NO specificity: only ORDER defends it.

    `extra_css` concatenates several modules, so a bare rule written in a LATER
    module overrides an earlier module's responsive version, at equal weight,
    without anything saying so. It happened on `.case-explorer`: `landing.py` set
    `grid-template-columns:1fr` under 760px, and `landing_cas.py`'s bare rule
    went back to two columns. Measured at 375px before the fix: `230px 103px`, a
    business case panel 103 pixels wide, cut by the card's `overflow:hidden` —
    the site's showcase, unreadable on a phone.

    The witness is about the REALLY SERVED page, never a module: the
    concatenation plays out between the two.
    """
    page = requests.get(platform, timeout=10).text
    feuilles = re.findall(r"<style[^>]*>(.*?)</style>", page, re.S)
    assert feuilles, "aucune feuille de style dans la page servie"
    regles = _css_rules("\n".join(feuilles))
    assert len(regles) > 100, f"extracteur muet : {len(regles)} règles lues"
    assert any(media for _, media, _, _ in regles), "aucune @media reconnue"

    ecrasees = []
    for rang, media, selecteur, proprietes in regles:
        if not media:
            continue
        for rang2, media2, selecteur2, proprietes2 in regles:
            if media2 or rang2 <= rang or selecteur2 != selecteur:
                continue
            communes = proprietes & proprietes2
            if communes and _specificite(selecteur2) >= _specificite(selecteur):
                ecrasees.append(f"{selecteur} → {sorted(communes)}")

    assert not ecrasees, (
        "règle(s) responsive écrasée(s) par une règle nue écrite plus tard, "
        "à poids égal ou supérieur : " + " ; ".join(sorted(set(ecrasees))))


def test_each_site_page_carries_a_title_naming_it():
    """Two pages cannot carry the same `<title>`.

    The console carried word for word the HOME page's — "monl compiler, le métier
    est compilé". All its neighbors name themselves ("MCP — …", "Votre compte —
    …"): with several tabs open, the console's was indistinguishable from the home
    page, and a bookmark did not say where it led. Found by measuring the site at
    375px, not by rereading it: the probe reported each page's title, and two
    lines were identical.

    The witness reads the PAGE constants and not the routes: a page can exist
    without being mounted yet, and its title is what is at stake.
    """
    import importlib
    import pkgutil

    import monl_platform

    titres = {}
    for module in pkgutil.iter_modules(monl_platform.__path__):
        charge = importlib.import_module(f"monl_platform.{module.name}")
        for nom in dir(charge):
            valeur = getattr(charge, nom)
            if not (isinstance(valeur, str) and nom.endswith("_HTML")):
                continue
            trouve = re.search(r"<title>(.*?)</title>", valeur, re.S)
            if not trouve:
                continue
            titre = trouve.group(1).strip()
            # The same HTML re-exported by two modules (app_pages) is not a
            # duplicate: it is the SAME page. We therefore index by content.
            titres.setdefault(titre, set()).add(valeur)

    assert len(titres) > 5, f"extracteur muet : {len(titres)} titre(s) lu(s)"
    partages = {titre: len(pages) for titre, pages in titres.items() if len(pages) > 1}
    assert not partages, (
        "des pages DIFFÉRENTES partagent un titre — un onglet ne dit plus "
        f"laquelle est ouverte : {partages}")


def test_the_top_bar_is_opaque(platform):
    """A translucent sticky bar CUTS the text scrolling beneath it.

    Measured on /console: `background: color-mix(in srgb, var(--bg) 92%,
    transparent)` let 8 % of the content show through, and the line passing
    under the bar read as cut in two. A defect breaking nothing and no test could
    see — it only exists in what the user RECEIVES (point 164).

    The witness is about the SERVED page, and about the property rather than a
    value: `backdrop-filter` behind an opaque background blurs nothing any more,
    its presence would signal that translucency came back with it.
    """
    page = requests.get(platform, timeout=10).text
    feuilles = re.findall(r"<style[^>]*>(.*?)</style>", page, re.S)
    assert feuilles, "aucune feuille de style dans la page servie"
    regles = _css_rules("\n".join(feuilles))
    topbars = [(sel, props) for _, _, sel, props in regles
               if sel.strip() == ".topbar"]
    assert topbars, "règle .topbar introuvable : l'extracteur ne regarde rien"
    css = "\n".join(feuilles)
    bloc = re.search(r"\.topbar\s*\{([^}]*)\}", css, re.S)
    assert bloc, "corps de .topbar illisible"
    # A CSS comment is CONTENT (point 156): left in place, the word
    # "backdrop-filter" written in an explanation would turn this witness red.
    corps = re.sub(r"/\*.*?\*/", "", bloc.group(1), flags=re.S)
    assert "transparent" not in corps, corps
    assert "backdrop-filter" not in corps, corps
    assert re.search(r"background:\s*var\(--bg\)", corps), corps


# ---------------------------------------------------------------------------
# The "PetiteBoutique" card: what it announces, confronted with a REAL
# compilation. The page writes "the metrics below are checked by recompiling
# the spec in the tests" — it was false: no test compiled this spec,
# `PetiteBoutique` existed nowhere in the code, the displayed fragment could
# not even compile (neither `app`, nor `actor`, nor `workflow`), and of the
# three figures TWO were wrong (17 routes announced for 14, 12 files for 15).
# The tree also promised a `README.md` the compiler did not produce.
#
# Point 164's defect — the `/mcp` page announced four nonexistent tools because
# the list was hand-written — but worse: here the page explicitly claimed a
# check that did not exist.
# ---------------------------------------------------------------------------

#: What we do not count as a "delivered file": the spec is the INPUT, the
#: secret is made at first startup, the database only exists at runtime. The
#: rule is written here rather than guessed — without it, the announced figure
#: would depend on the order in which the test was run.
_HORS_ARCHIVE = {"spec.ml", ".jwt_secret"}


def _showcase_archive(dossier):
    """Compiles the home page's spec and returns what a user receives."""
    from monl.cli import compile_project

    spec = dossier / "spec.ml"
    spec.write_text(landing_vitrine.SPEC_VITRINE, encoding="utf-8")
    compile_project(str(spec), str(dossier))
    fichiers = {
        chemin.relative_to(dossier).as_posix()
        for chemin in dossier.rglob("*")
        if chemin.is_file() and chemin.name not in _HORS_ARCHIVE
        and not chemin.name.endswith(".db")
    }
    routes = len(re.findall(r"^@app\.(?:get|post|put|delete|patch)\(",
                            (dossier / "app.py").read_text(encoding="utf-8"), re.M))
    contrat = json.loads((dossier / "frontend_contract.json").read_text(encoding="utf-8"))
    return fichiers, routes, len(contrat["entities"])


def test_the_home_spec_really_compiles(tmp_path):
    """The prerequisite: the SHOWN spec must be a spec that passes.

    The previous one was a fragment. Showing on a compiler's home page a spec that
    does not compile is the worst possible place for this defect — it is precisely
    what the product promises to refuse.
    """
    fichiers, routes, entites = _showcase_archive(tmp_path)

    assert "app.py" in fichiers and "schema.sql" in fichiers
    assert routes > 0 and entites > 0


def test_the_announced_figures_are_the_compilations(tmp_path):
    """The card's three numbers, confronted with the real result."""
    fichiers, routes, entites = _showcase_archive(tmp_path)

    assert entites == landing_vitrine.ENTITES, (
        f"la carte annonce {landing_vitrine.ENTITES} entités, la compilation en "
        f"produit {entites}")
    assert routes == landing_vitrine.ROUTES, (
        f"la carte annonce {landing_vitrine.ROUTES} routes, app.py en déclare "
        f"{routes}")
    assert len(fichiers) == landing_vitrine.FICHIERS, (
        f"la carte annonce {landing_vitrine.FICHIERS} fichiers, l'archive en "
        f"contient {len(fichiers)} : {sorted(fichiers)}")


def test_the_tree_names_no_missing_file(tmp_path):
    """THE ORIGINAL DEFECT: the card promised a nonexistent `README.md`.

    We also check that the tree stays an EXCERPT. Otherwise, listing it in full
    would make the witness pass without guaranteeing anything about readability,
    and above all the card would stop being a card.
    """
    fichiers, _routes, _entites = _showcase_archive(tmp_path)
    annonces = [nom for nom, _role in landing_vitrine.ARBRE]

    absents = [nom for nom in annonces if nom not in fichiers]
    assert not absents, (
        f"la carte nomme des fichiers que le compilateur ne produit pas : "
        f"{absents}")
    assert 0 < len(annonces) < len(fichiers), (
        "l'arborescence doit rester un extrait lisible, pas l'archive entière")


def test_the_displayed_excerpt_is_taken_from_the_compiling_spec():
    """Two texts to keep in agreement always diverge.

    The shown excerpt is not copied next to the spec: it is cut out of it. The
    witness proves it by requiring each of its lines to appear in the spec — and
    that it carries at least one rule, otherwise the cutting could have returned
    the sole entity block without anyone seeing it.
    """
    extrait = landing_vitrine.extrait_affiche()
    lignes = [ligne for ligne in extrait.splitlines() if ligne.strip()]

    assert lignes, "l'extrait est vide"
    for ligne in lignes:
        assert ligne in landing_vitrine.SPEC_VITRINE, (
            f"l'extrait affiché contient une ligne absente de la spec : {ligne!r}")
    assert any(ligne.startswith("rule ") for ligne in lignes), (
        "l'extrait ne montre aucune règle : la page ne montrerait que des champs")


def test_the_served_page_names_only_real_files(platform, tmp_path):
    """The last link: the rule is about the SERVED PAGE, not the constants.

    Without it, we would know the constants are right, never that they are the
    ones a visitor reads — point 163's distinction between what is checked and
    what is served.

    The first version of this witness forbade `README.md` HARD-CODED. That froze a
    past defect instead of guarding the invariant: the file did not exist, it has
    existed since point 176, and the assertion became false the day the page was
    right. We therefore read the REALLY served tree and confront it with the
    archive — a rule, not a list of forbidden names.
    """
    texte = requests.get(platform, timeout=10).text
    fichiers, _routes, _entites = _showcase_archive(tmp_path)

    assert f"<b>{landing_vitrine.ROUTES}</b><span>API routes</span>" in texte
    assert f"<b>{landing_vitrine.FICHIERS}</b><span>files</span>" in texte

    arbre = texte.split('class="tree"')[1].split("</div>")[0]
    noms = re.findall(r"[├└]──\s*([^\s<]+)", arbre)
    assert noms, "l'arborescence servie est vide ou a changé de forme"
    absents = [nom for nom in noms if nom not in fichiers]
    assert not absents, (
        f"la page servie nomme des fichiers que l'archive ne contient pas : "
        f"{absents}")


def _lines(texte):
    return {ligne.strip() for ligne in texte.splitlines() if ligne.strip()}


def test_each_case_excerpt_appears_in_its_examples_spec():
    """The "communaute" excerpt displayed `rule Membre.pseudo generated
    "MBR-{NNNN}"`: absent from the spec, and invalid (`generated` takes no
    template). Copied by hand, nothing confronted it with the served spec."""
    from monl_platform import examples, landing_cas

    assert set(landing_cas.CASE_SNIPPETS) == set(examples.BY_ID)
    for ident, extrait in landing_cas.CASE_SNIPPETS.items():
        absentes = _lines(extrait) - _lines(examples.spec_of(ident))
        assert _lines(extrait), ident
        assert not absentes, (ident, absentes)


def test_the_hero_demo_is_taken_from_the_compiling_spec():
    from monl_platform import landing

    absentes = _lines(landing.DEMO_HERO_SOURCE) - _lines(landing_vitrine.SPEC_VITRINE)
    assert _lines(landing.DEMO_HERO_SOURCE)
    assert not absentes, absentes
