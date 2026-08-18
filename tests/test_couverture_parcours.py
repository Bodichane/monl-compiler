"""Couverture du frontend livré : le contrat doit devenir un parcours réel."""

import json

from monl.cli import check_coherence, compile_project

SPEC = """app BoutiqueCouverture

entity Product
    label: String

entity Customer
    email: String

entity Order
    label: String

actor Customer selfRegister
actor Admin

rule Product.Read public

workflow Catalogue for Customer
    Read Product

workflow Compte for Customer
    Create Customer
    Read Customer

workflow Commande for Customer
    Create Order
    Read Order
    Update Order
    Delete Order

workflow Backoffice for Admin
    Create Product
    Read Product
    Update Product
    Delete Product
"""

SPEC_VISUELLE = """app BoutiqueVisuelle

entity Product
    title: String
    price: Money
    image: Image

actor Visitor

rule Product.Read public

workflow Catalogue for Visitor
    Read Product

landing
    brief: "Une boutique visuelle qui présente ses pièces avec soin."
    section "Notre matière": "Chaque pièce naît d'un geste lent et précis."
"""


def _project(tmp_path):
    project = tmp_path / "boutique"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    contract = compile_project(str(spec), str(project))
    return project, contract


def _visual_project(tmp_path):
    project = tmp_path / "boutique-visuelle"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC_VISUELLE, encoding="utf-8")
    contract = compile_project(str(spec), str(project))
    return project, contract


def _all_route_fetches(contract, template=False):
    lines = ["const API_BASE = '';", "const id = 1;"]
    for route in contract["routes"]:
        if route["path"] == "/paiement/webhook":
            continue
        path = route["path"].replace("{id}", "${id}")
        if template:
            expression = f"`${{API_BASE}}{path}`"
        else:
            expression = json.dumps(path.replace("${id}", "1"))
        lines.append(f"fetch({expression}, {{method: '{route['method']}'}});")
    return "\n".join(lines)


def test_un_frontend_minimal_n_est_pas_declare_reussi(tmp_path):
    project, _contract = _project(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<script>fetch('/product?limit=200');</script>", encoding="utf-8")

    ok, errors, warnings = check_coherence(str(project))

    assert not ok
    message = "\n".join(errors + warnings)
    assert "Couverture frontend" in message
    assert "workflow 'Commande'" in message
    assert "workflow 'Compte'" in message
    assert "POST /order" in message
    # Le back-office n'est pas une promesse de la vitrine publique : il est
    # nommé, mais son absence ne refuse pas la construction.
    assert any("Backoffice" in warning for warning in warnings)
    assert not any("workflow 'Backoffice'" in error for error in errors)


def test_un_frontend_qui_couvre_les_routes_du_contrat_passe(tmp_path):
    project, contract = _project(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<script src=\"app.js\"></script>", encoding="utf-8")
    (frontend / "app.js").write_text(
        _all_route_fetches(contract), encoding="utf-8")

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("Couverture frontend" in warning for warning in warnings)
    assert not any("Parcours frontend manquant" in warning for warning in warnings)


def test_un_fetch_par_gabarit_api_base_couvre_la_bonne_route(tmp_path):
    project, contract = _project(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<script src=\"app.js\"></script>", encoding="utf-8")
    (frontend / "app.js").write_text(
        _all_route_fetches(contract, template=True), encoding="utf-8")

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("POST /order" in message
                   for message in errors + warnings)


def _write_frontend(project, app_js, index_html='<script src="app.js"></script>'):
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(index_html, encoding="utf-8")
    (frontend / "app.js").write_text(app_js, encoding="utf-8")


def test_un_fetch_auth_sous_un_prefixe_inexistant_refuse_la_construction(tmp_path):
    project, contract = _project(tmp_path)
    app_js = _all_route_fetches(contract) + """
async function authenticate(action) {
    return fetch(`/auth/${action === 'login' ? 'login' : 'register'}`, {
        method: 'POST'
    });
}
"""
    _write_frontend(project, app_js)

    ok, errors, _warnings = check_coherence(str(project))

    assert not ok
    message = "\n".join(errors)
    assert "REFUSÉ" in message
    assert "/auth" in message
    assert "/login" in message and "/register" in message


def test_un_fetch_vers_login_et_register_du_contrat_passe(tmp_path):
    project, contract = _project(tmp_path)
    app_js = _all_route_fetches(contract) + """
fetch('/login', {method: 'POST'});
fetch('/register', {method: 'POST'});
"""
    _write_frontend(project, app_js)

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("/login" in message or "/register" in message
                   for message in errors + warnings)


def test_un_lien_de_navigation_ne_declenche_pas_le_controle_fetch(tmp_path):
    project, contract = _project(tmp_path)
    _write_frontend(
        project,
        _all_route_fetches(contract) + "\nfunction aller(route) {}\naller('/panier');",
        '<a href="#/panier">Panier</a><script src="app.js"></script>',
    )

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("/panier" in message for message in errors + warnings)


def test_un_chemin_fetch_irreductible_ne_declenche_rien(tmp_path):
    project, contract = _project(tmp_path)
    _write_frontend(
        project,
        _all_route_fetches(contract) + "\nfetch(url, {method: 'GET'});",
    )

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("REFUSÉ" in message for message in errors + warnings)


def test_le_brief_enonce_le_plancher_des_workflows(tmp_path):
    project, _contract = _project(tmp_path)
    brief = (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")

    assert "PLANCHER DE PARCOURS" in brief
    assert "workflows déclarés par la spec" in brief
    assert "Pour CHAQUE workflow" in brief
    assert "compte les routes appelées" in brief


def test_le_brief_interdit_les_images_locales_hors_manifeste_et_nomme_svg_en_ligne(
        tmp_path):
    project, _contract = _project(tmp_path)
    # La consigne est de la PROSE : elle se replie au fil des relectures, et un
    # test qui exige une coupure de ligne précise casserait à chaque
    # reformatage sans qu'aucune règle n'ait bougé. On compare donc sur les
    # espaces normalisés, ce qui laisse le sens comme seul invariant.
    brief = " ".join(
        (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8").split())

    assert "INTERDICTION EXPLICITE" in brief
    assert (
        "aucun fichier image local qui n'est pas listé par `ASSET_MANIFEST.json`"
    ) in brief
    assert "SVG EN LIGNE dans le HTML" in brief
    assert "OBLIGATION DE LIVRAISON" not in brief
    assert "generated_assets: []" not in brief


def test_le_brief_enumere_les_marqueurs_avec_fichier_et_bloc(tmp_path):
    project, _contract = _visual_project(tmp_path)
    brief = (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    manifest_lines = (project / "ASSET_MANIFEST.json").read_text(
        encoding="utf-8").splitlines()
    manifest = json.loads("\n".join(manifest_lines[1:]))
    markers = manifest["required_markers"]["index.html"]

    assert markers
    assert 'data-monl-section="panier"' in markers
    assert 'data-monl-media="product"' in markers
    assert "Marqueurs visuels obligatoires — fichier et bloc exacts" in brief
    for marker in markers:
        assert (
            f"Fichier exact : `frontend/index.html` — marqueur exact : `{marker}` — "
            "bloc exact :"
        ) in brief


def test_un_projet_sans_marqueur_ne_declenche_pas_une_liste_visuelle_vide(tmp_path):
    project, _contract = _project(tmp_path)
    brief = (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")

    assert "Marqueurs visuels obligatoires — fichier et bloc exacts" not in brief
