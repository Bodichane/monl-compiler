"""Business templates of the catalog: real compilation and contract promises.

SELF-CONTAINED by construction. The first version read
`projets/CommunauteHub` and `projets/GestionPro` — but `/projets/` is ignored
by git: the suite passed on its author's machine and failed on any fresh
clone, CI included (6 `FileNotFoundError`). A test cannot depend on what the
repository does not carry. The specs therefore live here, and each test
compiles its own.
"""

import json

import pytest

from monl.ast_validator import MonlAST
from monl.frontend_contract import generate_frontend_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

COMMUNITY = """app CommunauteHub

entity Article
    titre: String
    corps: Text
    auteur: String
    status: String
    publieLe: Date

entity Post
    content: Text
    likes: Integer
    status: String

entity Like
    note: String

entity ArticleReport
    reason: Text
    status: String

entity PostReport
    reason: Text
    status: String

actor Member selfRegister
actor Moderator

relation Member hasMany Article
relation Member hasMany Post
relation Member hasMany Like
relation Post hasMany Like
relation Member hasMany ArticleReport
relation Member hasMany PostReport

rule Article.status oneOf "draft", "published"
rule Post.status oneOf "published", "hidden"
rule Article.Read publicWhen status "published"
rule Post.Read publicWhen status "published"
rule Article.Read sharedBy Moderator
rule Post.Read sharedBy Moderator
rule Like.Create oncePer Member, Post
rule Like.Create increments Post.likes by 1
rule Article.Update sharedBy Member, Moderator
rule ArticleReport.status oneOf "open", "resolved"
rule PostReport.status oneOf "open", "resolved"

workflow Ecrire for Member
    Create Article
    Read Article
    Update Article
    Create Post
    Read Post

workflow Reagir for Member
    Create Like
    Create ArticleReport
    Create PostReport

workflow Moderer for Moderator
    Read Article
    Update Article
    Read Post
    Update Post
    Read ArticleReport
    Update ArticleReport
    Read PostReport
    Update PostReport

seed Article
    titre: "Le journal du terrain", corps: "Notes et retours d'expérience publiés après relecture.", auteur: "Camille", status: "published", publieLe: "2026-08-01"
    titre: "Brouillon de la rentrée", corps: "Ce texte reste invisible tant qu'il n'est pas relu.", auteur: "Camille", status: "draft", publieLe: "2026-08-10"

seed Post
    content: "Premier fil de la communauté — présentez-vous ici.", likes: 24, status: "published"
    content: "Quels outils utilisez-vous au quotidien ?", likes: 51, status: "published"

landing
    brief: "Un média communautaire éditorial réunissant articles, discussions, modération et réactions."
    section "La ligne éditoriale": "Chaque article est relu avant publication.¶Les brouillons restent visibles de leur seul auteur."
    question "Qui peut masquer un contenu ?": "Les modérateurs, qui continuent de le voir après l'avoir masqué."
"""

MANAGEMENT = """app GestionPro

entity Product
    nom: String
    prix: Money
    stockQuantity: Integer

entity StockReceipt
    quantity: Integer

entity StockIssue
    quantity: Integer

entity Budget
    intitule: String
    spent: Money

entity Expense
    libelle: String
    amount: Money

entity Purchase
    total: Money
    deliveryStatus: String
    trackingNumber: String

entity PurchaseLine
    quantity: Integer
    total: Money

actor Buyer selfRegister
actor Seller

relation Product hasMany StockReceipt
relation Product hasMany StockIssue
relation Seller hasMany Budget
relation Budget hasMany Expense
relation Buyer hasMany Purchase
relation Purchase hasMany PurchaseLine
relation Product hasMany PurchaseLine

rule StockReceipt.quantity required
rule StockIssue.quantity required
rule StockReceipt.Create increments Product.stockQuantity by quantity
rule StockIssue.Create decrements Product.stockQuantity by quantity
rule Budget.Read ownedBy Seller
rule Budget.Update ownedBy Seller
rule Expense.Read ownedBy Budget
rule Expense.Update ownedBy Budget
rule Budget.spent sumOf Expense.amount
rule PurchaseLine.quantity required
rule Product.stockQuantity min 0
rule PurchaseLine.total derivedFrom Product.prix by quantity
rule Purchase.total sumOf PurchaseLine.total
rule Purchase.total payable
rule Purchase.Read ownedBy Buyer
rule Purchase.Update ownedBy Buyer
rule PurchaseLine.Read ownedBy Purchase
rule PurchaseLine.Update ownedBy Purchase
rule Purchase.deliveryStatus writableAfterPayment Seller
rule Purchase.trackingNumber writableAfterPayment Seller

workflow Acheter for Buyer
    Create Purchase
    Read Purchase
    Create PurchaseLine
    Read PurchaseLine

workflow Gerer for Seller
    Create Product
    Read Product
    Create StockReceipt
    Create StockIssue
    Create Budget
    Read Budget
    Update Budget
    Create Expense
    Read Expense
    Update Expense

seed Product
    nom: "Établi modulaire", prix: 249.0, stockQuantity: 12
    nom: "Servante d'atelier", prix: 89.5, stockQuantity: 30

landing
    brief: "Un espace opérationnel qui suit stock, budgets et commandes jusqu'à la livraison."
    section "Comment le stock est tenu": "Chaque entrée et chaque sortie porte sa quantité.¶Le stock ne passe jamais sous zéro."
    question "Qui met à jour la livraison ?": "Le vendeur, après le règlement, par une route dédiée."
"""


