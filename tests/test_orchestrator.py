# Tests de l'orchestrateur (pivot, briques 2-3) : contrat frontend, monl
# run (cohérence) et monl update (delta). Le test central vérifie que le
# contrat ne peut PAS diverger de l'API : chaque route du contrat est
# confrontée aux décorateurs réellement écrits dans app.py.
import hashlib
import json
import os
import re

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

# Le rôle d'administration est provisionné hors ligne : ces tests portent sur
# la cohérence du contrat, pas sur une vitrine qui promet un back-office.
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


def test_delta_signale_un_type_de_champ_modifie(tmp_path, capsys):
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
    assert "type de champ changé : Note.priority : String → Integer" in capsys.readouterr().out


def test_brief_express_autorise_textes_blocs_et_images_matricielles_locales(tmp_path):
    answers = iter(["1", "StudioExpress", "Portfolio de céramique contemporaine."])
    spec_text = GuidedDialogue(
        ask=lambda prompt: next(answers), express=True).run()
    proj = tmp_path / "express"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(spec_text, encoding="utf-8")
    compile_project(str(spec), str(proj))
    prompt = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Mode express" in prompt
    assert "page dense en blocs réellement utiles" in prompt
    # Renversement explicite : le texte peut organiser la page, mais les
    # octets d'une image sont désormais produits par le fournisseur image et
    # écrits dans assets/ avant l'appel au modèle texte.
    assert "images matricielles" in prompt
    assert "ne pas tenter de produire ses octets" in prompt
    assert "illustrations `.svg` originales" not in prompt
    assert "Ne jamais fabriquer côté navigateur de faux produits" in prompt


def test_contrat_correspond_aux_routes_reelles_de_app_py(tmp_path):
    proj, _spec, contract = _fresh_project(tmp_path)
    app_code = (proj / "app.py").read_text(encoding="utf-8")
    real_routes = set()
    for m in re.finditer(r"@app\.(get|post|put|delete)\('([^']+)'", app_code):
        real_routes.add((m.group(1).upper(), m.group(2)))
    # Routes hors périmètre du contrat métier (auth systématique + pages).
    infra = {("POST", "/register"), ("POST", "/login"), ("POST", "/logout"),
             ("GET", "/"), ("GET", "/health"), ("GET", "/health/ready")}
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
    """POINT 91 : ce test encodait le MENSONGE. Il exigeait que le contrat
    recopie les `rule X.y required` de la spec — alors que les schémas Pydantic
    générés rendent obligatoire TOUT champ d'entrée, déclaré ou non (point 85 :
    « required reste une assertion, les schémas rendent déjà tout champ
    obligatoire »).

    Un frontend fidèle au contrat omettait donc les champs non déclarés et
    récoltait un 422. Vu en vrai sur `projets/SneakerLab` : ajouter `email` et
    `address` à la fiche client a cassé le formulaire d'un site en marche,
    pendant que le contrat les annonçait facultatifs.

    Le témoin est plus bas : `app.py` doit exiger les DEUX."""
    proj, _spec, contract = _fresh_project(tmp_path)
    fields = {f["name"]: f for f in contract["entities"]["Item"]["fields"]}
    assert fields["label"]["required"] is True
    assert fields["price"]["required"] is True, "non déclaré, et pourtant exigé"

    genere = (proj / "app.py").read_text(encoding="utf-8")
    schema = genere.split("class ItemSchema(BaseModel):")[1].split("class ")[0]
    for champ in ("label", "price"):
        ligne = next(li for li in schema.splitlines() if li.strip().startswith(champ))
        assert "Optional" not in ligne and "= None" not in ligne, ligne

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


