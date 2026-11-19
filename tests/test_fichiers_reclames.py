# Brick 29 (point 137) — every local file CLAIMED by the frontend must really
# be served.
#
# The defect that gave birth to the brick is real: AtelierNaya referenced six
# SVGs the AI had never delivered, and `monl run --check` answered green.
# Nothing broke — a missing file raises no JavaScript exception, so jsdom did
# not flinch; the page displayed with six holes.
#
# The counter-proofs count as much as the check: a check refusing EVERYTHING
# would pass the first test. We therefore also check that a contract route,
# fragment navigation and a CDN are NEVER denounced (points 57 and 92: a
# warning that is wrong about a correct site teaches people to stop reading
# warnings).
import pytest

from monl.cli import compile_project
from monl.smoke_test import run_smoke_test

SPEC = """app Atelier

entity Item
    label: String
    price: Money

actor Admin selfRegister

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item

seed Item
    label: "Alpha", price: 9.5
"""

APPEL = ("<script>fetch('/item?limit=5').then(r => r.json())"
         ".then(d => { document.body.dataset.n = d.total; });</script>")


def _quiet(*_a, **_k):
    pass


@pytest.fixture()
def project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    return proj


def _frontend(project, **fichiers):
    front = project / "frontend"
    front.mkdir(exist_ok=True)
    for nom, contenu in fichiers.items():
        cible = front / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
    return front


def _page(corps):
    return f"<!doctype html><html><body>{corps}{APPEL}</body></html>"


# --------------------------------------------------------------- the defect --
def test_a_referenced_but_missing_svg_fails_the_smoke_test(project):
    """AtelierNaya's case, reduced to its simplest expression."""
    _frontend(project, **{"index.html": _page('<img src="hero.svg" alt="">')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("hero.svg" in e and "404" in e for e in errors), errors


def test_the_same_frontend_passes_once_the_file_is_delivered(project):
    """Indispensable COUNTER-PROOF: without it, a check refusing every frontend
    would pass the previous test without anything showing it."""
    _frontend(project, **{"index.html": _page('<img src="hero.svg" alt="">'),
                         "hero.svg": '<svg xmlns="http://www.w3.org/2000/svg"/>'})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors


def test_each_missing_file_is_named_with_its_page(project):
    """A report saying "files are missing" would help nobody: the file name AND
    the page name make the fix possible without searching."""
    _frontend(project, **{"index.html": _page(
        '<img src="a.svg"><img src="b.png"><link rel="stylesheet" href="c.css">')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    for attendu in ("a.svg", "b.png", "c.css"):
        assert any(attendu in e for e in errors), (attendu, errors)
    assert all("index.html" in e for e in errors if ".svg" in e), errors


def test_a_missing_image_is_denounced_with_the_assets_advice(project):
    """The message must point to assets (brick 13), not leave people searching.
    The cause is real and silent: `monl import` KEEPS only the allowlist (see the
    archive test below)."""
    _frontend(project, **{"index.html": _page('<img src="photo.jpg">')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("photo.jpg" in e and "assets" in e for e in errors), errors


def test_an_image_really_present_in_frontend_is_served(project):
    """Safeguard against the message I was about to write: `frontend/` is served
    by StaticFiles, which filters NOTHING. An image dropped by hand therefore
    works perfectly, and denouncing it would be a false positive. The allowlist
    governs what the AI may DELIVER, not what the server serves."""
    front = _frontend(project, **{"index.html": _page('<img src="photo.jpg">')})
    (front / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0 pas du texte")
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors


def test_an_imported_archive_loses_its_images_and_the_smoke_test_says_so(project, tmp_path):
    """The path where the defect REALLY arrives, tested end to end.

    `monl import` removes from the archive everything outside the allowlist —
    without a word — then checks. Before this brick, the page stayed and claimed
    a photo the import had just thrown away: import successful, site full of
    holes. The smoke test must refuse."""
    import zipfile

    from monl.frontend_ai import import_and_verify

    archive = tmp_path / "site.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("index.html", _page('<img src="photo.jpg" alt="">'))
        z.writestr("photo.jpg", "�� pas du texte")
    ok, errors = import_and_verify(str(project), str(archive), say=_quiet)
    assert not (project / "frontend" / "photo.jpg").exists(), (
        "l'archive a conservé la photo : le scénario testé n'existe plus")
    assert not ok
    assert any("photo.jpg" in e for e in errors), errors


def test_a_css_reference_counts_too(project):
    """A background image does not live in the HTML. Reading only the pages
    would let half of a real site's references through."""
    _frontend(project, **{
        "index.html": _page('<link rel="stylesheet" href="styles.css">'),
        "styles.css": "body { background: url('fond.png') no-repeat; }"})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("fond.png" in e and "styles.css" in e for e in errors), errors


def test_a_reference_leaving_the_site_is_named(project):
    _frontend(project, **{"index.html": _page('<img src="../../secret.png">')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("escapes the site" in e for e in errors), errors


# ------------------------------------------------ forbidden false positives --
def test_neither_contract_route_nor_navigation_is_denounced(project):
    """The check must NEVER confuse a link with a file.

    `#/panier` is navigation (point 92, where the same warning had denounced four
    correct routes), `/item` is a contract route, and an anchor stays an anchor.
    None of the three carries an extension: that is precisely what puts them out
    of the check's reach."""
    _frontend(project, **{"index.html": _page(
        '<a href="#/panier">Panier</a><a href="/item">Articles</a>'
        '<a href="#haut">Haut</a><a href="/">Accueil</a>')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors


def test_neither_absolute_url_nor_data_uri_is_treated_as_a_file(project):
    """A remote URL is not ours: asking the ephemeral server for it would give a
    404 on a perfectly correct site. The CDN already has its own refusal
    elsewhere — it is not this check's job to duplicate it."""
    _frontend(project, **{"index.html": _page(
        '<img src="https://exemple.com/a.png">'
        '<img src="//cdn.exemple.com/b.svg">'
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">'
        '<a href="mailto:contact@exemple.com">Écrire</a>')})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors


def test_a_reference_with_a_version_parameter_is_resolved(project):
    """`styles.css?v=3` is a common way to bust the cache. The file exists:
    denouncing it would be a false positive."""
    _frontend(project, **{
        "index.html": _page('<link rel="stylesheet" href="styles.css?v=3">'),
        "styles.css": "body { color: #111; }"})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors


def test_a_frontend_without_any_reference_stays_green(project):
    """The simplest case, and the safeguard against a check that would fail on
    nothing."""
    _frontend(project, **{"index.html": _page("<h1>Atelier</h1>")})
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors
