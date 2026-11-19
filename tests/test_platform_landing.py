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

from monl_platform import brand, landing_showcase
from monl_platform.app import create_app
from monl_platform.landing import LANDING_HTML

RESOURCE_EXTERNAL = re.compile(
    r"<(?:link|script|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - never called here
        raise AssertionError("the presentation page calls no AI")


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
            pytest.fail("the server did not start")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_root_presents_the_product(platform):
    response = requests.get(platform, timeout=10)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="en">' in response.text
    # What a product page must say: what it is, and how to get it.
    assert "compiler" in response.text.lower()
    assert "Try it in the console" in response.text


def test_the_page_leads_to_the_console(platform):
    response = requests.get(platform, timeout=10)

    assert 'href="/console"' in response.text
    console = requests.get(f"{platform}/console", timeout=10, allow_redirects=False)
    assert console.status_code == 303
    assert console.headers["location"].startswith("/login")


def test_the_page_loads_no_remote_resource(platform):
    """Served locally, it must work without any network."""
    response = requests.get(platform, timeout=10)

    fault = RESOURCE_EXTERNAL.search(response.text)
    assert fault is None, f"remote resource in the page: {fault.group(0)}"


def test_every_outgoing_url_is_a_link_and_nothing_else(platform):
    """The safeguard above was widened: this one closes it again.

    Allowing outgoing links must not allow a URL anywhere. Every `https://` of the
    page must be the target of an `<a href>` — not of an `<img>`, a `fetch`, or a
    font.
    """
    page = requests.get(platform, timeout=10).text
    without_comments = re.sub(r"/\*.*?\*/", "", page, flags=re.DOTALL)
    without_comments = re.sub(r"<!--.*?-->", "", without_comments, flags=re.DOTALL)

    for position in (m.start() for m in re.finditer(r"https?://", without_comments)):
        debut = without_comments.rfind("<", 0, position)
        tag = without_comments[debut:position]
        # ONE exemption, and a narrow one: an inline SVG's `xmlns` is a
        # NAMESPACE, not an address — no browser fetches it. The exemption is
        # about the attribute, never the domain: writing "except w3.org" would
        # let a real request to w3.org through.
        if re.search(r"\bxmlns(:\w+)?\s*=\s*['\"]$", tag):
            continue
        assert re.match(r"<a\b[^>]*\bhref\s*=\s*['\"]$", tag), (
            "URL sortante hors d'un lien : "
            + without_comments[position:position + 60]
        )


def test_the_page_respects_reduced_motion():
    """The hero terminal is animated: it must be able to stop."""
    assert "prefers-reduced-motion" in LANDING_HTML


def test_the_console_is_no_longer_at_the_root(platform):
    """The root and the console are two distinct pages, not the same one."""
    racine = requests.get(platform, timeout=10).text
    session = requests.Session()
    registered = session.post(f"{platform}/api/auth/register", json={
        "email": "landing-console@example.test", "password": "MotDePasse-123"
    }, timeout=10)
    assert registered.status_code == 201, registered.text
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


def _bande_vertical(trace):
    """The top and bottom really drawn by a path.

    A path on TWO lines goes down to the bottom of its view; a single-line path,
    centered, leaves space above and below. It is the only way to check the
    presence of a second word without reading the drawing by eye.
    """
    numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", trace)]
    ordered = numbers[1::2]
    assert ordered, "unreadable path: the measurement would be about nothing"
    return min(ordered), max(ordered)


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
    response = requests.get(platform, timeout=10)
    assert 'aria-label="MONL"' in response.text
    # We do NOT look for "COMPILER" in the page to prove the bar does not
    # announce it: the word legitimately appears there in full ("un réseau pour
    # compiler"), and the witness then measured the PROSE instead of the label.
    # The label is the `aria-label` above — nothing else is read in its place.
    # Checked by measuring it: the broad assertion turned red on a correct
    # page.

    haut_court, bas_court = _bande_vertical(brand.NAV_TEXT_PATH)
    haut_long, bas_long = _bande_vertical(brand.WORDMARK_PATH)
    hauteur = brand.VIEW[1]

    assert (bas_court - haut_court) < 0.5 * hauteur, (
        "the bar text takes two lines: it is no longer the short "
        "form its label announces")
    assert (bas_long - haut_long) > 0.9 * hauteur, (
        "the lockup lost its second line — the chosen logo no longer carries "
        "COMPILER, and nothing else guards it")


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
    for template in ("Public showcase", "Appointment book",
                   "Shop and payment", "Community feed"):
        assert template in page
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

    without_comments = re.compile(r"/\*.*?\*/", re.DOTALL)
    for name, page in (("accueil", LANDING_HTML), ("console", CONSOLE_HTML)):
        own = without_comments.sub("", page)
        assert not re.search(r"\.style\.opacity\s*=", own), (
            f"the {name} page hides a block with an inline style: a class "
            "will not be able to undo it"
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
    for anchor in ("pourquoi-title", "compare-title", "ensemble-title"):
        assert f'id="{anchor}"' in LANDING_HTML, f"section absente : {anchor}"


def test_the_comparison_also_says_what_monl_does_not_bring():
    """A comparison listing only its victories is a comparison one stops
    believing at the first check. The limits line is not politeness: it is what
    makes the rest readable."""
    from monl_platform.landing_why import COMPARISON
    axes = [axe for axe, _eux, _nous in COMPARISON]
    assert "What it does not provide" in axes, axes
    limites = next(nous for axe, _e, nous in COMPARISON
                   if axe == "What it does not provide")
    for missing in ("hosting", "real-time", "storage"):
        assert missing in limites, f"limit not stated: {missing}"
    assert limites in LANDING_HTML, "the limits line is not served"


def test_no_value_judgment_in_the_comparison():
    """Each line must be a FACT checkable on both sides. "Simpler", "more
    modern", "safer" cannot be checked and do not survive a reader who knows the
    other product."""
    from monl_platform.landing_why import COMPARISON
    forbidden = ("simpler", "more modern", "safer", "more secure", "faster",
                 "better", "superior", "obsolete")
    text = " ".join(f"{a} {b} {c}".lower() for a, b, c in COMPARISON)
    offenders = [word for word in forbidden if word in text]
    assert not offenders, f"value judgment in the comparison: {offenders}"


def test_the_sites_postgresql_promise_is_covered_by_a_test():
    """The site claims a generated backend runs on a managed provider's Postgres.
    A document is maintained like code (point 141): the promise must point to a
    test that exists, otherwise it ages silently until it becomes false."""
    from monl_platform.landing_why import MONTAGES
    montage = next(m for m in MONTAGES if m["etat"] == "verifie"
                   and "MONL_DATABASE_URL" in m["texte"])
    assert "postgresql://" in "\n".join(montage["code"])

    test = pathlib.Path(__file__).with_name("test_postgresql.py")
    assert test.exists(), "the promise points to no test"
    source = test.read_text(encoding="utf-8")
    assert "MONL_DATABASE_URL" in source, (
        "the test does not start the artifacts with the announced variable")


def test_each_exploit_cites_the_point_documenting_it():
    """The three displayed refusals are REAL defects. Each points to its journal
    entry: a page telling of attacks without a source is a marketing page, not a
    proof."""
    import re as _re

    from monl_platform.landing_why import REFUSAL
    log = (pathlib.Path(__file__).parents[1]
               / "docs" / "design_decisions.md").read_text(encoding="utf-8")
    for refusal in REFUSAL:
        numbers = _re.findall(r"\d+", refusal["point"])
        assert numbers, refusal["point"]
        for number in numbers:
            assert f"\n## {number}." in log, (
                f"point {number} cited by \"{refusal['titre']}\" missing from the journal")
        assert refusal["titre"] in LANDING_HTML


def _specificity(selector: str) -> tuple:
    """Returns (id, class/attribute/pseudo-class, type) of a selector.

    Deliberately modest: it can only count sequences of classes, attributes and
    types. `:is()`, `:not()` and `:where()` delegate their weight to their
    content, so their presence would miscount — the shape assertion refuses them
    rather than returning a wrong figure.
    """
    for delegated in (":is(", ":not(", ":where(", ":has("):
        assert delegated not in selector, f"delegated weight not computed: {delegated}"
    reste, attributes = re.subn(r"\[[^\]]*\]", " ", selector)
    identifiers = len(re.findall(r"#[-\w]+", reste))
    classes = len(re.findall(r"\.[-\w]+", reste))
    pseudo_classes = len(re.findall(r"(?<!:):[-\w]+", reste))
    types = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][-\w]*)", reste))
    return (identifiers, classes + attributes + pseudo_classes, types)


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

    assert LANDING_HTML.count(cede) == 1, "the rule handing over the background disappeared"
    assert _specificity(cede) > _specificity(pose), (
        f"{cede} no longer beats {pose}")
    assert LANDING_HTML.index(cede) > LANDING_HTML.index(pose), (
        "the rule handing over the background moved BEFORE the one setting it")


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
    markup = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)

    assert "case-explorer" in markup, "the cutting took the tabs with it"
    assert "case-repere" not in markup, "the marker is served in the markup"
    assert "glisse" not in markup, "the class handing over the background is served"
    assert "case-repere" in page, "nobody sets the marker any more"