def test_run_check_signale_un_artefact_produit_par_un_compilateur_anterieur(tmp_path):
    """Point 81. Les contrôles de cohérence comparaient aux empreintes
    ENREGISTRÉES à la compilation : ils détectaient une retouche à la main — leur
    but — et laissaient passer un projet dont les artefacts venaient d'un
    compilateur antérieur. 'monl run' annonçait alors « cohérence vérifiée » sur
    un backend que le compilateur courant n'écrirait plus, y compris après qu'un
    correctif ait fermé un trou.

    Trouvé sur un vrai projet (`projets/SneakerLab`) : son contrat n'avait pas la
    note `PUT` du point 81 et le contrôle affichait ✅. Un numéro de version
    n'aurait rien vu — `__version__` n'a pas bougé pendant les points 74 à 81 —
    d'où la comparaison à une régénération.

    La simulation est fidèle : le contrat sur disque est modifié ET son empreinte
    enregistrée mise à jour, ce qui est exactement l'état qu'un compilateur
    antérieur aurait laissé (cohérent avec lui-même, divergent du compilateur
    courant). Sans la mise à jour de l'empreinte, c'est le contrôle de retouche à
    la main qui répondrait, et le test ne prouverait rien."""
    proj, _spec, _c = _fresh_project(tmp_path)
    ok, _errors, warnings = check_coherence(str(proj))
    assert ok
    assert not any("compilateur antérieur" in w for w in warnings)

    contract_path = proj / "frontend_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["monl_contract_version"] = 1  # ce qu'un compilateur d'alors écrivait
    contract_path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                        sort_keys=True), encoding="utf-8")
    state_path = proj / "monl.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["contract_sha256"] = hashlib.sha256(
        contract_path.read_bytes()).hexdigest()
    state_path.write_text(json.dumps(state), encoding="utf-8")

    ok, errors, warnings = check_coherence(str(proj))
    # Un avertissement, pas une erreur : bloquer 'monl run' immobiliserait toute
    # application après n'importe quelle évolution du compilateur, y compris
    # celles qui ne la concernent pas. Même arbitrage que pour l'état antérieur
    # au scellé du backend.
    assert ok, errors
    perimes = [w for w in warnings if "compilateur antérieur" in w]
    assert perimes, warnings
    # L'avertissement doit NOMMER l'artefact et la commande qui resynchronise :
    # sans cela il ne serait pas actionnable.
    assert "frontend_contract.json" in perimes[0]
    assert "monl update" in perimes[0]
    # ... et ne pas accuser les artefacts qui sont, eux, à jour.
    assert "app.py" not in perimes[0]

    # La resynchronisation lève l'avertissement.
    compile_project(str(_spec), str(proj))
    ok, errors, warnings = check_coherence(str(proj))
    assert ok, errors
    assert not any("compilateur antérieur" in w for w in warnings)


def test_frontend_hors_contrat_declenche_avertissement(tmp_path):
    proj, _spec, _c = _fresh_project(tmp_path)
    front = proj / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        "<script>fetch('/item?limit=3'); fetch('/fantome/1');</script>",
        encoding="utf-8")
    ok, errors, warnings = check_coherence(str(proj))
    # Renversement rendu nécessaire par le contrôle demandé : un chemin passé
    # à fetch n'est plus seulement un avertissement, car il peut viser le vide.
    assert not ok
    assert any("/fantome" in error for error in errors)
    assert any("/fantome" in w for w in warnings)
    # Le nouveau contrôle peut nommer /item dans son décompte de couverture ;
    # ce test porte uniquement sur l'ancien avertissement de chemin inconnu.
    assert not any("chemins absents du contrat" in w and "/item" in w
                   for w in warnings)


def test_les_routes_de_navigation_ne_declenchent_pas_lavertissement(tmp_path):
    """POINT 92 : sur `projets/SneakerLab`, l'avertissement dénonçait `/admin`,
    `/catalogue`, `/commandes` et `/compte` — quatre routes de NAVIGATION d'une
    application monopage, aucun défaut. Un avertissement qui crie au loup sur un
    site correct apprend à ne plus lire les avertissements ; il valait mieux
    l'affûter que le supprimer.

    La preuve vit dans le fichier : `#/catalogue` déclare la route côté client,
    donc `aller('/catalogue')` n'est pas un appel d'API. Le témoin est dans le
    même fichier — un vrai chemin mal tapé n'apparaît jamais derrière un dièse,
    et reste signalé."""
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
    # `/fantome` est désormais le cas de refus ci-dessus ; le témoin de ce
    # test est volontairement uniquement une navigation `#/catalogue`.


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

