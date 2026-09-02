"""Modèles métier du catalogue : compilation réelle et promesses du contrat.

AUTONOMES par construction. La première version lisait `projets/CommunauteHub`
et `projets/GestionPro` — or `/projets/` est ignoré par git : la suite passait
sur le poste de son auteur et échouait sur tout clone neuf, CI comprise
(6 `FileNotFoundError`). Un test ne peut pas dépendre de ce que le dépôt ne
transporte pas. Les specs vivent donc ici, et chaque test compile la sienne.
"""

import json

import pytest

from monl.ast_validator import MonlAST
from monl.frontend_contract import generate_frontend_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_string

COMMUNAUTE = """app CommunauteHub

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

GESTION = """app GestionPro

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


def _compiler(source, chemin):
    """Le vrai pipeline : parseur → validateur → générateur → contrat."""
    normalise = MonlAST(parse_monl_string(source), base_dir=str(chemin)).validate_and_audit()
    generateur = MonlSecureGenerator(normalise, output_dir=str(chemin))
    generateur.generate_all()
    contrat = generate_frontend_contract(normalise, generateur, str(chemin))
    return normalise, contrat


@pytest.fixture(scope="module")
def communaute(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("communaute")
    return _compiler(COMMUNAUTE, chemin) + (chemin,)


@pytest.fixture(scope="module")
def gestion(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("gestion")
    return _compiler(GESTION, chemin) + (chemin,)


@pytest.mark.parametrize("source", [COMMUNAUTE, GESTION],
                         ids=["CommunauteHub", "GestionPro"])
def test_chaque_modele_metier_produit_un_backend_valide(source, tmp_path):
    _normalise, contrat = _compiler(source, tmp_path)
    assert contrat["business_rules"] is not None
    compile((tmp_path / "app.py").read_text(encoding="utf-8"),
            str(tmp_path / "app.py"), "exec")
    assert (tmp_path / "frontend_contract.json").exists()


def test_communaute_filtre_les_contenus_et_modere(communaute):
    normalise, _contrat, _chemin = communaute
    securite = normalise["security"]
    assert securite["public_conditions"]["Article.Read"] == {
        "field": "status", "value": "published"}
    assert securite["public_conditions"]["Post.Read"] == {
        "field": "status", "value": "published"}
    assert {"ArticleReport", "PostReport"} <= set(normalise["schema"]["entities"])


def test_le_moderateur_transperce_la_condition_de_publication(communaute):
    """POINT 116 : sans cette exemption, masquer un contenu le retirait aussi
    au modérateur qui venait de le masquer."""
    normalise, _contrat, chemin = communaute
    assert normalise["security"]["access_supervisors"]["Post.Read"] == ["Moderator"]
    genere = (chemin / "app.py").read_text(encoding="utf-8")
    assert "get_optional_identity" in genere
    assert '_ident.get(\'actor\') in {"Moderator"}' in genere


def test_les_likes_sont_uniques_par_compte_et_par_cible(communaute):
    normalise, _contrat, chemin = communaute
    regles = {r["trigger_entity"]: r["parents"]
              for r in normalise["security"]["once_per"]}
    assert regles["Like"] == ["Member", "Post"]
    assert "idx_once_per_like" in (chemin / "app.py").read_text(encoding="utf-8")


def test_gestion_porte_les_calculs_metier(gestion):
    normalise, _contrat, _chemin = gestion
    inventaire = normalise["security"]["reputation_rules"]
    assert {(r["trigger_entity"], r["direction"], r["amount_field"])
            for r in inventaire} == {
        ("StockReceipt", "increments", "quantity"),
        ("StockIssue", "decrements", "quantity"),
    }
    assert {"entity": "Budget", "field": "spent",
            "source_entity": "Expense", "source_field": "amount"} in \
        normalise["security"]["aggregated_fields"]


def test_achat_expose_calcul_paiement_et_livraison_post_paiement(gestion):
    normalise, contrat, chemin = gestion
    securite = normalise["security"]
    assert securite["payable_fields"] == [{"entity": "Purchase", "field": "total"}]
    assert securite["writable_after_payment"]["Purchase"]["actor"] == "Seller"
    route = next(r for r in contrat["routes"]
                 if r["path"] == "/purchase/{id}/apres-paiement")
    assert route["method"] == "PUT"
    assert route["allowed_actors"] == ["Seller"]
    assert set(route["request_fields"]) == {"deliveryStatus", "trackingNumber"}
    assert "PUT /purchase/{id}/apres-paiement" in \
        (chemin / "docs/FRONTEND_PROMPT.md").read_text(encoding="utf-8")


def test_le_contrat_de_communaute_transporte_les_deux_regles_metier(communaute):
    _normalise, _contrat, chemin = communaute
    contrat = json.loads(
        (chemin / "frontend_contract.json").read_text(encoding="utf-8"))
    assert contrat["business_rules"]["public_when"]["Post.Read"]["value"] == "published"
    assert {"trigger_entity": "Like", "parents": ["Member", "Post"]} in \
        contrat["business_rules"]["once_per"]
