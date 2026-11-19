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


def _render(slug, body):
    return f'<section data-monl-section="{slug}">{body}</section>'


# ----------------------------------------------- the substance of a section --
def test_an_empty_section_is_refused_naming_what_is_missing():
    rules = {'data-monl-section="hero"': rule_for("hero")}

    faults = substance_errors(_render("hero", ""), rules)

    assert len(faults) == 1
    assert "hero" in faults[0]
    assert "a heading" in faults[0]
    assert "an action" in faults[0]
    assert "readable text" in faults[0]


def test_a_title_alone_does_not_make_a_section():
    """It is the most frequent shell: the skeleton without the content."""
    rules = {'data-monl-section="trust"': rule_for("trust")}

    faults = substance_errors(_render("trust", "<h2>Confiance</h2>"), rules)

    assert faults and "readable text" in faults[0]


def test_a_filled_section_is_accepted():
    rules = {'data-monl-section="trust"': rule_for("trust")}
    body = ("<h2>Comment nous travaillons</h2><p>"
             + "Chaque pièce part sous cinq jours et le montant est calculé "
               "par le serveur, jamais par le navigateur. " * 2
             + "</p>")

    assert substance_errors(_render("trust", body), rules) == []


def test_a_scripts_text_does_not_count():
    """A `<script>` is not read by a human: counting it would let one pass the
    barrier with a well-filled JavaScript variable."""
    rules = {'data-monl-section="trust"': rule_for("trust")}
    body = "<h2>T</h2><script>var t = \"" + "x" * 400 + "\";</script>"

    faults = substance_errors(_render("trust", body), rules)

    assert faults and "readable text" in faults[0]


def test_a_section_does_not_borrow_its_neighbors_text():
    """A never-closed `<p>` is legal HTML5. If depth leaks, the section swallows
    everything after it and the barrier refuses nothing any more."""
    rules = {'data-monl-section="hero"': rule_for("hero")}
    html = ('<section data-monl-section="hero"><h1>Bonjour</h1>'
            '<a href="#a">Voir</a><p></section>'
            "<div>" + "beaucoup de texte ailleurs " * 20 + "</div>")

    faults = substance_errors(html, rules)

    assert faults and "readable text" in faults[0]


def test_a_form_is_required_where_writing_is_needed():
    rules = {'data-monl-section="contact"': rule_for("contact")}
    sans = _render("contact", "<h2>Nous écrire</h2><p>Par courriel.</p>")
    with_ = _render("contact", "<h2>Nous écrire</h2>"
                              "<form><input><button>Envoyer</button></form>")

    assert substance_errors(sans, rules) and "<form>" in substance_errors(sans, rules)[0]
    assert substance_errors(with_, rules) == []


def test_a_declared_section_never_requires_more_than_its_own_text():
    """Requiring a hundred characters from a section whose author wrote thirty
    would fail an honest spec: the threshold is capped by what is declared."""
    short = rule_for("a-propos", declared_body_length=30)
    long = rule_for("a-propos", declared_body_length=5000)

    assert short["text"] == 30
    assert long["text"] == 100


def test_a_missing_section_is_not_reported_twice():
    """Absence is already the presence check's job."""
    rules = {'data-monl-section="faq"': rule_for("faq")}

    assert substance_errors("<main></main>", rules) == []


# ---------------------------------------------------------------- the floor --
def _profile(contract, kind):
    return [p["name"] for p in select_ui_patterns(contract, kind)]


def test_every_application_carries_a_section_for_its_own_substance():
    """`exemples/05_classement.ml` only required `hero` and `closing-cta`: the
    ranking itself was required on no screen."""
    contract = {"brief": "Un classement", "entities": {"Entry": {"archetype": "post"}},
                "routes": [{"action": "Read", "entity": "Entry", "path": "/entry"}]}

    names = _profile(contract, "generic")

    assert "catalogue" in names


def test_the_floor_is_at_least_four_sections():
    contract = {"brief": "x", "entities": {"Entry": {}}, "routes": []}

    names = _profile(contract, "generic")

    assert {"hero", "trust", "closing-cta"} <= set(names)
    assert len(names) >= 4


def test_a_booking_keeps_its_journey_and_gains_no_catalog():
    """The journey really offered decides, never the number of sections."""
    contract = {"brief": "x", "entities": {"Booking": {"archetype": "shop"}},
                "routes": [{"action": "Create", "entity": "Booking",
                            "path": "/booking"}]}

    names = _profile(contract, "service")

    assert "booking" in names
    assert "catalogue" not in names


# ------------------------------------------------- end to end, on a project --
def _compiler(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))
    lines = (tmp_path / ASSET_MANIFEST_FILENAME).read_text(encoding="utf-8").splitlines()
    body = lines[1:] if lines and lines[0].lstrip().startswith("<!--") else lines
    return json.loads("\n".join(body))


@pytest.fixture()
def project(tmp_path):
    manifest = _compiler(tmp_path)
    (tmp_path / "frontend").mkdir()

    def deliver(filled):
        blocks = []
        for marker in manifest["required_markers"]["index.html"]:
            rule = manifest["section_substance"]["index.html"].get(marker, {})
            if not filled:
                blocks.append(f"<div {marker}></div>")
                continue
            body = ["<h2>Un titre</h2>",
                     "<p>" + "Du texte réellement lisible sur la page. " * 8 + "</p>",
                     '<a href="#s">Agir</a>']
            if rule.get("form"):
                body.append("<form><input><button>Envoyer</button></form>")
            blocks.append(f"<div {marker}>" + "".join(body) + "</div>")
        (tmp_path / "frontend" / "index.html").write_text(
            "\n".join(blocks), encoding="utf-8")
        assert activate_asset_manifest(str(tmp_path))
        return _design_completeness_errors(str(tmp_path))

    return deliver, manifest


def test_a_project_delivered_as_an_empty_shell_is_refused(project):
    deliver, manifest = project

    faults = deliver(filled=False)

    assert faults, "a page of empty sections must be refused"
    empty = [f for f in faults if f.startswith("empty or incomplete section")]
    assert len(empty) == len(manifest["section_substance"]["index.html"])


def test_the_same_project_really_filled_is_accepted(project):
    """Counter-proof: without it, a barrier refusing everything would pass."""
    deliver, _ = project

    assert deliver(filled=True) == []


def test_the_manifest_carries_each_sections_rule(project):
    _deliver, manifest = project
    rules = manifest["section_substance"]["index.html"]

    assert set(rules) <= set(manifest["required_markers"]["index.html"])
    # The invariant is NOT "a title everywhere": the footer has none, and
    # imposing one would make "Footer" written in large type, which no real
    # site does. What counts is that no rule is empty — a rule requiring
    # nothing is a rule producing nothing, exactly what point 85 forbids.
    assert all(any(r.values()) for r in rules.values())
    assert 'data-monl-section="trust"' in rules
    assert 'data-monl-section="footer"' in rules
