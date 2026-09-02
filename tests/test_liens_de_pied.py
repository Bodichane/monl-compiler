"""Un pied de page sans liens est le dernier aveu qu'un site est une maquette.

Deux mots gris, aucun réseau, aucune mention, aucun contact : c'est ce que
produisaient tous les sites, parce que le pied de page n'était exigé NULLE
PART — le plancher du point 143 comptait quatre sections et s'arrêtait
au-dessus de lui.

monl ne peut pas DEVINER une adresse : une page Instagram inventée mène chez
quelqu'un d'autre. Il la fait donc DÉCLARER, puis il l'exige — même arbitrage
qu'aux points 83 (les assets) et 86 (le stock).
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


# ─────────────────────────────────────────────── ce que la spec accepte ──
def test_les_liens_traversent_dans_l_ordre_declare():
    """Dans un pied de page, l'ordre est celui qu'on veut voir."""
    ast = _valider([
        'link "Instagram": "https://instagram.com/atelier"',
        'link "Nous ecrire": "mailto:bonjour@atelier.fr"',
        'link "Nous appeler": "tel:+33123456789"',
    ])

    liens = ast["landing"]["links"]

    assert [lien["label"] for lien in liens] == ["Instagram", "Nous ecrire", "Nous appeler"]
    assert liens[0]["url"] == "https://instagram.com/atelier"


def test_une_spec_sans_lien_compile_a_l_identique():
    """Une spec écrite avant cette brique ne doit pas changer de sens."""
    assert _valider([])["landing"]["links"] == []


# ──────────────────────────────────────────────────── ce qu'elle refuse ──
@pytest.mark.parametrize("ligne, attendu", [
    ('link "Instagram": "instagram.com/atelier"', "chemin du site lui-même"),
    ('link "Site": "www.exemple.fr"', "chemin du site lui-même"),
    ('link "Vide": ""', "non vides"),
    ('link "": "https://exemple.fr"', "non vides"),
])
def test_une_adresse_inutilisable_est_refusee(ligne, attendu):
    """Un lien qui ne marche pas est pire qu'un lien absent : il se voit.

    Sans schéma, le navigateur lit « instagram.com/atelier » comme un chemin
    RELATIF et mène à une page inexistante du site.
    """
    with pytest.raises(ValueError, match=attendu):
        _valider([ligne])


def test_deux_liens_au_meme_libelle_sont_refuses():
    with pytest.raises(ValueError, match="portent le libellé"):
        _valider([
            'link "Instagram": "https://instagram.com/a"',
            'link "instagram": "https://instagram.com/b"',
        ])


def test_la_meme_adresse_deux_fois_est_refusee():
    with pytest.raises(ValueError, match="déclarée deux fois"):
        _valider([
            'link "Notre page": "https://exemple.fr"',
            'link "Nous suivre": "https://exemple.fr"',
        ])


# ─────────────────────────────────────── ce que le projet compilé exige ──
@pytest.fixture()
def projet(tmp_path):
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


def test_le_pied_de_page_est_une_section_obligatoire(projet):
    _livrer, manifest = projet

    assert 'data-monl-section="footer"' in manifest["required_markers"]["index.html"]
    assert 'data-monl-section="footer"' in manifest["section_substance"]["index.html"]


def test_le_pied_de_page_n_exige_pas_de_titre():
    """Lui en imposer un ferait écrire « Pied de page » en gros, ce qu'aucun
    site réel ne fait."""
    regle = rule_for("footer")

    assert not regle.get("heading")
    assert regle["action"] and regle["text"]


def test_un_lien_declare_absent_du_site_est_refuse(projet):
    livrer, _ = projet

    fautes = livrer(avec_liens=False)

    manquants = [f for f in fautes if f.startswith("lien déclaré absent")]
    assert len(manquants) == 2, fautes
    assert "instagram.com/atelier" in " ".join(manquants)
    assert "mailto:bonjour@atelier.fr" in " ".join(manquants)


def test_le_meme_site_avec_ses_liens_est_accepte(projet):
    """Contre-épreuve : sans elle, un contrôle qui refuse tout passerait."""
    livrer, _ = projet

    assert livrer(avec_liens=True) == []


def test_le_brief_dit_quoi_mettre_dans_le_pied_de_page(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(BASE.format(
        liens='    link "Instagram": "https://instagram.com/atelier"\n'), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))

    brief = (tmp_path / "docs/DESIGN_SYSTEM.md").read_text(encoding="utf-8")

    assert "## Pied de page" in brief
    assert "https://instagram.com/atelier" in brief
    # Une barrière que l'IA ne connaît pas ne produit pas de la qualité, elle
    # produit des reprises facturées.
    assert "fait échouer la construction" in brief
    assert "Ne JAMAIS inventer" in brief
