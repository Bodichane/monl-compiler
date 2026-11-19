"""A footer without links is the last admission that a site is a mockup.

Two gray words, no network, no notice, no contact: that is what every site
produced, because the footer was required NOWHERE — point 143's floor counted
four sections and stopped above it.

monl cannot GUESS an address: an invented Instagram page leads to someone
else's. It therefore makes it DECLARED, then requires it — the same ruling as
at points 83 (assets) and 86 (stock).
"""

import contextlib
import io
import json

import pytest

from monl.ast_validator import MonlAST
from monl.cli import compile_project
from monl.design_system import ASSET_MANIFEST_FILENAME, activate_asset_manifest
from monl.frontend_ai import _design_completeness_errors
from monl.parser import parse_monl_string
from monl.section_substance import rule_for
from tests.support.cases import check_each_case

BASE = """app Atelier

entity Piece
    name: String

actor Visitor selfRegister

rule Piece.Read public

landing
    brief: "Un atelier de ceramique."
{liens}
workflow Gerer for Visitor
    Create Piece
    Read Piece
"""


def _validate(links):
    spec = BASE.format(liens="".join(f"    {line}\n" for line in links))
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# ──────────────────────────────────────────────────── what the spec accepts ──
def test_links_go_through_in_declared_order():
    """In a footer, the order is the one we want to see."""
    ast = _validate([
        'link "Instagram": "https://instagram.com/atelier"',
        'link "Nous ecrire": "mailto:bonjour@atelier.fr"',
        'link "Nous appeler": "tel:+33123456789"',
    ])

    links = ast["landing"]["links"]

    assert [link["label"] for link in links] == ["Instagram", "Nous ecrire", "Nous appeler"]
    assert links[0]["url"] == "https://instagram.com/atelier"


def test_a_spec_without_links_compiles_identically():
    """A spec written before this brick must not change meaning."""
    assert _validate([])["landing"]["links"] == []


# ────────────────────────────────────────────────────────── what it refuses ──
def test_an_unusable_address_is_refused():
    """A link that does not work is worse than a missing link: it shows.

    Without a scheme, the browser reads "instagram.com/atelier" as a RELATIVE
    path and leads to a nonexistent page of the site.
    """
    table = [
        ('link "Instagram": "instagram.com/atelier"', "path on the site itself"),
        ('link "Site": "www.exemple.fr"', "path on the site itself"),
        ('link "Vide": ""', "non-empty"),
        ('link "": "https://exemple.fr"', "non-empty"),
    ]

    def cas(line, expected):
        with pytest.raises(ValueError, match=expected):
            _validate([line])

    check_each_case(table, cas)


def test_two_links_with_the_same_label_are_refused():
    with pytest.raises(ValueError, match="have the label"):
        _validate([
            'link "Instagram": "https://instagram.com/a"',
            'link "instagram": "https://instagram.com/b"',
        ])


def test_the_same_address_twice_is_refused():
    with pytest.raises(ValueError, match="declared twice"):
        _validate([
            'link "Notre page": "https://exemple.fr"',
            'link "Nous suivre": "https://exemple.fr"',
        ])


# ─────────────────────────────────────── what the compiled project requires ──
@pytest.fixture()
def project(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(BASE.format(
        liens='    link "Instagram": "https://instagram.com/atelier"\n'
              '    link "Nous ecrire": "mailto:bonjour@atelier.fr"\n'),
        encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))
    lines = (tmp_path / ASSET_MANIFEST_FILENAME).read_text(encoding="utf-8").splitlines()
    manifest = json.loads("\n".join(lines[1:]))
    (tmp_path / "frontend").mkdir()

    def deliver(with_links=True):
        rules = manifest["section_substance"]["index.html"]
        blocks = []
        for marker in manifest["required_markers"]["index.html"]:
            rule = rules.get(marker, {})
            body = ["<h2>Un titre</h2>",
                     "<p>" + "Du texte réellement lisible sur la page. " * 8 + "</p>",
                     '<a href="#s">Agir</a>']
            if rule.get("form"):
                body.append("<form><input><button>Envoyer</button></form>")
            if 'section="footer"' in marker and with_links:
                body.append('<a href="https://instagram.com/atelier">Instagram</a>'
                             '<a href="mailto:bonjour@atelier.fr">Nous écrire</a>')
            blocks.append(f"<div {marker}>" + "".join(body) + "</div>")
        (tmp_path / "frontend" / "index.html").write_text(
            "\n".join(blocks), encoding="utf-8")
        assert activate_asset_manifest(str(tmp_path))
        return _design_completeness_errors(str(tmp_path))

    return deliver, manifest


def test_the_footer_is_a_required_section(project):
    _deliver, manifest = project

    assert 'data-monl-section="footer"' in manifest["required_markers"]["index.html"]
    assert 'data-monl-section="footer"' in manifest["section_substance"]["index.html"]


def test_the_footer_requires_no_title():
    """Imposing one would make "Footer" written in large type, which no real site
    does."""
    rule = rule_for("footer")

    assert not rule.get("heading")
    assert rule["action"] and rule["text"]


def test_a_declared_link_missing_from_the_site_is_refused(project):
    deliver, _ = project

    faults = deliver(with_links=False)

    missing = [f for f in faults if f.startswith("declared link missing")]
    assert len(missing) == 2, faults
    assert "instagram.com/atelier" in " ".join(missing)
    assert "mailto:bonjour@atelier.fr" in " ".join(missing)


def test_the_same_site_with_its_links_is_accepted(project):
    """Counter-proof: without it, a check refusing everything would pass."""
    deliver, _ = project

    assert deliver(with_links=True) == []


def test_the_brief_says_what_to_put_in_the_footer(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(BASE.format(
        liens='    link "Instagram": "https://instagram.com/atelier"\n'), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))

    brief = (tmp_path / "docs/DESIGN_SYSTEM.md").read_text(encoding="utf-8")

    assert "## Footer" in brief
    assert "https://instagram.com/atelier" in brief
    # A barrier the AI does not know produces no quality, it produces billed
    # retries.
    assert "makes the build fail" in brief
    assert "NEVER invent" in brief
