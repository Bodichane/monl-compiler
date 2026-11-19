# Tests of the orchestrator (pivot, bricks 2-3): frontend contract, monl run
# (consistency) and monl update (delta). The central test checks that the
# contract CANNOT diverge from the API: each contract route is confronted with
# the decorators really written in app.py.
import ast
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from monl.cli import (
    _contract_signature,
    _load_state,
    _rapporter_delta,
    check_coherence,
    compile_project,
)
from monl.dialogue_engine import GuidedDialogue

REPO = os.path.join(os.path.dirname(__file__), "..")

SPEC = """app ContractTest

entity Item
    label: String
    price: Money

entity Note
    body: Text

# The administration role is provisioned offline: these tests are about the
# contract's consistency, not a showcase promising a back office.
actor Admin

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item

workflow ManageNote for Admin
    Create Note
    Read Note
"""


def _fresh_project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    spec_path = proj / "spec.ml"
    spec_path.write_text(SPEC, encoding="utf-8")
    contract = compile_project(str(spec_path), str(proj))
    return proj, spec_path, contract


def test_delta_reports_a_changed_field_type(tmp_path, capsys):
    ancienne = {
        "routes": [],
        "entities": {"Note": {"fields": [{"name": "priority", "type": "String"}]}},
    }
    nouvelle = {
        "routes": [],
        "entities": {"Note": {"fields": [{"name": "priority", "type": "Integer"}]}},
    }

    assert _rapporter_delta(
        _contract_signature(ancienne),
        _contract_signature(nouvelle),
        str(tmp_path),
        ecrire_brief=False,
    )
    assert "field type changed: Note.priority: String → Integer" in capsys.readouterr().out


def test_express_brief_allows_texts_blocks_and_local_raster_images(tmp_path):
    answers = iter(["1", "StudioExpress", "Portfolio de céramique contemporaine."])
    spec_text = GuidedDialogue(
        ask=lambda prompt: next(answers), express=True).run()
    proj = tmp_path / "express"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(spec_text, encoding="utf-8")
    compile_project(str(spec), str(proj))
    prompt = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Express mode" in prompt
    assert "page dense with genuinely useful blocks" in prompt
    # Explicit reversal: the text can organize the page, but an image's bytes
    # are now produced by the image provider and written into assets/ before
    # the text model is called.
    assert "raster images" in prompt
    assert "do not try to produce its bytes" in " ".join(prompt.split())
    assert "illustrations `.svg` originales" not in prompt
    assert "original `.svg` illustrations" not in prompt
    assert "Never fabricate in the browser fake products" in prompt


def test_contract_matches_the_real_routes_of_app_py(tmp_path):
    proj, _spec, contract = _fresh_project(tmp_path)
    app_code = (proj / "app.py").read_text(encoding="utf-8")
    real_routes = set()
    for m in re.finditer(r"@app\.(get|post|put|delete)\('([^']+)'", app_code):
        real_routes.add((m.group(1).upper(), m.group(2)))
    # Routes outside the business contract's scope (systematic auth + pages).
    infra = {("POST", "/register"), ("POST", "/login"), ("POST", "/logout"),
             ("GET", "/"), ("GET", "/health"), ("GET", "/health/ready")}
    contract_routes = {(r["method"], r["path"]) for r in contract["routes"]}
    assert contract_routes == real_routes - infra, (
        "the frontend contract diverged from the really generated routes")


def test_contract_imposes_same_origin_never_a_hard_coded_port(tmp_path):
    """Regression (point 51): the contract announced 'http://127.0.0.1:8000' and
    the brief made it an order. An obedient AI therefore produced a frontend
    calling 8000 no matter what — broken under 'monl run --port', and failed by the
    smoke test (ephemeral port) for having followed the contract. The frontend
    being served on /site by the API server, the only correct base is the page's
    origin."""
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["api"]["base_url"] == ""
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    absolue = re.findall(r"`https?://[^`]+`", brief)
    assert not absolue, f"the brief still imposes an absolute URL: {absolue}"
    assert "RELATIVE" in brief


def test_contract_fields_mark_required(tmp_path):
    """POINT 91: this test encoded the LIE. It required the contract to copy the
    spec's `rule X.y required` — while the generated Pydantic schemas make EVERY
    input field mandatory, declared or not (point 85: "required stays an
    assertion, the schemas already make every field mandatory").

    A frontend faithful to the contract therefore omitted undeclared fields and
    collected a 422. Seen for real on `projets/SneakerLab`: adding `email` and
    `address` to the customer record broke a running site's form, while the
    contract announced them optional.

    The witness is below: `app.py` must require BOTH."""
    proj, _spec, contract = _fresh_project(tmp_path)
    fields = {f["name"]: f for f in contract["entities"]["Item"]["fields"]}
    assert fields["label"]["required"] is True
    assert fields["price"]["required"] is True, "not declared, and yet required"

    genere = (proj / "app.py").read_text(encoding="utf-8")
    schema = genere.split("class ItemSchema(BaseModel):")[1].split("class ")[0]
    for champ in ("label", "price"):
        ligne = next(li for li in schema.splitlines() if li.strip().startswith(champ))
        assert "Optional" not in ligne and "= None" not in ligne, ligne

    # Item.Read is public, Note.Read is not.
    auth = {(r["path"], r["method"]): r["auth_required"] for r in contract["routes"]}
    assert auth[("/item", "GET")] is False
    assert auth[("/note", "GET")] is True


