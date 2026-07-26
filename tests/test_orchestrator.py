# Tests de l'orchestrateur (pivot, briques 2-3) : contrat frontend, monl
# run (cohérence) et monl update (delta). Le test central vérifie que le
# contrat ne peut PAS diverger de l'API : chaque route du contrat est
# confrontée aux décorateurs réellement écrits dans app.py.
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cli import compile_project, check_coherence, _load_state  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")

SPEC = """app ContractTest

entity Item
    label: String
    price: Money

entity Note
    body: Text

actor Admin selfRegister

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


def test_contrat_correspond_aux_routes_reelles_de_app_py(tmp_path):
    proj, _spec, contract = _fresh_project(tmp_path)
    app_code = (proj / "app.py").read_text(encoding="utf-8")
    real_routes = set()
    for m in re.finditer(r"@app\.(get|post|put|delete)\('([^']+)'", app_code):
        real_routes.add((m.group(1).upper(), m.group(2)))
    # Routes hors périmètre du contrat métier (auth systématique + pages).
    infra = {("POST", "/register"), ("POST", "/login"), ("POST", "/logout"),
             ("GET", "/")}
    contract_routes = {(r["method"], r["path"]) for r in contract["routes"]}
    assert contract_routes == real_routes - infra, (
        "le contrat frontend a divergé des routes réellement générées")


def test_contrat_impose_la_meme_origine_jamais_un_port_code_en_dur(tmp_path):
    """Régression (point 51) : le contrat annonçait 'http://127.0.0.1:8000'
    et le brief en faisait un ordre. Une IA obéissante produisait donc un
    frontend qui appelle 8000 quoi qu'il arrive — cassé sous 'monl run
    --port', et recalé par le smoke test (port éphémère) pour avoir suivi le
    contrat. Le frontend étant servi sur /site par le serveur de l'API, la
    seule base correcte est l'origine de la page."""
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["api"]["base_url"] == ""
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    absolue = re.findall(r"`https?://[^`]+`", brief)
    assert not absolue, f"le brief impose encore une URL absolue : {absolue}"
    assert "RELATIFS" in brief


def test_champs_du_contrat_marquent_requis(tmp_path):
    _proj, _spec, contract = _fresh_project(tmp_path)
    fields = {f["name"]: f for f in contract["entities"]["Item"]["fields"]}
    assert fields["label"]["required"] is True
    assert fields["price"]["required"] is False
    # Item.Read est public, Note.Read ne l'est pas.
    auth = {(r["path"], r["method"]): r["auth_required"] for r in contract["routes"]}
    assert auth[("/item", "GET")] is False
    assert auth[("/note", "GET")] is True


def test_run_check_detecte_spec_modifiee_et_contrat_edite(tmp_path):
    proj, spec_path, _ = _fresh_project(tmp_path)
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors

    # 1. spec modifiée sans update -> erreur explicite
    spec_path.write_text(SPEC + "\n# commentaire ajouté\n", encoding="utf-8")
    ok, errors, _w = check_coherence(str(proj))
    assert not ok and any("monl update" in e for e in errors)

    # resynchronisation par update -> redevient cohérent
    compile_project(str(spec_path), str(proj))
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors

    # 2. contrat édité à la main -> erreur explicite
    contract_path = proj / "frontend_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["app"] = "Falsifié"
    contract_path.write_text(json.dumps(data), encoding="utf-8")
    ok, errors, _w = check_coherence(str(proj))
    assert not ok and any("modifié à la main" in e for e in errors)


def test_frontend_hors_contrat_declenche_avertissement(tmp_path):
    proj, _spec, _c = _fresh_project(tmp_path)
    front = proj / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        "<script>fetch('/item?limit=3'); fetch('/fantome/1');</script>",
        encoding="utf-8")
    ok, errors, warnings = check_coherence(str(proj))
    assert ok, errors
    assert any("/fantome" in w for w in warnings)
    assert not any("/item" in w for w in warnings)


def test_update_rapporte_le_delta_du_contrat(tmp_path):
    proj, spec_path, contract_v1 = _fresh_project(tmp_path)
    routes_v1 = {f"{r['method']} {r['path']}" for r in contract_v1["routes"]}

    # Évolution : un champ sur Item et l'action Delete sur Note.
    evolved = SPEC.replace("    price: Money", "    price: Money\n    stock: Integer")
    evolved = evolved.replace("    Read Note", "    Read Note\n    Delete Note")
    spec_path.write_text(evolved, encoding="utf-8")
    contract_v2 = compile_project(str(spec_path), str(proj))

    routes_v2 = {f"{r['method']} {r['path']}" for r in contract_v2["routes"]}
    fields_v2 = {f["name"] for f in contract_v2["entities"]["Item"]["fields"]}
    assert "DELETE /note/{id}" in routes_v2 - routes_v1
    assert "stock" in fields_v2
    # L'état enregistré suit la nouvelle spec (run redevient cohérent).
    state = _load_state(str(proj))
    assert state["spec"] == "spec.ml"
    ok, errors, _w = check_coherence(str(proj))
    assert ok, errors


# ---- Rôles de champs et archétypes (point 54) ----

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


def _contrat_archetypes(tmp_path):
    proj = tmp_path / "formes"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_ARCHETYPES, encoding="utf-8")
    return compile_project(str(spec), str(proj))


def test_archetype_derive_de_la_spec(tmp_path):
    """Restauration, dans le contrat, de ce que le pivot avait supprimé avec
    le frontend généré (points 35 puis 54). Sans lui, l'IA ne reçoit qu'une
    liste de {nom, type} et doit tout redeviner."""
    c = _contrat_archetypes(tmp_path)
    formes = {e: s["archetype"] for e, s in c["entities"].items()}
    assert formes["Project"] == "gallery"      # média + titre + description
    assert formes["Product"] == "shop"         # un Money l'emporte
    assert formes["Shot"] == "gallery"         # média seul : écart voulu / point 35
    assert formes["Entry"] == "list"           # rien à montrer
    # Lisible mais NON publique : une collection interne se gère, ne se
    # parcourt pas — défaut réel de la 1re version, qui conseillait une
    # galerie pour un formulaire de contact.
    assert formes["Message"] == "list"


def test_roles_de_champs_derives_et_jamais_sur_un_champ_masque(tmp_path):
    c = _contrat_archetypes(tmp_path)
    roles = {f["name"]: f["role"] for f in c["entities"]["Project"]["fields"]}
    assert roles == {"title": "title", "description": "description",
                     "imageUrl": "media", "category": "category"}
    # Le titre n'est jamais l'URL, même quand elle est le premier String
    # déclaré : afficher une URL en guise de nom est un défaut réel.
    shot = {f["name"]: f["role"] for f in c["entities"]["Shot"]["fields"]}
    assert shot["coverUrl"] == "media" and shot["legend"] == "description"


def test_le_brief_transmet_la_forme_conseillee(tmp_path):
    """Un rôle calculé mais absent du brief ne servirait à personne."""
    proj = tmp_path / "formes"
    _contrat_archetypes(tmp_path)
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Forme conseillée : galerie" in brief
    assert "Forme conseillée : boutique" in brief
    assert "MÉDIA" in brief and "TITRE" in brief