# Depuis le point 79, `payable` exige un montant calculé par le serveur : le
# créateur d'une commande en devient le propriétaire, donc le payeur.
rule Commande.total derivedFrom Article.prix by quantite
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
             ("GET", "/"), ("GET", "/health"), ("GET", "/health/ready")}
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
    # Le témoin est `quantite` : depuis le point 79, `total` est CALCULÉ par le
    # serveur, donc lui aussi absent de l'entrée. Il en faut un, sinon un
    # `request_fields` vide passerait ce test.
    assert "quantite" in creation["request_fields"]
    for reserve in ("total", "payment_status", "payment_ref"):
        assert reserve not in creation["request_fields"], reserve


# ------------------------------------- suivi du paiement (point 76) ----------

def _champs_commande(contract):
    return {f["name"]: f for f in contract["entities"]["Commande"]["fields"]}


def test_les_colonnes_de_suivi_sont_declarees_en_sortie(tmp_path):
    """Symétrique du test précédent, et le trou qu'il laissait ouvert : le
    contrat ne devait pas annoncer ces champs EN ENTRÉE, mais il ne les
    annonçait nulle part — alors que le backend les renvoie (`SELECT *`) à
    chaque lecture. Une IA d'interface fidèle au contrat ne pouvait donc pas
    savoir qu'ils existent, ni afficher l'issue d'un règlement : le bouton
    était dessinable, son résultat non."""
    _proj, contract = _projet_payable(tmp_path)
    champs = _champs_commande(contract)
    for colonne in ("payment_status", "payment_ref"):
        assert colonne in champs, f"{colonne} absent du contrat"
        assert champs[colonne]["server_generated"] is True
        assert champs[colonne]["payment_tracking"] is True
        assert champs[colonne]["hidden_in_reads"] is False


def test_les_colonnes_de_suivi_ne_volent_aucun_role_de_mise_en_page(tmp_path):
    """Les rôles (point 35) commandent la mise en page, et « méta » n'a que
    trois emplacements. Passer ces deux colonnes à l'attribution des rôles
    leur en donnait deux, donc les faisait afficher comme des informations
    secondaires quelconques — en évinçant de vrais champs de la spec. Elles
    n'ont aucun rôle, et les champs déclarés gardent le leur."""
    _proj, contract = _projet_payable(tmp_path)
    champs = _champs_commande(contract)
    assert champs["payment_status"]["role"] is None
    assert champs["payment_ref"]["role"] is None
    # Les champs de la spec ne bougent pas, ni la forme déduite de l'entité.
    assert champs["libelle"]["role"] == "title"
    assert champs["total"]["role"] == "price"
    assert contract["entities"]["Commande"]["archetype"] == "list"


def test_le_brief_explique_chaque_colonne_de_suivi_distinctement(tmp_path):
    """L'IA lit le brief, pas le JSON. Et une explication commune aux deux
    colonnes annonçait « 'en_attente' / 'payee' » pour `payment_ref`, qui
    contient une référence de session : défaut vu en relisant le brief produit,
    pas le code. Chaque colonne dit ce qu'elle porte."""
    proj, contract = _projet_payable(tmp_path)
    champs = _champs_commande(contract)
    assert champs["payment_status"]["note"] != champs["payment_ref"]["note"]
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    # Les valeurs à comparer sont écrites : sans elles, l'IA devine 'paid'.
    assert "'en_attente'" in brief and "'payee'" in brief
    for colonne in ("payment_status", "payment_ref"):
        assert f"`{colonne}: String`" in brief
    # La marche à suivre est rattachée à la ROUTE aussi : savoir ouvrir un
    # règlement ne dit pas comment en montrer l'issue.
    assert "payment_status" in next(
        r["note"] for r in contract["routes"]
        if r["path"] == "/commande/{id}/paiement")