def test_run_check_detects_modified_spec_and_edited_contract(tmp_path):
    proj, spec_path, _ = _fresh_project(tmp_path)
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors

    # 1. spec modified without update -> explicit error
    spec_path.write_text(SPEC + "\n# commentaire ajouté\n", encoding="utf-8")
    ok, errors, _w = check_coherence(str(proj))
    assert not ok and any("monl update" in e for e in errors)

    # resynchronization by update -> consistent again
    compile_project(str(spec_path), str(proj))
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors

    # 2. contract edited by hand -> explicit error
    contract_path = proj / "frontend_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["app"] = "Falsifié"
    contract_path.write_text(json.dumps(data), encoding="utf-8")
    ok, errors, _w = check_coherence(str(proj))
    assert not ok and any("modified manually" in e for e in errors)


def test_run_check_reports_an_artifact_from_an_earlier_compiler(tmp_path):
    """Point 81. The consistency checks compared against the fingerprints
    RECORDED at compile time: they detected a hand edit — their purpose — and let
    through a project whose artifacts came from an earlier compiler. 'monl run'
    then announced "consistency checked" on a backend the current compiler would
    no longer write, including after a fix had closed a hole.

    Found on a real project (`projets/SneakerLab`): its contract lacked point
    81's `PUT` note and the check showed ✅. A version number would have seen
    nothing — `__version__` did not move during points 74 to 81 — hence the
    comparison with a regeneration.

    The simulation is faithful: the contract on disk is modified AND its recorded
    fingerprint updated, which is exactly the state an earlier compiler would have
    left (consistent with itself, diverging from the current compiler). Without
    the fingerprint update, the hand-edit check would answer, and the test would
    prove nothing."""
    proj, _spec, _c = _fresh_project(tmp_path)
    ok, _errors, warnings = check_coherence(str(proj))
    assert ok
    assert not any("Artifacts produced by an earlier compiler" in w for w in warnings)

    contract_path = proj / "frontend_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["monl_contract_version"] = 1  # what a compiler of the time wrote
    contract_path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                        sort_keys=True), encoding="utf-8")
    state_path = proj / "monl.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["contract_sha256"] = hashlib.sha256(
        contract_path.read_bytes()).hexdigest()
    state_path.write_text(json.dumps(state), encoding="utf-8")

    ok, errors, warnings = check_coherence(str(proj))
    # A warning, not an error: blocking 'monl run' would immobilize every
    # application after any compiler change, including those not concerning it.
    # Same arbitration as for the state preceding the backend seal.
    assert ok, errors
    perimes = [w for w in warnings
               if "Artifacts produced by an earlier compiler" in w]
    assert perimes, warnings
    # The warning must NAME the artifact and the resynchronizing command:
    # otherwise it would not be actionable.
    assert "frontend_contract.json" in perimes[0]
    assert "monl update" in perimes[0]
    # ... and must not accuse the artifacts that are up to date.
    assert "app.py" not in perimes[0]

    # Resynchronization lifts the warning.
    compile_project(str(_spec), str(proj))
    ok, errors, warnings = check_coherence(str(proj))
    assert ok, errors
    assert not any("Artifacts produced by an earlier compiler" in w
                   for w in warnings)


def test_out_of_contract_frontend_triggers_warning(tmp_path):
    proj, _spec, _c = _fresh_project(tmp_path)
    front = proj / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        "<script>fetch('/item?limit=3'); fetch('/fantome/1');</script>",
        encoding="utf-8")
    ok, errors, warnings = check_coherence(str(proj))
    # Reversal made necessary by the requested check: a path passed to fetch is
    # no longer only a warning, since it can target nothing.
    assert not ok
    assert any("/fantome" in error for error in errors)
    assert any("/fantome" in w for w in warnings)
    # The new check can name /item in its coverage count; this test is only
    # about the old unknown-path warning.
    assert not any("paths missing from the contract" in w and "/item" in w
                   for w in warnings)


def test_navigation_routes_do_not_trigger_the_warning(tmp_path):
    """POINT 92: on `projets/SneakerLab`, the warning denounced `/admin`,
    `/catalogue`, `/commandes` and `/compte` — four NAVIGATION routes of a
    single-page application, no defect. A warning crying wolf on a correct site
    teaches people to stop reading warnings; sharpening it was better than
    removing it.

    The proof lives in the file: `#/catalogue` declares the client-side route, so
    `aller('/catalogue')` is not an API call. The witness is in the same file — a
    real mistyped path never appears behind a hash, and stays reported."""
    proj, _spec, _c = _fresh_project(tmp_path)
    front = proj / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        "<a href=\"#/catalogue\">Catalogue</a>"
        "<script>function aller(r){}; aller('/catalogue');"
        " fetch('/item');</script>",
        encoding="utf-8")
    ok, errors, warnings = check_coherence(str(proj))
    assert ok, errors
    assert not any("/catalogue" in w for w in warnings), warnings
    # `/fantome` is now the refusal case above; this test's witness is
    # deliberately only a `#/catalogue` navigation.


def test_update_reports_the_contract_delta(tmp_path):
    proj, spec_path, contract_v1 = _fresh_project(tmp_path)
    routes_v1 = {f"{r['method']} {r['path']}" for r in contract_v1["routes"]}

    # Evolution: a field on Item and the Delete action on Note.
    evolved = SPEC.replace("    price: Money", "    price: Money\n    stock: Integer")
    evolved = evolved.replace("    Read Note", "    Read Note\n    Delete Note")
    spec_path.write_text(evolved, encoding="utf-8")
    contract_v2 = compile_project(str(spec_path), str(proj))

    routes_v2 = {f"{r['method']} {r['path']}" for r in contract_v2["routes"]}
    fields_v2 = {f["name"] for f in contract_v2["entities"]["Item"]["fields"]}
    assert "DELETE /note/{id}" in routes_v2 - routes_v1
    assert "stock" in fields_v2
    # The recorded state follows the new spec (run becomes consistent again).
    state = _load_state(str(proj))
    assert state["spec"] == "spec.ml"
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors


# ---- Field roles and archetypes (point 54) ----

