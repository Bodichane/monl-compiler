"""A delivered site is never an empty shell.

The completeness check verified that a marker was PRESENT. A marker names a
section, it does not prove there is anything in it: a page made of eight
empty `<section>` passed, and the repository's test asserted it. These tests
cover both halves of the defect — each section's SUBSTANCE, and the NUMBER of
required sections.
"""

import contextlib
import io
import json

import pytest

from monl.cli import compile_project
from monl.design_system import ASSET_MANIFEST_FILENAME, activate_asset_manifest
from monl.frontend_ai import _design_completeness_errors
from monl.section_substance import rule_for, substance_errors
from monl.ui_patterns import select_ui_patterns

SPEC = """app Atelier

entity Piece
    name: String
    price: Money

actor Visitor selfRegister

rule Piece.Read public

landing
    brief: "Un atelier de céramique qui vend ses pièces en direct."
    section "À propos": "Des objets fabriqués en petites séries."

workflow Gerer for Visitor
    Create Piece
    Read Piece
"""


def _rendre(slug, corps):
    return f'<section data-monl-section="{slug}">{corps}</section>'


# ----------------------------------------------- the substance of a section --
def test_an_empty_section_is_refused_naming_what_is_missing():
    regles = {'data-monl-section="hero"': rule_for("hero")}

    fautes = substance_errors(_rendre("hero", ""), regles)

    assert len(fautes) == 1
    assert "hero" in fautes[0]
    assert "a heading" in fautes[0]
    assert "an action" in fautes[0]
    assert "readable text" in fautes[0]


def test_a_title_alone_does_not_make_a_section():
    """It is the most frequent shell: the skeleton without the content."""
    regles = {'data-monl-section="trust"': rule_for("trust")}

    fautes = substance_errors(_rendre("trust", "<h2>Confiance</h2>"), regles)

    assert fautes and "readable text" in fautes[0]


def test_a_filled_section_is_accepted():
    regles = {'data-monl-section="trust"': rule_for("trust")}
    corps = ("<h2>Comment nous travaillons</h2><p>"
             + "Chaque pièce part sous cinq jours et le montant est calculé "
               "par le serveur, jamais par le navigateur. " * 2
             + "</p>")

    assert substance_errors(_rendre("trust", corps), regles) == []


def test_a_scripts_text_does_not_count():
    """A `<script>` is not read by a human: counting it would let one pass the
    barrier with a well-filled JavaScript variable."""
    regles = {'data-monl-section="trust"': rule_for("trust")}
    corps = "<h2>T</h2><script>var t = \"" + "x" * 400 + "\";</script>"

    fautes = substance_errors(_rendre("trust", corps), regles)

    assert fautes and "readable text" in fautes[0]


def test_a_section_does_not_borrow_its_neighbors_text():
    """A never-closed `<p>` is legal HTML5. If depth leaks, the section swallows
    everything after it and the barrier refuses nothing any more."""
    regles = {'data-monl-section="hero"': rule_for("hero")}
    html = ('<section data-monl-section="hero"><h1>Bonjour</h1>'
            '<a href="#a">Voir</a><p></section>'
            "<div>" + "beaucoup de texte ailleurs " * 20 + "</div>")

    fautes = substance_errors(html, regles)

    assert fautes and "readable text" in fautes[0]


def test_a_form_is_required_where_writing_is_needed():
    regles = {'data-monl-section="contact"': rule_for("contact")}
    sans = _rendre("contact", "<h2>Nous écrire</h2><p>Par courriel.</p>")
    avec = _rendre("contact", "<h2>Nous écrire</h2>"
                              "<form><input><button>Envoyer</button></form>")

    assert substance_errors(sans, regles) and "<form>" in substance_errors(sans, regles)[0]
    assert substance_errors(avec, regles) == []


def test_a_declared_section_never_requires_more_than_its_own_text():
    """Requiring a hundred characters from a section whose author wrote thirty
    would fail an honest spec: the threshold is capped by what is declared."""
    court = rule_for("a-propos", declared_body_length=30)
    long = rule_for("a-propos", declared_body_length=5000)

    assert court["text"] == 30
    assert long["text"] == 100