def test_sans_payable_aucune_colonne_de_suivi_dans_le_contrat(tmp_path):
    """Le témoin : ces champs n'existent pas en base sans `payable`. Les
    déclarer quand même enverrait l'IA lire un champ toujours absent."""
    _proj, _spec, contract = _fresh_project(tmp_path)
    for spec_entite in contract["entities"].values():
        noms = {f["name"] for f in spec_entite["fields"]}
        assert not (noms & {"payment_status", "payment_ref"})


# --------------------------------------------------------------------------
# POINT 88 : les clés étrangères, confrontées au schéma RÉELLEMENT écrit
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
    """{(table, colonne): table_référencée} lu dans le VRAI schema.sql."""
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


def test_le_contrat_dit_laquelle_des_deux_sortes_de_cle_etrangere(tmp_path):
    """POINT 88 : une clé étrangère de monl référence l'une de DEUX choses —
    le registre des COMPTES (`_monl_users`) quand la route Create la peuple
    depuis le jeton, ou l'`id` d'une table métier sinon. `schema.sql` écrit
    bien deux `REFERENCES` différents ; le contrat annonçait le même dans les
    deux cas.

    Ce que ça coûtait, vérifié sur `projets/SneakerLab` : une interface fidèle
    au contrat joint `order.customer_id` à `customer.id`, alors que la bonne
    jointure est `customer.customer_id`. Une jointure qui marche À MOITIÉ —
    juste tant que l'identifiant de compte et celui de la fiche coïncident,
    c'est-à-dire sur les premiers enregistrements, c'est-à-dire pendant les
    tests. Le bon nom s'affiche sur la commande la plus ancienne, et rien sur
    les suivantes."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_COMPTES, encoding="utf-8")
    contrat = compile_project(str(proj / "spec.ml"), str(proj))
    reelles = _references_reelles((proj / "schema.sql").read_text(encoding="utf-8"))
    assert reelles, "aucune contrainte FOREIGN KEY lue : le test ne prouve rien"

    vues = 0
    for entite, spec in contrat["entities"].items():
        for lien in spec["foreign_keys"]:
            cible = reelles.get((entite.lower(), lien["column"]))
            assert cible is not None, f"{entite}.{lien['column']} absente du schéma"
            vers_un_compte = cible == "_monl_users"
            assert lien["references_account"] == vers_un_compte, (
                f"{entite}.{lien['column']} : le contrat dit "
                f"references_account={lien['references_account']}, "
                f"schema.sql dit REFERENCES {cible}")
            vues += 1
    assert vues >= 4, f"trop peu de clés confrontées ({vues})"

    # Les DEUX sortes doivent être représentées : un jeu d'essai qui n'en
    # contiendrait qu'une laisserait passer un contrat qui répond toujours
    # pareil.
    sortes = {lien["references_account"]
              for spec in contrat["entities"].values()
              for lien in spec["foreign_keys"]}
    assert sortes == {True, False}, sortes


def test_une_cle_de_compte_dit_comment_retrouver_la_fiche(tmp_path):
    """Signaler la nature de la colonne ne suffit pas : l'interface doit savoir
    QUOI faire à la place. La note nomme la colonne homonyme."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_COMPTES, encoding="utf-8")
    contrat = compile_project(str(proj / "spec.ml"), str(proj))
    lien = next(li for li in contrat["entities"]["Commande"]["foreign_keys"]
                if li["column"] == "client_id")
    assert lien["references_account"] is True
    assert "COMPTE" in lien["note"]
    assert "`client_id` vaut cette même valeur" in lien["note"]
    assert "jamais celui dont `id`" in lien["note"]