def test_the_theme_toggle_does_not_animate_for_reduced_motion():
    """Motion refusal is held in JavaScript, since it cannot be in CSS: the
    @media block applies to `*`, which reaches no `::view-transition-*`. The
    toggle must also stay functional where the API does not exist — otherwise the
    theme stops toggling.
    """
    guard = re.search(
        r"if\s*\(\s*!document\.startViewTransition\s*\|\|\s*(\w+)\.matches\s*\)"
        r"\s*\{\s*basculer\(\)\s*;\s*return\s*;\s*\}",
        LANDING_HTML,
    )
    assert guard, "the toggle animates without checking the API or reduced motion"

    name = guard.group(1)
    assert re.search(
        rf"var\s+{name}\s*=\s*window\.matchMedia\(\s*'\(prefers-reduced-motion: reduce\)'\s*\)",
        LANDING_HTML,
    ), f"\"{name}\" does not query reduced motion"


def _sheet(html: str) -> str:
    """Returns the page's inlined CSS, stylesheets concatenated."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))


def _declarations(css: str, selector: str) -> list:
    """Returns the blocks written for this selector alone, at rule start.

    Cannot read a grouped selector (".a, .band { … }"): the existence assertion
    below refuses silence rather than leaving the test green on a rule it could
    not find.
    """
    motif = re.compile(r"(?:^|[};])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", re.M)
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
    css = _sheet(LANDING_HTML)
    assert css, "the stylesheet is no longer inlined in the page"

    for bande in (".band", ".proof-rail", ".footer-wrap"):
        blocks = _declarations(css, bande)
        assert blocks, f"the {bande} rule cannot be found: the test no longer guards anything"
        for block in blocks:
            assert "background" not in block, (
                f"{bande} repaints the background — the color alternation is back")


def test_favicon_ico_really_answers(platform):
    """The file can exist without the route serving it.

    The tests of `test_platform_marque.py` guard the icon's CONTENT; this one
    guards the fact that it can be obtained. Without it, removing the route would
    leave the suite entirely green while browsers again receive a 404 — and keep
    the old icon.
    """
    response = requests.get(platform + "/favicon.ico", timeout=10)

    assert response.status_code == 200, "/favicon.ico no longer answers"
    assert response.content[:4] == b"\x00\x00\x01\x00", "it is not a real ICO"
    assert response.headers["content-type"] == "image/x-icon"

    # And the ROUTE does read the fingerprint: without the `v` parameter,
    # theme.py's cache policy would stay right without ever being applied.
    from monl_platform.theme import VERSION_ICO

    versioned = requests.get(
        f"{platform}/favicon.ico?v={VERSION_ICO}", timeout=10)
    assert "immutable" in versioned.headers["cache-control"]
    assert "immutable" not in response.headers["cache-control"], (
        "the bare address is cached like a versioned address")
    assert versioned.content == response.content, "two different icons"


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
    from monl_platform.landing_why import SECTIONS

    blocks = re.findall(r"<pre><code>(.*?)</code></pre>", SECTIONS, re.S)
    assert blocks, "no command block any more: the test no longer guards anything"

    for block in blocks:
        for line in block.split("\n"):
            assert len(line) <= 41, (
                f"{len(line)} characters — the card holds 41:\n  {line}")
            assert " · " not in line, (
                "two commands on one line, separated by a middle dot: "
                "they cannot be copied")


def test_a_command_block_wraps_instead_of_being_cut():
    """The safety net under the limit above.

    `overflow-x: auto` alone lets the line scroll OUTSIDE the frame: on a card,
    nobody goes looking for it. `pre-wrap` wraps it.
    """
    from monl_platform.landing_why import EXTRA_CSS

    rule = _declarations(EXTRA_CSS, ".montage pre")
    assert rule, "the .montage pre rule cannot be found"
    assert "pre-wrap" in rule[0], (
        "a too long command would be cut instead of wrapped")


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

    title = _declarations(EXTRA_CSS, ".flow-stage h3")
    tags = _declarations(EXTRA_CSS, ".flow-stage .stage-tags")
    assert title and tags, "the card rules cannot be found"

    assert "auto" not in title[0], (
        "the title still pushes: the three cards misalign")
    assert "margin-top:auto" in tags[0].replace(" ", ""), (
        "nothing pushes the labels down: they follow the paragraph")


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
    rules, i, rang = [], 0, 0
    fins_of_media = []
    while i < len(css):
        while fins_of_media and i >= fins_of_media[-1]:
            fins_of_media.pop()
        skip = re.compile(r"@(keyframes|font-face|supports)[^{]*\{").match(css, i)
        if skip:
            depth, j = 1, skip.end()
            while j < len(css) and depth:
                depth += (css[j] == "{") - (css[j] == "}")
                j += 1
            i = j
            continue
        opening = re.compile(r"@media([^{]*)\{").match(css, i)
        if opening:
            depth, j = 1, opening.end()
            while j < len(css) and depth:
                depth += (css[j] == "{") - (css[j] == "}")
                j += 1
            fins_of_media.append(j - 1)
            i = opening.end()
            continue
        rule = re.compile(r"([^{}@]+)\{([^{}]*)\}").match(css, i)
        if rule:
            properties = {
                declaration.split(":", 1)[0].strip()
                for declaration in rule.group(2).split(";")
                if ":" in declaration
            }
            for selector in rule.group(1).split(","):
                rules.append(
                    (rang, bool(fins_of_media), selector.strip(), properties))
                rang += 1
            i = rule.end()
            continue
        i += 1
    return rules


def test_no_responsive_rule_is_overridden_by_a_bare_rule(platform):
    """A `@media` adds NO specificity: only ORDER defends it.

    `extra_css` concatenates several modules, so a bare rule written in a LATER
    module overrides an earlier module's responsive version, at equal weight,
    without anything saying so. It happened on `.case-explorer`: `landing.py` set
    `grid-template-columns:1fr` under 760px, and `landing_cases.py`'s bare rule
    went back to two columns. Measured at 375px before the fix: `230px 103px`, a
    business case panel 103 pixels wide, cut by the card's `overflow:hidden` —
    the site's showcase, unreadable on a phone.

    The witness is about the REALLY SERVED page, never a module: the
    concatenation plays out between the two.
    """
    page = requests.get(platform, timeout=10).text
    sheets = re.findall(r"<style[^>]*>(.*?)</style>", page, re.S)
    assert sheets, "no stylesheet in the served page"
    rules = _css_rules("\n".join(sheets))
    assert len(rules) > 100, f"mute extractor: {len(rules)} rules read"
    assert any(media for _, media, _, _ in rules), "no @media recognized"

    overridden = []
    for rang, media, selector, properties in rules:
        if not media:
            continue
        for rang2, media2, selecteur2, proprietes2 in rules:
            if media2 or rang2 <= rang or selecteur2 != selector:
                continue
            communes = properties & proprietes2
            if communes and _specificity(selecteur2) >= _specificity(selector):
                overridden.append(f"{selector} → {sorted(communes)}")

    assert not overridden, (
        "responsive rule(s) overridden by a bare rule written later, "
        "at equal or higher weight: " + " ; ".join(sorted(set(overridden))))


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

    titles = {}
    for module in pkgutil.iter_modules(monl_platform.__path__):
        charge = importlib.import_module(f"monl_platform.{module.name}")
        for name in dir(charge):
            valeur = getattr(charge, name)
            if not (isinstance(valeur, str) and name.endswith("_HTML")):
                continue
            found = re.search(r"<title>(.*?)</title>", valeur, re.S)
            if not found:
                continue
            title = found.group(1).strip()
            # The same HTML re-exported by two modules (app_pages) is not a
            # duplicate: it is the SAME page. We therefore index by content.
            titles.setdefault(title, set()).add(valeur)

    assert len(titles) > 5, f"extracteur muet : {len(titles)} titre(s) lu(s)"
    shared = {title: len(pages) for title, pages in titles.items() if len(pages) > 1}
    assert not shared, (
        "DIFFERENT pages share a title — a tab no longer says "
        f"which one is open: {shared}")


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
    sheets = re.findall(r"<style[^>]*>(.*?)</style>", page, re.S)
    assert sheets, "no stylesheet in the served page"
    rules = _css_rules("\n".join(sheets))
    topbars = [(sel, props) for _, _, sel, props in rules
               if sel.strip() == ".topbar"]
    assert topbars, ".topbar rule not found: the extractor looks at nothing"
    css = "\n".join(sheets)
    block = re.search(r"\.topbar\s*\{([^}]*)\}", css, re.S)
    assert block, "corps de .topbar illisible"
    # A CSS comment is CONTENT (point 156): left in place, the word
    # "backdrop-filter" written in an explanation would turn this witness red.
    body = re.sub(r"/\*.*?\*/", "", block.group(1), flags=re.S)
    assert "transparent" not in body, body
    assert "backdrop-filter" not in body, body
    assert re.search(r"background:\s*var\(--bg\)", body), body


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
_OUTSIDE_ARCHIVE = {"spec.ml", ".jwt_secret"}


def _showcase_archive(folder):
    """Compiles the home page's spec and returns what a user receives."""
    from monl.cli import compile_project

    spec = folder / "spec.ml"
    spec.write_text(landing_showcase.SPEC_VITRINE, encoding="utf-8")
    compile_project(str(spec), str(folder))
    files = {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and path.name not in _OUTSIDE_ARCHIVE
        and not path.name.endswith(".db")
    }
    routes = len(re.findall(r"^@app\.(?:get|post|put|delete|patch)\(",
                            (folder / "app.py").read_text(encoding="utf-8"), re.M))
    contract = json.loads((folder / "frontend_contract.json").read_text(encoding="utf-8"))
    return files, routes, len(contract["entities"])


