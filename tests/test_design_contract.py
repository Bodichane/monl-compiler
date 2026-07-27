"""La direction de design est vérifiable quand la spec la déclare (bêta 3).

La clause 'design' du contrat était la seule qu'aucun contrôle ne confrontait
au livrable. Ces tests fixent la règle retenue : épinglée par la spec, elle
est contraignante ; déduite du vocabulaire, elle reste une proposition.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ast_validator import MonlAST  # noqa: E402
from frontend_contract import build_contract  # noqa: E402
from generator import MonlSecureGenerator  # noqa: E402
from parser import parse_monl_file  # noqa: E402
from smoke_test import _verifier_palette  # noqa: E402

BASE = """app Reparation

entity Piece
    label: String

actor Client selfRegister

workflow Catalogue for Client
    Create Piece
    Read Piece
"""

EPINGLE = BASE + """
ui Piece
    theme: atelier
"""


def _contrat(spec_source, workdir):
    chemin = os.path.join(workdir, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec_source)
    ast = MonlAST(parse_monl_file(chemin)).validate_and_audit()
    generateur = MonlSecureGenerator(ast, output_dir=workdir)
    return build_contract(ast, generateur)


def _frontend(workdir, css):
    dossier = os.path.join(workdir, "frontend")
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(css)
    return dossier


def test_theme_epingle_est_exact_et_contraignant():
    """Un thème épinglé échappe à la variation de teinte et lie le frontend."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(EPINGLE, workdir)
        design = contrat["design"]
        assert design["name"] == "atelier"
        assert design["pinned"] is True
        # Valeurs exactes du thème : une palette vérifiable ne peut pas être
        # décalée par la graine de variation propre au projet.
        assert design["accent"] == "#D9F227"
        assert design["bg"] == "#F1F3EE"

        # La direction couvre aussi la typographie (point 52) : un frontend
        # conforme applique la police de titrage, pas seulement la palette.
        TYPO = "h1{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;}"
        conforme = _frontend(workdir, ":root{--a:#F1F3EE;--b:#FBFCFA;--c:#101C24;"
                                      "--d:#D9F227;--e:#A8412A;}" + TYPO)
        assert _verifier_palette(conforme, contrat) == []

        ecart = _frontend(workdir, ":root{--a:#F1F3EE;--b:#FBFCFA;--c:#101C24;"
                                   "--d:#FF00FF;--e:#A8412A;}" + TYPO)
        problemes = _verifier_palette(ecart, contrat)
        assert len(problemes) == 1
        message, bloquant = problemes[0]
        assert bloquant is True
        assert "#D9F227" in message

        # Thème épinglé mais SEULE la typographie s'écarte : signalé, jamais
        # bloquant — une pile de polices a des quasi-équivalents qu'une
        # recherche textuelle ne sait pas distinguer d'un oubli.
        typo_seule = _frontend(workdir, ":root{--a:#F1F3EE;--b:#FBFCFA;--c:#101C24;"
                                        "--d:#D9F227;--e:#A8412A;}"
                                        "h1{font-family:Futura,sans-serif;}")
        problemes = _verifier_palette(typo_seule, contrat)
        assert len(problemes) == 1
        message, bloquant = problemes[0]
        assert bloquant is False
        assert "police de titrage" in message