def test_le_delta_signale_un_role_nouvellement_autorise(tmp_path, capsys):
    """POINT 88 : ouvrir une route existante à un rôle de plus ne crée AUCUNE
    route nouvelle — seulement un acteur de plus. Le delta ne comparait que
    méthode+chemin, si bien qu'ouvrir le carnet de commandes à l'administrateur
    faisait répondre « aucun changement d'interface, le frontend existant reste
    valide ». C'était vrai et trompeur : rien n'était cassé, et pourtant tout un
    écran manquait — or le rapport de delta existe précisément pour dire ce
    qu'il reste à écrire."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    spec.write_text(SPEC_COMPTES, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    # Le patron gagne le droit de faire avancer une commande. Aucune route
    # nouvelle : PUT /commande/{id} existait déjà pour le client.
    evolue = SPEC_COMPTES.replace(
        "rule Commande.Update ownedBy Client",
        "rule Commande.Update ownedBy Client\n"
        "rule Commande.Update sharedBy Client, Patron").replace(
        "workflow Gerer for Patron\n    Read Commande",
        "workflow Gerer for Patron\n    Read Commande\n    Update Commande")
    spec.write_text(evolue, encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "aucun changement d'interface" not in sortie, sortie
    assert "accès ouvert : PUT /commande/{id} → Patron" in sortie, sortie
    # Et la consigne pour l'IA frontend dit quoi en faire.
    brief = (proj / "FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "Rôles nouvellement autorisés" in brief
    assert "supervision" in brief

    contrat = json.loads((proj / "frontend_contract.json").read_text(encoding="utf-8"))
    put = next(r for r in contrat["routes"]
               if r["method"] == "PUT" and r["path"] == "/commande/{id}")
    assert put["allowed_actors"] == ["Client", "Patron"]


def test_le_delta_ne_rapporte_pas_deux_fois_une_route_nouvelle(tmp_path, capsys):
    """Le témoin du test ci-dessus : une route qui APPARAÎT porte forcément des
    acteurs nouveaux. Les compter aussi comme « accès ouverts » dirait deux fois
    la même chose, et noierait le signal qu'on vient d'ajouter."""
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

    assert "route ajoutée : DELETE /commande/{id}" in sortie, sortie
    assert "accès ouvert : DELETE /commande/{id}" not in sortie, sortie


def test_le_delta_signale_un_champ_devenu_en_lecture_seule(tmp_path, capsys):
    """POINT 89 : l'autre moitié de l'angle mort du point 88. Poser une règle qui
    fait CALCULER un champ existant par le serveur ne renomme rien : le delta
    comparait des noms, et répondait « aucun changement d'interface » pendant
    que le formulaire de saisie devenait un champ que le serveur ignore.

    Le pire des deux cas, d'ailleurs : envoyer la valeur n'échoue même pas, elle
    est silencieusement écartée — l'utilisateur croit avoir saisi une date."""
    from monl.cli import cmd_update

    proj = tmp_path / "proj"
    proj.mkdir()
    spec = proj / "spec.ml"
    # Le champ existe d'abord comme un attribut ORDINAIRE, saisi par le client.
    depart = SPEC_COMPTES.replace("    statut: String",
                                  "    statut: String\n    creeLe: DateTime")
    spec.write_text(depart, encoding="utf-8")
    compile_project(str(spec), str(proj))
    capsys.readouterr()

    spec.write_text(depart + "rule Commande.creeLe timestamp\n", encoding="utf-8")
    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "aucun changement d'interface" not in sortie, sortie
    assert "champ devenu en lecture seule : Commande.creeLe" in sortie, sortie
    # Aucun champ n'a été ajouté ni retiré : c'est bien le SENS qui a changé.
    assert "champ ajouté" not in sortie, sortie
    assert "champ retiré" not in sortie, sortie
    brief = (proj / "FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "LECTURE SEULE" in brief
    assert "retirer des formulaires" in brief


def test_le_delta_signale_un_prealable_ajoute(tmp_path, capsys):
    """POINT 90 : troisième forme du même angle mort — après les acteurs
    (point 88) et la lecture seule (point 89). La route ne change ni de chemin,
    ni d'acteurs, ni de champs : elle gagne une CONDITION. Et pourtant c'est tout
    le parcours utilisateur qu'il faut reprendre — créer la fiche avant le tunnel
    d'achat, sous peine de 409 au dernier écran."""
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

    assert "aucun changement d'interface" not in sortie, sortie
    assert "préalable ajouté : POST /commande → exige un Client" in sortie, sortie
    # Rien d'autre n'a bougé : c'est bien la CONDITION seule qui change.
    assert "route ajoutée" not in sortie, sortie
    assert "champ ajouté" not in sortie, sortie
    assert "accès ouvert" not in sortie, sortie
    brief = (proj / "FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "PRÉALABLES ajoutés" in brief
    assert "AVANT le formulaire" in brief


def test_un_champ_neuf_en_lecture_seule_est_annonce_comme_tel(tmp_path, capsys):
    """La rubrique du brief s'intitule « à afficher/saisir » : sur un horodatage,
    ce serait un contresens. Le nom seul ne dit pas qu'un champ est en lecture
    seule — c'est le contrat qui le sait, donc le delta doit le reporter."""
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

    assert "champ ajouté : Commande.creeLe (lecture seule" in sortie, sortie
    # Et le champ ordinaire du même lot, lui, ne porte pas l'annotation.
    assert "champ devenu en lecture seule" not in sortie, sortie


# --------------------------------------------------- POINT 91 : les verrous --
# Un panier complet : c'est la seule forme où le verrou a DEUX visages — la
# commande encaissée qui se fige elle-même, et ses lignes qui se figent avec
# elle (c'est par la ligne que le total remontait après règlement).
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

# Le message est écrit par `_payment_lock_lines` et par lui seul : il distingue
# le VERROU des autres lectures de `payment_status` — notamment celle de la
# route de règlement, qui refuse un second paiement pour une raison à elle,
# déjà décrite dans sa propre note.
GARDE_VERROU = "déjà réglé : un enregistrement encaissé"


def _routes_verrouillees_dans_app(app_code):
    blocs = re.split(r"(?=@app\.(?:get|post|put|delete)\()", app_code)
    trouvees = set()
    for bloc in blocs[1:]:
        entete = re.match(r"@app\.(get|post|put|delete)\('([^']+)'", bloc)
        if entete and GARDE_VERROU in bloc:
            trouvees.add((entete.group(1).upper(), entete.group(2)))
    return trouvees


def test_le_contrat_porte_tous_les_verrous_reellement_generes(tmp_path):
    """POINT 91 : le contrat doit décrire ce que le backend FAIT (points 76, 79,
    88, 89). Ici il ne le faisait qu'à moitié : `PUT` et `DELETE` portaient la
    note du verrou, `POST /ligne` non — alors que le backend refuse déjà d'y
    rattacher une ligne de plus une fois la commande réglée. Une IA fidèle au
    contrat dessinait donc un « + Ajouter un article » sur une commande payée,
    et le refus se découvrait au clic.

    Le test est celui de la non-divergence appliqué au verrou : pas la présence
    d'un chemin attendu, mais l'ÉGALITÉ avec les gardes réellement écrites dans
    app.py — la seule forme qui reste vraie quand une brique bougera."""
    proj = tmp_path / "panier"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PANIER + VERROU_PAYABLE, encoding="utf-8")
    contract = compile_project(str(proj / "spec.ml"), str(proj))

    annonces = {(r["method"], r["path"]) for r in contract["routes"]
                if r.get("payment_locked")}
    reelles = _routes_verrouillees_dans_app((proj / "app.py").read_text(encoding="utf-8"))
    assert annonces == reelles, (
        f"le contrat annonce {sorted(annonces)}, le backend verrouille "
        f"{sorted(reelles)}")
    # Et le verrou couvre bien les deux visages : la commande, et ses lignes.
    assert ("PUT", "/commande/{id}") in annonces
    assert ("POST", "/ligne") in annonces
    # Le témoin : ouvrir une commande de PLUS n'a jamais été verrouillé — une
    # entité payable ne se fige pas elle-même à la création, elle n'existe pas
    # encore. Un verrou annoncé là ferait disparaître le bouton « Commander ».
    assert ("POST", "/commande") not in annonces
    # Chaque route verrouillée porte sa note : le JSON sert au delta, la note
    # sert à l'IA, qui ne lit que le brief.
    for route in contract["routes"]:
        if route.get("payment_locked"):
            assert "VERROU" in (route.get("note") or ""), route["path"]


def test_sans_payable_aucune_route_n_est_verrouillee(tmp_path):
    """Le témoin de la brique : un panier de pièces détachées reste modifiable.
    C'est l'ENCAISSEMENT qui fige, pas l'agrégation — un verrou qui figerait
    tout ferait passer le test précédent sans rien garantir."""
    proj = tmp_path / "panier_libre"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC_PANIER, encoding="utf-8")
    contract = compile_project(str(proj / "spec.ml"), str(proj))

    assert not [r for r in contract["routes"] if r.get("payment_locked")]
    assert not _routes_verrouillees_dans_app(
        (proj / "app.py").read_text(encoding="utf-8"))
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "VERROU" not in brief