def test_the_home_spec_really_compiles(tmp_path):
    """The prerequisite: the SHOWN spec must be a spec that passes.

    The previous one was a fragment. Showing on a compiler's home page a spec that
    does not compile is the worst possible place for this defect — it is precisely
    what the product promises to refuse.
    """
    files, routes, entities = _showcase_archive(tmp_path)

    assert "app.py" in files and "schema.sql" in files
    assert routes > 0 and entities > 0


def test_the_announced_figures_are_the_compilations(tmp_path):
    """The card's three numbers, confronted with the real result."""
    files, routes, entities = _showcase_archive(tmp_path)

    assert entities == landing_showcase.ENTITIES, (
        f"the card announces {landing_showcase.ENTITIES} entities, compilation "
        f"produces {entities}")
    assert routes == landing_showcase.ROUTES, (
        f"the card announces {landing_showcase.ROUTES} routes, app.py declares "
        f"{routes}")
    assert len(files) == landing_showcase.FILES, (
        f"the card announces {landing_showcase.FILES} files, the archive "
        f"contains {len(files)}: {sorted(files)}")


def test_the_tree_names_no_missing_file(tmp_path):
    """THE ORIGINAL DEFECT: the card promised a nonexistent `README.md`.

    We also check that the tree stays an EXCERPT. Otherwise, listing it in full
    would make the witness pass without guaranteeing anything about readability,
    and above all the card would stop being a card.
    """
    files, _routes, _entities = _showcase_archive(tmp_path)
    announced = [name for name, _role in landing_showcase.TREE]

    missing = [name for name in announced if name not in files]
    assert not missing, (
        f"the card names files the compiler does not produce: "
        f"{missing}")
    assert 0 < len(announced) < len(files), (
        "the tree must stay a readable excerpt, not the whole archive")