SPEC_ARCHETYPES = """app Formes

entity Project
    title: String
    description: Text
    imageUrl: String
    category: String

entity Product
    label: String
    price: Money

entity Shot
    coverUrl: String
    legend: Text

entity Entry
    name: String
    score: Integer

entity Message
    author: String
    content: Text

actor Admin selfRegister

rule Project.Read public
rule Product.Read public
rule Shot.Read public
rule Entry.Read public

workflow Gerer for Admin
    Create Project
    Read Project
    Create Product
    Read Product
    Create Shot
    Read Shot
    Create Entry
    Read Entry
    Create Message
    Read Message
"""


def _archetypes_contract(tmp_path):
    proj = tmp_path / "formes"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_ARCHETYPES, encoding="utf-8")
    return compile_project(str(spec), str(proj))


def test_archetype_derived_from_the_spec(tmp_path):
    """Restoring, in the contract, what the pivot had removed with the generated
    frontend (points 35 then 54). Without it, the AI only gets a list of {name,
    type} and must guess everything again."""
    c = _archetypes_contract(tmp_path)
    formes = {e: s["archetype"] for e, s in c["entities"].items()}
    assert formes["Project"] == "gallery"      # media + title + description
    assert formes["Product"] == "shop"         # un Money l'emporte
    assert formes["Shot"] == "gallery"         # media alone: intended gap / point 35
    assert formes["Entry"] == "list"           # nothing to show
    # Readable but NOT public: an internal collection is managed, not browsed —
    # a real defect of the 1st version, which advised a gallery for a contact
    # form.
    assert formes["Message"] == "list"


def test_field_roles_derived_and_never_on_a_hidden_field(tmp_path):
    c = _archetypes_contract(tmp_path)
    roles = {f["name"]: f["role"] for f in c["entities"]["Project"]["fields"]}
    assert roles == {"title": "title", "description": "description",
                     "imageUrl": "media", "category": "category"}
    # The title is never the URL, even when it is the first declared String:
    # displaying a URL as a name is a real defect.
    shot = {f["name"]: f["role"] for f in c["entities"]["Shot"]["fields"]}
    assert shot["coverUrl"] == "media" and shot["legend"] == "description"


def test_the_brief_passes_on_the_advised_form(tmp_path):
    """A role computed but absent from the brief would serve nobody."""
    proj = tmp_path / "formes"
    _archetypes_contract(tmp_path)
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Suggested form: gallery" in brief
    assert "Suggested form: shop" in brief
    assert "MEDIA" in brief and "TITLE" in brief


# ---- Editorial content goes through to the brief (point 55) ----

SPEC_EDITORIALE = SPEC + """
landing
    brief: "vitrine de démonstration"
    section "À propos": "Atelier fondé en 2015, spécialisé dans la pièce unique."
"""


def test_contenu_editorial_transmis_tel_quel(tmp_path):
    proj = tmp_path / "edito"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_EDITORIALE, encoding="utf-8")
    contract = compile_project(str(spec), str(proj))

    assert contract["sections"] == [
        {"title": "À propos",
         "body": "Atelier fondé en 2015, spécialisé dans la pièce unique."}]
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    # The text must arrive INTACT: it is content, not a style instruction the
    # AI could rephrase.
    assert "Atelier fondé en 2015, spécialisé dans la pièce unique." in brief
    assert "publish as is" in brief


def test_without_section_no_editorial_block_in_the_brief(tmp_path):
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["sections"] == []
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Contenu éditorial" not in brief


# ---- The announced body is what the backend requires (point 57) ----

SPEC_DEUX_PARENTS = """app Blog

entity Article
    title: String

entity Comment
    content: Text

entity Reader
    displayName: String

relation Article hasMany Comment
relation Reader hasMany Comment

actor Author
actor Reader selfRegister

rule Article.Read public
rule Comment.Read public
rule Comment.Update ownedBy Reader
rule Comment.Delete ownedBy Reader

workflow RedigerArticle for Author
    Create Article
    Read Article

workflow Commenter for Reader
    Create Comment
    Read Comment
    Update Comment
    Delete Comment

workflow GererReader for Reader
    Create Reader
    Read Reader
"""