def test_le_delta_signale_un_verrou_de_paiement(tmp_path, capsys):
    """POINT 91 : quatrième forme de l'angle mort des points 88 à 90. Poser
    `payable` ne renomme aucune des routes d'écriture existantes — elles gagnent
    un REFUS conditionnel. Le delta répondait « aucun changement d'interface »
    pendant que quatre boutons devenaient des 409 en puissance."""
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

    assert "aucun changement d'interface" not in sortie, sortie
    assert "verrou de paiement : PUT /commande/{id} → figé une fois Commande réglé" \
        in sortie, sortie
    assert "verrou de paiement : POST /ligne → figé une fois Commande réglé" \
        in sortie, sortie
    brief = (proj / "FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "VERROUS de paiement" in brief
    assert "payment_status" in brief


def test_le_delta_ne_rapporte_pas_deux_fois_un_verrou_sur_route_nouvelle(tmp_path, capsys):
    """Même arbitrage anti-doublon qu'aux points 88 à 90 : une route qui vient
    d'apparaître porte son verrou dans « route ajoutée ». L'y compter deux fois
    noierait le signal — et c'est précisément le cas ici, `Delete Commande`
    arrivant verrouillée dès sa première apparition."""
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

    assert "route ajoutée : DELETE /commande/{id}" in sortie, sortie
    assert "verrou de paiement" not in sortie, sortie


# --------------------------------------------------- POINT 94 : la FAQ --
SPEC_FAQ = SPEC + """
landing
    brief: "vitrine de démonstration"
    section "À propos": "Atelier fondé en 2015."
    question "Comment choisir ma taille ?": "Nos paires taillent normalement."
    question "Puis-je annuler une commande ?": "Oui, tant qu'elle est en préparation."
"""


def _projet_faq(tmp_path, spec=SPEC_FAQ, nom="faq"):
    proj = tmp_path / nom
    proj.mkdir()
    (proj / "spec.ml").write_text(spec, encoding="utf-8")
    return proj, compile_project(str(proj / "spec.ml"), str(proj))


def test_la_faq_est_une_liste_de_couples_dans_le_contrat(tmp_path):
    """LE défaut constaté sur `projets/SneakerLab` : les quatre questions
    tenaient dans UNE chaîne `section`, et l'interface les rendait collées en un
    seul paragraphe. Elle était fidèle — c'est le modèle de contenu qui ne
    savait pas dire « une FAQ ». Une structure qu'on ne déclare pas est une
    structure que l'IA doit deviner, et qu'elle reperdra à la reconstruction
    suivante."""
    _proj, contract = _projet_faq(tmp_path)
    assert contract["faq"] == [
        {"question": "Comment choisir ma taille ?",
         "answer": "Nos paires taillent normalement."},
        {"question": "Puis-je annuler une commande ?",
         "answer": "Oui, tant qu'elle est en préparation."}]
    # Et elle ne se confond pas avec les sections : ce sont deux rubriques.
    assert [s["title"] for s in contract["sections"]] == ["À propos"]


def test_lordre_des_questions_est_celui_de_la_spec(tmp_path):
    """Dans une FAQ, l'ordre porte du sens — on répond d'abord à ce qu'on
    demande le plus. Rien ne permettrait de le retrouver après coup."""
    inverse = SPEC_FAQ.replace(
        '    question "Comment choisir ma taille ?": "Nos paires taillent normalement."\n', "")
    inverse += '    question "Comment choisir ma taille ?": "Nos paires taillent normalement."\n'
    _proj, contract = _projet_faq(tmp_path, inverse, nom="ordre")
    assert [q["question"] for q in contract["faq"]] == [
        "Puis-je annuler une commande ?", "Comment choisir ma taille ?"]


def test_le_brief_dit_que_la_faq_est_une_liste_et_jamais_un_paragraphe(tmp_path):
    """L'IA ne lit pas le JSON du contrat, elle lit le brief. Y déposer les
    couples sans dire ce qu'ils sont laisserait refaire exactement le pavé de
    prose qu'on répare."""
    proj, _contract = _projet_faq(tmp_path)
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Questions fréquentes — une LISTE" in brief
    assert "Jamais en un seul paragraphe" in brief
    assert "**Comment choisir ma taille ?**" in brief
    assert "Nos paires taillent normalement." in brief


def test_sans_question_aucun_bloc_faq_dans_le_brief(tmp_path):
    """Le témoin : une rubrique absente de la spec ne doit laisser aucune trace.
    Une FAQ vide annoncée enverrait l'IA construire un accordéon sans contenu."""
    proj, _spec, contract = _fresh_project(tmp_path)
    assert contract["faq"] == []
    brief = (proj / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "Questions fréquentes" not in brief


def test_une_question_sans_reponse_est_refusee(tmp_path):
    """Même exigence que pour une `section` (point 55), même raison : une entrée
    muette à l'écran doit être refusée à la compilation, pas découverte par le
    visiteur."""
    from monl.ast_validator import ASTValidationError, MonlAST
    from monl.parser import parse_monl_string

    spec = SPEC_FAQ.replace('"Nos paires taillent normalement."', '"   "')
    with pytest.raises((ASTValidationError, ValueError)) as refus:
        MonlAST(parse_monl_string(spec)).validate_and_audit()
    assert "question" in str(refus.value)


def test_le_delta_signale_une_question_ajoutee_et_un_texte_reecrit(tmp_path, capsys):
    """POINT 94 : cinquième forme de l'angle mort des points 88 à 91, et la
    première qui ne touche pas aux données. Ajouter une question ne crée aucune
    route, aucun champ — `monl update` répondait « aucun changement d'interface »
    avec un bloc entier à écrire sur l'accueil. L'angle mort existait pour
    `section` depuis le point 55 ; la FAQ y serait tombée le jour de sa
    naissance.

    Le troisième cas est le plus silencieux : un texte RÉÉCRIT ne renomme rien.
    Comparer les seuls titres, c'est l'erreur exacte du point 89."""
    from monl.cli import cmd_update

    proj, _contract = _projet_faq(tmp_path, nom="delta")
    capsys.readouterr()
    evolue = (SPEC_FAQ.replace('"Atelier fondé en 2015."', '"Atelier fondé en 2015, et agrandi depuis."')
              + '    question "Livrez-vous en Europe ?": "Oui, sous 3 à 5 jours."\n')
    (proj / "spec.ml").write_text(evolue, encoding="utf-8")

    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "aucun changement d'interface" not in sortie, sortie
    assert "contenu ajouté : question « Livrez-vous en Europe ? »" in sortie, sortie
    assert "contenu réécrit : section « À propos »" in sortie, sortie
    # Rien d'autre n'a bougé : ni route, ni champ.
    assert "route ajoutée" not in sortie, sortie
    assert "champ ajouté" not in sortie, sortie
    brief = (proj / "FRONTEND_UPDATE_PROMPT.md").read_text(encoding="utf-8")
    assert "Contenu éditorial AJOUTÉ" in brief
    assert "Contenu RÉÉCRIT" in brief
