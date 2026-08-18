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


def _project(tmp_path):
    project = tmp_path / "boutique"
    project.mkdir()
    spec = project / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
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


def test_le_brief_enonce_le_plancher_des_workflows(tmp_path):
    project, _contract = _project(tmp_path)
    brief = (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")

    assert "PLANCHER DE PARCOURS" in brief
    assert "workflows déclarés par la spec" in brief
    assert "Pour CHAQUE workflow" in brief
    assert "compte les routes appelées" in brief


def test_le_brief_impose_de_livrer_les_ressources_locales_referencees(tmp_path):
    project, _contract = _project(tmp_path)
    # La consigne est de la PROSE : elle se replie au fil des relectures, et un
    # test qui exige une coupure de ligne précise casserait à chaque
    # reformatage sans qu'aucune règle n'ait bougé. On compare donc sur les
    # espaces normalisés, ce qui laisse le sens comme seul invariant.
    brief = " ".join(
        (project / "FRONTEND_PROMPT.md").read_text(encoding="utf-8").split())

    assert (
        "OBLIGATION DE LIVRAISON : toute ressource locale référencée doit être "
        "livrée dans cette construction, sous le chemin exact référencé"
    ) in brief
    assert "chaque `.svg` planifié par le manifeste" in brief
    assert "écrit EN LIGNE plutôt que référencé" in brief
