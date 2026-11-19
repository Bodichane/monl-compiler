"""Coverage of the delivered frontend: the contract must become a real journey."""

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

SPEC_VISUAL = """app BoutiqueVisuelle

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
    spec.write_text(SPEC_VISUAL, encoding="utf-8")
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


def test_a_minimal_frontend_is_not_declared_successful(tmp_path):
    project, _contract = _project(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<script>fetch('/product?limit=200');</script>", encoding="utf-8")

    ok, errors, warnings = check_coherence(str(project))

    assert not ok
    message = "\n".join(errors + warnings)
    assert "Frontend coverage:" in message
    assert "workflow 'Commande'" in message
    assert "workflow 'Compte'" in message
    assert "POST /order" in message
    # The back office is not a promise of the public showcase: it is named, but
    # its absence does not refuse the build.
    assert any("Backoffice" in warning for warning in warnings)
    assert not any("workflow 'Backoffice'" in error for error in errors)


def test_a_frontend_covering_the_contract_routes_passes(tmp_path):
    project, contract = _project(tmp_path)
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        "<script src=\"app.js\"></script>", encoding="utf-8")
    (frontend / "app.js").write_text(
        _all_route_fetches(contract), encoding="utf-8")

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("Frontend coverage:" in warning for warning in warnings)
    assert not any("Missing frontend workflow:" in warning for warning in warnings)


def test_an_api_base_template_fetch_covers_the_right_route(tmp_path):
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


def test_an_auth_fetch_under_a_nonexistent_prefix_refuses_the_build(tmp_path):
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
    assert "REJECTED: fetch calls path /auth, which is absent from the contract" in message
    assert "/auth" in message
    assert "/login" in message and "/register" in message


def test_a_fetch_to_the_contracts_login_and_register_passes(tmp_path):
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


def test_a_navigation_link_does_not_trigger_the_fetch_check(tmp_path):
    project, contract = _project(tmp_path)
    _write_frontend(
        project,
        _all_route_fetches(contract) + "\nfunction aller(route) {}\naller('/panier');",
        '<a href="#/panier">Panier</a><script src="app.js"></script>',
    )

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("/panier" in message for message in errors + warnings)


def test_an_irreducible_fetch_path_triggers_nothing(tmp_path):
    project, contract = _project(tmp_path)
    _write_frontend(
        project,
        _all_route_fetches(contract) + "\nfetch(url, {method: 'GET'});",
    )

    ok, errors, warnings = check_coherence(str(project))

    assert ok, errors
    assert not any("REJECTED: fetch calls path" in message
                   for message in errors + warnings)


def test_the_brief_states_the_workflow_floor(tmp_path):
    project, _contract = _project(tmp_path)
    # Prose wrapped at 79 columns: compare on normalized whitespace.
    brief = " ".join(
        (project / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8").split())

    assert "WORKFLOW FLOOR" in brief
    assert "workflows declared by the spec" in brief
    assert "For EACH workflow" in brief
    assert "counts the routes called" in brief


def test_the_brief_forbids_local_images_outside_manifest_and_names_inline_svg(
        tmp_path):
    project, _contract = _project(tmp_path)
    # The instruction is PROSE: it rewraps with each review, and a test
    # requiring a precise line break would break on every reformatting without
    # any rule having moved. We therefore compare on normalized whitespace,
    # which leaves the meaning as the only invariant.
    brief = " ".join(
        (project / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8").split())

    assert "EXPLICIT BAN" in brief
    assert (
        "any local image file that is not listed by `ASSET_MANIFEST.json`"
    ) in brief
    assert "SVG INLINE in the HTML" in brief
    assert "OBLIGATION DE LIVRAISON" not in brief
    assert "generated_assets: []" not in brief


def test_the_brief_lists_markers_with_file_and_block(tmp_path):
    project, _contract = _visual_project(tmp_path)
    brief = (project / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    manifest_lines = (project / "docs/ASSET_MANIFEST.json").read_text(
        encoding="utf-8").splitlines()
    manifest = json.loads("\n".join(manifest_lines[1:]))
    markers = manifest["required_markers"]["index.html"]

    assert markers
    assert 'data-monl-section="panier"' in markers
    assert 'data-monl-media="product"' in markers
    assert "Required visual markers — exact file and block" in brief
    for marker in markers:
        assert (
            f"Exact file: `frontend/index.html` — exact marker: `{marker}` — "
            "exact block:"
        ) in brief


def test_a_project_without_markers_does_not_trigger_an_empty_visual_list(tmp_path):
    project, _contract = _project(tmp_path)
    brief = (project / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")

    assert "Marqueurs visuels obligatoires — fichier et bloc exacts" not in brief


# ---- The parameter must REACH the fetch, whatever the spelling (point 150) ----

FUNCTION_DIRECT = """
async function api(endpoint, options) {
  const response = await fetch(endpoint, options);
  return response.json();
}
api('/product?limit=100');
api('/order', {method: 'POST'});
"""

FUNCTION_TEMPLATE = """
const API_BASE = '';
async function api(endpoint, options) {
  const response = await fetch(`${API_BASE}${endpoint}`, options);
  return response.json();
}
api('/product?limit=100');
api('/order', {method: 'POST'});
"""

# The spelling REALLY produced by the model, and the one that led to "0 routes
# called" on a frontend that called five.
FUNCTION_BY_VARIABLE = """
const API_BASE = '';
async function api(endpoint, options = {}) {
  const config = { headers: {} , ...options };
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, config);
  return await response.json();
}
api('/product?limit=100');
api('/order', {method: 'POST'});
"""


def _calls(tmp_path, source, name="ecriture"):
    from monl.cli import _frontend_fetch_calls

    folder = tmp_path / name / "frontend"
    folder.mkdir(parents=True)
    (folder / "app.js").write_text(source, encoding="utf-8")
    return _frontend_fetch_calls(str(folder))


def test_the_three_spellings_of_an_access_function_are_seen(tmp_path):
    """The refusal fell on a CORRECT site, and the brief was the cause.

    It asks to factor the code — and that factoring is exactly what made the
    call invisible to the check. Measured with real spend: 12.8 KB of JavaScript
    calling five routes, counted as zero.
    """
    for name, source in (("directe", FUNCTION_DIRECT),
                        ("gabarit", FUNCTION_TEMPLATE),
                        ("variable", FUNCTION_BY_VARIABLE)):
        calls = _calls(tmp_path, source, name)
        assert ("GET", "/product") in calls, (name, calls)
        assert ("POST", "/order") in calls, (name, calls)


def test_a_function_not_passing_its_parameter_is_not_an_api(tmp_path):
    """The check stays conservative: it requires a DEMONSTRABLE flow.

    Without this counter-proof, any function containing a `fetch` somewhere
    would have its arguments counted as routes — and coverage would become a
    check that refuses nothing any more.
    """
    source = """
    function journaliser(message, options) {
      fetch('/telemetrie', {method: 'POST', body: message});
    }
    journaliser('/product', {method: 'GET'});
    """

    calls = _calls(tmp_path, source, "sans-flux")

    assert ("GET", "/product") not in calls, (
        "an ordinary function argument was taken for a called route")
