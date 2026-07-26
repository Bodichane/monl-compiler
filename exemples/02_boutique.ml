app AtelierBoutique

# ─────────────────────────────────────────────────────────────────────
# BOUTIQUE E-COMMERCE COMPLÈTE — mobilier & objets design.
# Catalogue public (archétype boutique : prix, stock, bouton d'achat) +
# gestion vendeur + commandes. Les données de démonstration remplissent la
# vitrine dès l'ouverture, avec de vraies images produit.
# ─────────────────────────────────────────────────────────────────────

entity Product
    name: String
    description: Text
    imageUrl: String
    category: String
    price: Money
    stock: Integer

entity Order
    reference: UUID
    totalAmount: Money
    status: String

relation Customer hasMany Order

actor Customer selfRegister
actor ShopManager

rule Product.name required
rule Product.price min 0
rule Product.stock min 0
rule Product.Read public

workflow BrowseShop for Customer
    Read Product
    Create Order

workflow ManageShop for ShopManager
    Create Product
    Update Product
    Delete Product
    Update Order.status

# Catalogue de démonstration : 6 produits avec prix, stock varié (dont un
# épuisé, un en stock faible) et images réelles.
seed Product
    name: "Chaise Ligne", category: "Assises", price: 249.90, stock: 12, description: "Chêne massif et cannage tressé main.", imageUrl: "https://picsum.photos/seed/chaise/700/560"
    name: "Lampe Arc", category: "Luminaires", price: 189.00, stock: 4, description: "Laiton brossé, abat-jour orientable.", imageUrl: "https://picsum.photos/seed/lampe/700/560"
    name: "Table Onde", category: "Tables", price: 1200.00, stock: 0, description: "Édition limitée, plateau en frêne ondé.", imageUrl: "https://picsum.photos/seed/table/700/560"
    name: "Étagère Grid", category: "Rangements", price: 340.00, stock: 8, description: "Structure acier modulaire.", imageUrl: "https://picsum.photos/seed/etagere/700/560"
    name: "Fauteuil Coque", category: "Assises", price: 520.00, stock: 3, description: "Assise moulée, piètement compas.", imageUrl: "https://picsum.photos/seed/fauteuil/700/560"
    name: "Vase Galet", category: "Objets", price: 68.00, stock: 20, description: "Grès émaillé, pièce unique tournée main.", imageUrl: "https://picsum.photos/seed/vase/700/560"

landing
    brief: "AtelierBoutique édite du mobilier et des objets design en séries limitées. Parcourez notre catalogue et commandez en ligne."