def _schemas_pydantic(app_code):
    """Pydantic schema fields and their uses on the FastAPI routes."""
    tree = ast.parse(app_code)
    class_fields = {
        node.name: [
            child.target.id for child in node.body
            if isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
        ]
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    schemas = {name: fields for name, fields in class_fields.items()
               if name.endswith("Schema")}
    classes = set(class_fields)
    routes = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                continue
            if decorator.func.attr not in ("post", "put") or not decorator.args:
                continue
            if not isinstance(decorator.args[0], ast.Constant):
                continue
            model = next((arg.annotation.id for arg in node.args.args
                          if isinstance(arg.annotation, ast.Name)
                          and arg.annotation.id in classes), None)
            routes[(decorator.func.attr.upper(), decorator.args[0].value)] = (
                class_fields[model] if model is not None else [])
    return schemas, routes


def test_the_announced_body_is_the_one_the_backend_requires(tmp_path):
    """The contract announced `POST /comment` with only the `content` field while
    the backend also required `article_id`: every frontend faithful to the
    contract collected a 422. A contract badly describing what to send is worse
    than a mute one — one believes one followed it."""
    racine = os.path.dirname(os.path.dirname(__file__))
    specs = [*(Path(racine) / "exemples").glob("*.ml"),
             Path(racine) / "demo/spec.ml"]
    specs.append(None)  # historical witness with two parents, independent of the examples
    total = 0
    ecarts = []
    for index, source in enumerate(specs):
        proj = tmp_path / f"projet_{index}"
        proj.mkdir()
        spec = proj / "spec.ml"
        spec.write_text(SPEC_DEUX_PARENTS if source is None else
                        source.read_text(encoding="utf-8"), encoding="utf-8")
        if source is not None and (source.parent / "assets").is_dir():
            shutil.copytree(source.parent / "assets", proj / "assets")
        contract = compile_project(str(spec), str(proj))
        schemas, routes_app = _schemas_pydantic(
            (proj / "app.py").read_text(encoding="utf-8"))
        for route in contract["routes"]:
            if route["method"] not in ("POST", "PUT"):
                continue
            total += 1
            attendu = routes_app.get((route["method"], route["path"]))
            annonces = route.get("request_fields")
            ident = f"{route['method']} {route['path']} ({source or 'témoin blog'})"
            if attendu is None:
                ecarts.append(f"{ident}: aucune route POST/PUT AST correspondante")
                continue
            manquants = sorted(set(attendu) - set(annonces or []))
            superflus = sorted(set(annonces or []) - set(attendu))
            if manquants or superflus:
                ecarts.append(f"{ident}: exigés non annoncés={manquants}, "
                              f"annoncés non acceptés={superflus}")
    assert total >= 1, "non-vacuity: no POST/PUT route compared"
    assert total >= 39, f"non-vacuity: only {total} routes compared (39 measured)"
    assert schemas, "non-vacuity: no Pydantic schema extracted by AST"
    assert not ecarts, "\n".join(ecarts)

    # The precise case that made the real generation fail: the NON-owner parent
    # must be asked of the client (the owner is filled from the JWT and must
    # above all not be sent).
    creation = next(r for r in contract["routes"]
                    if r["entity"] == "Comment" and r["method"] == "POST")
    assert "article_id" in creation["request_fields"]
    assert "reader_id" not in creation["request_fields"]


def test_the_brief_announces_the_expected_body(tmp_path):
    """A field required but absent from the brief cannot be guessed: the AI does
    not read the contract's JSON, it reads this document."""
    proj = tmp_path / "blog"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_DEUX_PARENTS, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "body: `{content, article_id}`" in brief


def test_a_navigation_route_is_not_an_out_of_contract_path(tmp_path):
    """Real false positive: `'/edit">Modifier</a>'` is the end of a
    `#/article/<id>/edit` route cut by a concatenation. Every single-page
    application produces some; warning on it discredits the real signals."""
    proj, _spec, _c = _fresh_project(tmp_path)
    front = proj / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        "<script>fetch('/item?limit=3');"
        "var h = '<a href=\"#/item/' + id + '/edit\">Modifier</a>';"
        "</script>", encoding="utf-8")
    ok, errors, warnings = check_coherence(str(proj))
    assert ok, errors
    assert not any("/edit" in w for w in warnings), warnings


def test_editorial_content_is_required_on_the_home_page(tmp_path):
    """Observed defect: the "about" was rendered on a separate page
    (`#/apropos`), reachable only from the menu. A visitor opening only the home
    page never saw it — for an "about", that misses its reason for being. Nothing
    in the contract said WHERE this text should live."""
    proj = tmp_path / "edito"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_EDITORIALE, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "home page, not only behind a link" in brief
    # A long text keeps the right to have its own page AS WELL.
    assert "continue on its own page" in brief


def test_the_brief_gives_the_anatomy_and_the_neighbors(tmp_path):
    """The contract said which DATA exists, never what a visitor expects to find
    on a page of this kind (point 60). Two sites of the same genre look alike
    because they meet the same expectations: naming them gives the model a
    reference point, where the mere list of fields left it improvising."""
    proj = tmp_path / "formes"
    _archetypes_contract(tmp_path)
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Close to:" in brief
    assert "What a visitor expects to find there" in brief
    # Each form brings its own expectations, never a single list.
    assert "price and availability visible without scrolling" in brief   # shop
    assert "a dominant visual" in brief                                 # gallery


def test_availability_is_not_secondary_data(tmp_path):
    """`stock` got the "meta" role, hence treated as a detail, while availability
    is a product page essential on the same level as price (point 60)."""
    proj = tmp_path / "shop"
    proj.mkdir()
    (proj / "spec.ml").write_text("""app Boutique

entity Product
    name: String
    price: Money
    stock: Integer

actor Admin selfRegister
rule Product.Read public

workflow W for Admin
    Create Product
    Read Product
""", encoding="utf-8")
    contract = compile_project(str(proj / "spec.ml"), str(proj))
    roles = {f["name"]: f["role"] for f in contract["entities"]["Product"]["fields"]}
    assert roles["stock"] == "stock"
    assert "AVAILABILITY" in (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")


# ------------------------------------------- paiement (point 74) ------------
SPEC_PAYABLE = """app Boutique

entity Client
    nom: String

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
    quantite: Integer
    total: Money

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

# Since point 79, `payable` requires a server-calculated amount: the creator of
# an order becomes its owner, hence the payer.
rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
"""


def _payable_project(tmp_path):
    proj = tmp_path / "boutique"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PAYABLE, encoding="utf-8")
    return proj, compile_project(str(proj / "spec.ml"), str(proj))


def test_the_payment_routes_are_in_the_contract(tmp_path):
    """The `payable` brick's two routes are not born from a workflow: they
    therefore escape `_compute_route_map`, and the contract ignored them. Concrete
    consequence, not theoretical: the interface AI could not draw the payment
    button — the contract otherwise forbids it to call a path absent from
    `routes`. A brick the contract does not describe is a brick without an
    interface.

    The test is the non-divergence one, applied to a payable spec: it is not the
    presence of the two paths that is checked, but equality with the decorators
    really written in app.py."""
    proj, contract = _payable_project(tmp_path)
    app_code = (proj / "app.py").read_text(encoding="utf-8")
    real_routes = {(m.group(1).upper(), m.group(2)) for m in
                   re.finditer(r"@app\.(get|post|put|delete)\('([^']+)'", app_code)}
    infra = {("POST", "/register"), ("POST", "/login"), ("POST", "/logout"),
             ("GET", "/"), ("GET", "/health"), ("GET", "/health/ready")}
    contract_routes = {(r["method"], r["path"]) for r in contract["routes"]}
    assert contract_routes == real_routes - infra
    assert ("POST", "/commande/{id}/paiement") in contract_routes
    assert ("POST", "/paiement/webhook") in contract_routes


