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
from tests.support.cas import check_each_case

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


def _valider(liens):
    spec = BASE.format(liens="".join(f"    {ligne}\n" for ligne in liens))
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# ──────────────────────────────────────────────────── what the spec accepts ──
def test_links_go_through_in_declared_order():
    """In a footer, the order is the one we want to see."""
    ast = _valider([
        'link "Instagram": "https://instagram.com/atelier"',
        'link "Nous ecrire": "mailto:bonjour@atelier.fr"',
        'link "Nous appeler": "tel:+33123456789"',
    ])

    liens = ast["landing"]["links"]

    assert [lien["label"] for lien in liens] == ["Instagram", "Nous ecrire", "Nous appeler"]
    assert liens[0]["url"] == "https://instagram.com/atelier"


def test_a_spec_without_links_compiles_identically():
    """A spec written before this brick must not change meaning."""
    assert _valider([])["landing"]["links"] == []


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

    def cas(ligne, attendu):
        with pytest.raises(ValueError, match=attendu):
            _valider([ligne])

    check_each_case(table, cas)


def test_two_links_with_the_same_label_are_refused():
    with pytest.raises(ValueError, match="have the label"):
        _valider([
            'link "Instagram": "https://instagram.com/a"',
            'link "instagram": "https://instagram.com/b"',
        ])


def test_the_same_address_twice_is_refused():
    with pytest.raises(ValueError, match="declared twice"):
        _valider([
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
    lignes = (tmp_path / ASSET_MANIFEST_FILENAME).read_text(encoding="utf-8").splitlines()
    manifest = json.loads("\n".join(lignes[1:]))
    (tmp_path / "frontend").mkdir()

    def livrer(avec_liens=True):
        regles = manifest["section_substance"]["index.html"]
        blocs = []
        for marker in manifest["required_markers"]["index.html"]:
            regle = regles.get(marker, {})
            corps = ["<h2>Un titre</h2>",
                     "<p>" + "Du texte réellement lisible sur la page. " * 8 + "</p>",
                     '<a href="#s">Agir</a>']
            if regle.get("form"):
                corps.append("<form><input><button>Envoyer</button></form>")
            if 'section="footer"' in marker and avec_liens:
                corps.append('<a href="https://instagram.com/atelier">Instagram</a>'
                             '<a href="mailto:bonjour@atelier.fr">Nous écrire</a>')
            blocs.append(f"<div {marker}>" + "".join(corps) + "</div>")
        (tmp_path / "frontend" / "index.html").write_text(
            "\n".join(blocs), encoding="utf-8")
        assert activate_asset_manifest(str(tmp_path))
        return _design_completeness_errors(str(tmp_path))

    return livrer, manifest


def test_the_footer_is_a_required_section(project):
    _livrer, manifest = project

    assert 'data-monl-section="footer"' in manifest["required_markers"]["index.html"]
    assert 'data-monl-section="footer"' in manifest["section_substance"]["index.html"]


def test_the_footer_requires_no_title():
    """Imposing one would make "Footer" written in large type, which no real site
    does."""
    regle = rule_for("footer")

    assert not regle.get("heading")
    assert regle["action"] and regle["text"]


def test_a_declared_link_missing_from_the_site_is_refused(project):
    livrer, _ = project

    fautes = livrer(avec_liens=False)

    manquants = [f for f in fautes if f.startswith("declared link missing")]
    assert len(manquants) == 2, fautes
    assert "instagram.com/atelier" in " ".join(manquants)
    assert "mailto:bonjour@atelier.fr" in " ".join(manquants)


def test_the_same_site_with_its_links_is_accepted(project):
    """Counter-proof: without it, a check refusing everything would pass."""
    livrer, _ = project

    assert livrer(avec_liens=True) == []


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