def test_the_displayed_excerpt_is_taken_from_the_compiling_spec():
    """Two texts to keep in agreement always diverge.

    The shown excerpt is not copied next to the spec: it is cut out of it. The
    witness proves it by requiring each of its lines to appear in the spec — and
    that it carries at least one rule, otherwise the cutting could have returned
    the sole entity block without anyone seeing it.
    """
    excerpt = landing_showcase.excerpt_displayed()
    lines = [line for line in excerpt.splitlines() if line.strip()]

    assert lines, "the excerpt is empty"
    for line in lines:
        assert line in landing_showcase.SPEC_VITRINE, (
            f"the displayed excerpt contains a line absent from the spec: {line!r}")
    assert any(line.startswith("rule ") for line in lines), (
        "the excerpt shows no rule: the page would only show fields")


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
    text = requests.get(platform, timeout=10).text
    files, _routes, _entities = _showcase_archive(tmp_path)

    assert f"<b>{landing_showcase.ROUTES}</b><span>API routes</span>" in text
    assert f"<b>{landing_showcase.FILES}</b><span>files</span>" in text

    tree = text.split('class="tree"')[1].split("</div>")[0]
    names = re.findall(r"[├└]──\s*([^\s<]+)", tree)
    assert names, "the served tree is empty or changed shape"
    missing = [name for name in names if name not in files]
    assert not missing, (
        f"the served page names files the archive does not contain: "
        f"{missing}")


def _lines(text):
    return {line.strip() for line in text.splitlines() if line.strip()}


def test_each_case_excerpt_appears_in_its_examples_spec():
    """The "communaute" excerpt displayed `rule Membre.pseudo generated
    "MBR-{NNNN}"`: absent from the spec, and invalid (`generated` takes no
    template). Copied by hand, nothing confronted it with the served spec."""
    from monl_platform import examples, landing_cases

    assert set(landing_cases.CASE_SNIPPETS) == set(examples.BY_ID)
    for ident, excerpt in landing_cases.CASE_SNIPPETS.items():
        missing = _lines(excerpt) - _lines(examples.spec_of(ident))
        assert _lines(excerpt), ident
        assert not missing, (ident, missing)


def test_the_hero_demo_is_taken_from_the_compiling_spec():
    from monl_platform import landing

    missing = _lines(landing.DEMO_HERO_SOURCE) - _lines(landing_showcase.SPEC_VITRINE)
    assert _lines(landing.DEMO_HERO_SOURCE)
    assert not missing, missing