def test_the_brief_says_how_to_pay_and_not_to_call_the_webhook(tmp_path):
    """The AI does not read the contract's JSON, it reads the brief. A route
    listed without its procedure — no body, redirect to `url` — is hard to guess;
    and the webhook must be explicitly ruled out, otherwise a conscientious
    interface will try to notify it itself."""
    proj, _contract = _payable_project(tmp_path)
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "POST /commande/{id}/paiement" in brief
    assert "NO body" in brief and "montant_centimes" in brief
    assert "never by the frontend" in brief
    # And not only in the route inventory: payment is the only frontend journey
    # where an error costs money, it appears in the non-negotiable rules, which
    # the AI reads before the list.
    regles = brief.split("## Entities")[0].split("## Non-negotiable rules")[1]
    assert "with no body at all" in regles
    assert "NEVER call `POST /paiement/webhook`" in regles


def test_without_payable_the_brief_never_mentions_payment(tmp_path):
    """The witness: a rule absent from the spec must leave no trace in the brief.
    A payment instruction on a portfolio would send the AI building a button
    without a route."""
    proj, _spec, _contract = _fresh_project(tmp_path)
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "paiement" not in brief.lower()


def test_the_tracking_columns_are_not_announced_as_input(tmp_path):
    """`payment_status` and `payment_ref` belong to the server. The contract must
    not include them in the creation body: a faithful frontend would send them,
    and believe it could decide itself that an order is paid."""
    _proj, contract = _payable_project(tmp_path)
    creation = next(r for r in contract["routes"]
                    if r["method"] == "POST" and r["path"] == "/commande")
    # The witness is `quantite`: since point 79, `total` is CALCULATED by the
    # server, hence absent from input too. One is needed, otherwise an empty
    # `request_fields` would pass this test.
    assert "quantite" in creation["request_fields"]
    for reserve in ("total", "payment_status", "payment_ref"):
        assert reserve not in creation["request_fields"], reserve


# ------------------------------------- payment tracking (point 76) -----------

def _order_fields(contract):
    return {f["name"]: f for f in contract["entities"]["Commande"]["fields"]}


def test_the_tracking_columns_are_declared_as_output(tmp_path):
    """The symmetric of the previous test, and the hole it left open: the
    contract was not to announce these fields AS INPUT, but it announced them
    nowhere — while the backend returns them (`SELECT *`) on every read. An
    interface AI faithful to the contract therefore could not know they exist,
    nor show a payment's outcome: the button could be drawn, its result not."""
    _proj, contract = _payable_project(tmp_path)
    champs = _order_fields(contract)
    for colonne in ("payment_status", "payment_ref"):
        assert colonne in champs, f"{colonne} missing from the contract"
        assert champs[colonne]["server_generated"] is True
        assert champs[colonne]["payment_tracking"] is True
        assert champs[colonne]["hidden_in_reads"] is False


def test_the_tracking_columns_steal_no_layout_role(tmp_path):
    """Roles (point 35) drive the layout, and "meta" has only three slots.
    Passing these two columns to role assignment gave them two, hence displayed
    them as any secondary information — evicting real spec fields. They have no
    role, and the declared fields keep theirs."""
    _proj, contract = _payable_project(tmp_path)
    champs = _order_fields(contract)
    assert champs["payment_status"]["role"] is None
    assert champs["payment_ref"]["role"] is None
    # The spec's fields do not move, nor the form deduced from the entity.
    assert champs["libelle"]["role"] == "title"
    assert champs["total"]["role"] == "price"
    assert contract["entities"]["Commande"]["archetype"] == "list"


def test_the_brief_explains_each_tracking_column_distinctly(tmp_path):
    """The AI reads the brief, not the JSON. And an explanation shared by both
    columns announced "'en_attente' / 'payee'" for `payment_ref`, which contains
    a session reference: a defect seen by rereading the produced brief, not the
    code. Each column says what it carries."""
    proj, contract = _payable_project(tmp_path)
    champs = _order_fields(contract)
    assert champs["payment_status"]["note"] != champs["payment_ref"]["note"]
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    # The values to compare are written: without them, the AI guesses 'paid'.
    assert "'en_attente'" in brief and "'payee'" in brief
    for colonne in ("payment_status", "payment_ref"):
        assert f"`{colonne}: String`" in brief
    # The procedure is attached to the ROUTE too: knowing how to open a payment
    # does not say how to show its outcome.
    assert "payment_status" in next(
        r["note"] for r in contract["routes"]
        if r["path"] == "/commande/{id}/paiement")


def test_without_payable_no_tracking_column_in_the_contract(tmp_path):
    """The witness: these fields do not exist in the database without `payable`.
    Declaring them anyway would send the AI reading an always absent field."""
    _proj, _spec, contract = _fresh_project(tmp_path)
    for spec_entite in contract["entities"].values():
        noms = {f["name"] for f in spec_entite["fields"]}
        assert not (noms & {"payment_status", "payment_ref"})


# --------------------------------------------------------------------------
# POINT 88: foreign keys, confronted with the schema REALLY written
# --------------------------------------------------------------------------

SPEC_COMPTES = """app DeuxSortesDeCle

entity Commande
    statut: String

entity Article
    nom: String

entity Ligne
    quantite: Integer

entity Client
    nom: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Commande.statut required
rule Article.nom required
rule Client.nom required
rule Ligne.quantite required
rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Create Client
    Read Client
    Read Article

workflow Gerer for Patron
    Read Commande
    Read Ligne
    Read Client
    Create Article
    Read Article
"""