def _compiler(source, path):
    """The real pipeline: parser → validator → generator → contract."""
    normalise = MonlAST(parse_monl_string(source), base_dir=str(path)).validate_and_audit()
    generator = MonlSecureGenerator(normalise, output_dir=str(path))
    generator.generate_all()
    contract = generate_frontend_contract(normalise, generator, str(path))
    return normalise, contract


@pytest.fixture(scope="module")
def community(tmp_path_factory):
    path = tmp_path_factory.mktemp("communaute")
    return _compiler(COMMUNITY, path) + (path,)


@pytest.fixture(scope="module")
def management(tmp_path_factory):
    path = tmp_path_factory.mktemp("gestion")
    return _compiler(MANAGEMENT, path) + (path,)


@pytest.mark.parametrize("source", [COMMUNITY, MANAGEMENT],
                         ids=["CommunauteHub", "GestionPro"])
def test_each_business_template_produces_a_valid_backend(source, tmp_path):
    _normalise, contract = _compiler(source, tmp_path)
    assert contract["business_rules"] is not None
    compile((tmp_path / "app.py").read_text(encoding="utf-8"),
            str(tmp_path / "app.py"), "exec")
    assert (tmp_path / "frontend_contract.json").exists()


def test_community_filters_content_and_moderates(community):
    normalise, _contract, _path = community
    security = normalise["security"]
    assert security["public_conditions"]["Article.Read"] == {
        "field": "status", "value": "published"}
    assert security["public_conditions"]["Post.Read"] == {
        "field": "status", "value": "published"}
    assert {"ArticleReport", "PostReport"} <= set(normalise["schema"]["entities"])


def test_the_moderator_pierces_the_publication_condition(community):
    """POINT 116: without this exemption, hiding content also took it away from
    the moderator who had just hidden it."""
    normalise, _contract, path = community
    assert normalise["security"]["access_supervisors"]["Post.Read"] == ["Moderator"]
    generated = (path / "app.py").read_text(encoding="utf-8")
    assert "get_optional_identity" in generated
    assert '_ident.get(\'actor\') in {"Moderator"}' in generated


def test_likes_are_unique_per_account_and_target(community):
    normalise, _contract, path = community
    rules = {r["trigger_entity"]: r["parents"]
              for r in normalise["security"]["once_per"]}
    assert rules["Like"] == ["Member", "Post"]
    assert "idx_once_per_like" in (path / "app.py").read_text(encoding="utf-8")


def test_management_carries_business_calculations(management):
    normalise, _contract, _path = management
    inventory = normalise["security"]["reputation_rules"]
    assert {(r["trigger_entity"], r["direction"], r["amount_field"])
            for r in inventory} == {
        ("StockReceipt", "increments", "quantity"),
        ("StockIssue", "decrements", "quantity"),
    }
    assert {"entity": "Budget", "field": "spent",
            "source_entity": "Expense", "source_field": "amount"} in \
        normalise["security"]["aggregated_fields"]


def test_purchase_exposes_calculation_payment_and_post_payment_delivery(management):
    normalise, contract, path = management
    security = normalise["security"]
    assert security["payable_fields"] == [{"entity": "Purchase", "field": "total"}]
    assert security["writable_after_payment"]["Purchase"]["actor"] == "Seller"
    route = next(r for r in contract["routes"]
                 if r["path"] == "/purchase/{id}/apres-paiement")
    assert route["method"] == "PUT"
    assert route["allowed_actors"] == ["Seller"]
    assert set(route["request_fields"]) == {"deliveryStatus", "trackingNumber"}
    assert "PUT /purchase/{id}/apres-paiement" in \
        (path / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")


def test_the_community_contract_carries_both_business_rules(community):
    _normalise, _contract, path = community
    contract = json.loads(
        (path / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contract["business_rules"]["public_when"]["Post.Read"]["value"] == "published"
    assert {"trigger_entity": "Like", "parents": ["Member", "Post"]} in \
        contract["business_rules"]["once_per"]