def test_a_missing_section_is_not_reported_twice():
    """Absence is already the presence check's job."""
    regles = {'data-monl-section="faq"': rule_for("faq")}

    assert substance_errors("<main></main>", regles) == []


# ---------------------------------------------------------------- the floor --
def _profil(contract, kind):
    return [p["name"] for p in select_ui_patterns(contract, kind)]


def test_every_application_carries_a_section_for_its_own_substance():
    """`exemples/05_classement.ml` only required `hero` and `closing-cta`: the
    ranking itself was required on no screen."""
    contract = {"brief": "Un classement", "entities": {"Entry": {"archetype": "post"}},
                "routes": [{"action": "Read", "entity": "Entry", "path": "/entry"}]}

    noms = _profil(contract, "generic")

    assert "catalogue" in noms


def test_the_floor_is_at_least_four_sections():
    contract = {"brief": "x", "entities": {"Entry": {}}, "routes": []}

    noms = _profil(contract, "generic")

    assert {"hero", "trust", "closing-cta"} <= set(noms)
    assert len(noms) >= 4


def test_a_booking_keeps_its_journey_and_gains_no_catalog():
    """The journey really offered decides, never the number of sections."""
    contract = {"brief": "x", "entities": {"Booking": {"archetype": "shop"}},
                "routes": [{"action": "Create", "entity": "Booking",
                            "path": "/booking"}]}

    noms = _profil(contract, "service")

    assert "booking" in noms
    assert "catalogue" not in noms


# ------------------------------------------------- end to end, on a project --
def _compiler(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))
    lignes = (tmp_path / ASSET_MANIFEST_FILENAME).read_text(encoding="utf-8").splitlines()
    corps = lignes[1:] if lignes and lignes[0].lstrip().startswith("<!--") else lignes
    return json.loads("\n".join(corps))


@pytest.fixture()
def project(tmp_path):
    manifest = _compiler(tmp_path)
    (tmp_path / "frontend").mkdir()

    def livrer(remplie):
        blocs = []
        for marker in manifest["required_markers"]["index.html"]:
            regle = manifest["section_substance"]["index.html"].get(marker, {})
            if not remplie:
                blocs.append(f"<div {marker}></div>")
                continue
            corps = ["<h2>Un titre</h2>",
                     "<p>" + "Du texte réellement lisible sur la page. " * 8 + "</p>",
                     '<a href="#s">Agir</a>']
            if regle.get("form"):
                corps.append("<form><input><button>Envoyer</button></form>")
            blocs.append(f"<div {marker}>" + "".join(corps) + "</div>")
        (tmp_path / "frontend" / "index.html").write_text(
            "\n".join(blocs), encoding="utf-8")
        assert activate_asset_manifest(str(tmp_path))
        return _design_completeness_errors(str(tmp_path))

    return livrer, manifest


def test_a_project_delivered_as_an_empty_shell_is_refused(project):
    livrer, manifest = project

    fautes = livrer(remplie=False)

    assert fautes, "une page de sections vides doit être refusée"
    vides = [f for f in fautes if f.startswith("empty or incomplete section")]
    assert len(vides) == len(manifest["section_substance"]["index.html"])


def test_the_same_project_really_filled_is_accepted(project):
    """Counter-proof: without it, a barrier refusing everything would pass."""
    livrer, _ = project

    assert livrer(remplie=True) == []


def test_the_manifest_carries_each_sections_rule(project):
    _livrer, manifest = project
    regles = manifest["section_substance"]["index.html"]

    assert set(regles) <= set(manifest["required_markers"]["index.html"])
    # The invariant is NOT "a title everywhere": the footer has none, and
    # imposing one would make "Footer" written in large type, which no real
    # site does. What counts is that no rule is empty — a rule requiring
    # nothing is a rule producing nothing, exactly what point 85 forbids.
    assert all(any(r.values()) for r in regles.values())
    assert 'data-monl-section="trust"' in regles
    assert 'data-monl-section="footer"' in regles