def _references_reelles(schema_sql):
    """{(table, column): referenced_table} read in the REAL schema.sql."""
    trouve = {}
    table = None
    for ligne in schema_sql.splitlines():
        entete = re.match(r'CREATE TABLE IF NOT EXISTS "?(\w+)"?', ligne.strip())
        if entete:
            table = entete.group(1)
        contrainte = re.search(
            r'FOREIGN KEY \("(\w+)"\) REFERENCES "?(\w+)"?\(id\)', ligne)
        if contrainte and table:
            trouve[(table, contrainte.group(1))] = contrainte.group(2)
    return trouve


def test_the_contract_says_which_of_the_two_foreign_key_kinds(tmp_path):
    """POINT 88: a monl foreign key references one of TWO things — the ACCOUNTS
    registry (`_monl_users`) when the Create route fills it from the token, or a
    business table's `id` otherwise. `schema.sql` does write two different
    `REFERENCES`; the contract announced the same one in both cases.

    What it cost, checked on `projets/SneakerLab`: an interface faithful to the
    contract joins `order.customer_id` to `customer.id`, while the right join is
    `customer.customer_id`. A join that works HALFWAY — right only as long as the
    account id and the record id coincide, that is on the first records, that is
    during tests. The right name shows on the oldest order, and nothing on the
    following ones."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_COMPTES, encoding="utf-8")
    contrat = compile_project(str(proj / "spec.ml"), str(proj))
    reelles = _references_reelles((proj / "schema.sql").read_text(encoding="utf-8"))
    assert reelles, "no FOREIGN KEY constraint read: the test proves nothing"

    vues = 0
    for entite, spec in contrat["entities"].items():
        for lien in spec["foreign_keys"]:
            cible = reelles.get((entite.lower(), lien["column"]))
            assert cible is not None, f"{entite}.{lien['column']} missing from the schema"
            vers_un_compte = cible == "_monl_users"
            assert lien["references_account"] == vers_un_compte, (
                f"{entite}.{lien['column']}: the contract says "
                f"references_account={lien['references_account']}, "
                f"schema.sql says REFERENCES {cible}")
            vues += 1
    assert vues >= 4, f"too few keys confronted ({vues})"

    # BOTH kinds must be represented: a test set containing only one would let
    # through a contract always answering the same.
    sortes = {lien["references_account"]
              for spec in contrat["entities"].values()
              for lien in spec["foreign_keys"]}
    assert sortes == {True, False}, sortes


def test_an_account_key_says_how_to_find_the_record(tmp_path):
    """Reporting the column's nature is not enough: the interface must know WHAT
    to do instead. The note names the homonymous column."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_COMPTES, encoding="utf-8")
    contrat = compile_project(str(proj / "spec.ml"), str(proj))
    lien = next(li for li in contrat["entities"]["Commande"]["foreign_keys"]
                if li["column"] == "client_id")
    assert lien["references_account"] is True
    assert "ACCOUNT" in lien["note"]
    assert "`client_id` has this same value" in lien["note"]
    assert "never the one whose `id`" in lien["note"]


def test_the_delta_reports_a_newly_allowed_role(tmp_path, capsys):
    """POINT 88: opening an existing route to one more role creates NO new route
    — only one more actor. The delta only compared method+path, so opening the
    order book to the administrator made it answer "no interface change, the
    existing frontend stays valid". It was true and misleading: nothing was
    broken, and yet a whole screen was missing — and the delta report exists
    precisely to say what remains to write."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_COMPTES, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    # The boss gains the right to advance an order. No new route: PUT
    # /commande/{id} already existed for the customer.
    evolue = SPEC_COMPTES.replace(
        "rule Commande.Update ownedBy Client",
        "rule Commande.Update ownedBy Client\n"
        "rule Commande.Update sharedBy Client, Patron").replace(
        "workflow Gerer for Patron\n    Read Commande",
        "workflow Gerer for Patron\n    Read Commande\n    Update Commande")
    spec.write_text(evolue, encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "access granted: PUT /commande/{id} → Patron" in sortie, sortie
    # And the instruction for the frontend AI says what to do with it.
    brief = (proj / "docs/FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "Newly authorized roles" in brief
    assert "supervisor" in brief

    contrat = json.loads((proj / "frontend_contract.json").read_text(encoding="utf-8"))
    put = next(r for r in contrat["routes"]
               if r["method"] == "PUT" and r["path"] == "/commande/{id}")
    assert put["allowed_actors"] == ["Client", "Patron"]


def test_the_delta_does_not_report_a_new_route_twice(tmp_path, capsys):
    """The witness of the test above: a route that APPEARS necessarily carries
    new actors. Also counting them as "access opened" would say the same thing
    twice, and drown the signal just added."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_COMPTES, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(SPEC_COMPTES.replace(
        "workflow Gerer for Patron\n    Read Commande",
        "workflow Gerer for Patron\n    Delete Commande\n    Read Commande"),
        encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "route added: DELETE /commande/{id}" in sortie, sortie
    assert "access granted: DELETE /commande/{id}" not in sortie, sortie


