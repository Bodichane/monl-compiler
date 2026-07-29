# Tests de l'orchestrateur (pivot, briques 2-3) : contrat frontend, monl
# run (cohérence) et monl update (delta). Le test central vérifie que le
# contrat ne peut PAS diverger de l'API : chaque route du contrat est
# confrontée aux décorateurs réellement écrits dans app.py.
import json
import os
import re

from monl.cli import _load_state, check_coherence, compile_project

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


# ---- Le contenu éditorial traverse jusqu'au brief (point 55) ----

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
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    # Le texte doit arriver INTACT : c'est du contenu, pas une consigne de
    # style que l'IA pourrait reformuler.
    assert "Atelier fondé en 2015, spécialisé dans la pièce unique." in brief
    assert "publier tel quel" in brief


def test_sans_section_aucun_bloc_editorial_dans_le_brief(tmp_path):
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["sections"] == []
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Contenu éditorial" not in brief


# ---- Le corps de requête annoncé est celui qu'exige le backend (point 57) ----

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
    """Champs de chaque classe `<Entite>Schema` réellement écrite dans app.py."""
    schemas = {}
    for bloc in re.finditer(r"class (\w+)Schema\(BaseModel\):\n((?:    .+\n)+)", app_code):
        champs = re.findall(r"^    (\w+)\s*:", bloc.group(2), re.M)
        schemas[bloc.group(1)] = champs
    return schemas


def test_le_corps_annonce_est_celui_qu_exige_le_backend(tmp_path):
    """Le contrat annonçait `POST /comment` avec le seul champ `content`
    alors que le backend exigeait aussi `article_id` : tout frontend fidèle
    au contrat récoltait un 422. Un contrat qui décrit mal ce qu'il faut
    envoyer est pire qu'un contrat muet — on croit l'avoir suivi."""
    proj = tmp_path / "blog"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_DEUX_PARENTS, encoding="utf-8")
    contract = compile_project(str(spec), str(proj))
    schemas = _schemas_pydantic((proj / "app.py").read_text(encoding="utf-8"))

    for route in contract["routes"]:
        if route["action"] not in ("Create", "Update"):
            continue
        attendu = schemas.get(route["entity"])
        assert attendu is not None, f"aucun schéma Pydantic pour {route['entity']}"
        assert sorted(route["request_fields"]) == sorted(attendu), (
            f"{route['method']} {route['path']} : le contrat annonce "
            f"{sorted(route['request_fields'])}, le backend exige {sorted(attendu)}")

    # Le cas précis qui a fait échouer la génération réelle : le parent
    # NON propriétaire doit être demandé au client (le propriétaire, lui,
    # se peuple depuis le JWT et ne doit surtout pas être envoyé).
    creation = next(r for r in contract["routes"]
                    if r["entity"] == "Comment" and r["method"] == "POST")
    assert "article_id" in creation["request_fields"]
    assert "reader_id" not in creation["request_fields"]


def test_le_brief_annonce_le_corps_attendu(tmp_path):
    """Un champ exigé mais absent du brief est indevinable : l'IA ne lit pas
    le JSON du contrat, elle lit ce document."""
    proj = tmp_path / "blog"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_DEUX_PARENTS, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "corps : `{content, article_id}`" in brief


def test_une_route_de_navigation_n_est_pas_un_chemin_hors_contrat(tmp_path):
    """Faux positif réel : `'/edit">Modifier</a>'` est la fin d'une route
    `#/article/<id>/edit` coupée par une concaténation. Toute application
    monopage en produit ; avertir dessus décrédibilise les vrais signaux."""
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


def test_le_contenu_editorial_est_exige_sur_la_page_d_accueil(tmp_path):
    """Défaut constaté : l'« à propos » était rendu sur une page à part
    (`#/apropos`), atteignable par le seul menu. Un visiteur qui n'ouvre que
    l'accueil ne le voyait jamais — pour un « à propos », c'est manquer sa
    raison d'être. Rien dans le contrat ne disait OÙ ce texte devait vivre."""
    proj = tmp_path / "edito"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_EDITORIALE, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "page d'accueil, pas seulement derrière un lien" in brief
    # Un texte long garde le droit d'avoir sa propre page EN PLUS.
    assert "se prolonger sur sa propre page" in brief


def test_le_brief_donne_l_anatomie_et_les_voisins(tmp_path):
    """Le contrat disait quelles DONNÉES existent, jamais ce qu'un visiteur
    s'attend à trouver sur une page de cette nature (point 60). Deux sites du
    même genre se ressemblent parce qu'ils répondent aux mêmes attentes :
    les nommer donne un repère au modèle, là où la seule liste des champs le
    laissait improviser."""
    proj = tmp_path / "formes"
    _contrat_archetypes(tmp_path)
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Proche de :" in brief
    assert "Ce qu'un visiteur s'attend à y trouver" in brief
    # Chaque forme apporte ses propres attentes, jamais une liste unique.
    assert "prix et disponibilité visibles sans défiler" in brief   # shop
    assert "un visuel dominant" in brief                            # gallery


