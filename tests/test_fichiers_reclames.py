# Brique 29 (point 137) — tout fichier local RÉCLAMÉ par le frontend doit
# être réellement servi.
#
# Le défaut qui a fait naître la brique est réel : AtelierNaya référençait six
# SVG que l'IA n'avait jamais livrés, et `monl run --check` répondait vert.
# Rien ne cassait — un fichier absent ne lève aucune exception JavaScript, donc
# jsdom ne bronchait pas ; la page s'affichait avec six trous.
#
# Les contre-épreuves comptent autant que le contrôle : un contrôle qui refuse
# TOUT passerait le premier test. On vérifie donc aussi qu'une route du
# contrat, une navigation par fragment et un CDN ne sont JAMAIS dénoncés
# (points 57 et 92 : un avertissement qui se trompe sur un site correct apprend
# à ne plus lire les avertissements).
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
def projet(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    return proj


def _frontend(projet, **fichiers):
    front = projet / "frontend"
    front.mkdir(exist_ok=True)
    for nom, contenu in fichiers.items():
        cible = front / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
    return front


def _page(corps):
    return f"<!doctype html><html><body>{corps}{APPEL}</body></html>"


# ---------------------------------------------------------------- le défaut --
def test_un_svg_reference_mais_absent_fait_echouer_le_smoke_test(projet):
    """Le cas d'AtelierNaya, réduit à sa plus simple expression."""
    _frontend(projet, **{"index.html": _page('<img src="hero.svg" alt="">')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert not ok
    assert any("hero.svg" in e and "404" in e for e in errors), errors


def test_le_meme_frontend_passe_des_que_le_fichier_est_livre(projet):
    """CONTRE-ÉPREUVE indispensable : sans elle, un contrôle qui refuserait
    tout frontend passerait le test précédent sans que rien ne le montre."""
    _frontend(projet, **{"index.html": _page('<img src="hero.svg" alt="">'),
                         "hero.svg": '<svg xmlns="http://www.w3.org/2000/svg"/>'})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors


def test_chaque_fichier_manquant_est_nomme_avec_sa_page(projet):
    """Un rapport qui dirait « des fichiers manquent » n'aiderait personne :
    c'est le nom du fichier ET celui de la page qui rendent la correction
    possible sans chercher."""
    _frontend(projet, **{"index.html": _page(
        '<img src="a.svg"><img src="b.png"><link rel="stylesheet" href="c.css">')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert not ok
    for attendu in ("a.svg", "b.png", "c.css"):
        assert any(attendu in e for e in errors), (attendu, errors)
    assert all("index.html" in e for e in errors if ".svg" in e), errors


def test_une_image_absente_est_denoncee_avec_le_conseil_des_assets(projet):
    """Le message doit envoyer vers les assets (brique 13), pas laisser
    chercher. La cause est réelle et silencieuse : `monl import` ne RETIENT que
    la liste blanche (voir le test d'archive plus bas)."""
    _frontend(projet, **{"index.html": _page('<img src="photo.jpg">')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert not ok
    assert any("photo.jpg" in e and "assets" in e for e in errors), errors


def test_une_image_reellement_presente_dans_frontend_est_servie(projet):
    """Garde-fou contre le message que je m'apprêtais à écrire : `frontend/`
    est servi par StaticFiles, qui ne filtre RIEN. Une image déposée à la main
    fonctionne donc parfaitement, et la dénoncer serait un faux positif. La
    liste blanche gouverne ce que l'IA a le droit de LIVRER, pas ce que le
    serveur rend."""
    front = _frontend(projet, **{"index.html": _page('<img src="photo.jpg">')})
    (front / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0 pas du texte")
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors


def test_une_archive_importee_perd_ses_images_et_le_smoke_test_le_dit(projet, tmp_path):
    """La voie où le défaut arrive VRAIMENT, éprouvée de bout en bout.

    `monl import` retire de l'archive tout ce qui n'est pas dans la liste
    blanche — sans un mot — puis vérifie. Avant cette brique, la page restait
    et réclamait une photo que l'import venait de jeter : import réussi, site
    troué. Le smoke test doit refuser."""
    import zipfile

    from monl.frontend_ai import import_and_verify

    archive = tmp_path / "site.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("index.html", _page('<img src="photo.jpg" alt="">'))
        z.writestr("photo.jpg", "�� pas du texte")
    ok, errors = import_and_verify(str(projet), str(archive), say=_quiet)
    assert not (projet / "frontend" / "photo.jpg").exists(), (
        "l'archive a conservé la photo : le scénario testé n'existe plus")
    assert not ok
    assert any("photo.jpg" in e for e in errors), errors


def test_une_reference_du_css_compte_aussi(projet):
    """Une image de fond ne vit pas dans le HTML. Ne lire que les pages
    laisserait passer la moitié des références d'un site réel."""
    _frontend(projet, **{
        "index.html": _page('<link rel="stylesheet" href="styles.css">'),
        "styles.css": "body { background: url('fond.png') no-repeat; }"})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert not ok
    assert any("fond.png" in e and "styles.css" in e for e in errors), errors


def test_une_reference_qui_sort_du_site_est_nommee(projet):
    _frontend(projet, **{"index.html": _page('<img src="../../secret.png">')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert not ok
    assert any("sort du site" in e for e in errors), errors


# ------------------------------------------------- les faux positifs interdits --
def test_ni_route_du_contrat_ni_navigation_ne_sont_denoncees(projet):
    """Le contrôle ne doit JAMAIS confondre un lien avec un fichier.

    `#/panier` est de la navigation (point 92, où le même avertissement avait
    dénoncé quatre routes correctes), `/item` est une route du contrat, et une
    ancre reste une ancre. Aucun des trois ne porte d'extension : c'est
    précisément ce qui les met hors de portée du contrôle."""
    _frontend(projet, **{"index.html": _page(
        '<a href="#/panier">Panier</a><a href="/item">Articles</a>'
        '<a href="#haut">Haut</a><a href="/">Accueil</a>')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors


def test_ni_url_absolue_ni_data_uri_ne_sont_traitees_comme_des_fichiers(projet):
    """Une URL distante n'est pas à nous : la demander au serveur éphémère
    produirait un 404 sur un site parfaitement correct. Le CDN, lui, a déjà
    son propre refus ailleurs — ce n'est pas à ce contrôle-ci de le doubler."""
    _frontend(projet, **{"index.html": _page(
        '<img src="https://exemple.com/a.png">'
        '<img src="//cdn.exemple.com/b.svg">'
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">'
        '<a href="mailto:contact@exemple.com">Écrire</a>')})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors


def test_une_reference_avec_parametre_de_version_est_resolue(projet):
    """`styles.css?v=3` est un usage courant pour forcer le cache. Le fichier
    existe : le dénoncer serait un faux positif."""
    _frontend(projet, **{
        "index.html": _page('<link rel="stylesheet" href="styles.css?v=3">'),
        "styles.css": "body { color: #111; }"})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors


def test_un_frontend_sans_aucune_reference_reste_vert(projet):
    """Le cas le plus simple, et le garde-fou contre un contrôle qui
    échouerait à vide."""
    _frontend(projet, **{"index.html": _page("<h1>Atelier</h1>")})
    ok, errors, _w = run_smoke_test(str(projet), say=_quiet)
    assert ok, errors