def test_the_delta_reports_a_field_that_became_read_only(tmp_path, capsys):
    """POINT 89: the other half of point 88's blind spot. Setting a rule that
    makes the server CALCULATE an existing field renames nothing: the delta
    compared names, and answered "no interface change" while the input form was
    becoming a field the server ignores.

    The worse of the two cases, incidentally: sending the value does not even
    fail, it is silently discarded — the user believes they entered a date."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    # The field first exists as an ORDINARY attribute, entered by the client.
    depart = SPEC_COMPTES.replace("    statut: String",
                                  "    statut: String\n    creeLe: DateTime")
    spec.write_text(depart, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(depart + "rule Commande.creeLe timestamp\n", encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "field is now read-only: Commande.creeLe" in sortie, sortie
    # No field was added or removed: it is indeed the MEANING that changed.
    assert "field added" not in sortie, sortie
    assert "field removed" not in sortie, sortie
    brief = (proj / "docs/FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "READ-ONLY" in brief
    assert "remove from forms" in brief


def test_the_delta_reports_an_added_prerequisite(tmp_path, capsys):
    """POINT 90: third form of the same blind spot — after actors (point 88) and
    read-only (point 89). The route changes neither path, nor actors, nor fields:
    it gains a CONDITION. And yet the whole user journey must be redone — creating
    the record before the checkout funnel, or else a 409 on the last screen."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_COMPTES, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(SPEC_COMPTES + "rule Commande.Create requiresOwn Client\n",
                    encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "prerequisite added: POST /commande → requires a Client" in sortie, sortie
    # Nothing else moved: it is indeed the CONDITION alone that changes.
    assert "route added" not in sortie, sortie
    assert "field added" not in sortie, sortie
    assert "access granted" not in sortie, sortie
    brief = (proj / "docs/FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "Added PREREQUISITES" in brief
    assert "BEFORE the form" in brief


def test_a_new_read_only_field_is_announced_as_such(tmp_path, capsys):
    """The brief's section is titled "to display/enter": on a timestamp, that
    would be a misreading. The name alone does not say a field is read-only — the
    contract knows it, so the delta must report it."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_COMPTES, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(
        SPEC_COMPTES.replace("    statut: String",
                             "    statut: String\n    creeLe: DateTime")
        + "rule Commande.creeLe timestamp\n", encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "field added: Commande.creeLe (read-only" in sortie, sortie
    # And the same batch's ordinary field does not carry the annotation.
    assert "field is now read-only" not in sortie, sortie


# ------------------------------------------------------ POINT 91: the locks --
# A complete cart: it is the only form where the lock has TWO faces — the
# settled order freezing itself, and its lines freezing with it (the total went
# back up through the line after payment).
SPEC_PANIER = """app Panier

entity Article
    nom: String
    prix: Money

entity Commande
    libelle: String
    total: Money

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Article.Read public
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Commande.total sumOf Ligne.sousTotal

workflow Acheter for Client
    Read Article
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

VERROU_PAYABLE = "rule Commande.total payable\n"

# The message is written by `_payment_lock_lines` and by it alone: it
# distinguishes the LOCK from the other reads of `payment_status` — notably the
# payment route's, which refuses a second payment for a reason of its own,
# already described in its own note.
GARDE_VERROU = "already paid: a charged record"


def _locked_routes_in_app(app_code):
    blocs = re.split(r"(?=@app\.(?:get|post|put|delete)\()", app_code)
    trouvees = set()
    for bloc in blocs[1:]:
        entete = re.match(r"@app\.(get|post|put|delete)\('([^']+)'", bloc)
        if entete and GARDE_VERROU in bloc:
            trouvees.add((entete.group(1).upper(), entete.group(2)))
    return trouvees


def test_the_contract_carries_every_lock_really_generated(tmp_path):
    """POINT 91: the contract must describe what the backend DOES (points 76, 79,
    88, 89). Here it only did so halfway: `PUT` and `DELETE` carried the lock
    note, `POST /ligne` did not — while the backend already refuses to attach one
    more line once the order is settled. An AI faithful to the contract therefore
    drew a "+ Add an item" on a paid order, and the refusal was discovered on
    click.

    The test is the non-divergence one applied to the lock: not the presence of
    an expected path, but EQUALITY with the guards really written in app.py — the
    only form that stays true when a brick moves."""
    proj = tmp_path / "panier"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PANIER + VERROU_PAYABLE, encoding="utf-8")
    contract = compile_project(str(proj / "spec.ml"), str(proj))

    annonces = {(r["method"], r["path"]) for r in contract["routes"]
                if r.get("payment_locked")}
    reelles = _locked_routes_in_app((proj / "app.py").read_text(encoding="utf-8"))
    assert annonces == reelles, (
        f"the contract announces {sorted(annonces)}, the backend locks "
        f"{sorted(reelles)}")
    # And the lock does cover both faces: the order, and its lines.
    assert ("PUT", "/commande/{id}") in annonces
    assert ("POST", "/ligne") in annonces
    # The witness: opening ONE MORE order was never locked — a payable entity
    # does not freeze itself at creation, it does not exist yet. A lock
    # announced there would make the "Order" button disappear.
    assert ("POST", "/commande") not in annonces
    # Each locked route carries its note: the JSON serves the delta, the note
    # serves the AI, which only reads the brief.
    for route in contract["routes"]:
        if route.get("payment_locked"):
            assert "LOCK" in (route.get("note") or ""), route["path"]


def test_without_payable_no_route_is_locked(tmp_path):
    """The brick's witness: a spare parts cart stays modifiable. CHARGING
    freezes, not aggregation — a lock freezing everything would pass the previous
    test while guaranteeing nothing."""
    proj = tmp_path / "panier_libre"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PANIER, encoding="utf-8")
    contract = compile_project(str(proj / "spec.ml"), str(proj))

    assert not [r for r in contract["routes"] if r.get("payment_locked")]
    assert not _locked_routes_in_app(
        (proj / "app.py").read_text(encoding="utf-8"))
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "VERROU" not in brief


