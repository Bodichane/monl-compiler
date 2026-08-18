"""Un site livré n'est jamais une coquille vide.

Le contrôle de complétude vérifiait qu'un marqueur était PRÉSENT. Un marqueur
nomme une section, il ne prouve pas qu'il y a quelque chose dedans : une page
faite de huit `<section>` vides passait, et le test du dépôt l'affirmait. Ces
épreuves portent sur les deux moitiés du défaut — la MATIÈRE de chaque
section, et le NOMBRE de sections exigées.
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


# ------------------------------------------------------- la matière d'une section --
def test_une_section_vide_est_refusee_en_nommant_ce_qui_manque():
    regles = {'data-monl-section="hero"': rule_for("hero")}

    fautes = substance_errors(_rendre("hero", ""), regles)

    assert len(fautes) == 1
    assert "hero" in fautes[0]
    assert "un titre" in fautes[0]
    assert "une action" in fautes[0]
    assert "texte lisible" in fautes[0]


def test_un_titre_seul_ne_fait_pas_une_section():
    """C'est la coquille la plus fréquente : le squelette sans le contenu."""
    regles = {'data-monl-section="trust"': rule_for("trust")}

    fautes = substance_errors(_rendre("trust", "<h2>Confiance</h2>"), regles)

    assert fautes and "texte lisible" in fautes[0]


def test_une_section_pourvue_est_acceptee():
    regles = {'data-monl-section="trust"': rule_for("trust")}
    corps = ("<h2>Comment nous travaillons</h2><p>"
             + "Chaque pièce part sous cinq jours et le montant est calculé "
               "par le serveur, jamais par le navigateur. " * 2
             + "</p>")

    assert substance_errors(_rendre("trust", corps), regles) == []


def test_le_texte_d_un_script_ne_compte_pas():
    """Un `<script>` n'est pas lu par un humain : le compter permettrait de
    passer la barrière avec une variable JavaScript bien remplie."""
    regles = {'data-monl-section="trust"': rule_for("trust")}
    corps = "<h2>T</h2><script>var t = \"" + "x" * 400 + "\";</script>"

    fautes = substance_errors(_rendre("trust", corps), regles)

    assert fautes and "texte lisible" in fautes[0]


def test_une_section_n_emprunte_pas_le_texte_de_sa_voisine():
    """Un `<p>` jamais refermé est du HTML5 légal. Si la profondeur fuit, la
    section avale tout ce qui la suit et la barrière ne refuse plus rien."""
    regles = {'data-monl-section="hero"': rule_for("hero")}
    html = ('<section data-monl-section="hero"><h1>Bonjour</h1>'
            '<a href="#a">Voir</a><p></section>'
            "<div>" + "beaucoup de texte ailleurs " * 20 + "</div>")

    fautes = substance_errors(html, regles)

    assert fautes and "texte lisible" in fautes[0]


def test_un_formulaire_est_exige_la_ou_il_faut_ecrire():
    regles = {'data-monl-section="contact"': rule_for("contact")}
    sans = _rendre("contact", "<h2>Nous écrire</h2><p>Par courriel.</p>")
    avec = _rendre("contact", "<h2>Nous écrire</h2>"
                              "<form><input><button>Envoyer</button></form>")

    assert substance_errors(sans, regles) and "<form>" in substance_errors(sans, regles)[0]
    assert substance_errors(avec, regles) == []


def test_une_section_declaree_n_exige_jamais_plus_que_son_propre_texte():
    """Réclamer cent caractères à une rubrique dont l'auteur en a écrit trente
    ferait échouer une spec honnête : le seuil est plafonné par le déclaré."""
    court = rule_for("a-propos", declared_body_length=30)
    long = rule_for("a-propos", declared_body_length=5000)

    assert court["text"] == 30
    assert long["text"] == 100


def test_une_section_absente_n_est_pas_signalee_deux_fois():
    """L'absence est déjà le rôle du contrôle de présence."""
    regles = {'data-monl-section="faq"': rule_for("faq")}

    assert substance_errors("<main></main>", regles) == []


# ------------------------------------------------------------------ le plancher --
def _profil(contract, kind):
    return [p["name"] for p in select_ui_patterns(contract, kind)]


def test_toute_application_porte_une_section_pour_sa_propre_matiere():
    """`exemples/05_classement.ml` n'exigeait que `hero` et `closing-cta` : le
    classement lui-même n'était requis sur aucun écran."""
    contract = {"brief": "Un classement", "entities": {"Entry": {"archetype": "post"}},
                "routes": [{"action": "Read", "entity": "Entry", "path": "/entry"}]}

    noms = _profil(contract, "generic")

    assert "catalogue" in noms


def test_le_plancher_vaut_quatre_sections_au_minimum():
    contract = {"brief": "x", "entities": {"Entry": {}}, "routes": []}

    noms = _profil(contract, "generic")

    assert {"hero", "trust", "closing-cta"} <= set(noms)
    assert len(noms) >= 4


def test_une_reservation_garde_son_parcours_et_ne_gagne_pas_un_catalogue():
    """Le parcours réellement offert tranche, jamais le nombre de sections."""
    contract = {"brief": "x", "entities": {"Booking": {"archetype": "shop"}},
                "routes": [{"action": "Create", "entity": "Booking",
                            "path": "/booking"}]}

    noms = _profil(contract, "service")

    assert "booking" in noms
    assert "catalogue" not in noms


# ------------------------------------------------- de bout en bout, sur un projet --
def _compiler(tmp_path):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        compile_project(str(spec), str(tmp_path))
    lignes = (tmp_path / ASSET_MANIFEST_FILENAME).read_text(encoding="utf-8").splitlines()
    corps = lignes[1:] if lignes and lignes[0].lstrip().startswith("<!--") else lignes
    return json.loads("\n".join(corps))


@pytest.fixture()
def projet(tmp_path):
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


def test_un_projet_livre_en_coquille_vide_est_refuse(projet):
    livrer, manifest = projet

    fautes = livrer(remplie=False)

    assert fautes, "une page de sections vides doit être refusée"
    vides = [f for f in fautes if f.startswith("section vide ou incomplète")]
    assert len(vides) == len(manifest["section_substance"]["index.html"])


def test_le_meme_projet_reellement_rempli_est_accepte(projet):
    """Contre-épreuve : sans elle, une barrière qui refuse tout passerait."""
    livrer, _ = projet

    assert livrer(remplie=True) == []


def test_le_manifeste_porte_la_regle_de_chaque_section(projet):
    _livrer, manifest = projet
    regles = manifest["section_substance"]["index.html"]

    assert set(regles) <= set(manifest["required_markers"]["index.html"])
    assert all(r.get("heading") for r in regles.values())
    assert 'data-monl-section="trust"' in regles