def test_la_disponibilite_n_est_pas_une_donnee_secondaire(tmp_path):
    """`stock` recevait le rôle « méta », donc traité comme un détail, alors
    que la disponibilité est un essentiel de fiche produit au même rang que
    le prix (point 60)."""
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
    assert "DISPONIBILITÉ" in (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")


# ------------------------------------------- paiement (point 74) ------------
SPEC_PAYABLE = """app Boutique

entity Client
    nom: String

entity Commande
    libelle: String
    total: Money

relation Client hasMany Commande

actor Client selfRegister

rule Commande.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
"""


def _projet_payable(tmp_path):
    proj = tmp_path / "boutique"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PAYABLE, encoding="utf-8")
    return proj, compile_project(str(proj / "spec.ml"), str(proj))


def test_les_routes_de_paiement_sont_dans_le_contrat(tmp_path):
    """Les deux routes de la brique `payable` ne naissent pas d'un workflow :
    elles échappent donc à `_compute_route_map`, et le contrat les ignorait.
    Conséquence concrète, et pas théorique : l'IA d'interface ne pouvait pas
    dessiner le bouton de règlement — le contrat lui interdit par ailleurs
    d'appeler un chemin absent de `routes`. Une brique que le contrat ne
    décrit pas est une brique sans interface.

    Le test est celui de la non-divergence, appliqué à une spec payable : ce
    n'est pas la présence des deux chemins qui est vérifiée, mais l'égalité
    avec les décorateurs réellement écrits dans app.py."""
    proj, contract = _projet_payable(tmp_path)
    app_code = (proj / "app.py").read_text(encoding="utf-8")
    real_routes = {(m.group(1).upper(), m.group(2)) for m in
                   re.finditer(r"@app\.(get|post|put|delete)\('([^']+)'", app_code)}
    infra = {("POST", "/register"), ("POST", "/login"), ("POST", "/logout"),
             ("GET", "/")}
    contract_routes = {(r["method"], r["path"]) for r in contract["routes"]}
    assert contract_routes == real_routes - infra
    assert ("POST", "/commande/{id}/paiement") in contract_routes
    assert ("POST", "/paiement/webhook") in contract_routes


def test_le_brief_dit_comment_regler_et_de_ne_pas_appeler_le_webhook(tmp_path):
    """L'IA ne lit pas le JSON du contrat, elle lit le brief. Une route
    listée sans sa marche à suivre — aucun corps, rediriger vers `url` — se
    devine mal ; et le webhook, lui, doit être explicitement écarté, sinon
    une interface consciencieuse tentera de le notifier elle-même."""
    proj, _contract = _projet_payable(tmp_path)
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "POST /commande/{id}/paiement" in brief
    assert "AUCUN corps" in brief and "montant_centimes" in brief
    assert "jamais par le frontend" in brief
    # Et pas seulement dans l'inventaire des routes : le règlement est le seul
    # parcours du frontend où une erreur coûte de l'argent, il figure dans les
    # règles non négociables, que l'IA lit avant la liste.
    regles = brief.split("## Entités")[0].split("## Règles non négociables")[1]
    assert "sans aucun corps" in regles
    assert "Ne JAMAIS appeler `POST /paiement/webhook`" in regles


def test_sans_payable_le_brief_ne_parle_jamais_de_paiement(tmp_path):
    """Le témoin : une règle qui n'existe pas dans la spec ne doit laisser
    aucune trace dans le brief. Une consigne de règlement sur un portfolio
    enverrait l'IA construire un bouton qui n'a pas de route."""
    proj, _spec, _contract = _fresh_project(tmp_path)
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "paiement" not in brief.lower()


def test_les_colonnes_de_suivi_ne_sont_pas_annoncees_en_entree(tmp_path):
    """`payment_status` et `payment_ref` sont au serveur. Le contrat ne doit
    pas les faire figurer dans le corps de la création : un frontend fidèle
    les enverrait, et croirait pouvoir décider lui-même qu'une commande est
    payée."""
    _proj, contract = _projet_payable(tmp_path)
    creation = next(r for r in contract["routes"]
                    if r["method"] == "POST" and r["path"] == "/commande")
    assert "total" in creation["request_fields"]
    assert "payment_status" not in creation["request_fields"]
    assert "payment_ref" not in creation["request_fields"]