def test_the_delta_reports_a_payment_lock(tmp_path, capsys):
    """POINT 91: fourth form of the blind spot of points 88 to 90. Setting
    `payable` renames none of the existing write routes — they gain a conditional
    REFUSAL. The delta answered "no interface change" while four buttons became
    potential 409s."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_PANIER, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(SPEC_PANIER + VERROU_PAYABLE, encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "payment lock: PUT /commande/{id} → frozen once Commande is paid" \
        in sortie, sortie
    assert "payment lock: POST /ligne → frozen once Commande is paid" \
        in sortie, sortie
    brief = (proj / "docs/FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "PAYMENT LOCKS" in brief
    assert "payment_status" in brief


def test_the_delta_does_not_report_twice_a_lock_on_a_new_route(tmp_path, capsys):
    """Same anti-duplication arbitration as at points 88 to 90: a route that just
    appeared carries its lock in "route added". Counting it twice would drown the
    signal — and it is precisely the case here, `Delete Commande` arriving locked
    from its first appearance."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_PANIER + VERROU_PAYABLE, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(
        (SPEC_PANIER + VERROU_PAYABLE)
        .replace("rule Commande.Update ownedBy Client",
                 "rule Commande.Update ownedBy Client\n"
                 "rule Commande.Delete ownedBy Client")
        .replace("    Update Commande\n", "    Update Commande\n    Delete Commande\n"),
        encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "route added: DELETE /commande/{id}" in sortie, sortie
    assert "payment lock" not in sortie, sortie


# -------------------------------------------------------- POINT 94: the FAQ --
SPEC_FAQ = SPEC + """
landing
    brief: "vitrine de démonstration"
    section "À propos": "Atelier fondé en 2015."
    question "Comment choisir ma taille ?": "Nos paires taillent normalement."
    question "Puis-je annuler une commande ?": "Oui, tant qu'elle est en préparation."
"""


def _faq_project(tmp_path, spec=SPEC_FAQ, nom="faq"):
    proj = tmp_path / nom
    proj.mkdir()
    (proj / "spec.ml").write_text(spec, encoding="utf-8")
    return proj, compile_project(str(proj / "spec.ml"), str(proj))


def test_the_faq_is_a_list_of_pairs_in_the_contract(tmp_path):
    """THE defect observed on `projets/SneakerLab`: the four questions fit in ONE
    `section` string, and the interface rendered them glued into a single
    paragraph. It was faithful — the content model could not say "a FAQ". A
    structure one does not declare is a structure the AI must guess, and that it
    will lose again at the next rebuild."""
    _proj, contract = _faq_project(tmp_path)
    assert contract["faq"] == [
        {"question": "Comment choisir ma taille ?",
         "answer": "Nos paires taillent normalement."},
        {"question": "Puis-je annuler une commande ?",
         "answer": "Oui, tant qu'elle est en préparation."}]
    # And it is not confused with sections: they are two sections.
    assert [s["title"] for s in contract["sections"]] == ["À propos"]


def test_the_question_order_is_the_specs(tmp_path):
    """In a FAQ, order carries meaning — one answers first what is asked most.
    Nothing would allow finding it again afterwards."""
    inverse = SPEC_FAQ.replace(
        '    question "Comment choisir ma taille ?": "Nos paires taillent normalement."\n', "")
    inverse += '    question "Comment choisir ma taille ?": "Nos paires taillent normalement."\n'
    _proj, contract = _faq_project(tmp_path, inverse, nom="ordre")
    assert [q["question"] for q in contract["faq"]] == [
        "Puis-je annuler une commande ?", "Comment choisir ma taille ?"]


def test_the_brief_says_the_faq_is_a_list_never_a_paragraph(tmp_path):
    """The AI does not read the contract's JSON, it reads the brief. Putting the
    pairs there without saying what they are would get exactly the prose block we
    are fixing remade."""
    proj, _contract = _faq_project(tmp_path)
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Frequently asked questions — a LIST" in brief
    assert "Never as a single paragraph" in brief
    assert "**Comment choisir ma taille ?**" in brief
    assert "Nos paires taillent normalement." in brief


def test_without_question_no_faq_block_in_the_brief(tmp_path):
    """The witness: a section absent from the spec must leave no trace. An
    announced empty FAQ would send the AI building an accordion without content."""
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["faq"] == []
    brief = (proj / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Questions fréquentes" not in brief


def test_a_question_without_answer_is_refused(tmp_path):
    """Same requirement as for a `section` (point 55), same reason: an entry mute
    on screen must be refused at compile time, not discovered by the visitor."""
    from monl.ast_validator import ASTValidationError, MonlAST
    from monl.parser import parse_monl_string

    spec = SPEC_FAQ.replace('"Nos paires taillent normalement."', '"   "')
    with pytest.raises((ASTValidationError, ValueError)) as refus:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "question" in str(refus.value)


def test_the_delta_reports_an_added_question_and_a_rewritten_text(tmp_path, capsys):
    """POINT 94: fifth form of the blind spot of points 88 to 91, and the first
    not touching data. Adding a question creates no route, no field — `monl
    update` answered "no interface change" with a whole block to write on the
    home page. The blind spot had existed for `section` since point 55; the FAQ
    would have fallen into it the day it was born.

    The third case is the most silent: a REWRITTEN text renames nothing.
    Comparing titles alone is point 89's exact mistake."""
    from monl.cli import cmd_update

    proj, _contract = _faq_project(tmp_path, nom="delta")
    capsys.readouterr()
    evolue = (SPEC_FAQ.replace('"Atelier fondé en 2015."', '"Atelier fondé en 2015, et agrandi depuis."')
              + '    question "Livrez-vous en Europe ?": "Oui, sous 3 à 5 jours."\n')
    (proj / "spec.ml").write_text(evolue, encoding="utf-8")

    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "no interface changes" not in sortie, sortie
    assert "content added: question “Livrez-vous en Europe ?”" in sortie, sortie
    assert "content rewritten: section “À propos”" in sortie, sortie
    # Nothing else moved: neither route nor field.
    assert "route added" not in sortie, sortie
    assert "field added" not in sortie, sortie
    brief = (proj / "docs/FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "ADDED editorial content" in brief
    assert "REWRITTEN content" in brief