def test_sans_epinglage_le_visuel_appartient_a_l_ia():
    """Renversement assumé (point 58) : sans `ui … theme:`, monl ne propose
    plus de direction et n'a donc rien à reprocher. L'avertissement d'avant
    portait sur une devinette du compilateur, et poussait à reproduire l'aplat
    crème que la palette déduite rendait inévitable — elle n'offrait aucune
    surface sombre, donc aucun contraste possible sur de grandes zones."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(BASE, workdir)
        assert contrat["design"]["pinned"] is False
        # Un frontend qui ignore totalement la palette déduite : rien à dire.
        assert _verifier_palette(_frontend(workdir, "body{color:#123456}"), contrat) == []


def test_le_brief_rend_la_main_a_l_ia_quand_rien_n_est_epingle(tmp_path):
    """Le contrat JSON garde une palette calculée, mais le brief — le seul
    document que l'IA lit vraiment — doit dire clairement qu'elle est libre."""
    brief_path = tmp_path / "libre"
    brief_path.mkdir()
    (brief_path / "spec.ml").write_text(BASE, encoding="utf-8")
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from cli import compile_project  # noqa: E402
    compile_project(str(brief_path / "spec.ml"), str(brief_path))
    brief = (brief_path / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Direction de design — LIBRE" in brief
    assert "surfaces sombres" in brief          # ce qui était impossible avant
    # Les deux exigences qui ne sont pas des questions de goût subsistent.
    assert "4,5:1" in brief and "aucune ressource distante" in brief


def test_demo_livree_respecte_son_theme_epingle():
    """Le frontend de la démo applique réellement la palette que sa spec épingle."""
    racine = os.path.join(os.path.dirname(__file__), "..")
    ast = MonlAST(parse_monl_file(os.path.join(racine, "demo", "spec.ml"))).validate_and_audit()
    with tempfile.TemporaryDirectory() as workdir:
        contrat = build_contract(ast, MonlSecureGenerator(ast, output_dir=workdir))
    assert contrat["design"]["pinned"] is True
    assert _verifier_palette(os.path.join(racine, "demo", "frontend"), contrat) == []


# ---- Aucune police distante dans aucun thème (point 52) ----

# Familles présentes sur les machines sans rien télécharger : génériques CSS,
# mots-clés système, et faces livrées avec macOS / Windows / les distributions
# Linux courantes. Toute police ABSENTE de cette liste devrait être chargée
# depuis un CDN — ce que la règle « frontend AUTONOME » du même contrat
# interdit. C'est cette contradiction qui vidait l'identité typographique de
# chaque projet ; ce test la rend impossible à réintroduire par distraction.
FAMILLES_LOCALES = {
    "serif", "sans-serif", "monospace", "system-ui", "ui-monospace",
    "-apple-system", "sfmono-regular", "blinkmacsystemfont",
    "segoe ui", "roboto", "helvetica neue", "helvetica", "arial",
    "arial narrow", "liberation sans", "liberation sans narrow",
    "liberation serif", "georgia", "times new roman", "times",
    "palatino linotype", "book antiqua", "palatino", "urw palladio l",
    "trebuchet ms", "lucida grande", "lucida sans unicode",
    "dejavu sans", "dejavu sans mono", "verdana", "geneva",
    "menlo", "consolas", "courier new", "monaco",
}

THEMES = ("atelier", "editorial", "market", "console", "civic", "ledger")


def _design_du_theme(nom, workdir):
    spec = BASE + f"\nui Piece\n    theme: {nom}\n"
    return _contrat(spec, workdir)["design"]


def test_aucun_theme_ne_reclame_une_police_a_telecharger():
    for nom in THEMES:
        with tempfile.TemporaryDirectory() as workdir:
            design = _design_du_theme(nom, workdir)
            assert "google_fonts" not in design, (
                f"le thème « {nom} » réexpose google_fonts : le contrat "
                f"proposerait une police que sa règle d'autonomie interdit")
            for cle in ("font_display", "font_body", "font_mono"):
                for famille in design[cle].split(","):
                    famille = famille.strip().strip("'\"").lower()
                    assert famille in FAMILLES_LOCALES, (
                        f"{nom}.{cle} nomme « {famille} », absente des familles "
                        f"disponibles localement — il faudrait la télécharger")


def test_les_themes_restent_typographiquement_distincts():
    """Se passer de Google Fonts ne doit pas fondre les six systèmes en un
    seul : c'est la raison d'être du catalogue (deux apps ne se ressemblent
    jamais). On compare la face de TITRAGE, celle qui signe l'identité."""
    titrages = {}
    for nom in THEMES:
        with tempfile.TemporaryDirectory() as workdir:
            pile = _design_du_theme(nom, workdir)["font_display"]
            titrages[nom] = pile.split(",")[0].strip().strip("'\"").lower()
    assert len(set(titrages.values())) == len(THEMES), (
        f"deux thèmes partagent la même police de titrage : {titrages}")


# ---- Tons dérivés : la palette n'est pas plate (point 56) ----

TONS_DERIVES = ("ink_soft", "border", "surface_alt", "accent_soft", "accent_strong")


def _luminance(hexa):
    hexa = hexa.lstrip("#")
    canaux = (int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a, b):
    bas, haut = sorted((_luminance(a), _luminance(b)))
    return (haut + 0.05) / (bas + 0.05)


def test_chaque_theme_expose_ses_tons_derives():
    """Cinq valeurs plates ne suffisent pas à une interface : sans texte
    atténué, filet ni état de survol, le rendu paraît plat quelle que soit la
    palette. Ces tons sont déduits, jamais laissés à l'improvisation."""
    for nom in THEMES:
        with tempfile.TemporaryDirectory() as workdir:
            design = _design_du_theme(nom, workdir)
            for ton in TONS_DERIVES:
                assert design[ton].startswith("#") and len(design[ton]) == 7, (
                    f"{nom}.{ton} n'est pas une couleur : {design[ton]!r}")


def test_le_texte_attenue_reste_lisible_sur_tous_les_themes():
    """Une nuance proposée par le compilateur ne doit pas rendre illisible ce
    qu'elle sert à hiérarchiser. Seuil WCAG AA pour du texte : 4,5:1. Le pire
    des six thèmes fait foi, pas la moyenne (« civic » échouait à 4,26:1)."""
    for nom in THEMES:
        with tempfile.TemporaryDirectory() as workdir:
            design = _design_du_theme(nom, workdir)
            ratio = _contraste(design["ink_soft"], design["bg"])
            assert ratio >= 4.5, f"{nom} : texte atténué à {ratio:.2f}:1 sur son fond"


def test_les_tons_derives_suivent_la_variation_de_teinte():
    """Calculés APRÈS la variation propre au projet : un accent dérivé d'une
    teinte qui n'est plus celle du projet jurerait avec elle."""
    with tempfile.TemporaryDirectory() as workdir:
        design = _contrat(BASE, workdir)["design"]     # thème non épinglé
        assert design["accent_strong"] != design["accent"]
        # accent_soft tire l'accent vers le fond : il doit s'en rapprocher.
        assert (_contraste(design["accent_soft"], design["bg"])
                < _contraste(design["accent"], design["bg"]))
