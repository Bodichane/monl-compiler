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
    # Brique 16 (point 89) : l'instant où la commande est née. Écrit par le
    # serveur, jamais par le client — voir la règle plus bas.
    placedAt: DateTime

# Une commande contient plusieurs LIGNES : c'est ce qui la distingue d'un panier
# à un seul article. Chaque ligne dit quel produit et en quelle quantité ; son
# sous-total est calculé par le serveur, et le total de la commande en est la
# somme (briques 10, 11 et 12 — points 77, 81 et 82).
entity OrderLine
    quantity: Integer
    subTotal: Money

relation Customer hasMany Order
relation Order hasMany OrderLine
# Ce que la ligne porte : c'est cette relation qui permet au SERVEUR de lire
# le prix au catalogue. Sans elle, le montant ne pourrait venir que du client.
relation Product hasMany OrderLine

actor Customer selfRegister
actor ShopManager

rule Product.name required
rule Product.price min 0
rule Product.stock min 0
rule Product.Read public
rule Order.Read ownedBy Customer

# PROPRIÉTÉ TRANSITIVE (point 81) : une ligne appartient à qui possède sa
# commande. Sans cette règle, monl refuserait de compiler — une ligne dont
# personne n'est propriétaire serait ajoutable au panier de n'importe qui.
rule OrderLine.Read ownedBy Order
rule OrderLine.Update ownedBy Order
rule OrderLine.Delete ownedBy Order

# La quantité est le seul chiffre que le client fournit, et elle est obligatoire
# (sans quoi le calcul ci-dessous porterait sur du vide).
rule OrderLine.quantity required

# Le sous-total de la ligne est CALCULÉ PAR LE SERVEUR : prix du produit au
# catalogue multiplié par la quantité. Il disparaît donc des corps de requête, à
# la création comme à la modification. Sans cette règle, le client envoyait
# lui-même le montant — et `payable` le relisait en base en croyant le tenir de
# source sûre : deux exploits de trois requêtes suffisaient à encaisser un
# centime pour des centaines d'euros de marchandise (points 77 et 78).
rule OrderLine.subTotal derivedFrom Product.price by quantity

# Le total de la commande est la SOMME de ses lignes, recalculée par le serveur à
# chaque ligne ajoutée, modifiée ou supprimée (point 82). Sommer un sous-total
# que le client écrirait serait la même faille en une addition de plus : monl le
# refuse à la compilation.
rule Order.totalAmount sumOf OrderLine.subTotal

# BRIQUE 14 (point 86) : le stock suit les commandes. 'decrements' ne savait
# retirer qu'une CONSTANTE ('by 3') — il retire désormais CE QUE LE CLIENT A
# DEMANDÉ. Et il refuse de descendre sous le plancher déclaré plus haut par
# 'rule Product.stock min 0' : sans ce garde-fou, la boutique afficherait -3
# paires disponibles après avoir encaissé les huit qu'elle n'avait pas. Le
# plancher n'est pas câblé dans le compilateur — il est DÉCLARÉ dans la spec,
# et c'est sa présence qui arme la vérification.
rule OrderLine.Create decrements Product.stock by quantity

# Le champ nommé porte le MONTANT : c'est donc la commande qu'on encaisse.
# monl en dérive POST /order/{id}/paiement (aucun corps — le montant est relu
# en base à chaque appel) et POST /paiement/webhook, dont la signature est
# vérifiée avant toute écriture. Sans STRIPE_SECRET_KEY, ces deux routes
# répondent 503 en nommant la variable ; le reste de la boutique fonctionne.
# Depuis le point 79, cette règle EXIGE que le montant soit calculé par le
# serveur : un montant que le payeur peut écrire fait échouer la compilation.
rule Order.totalAmount payable

# Brique 16 (point 89) : la date d'arrivée de la commande, écrite par le serveur
# à la création et jamais ensuite. Elle disparaît des corps de requête — création
# ET modification : une date qu'on se donne à soi-même n'atteste de rien, et un
# carnet où chacun choisit ses dates ne dit plus dans quel ordre honorer.
# Format ISO 8601 UTC, à la milliseconde : trier ces chaînes, c'est trier le
# temps, sans conversion et sans ex aequo entre deux commandes rapprochées.
rule Order.placedAt timestamp

workflow BrowseShop for Customer
    Read Product
    Create Order
    Read Order
    Create OrderLine
    Read OrderLine
    Update OrderLine
    Delete OrderLine

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
