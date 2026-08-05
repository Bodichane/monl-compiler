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

# BRIQUE 21 (point 100) : le produit est ce qu'on MONTRE, la variante est ce
# qu'on VEND. Une chaise existe en chêne et en noyer : deux prix, deux stocks,
# une seule fiche au catalogue. C'est le modèle qu'un vrai marchand tient (un
# stock par référence vendable), et il ne demande AUCUNE syntaxe nouvelle au
# compilateur — seulement une relation. Il est resté hors de portée jusqu'au
# point 99 pour deux raisons distinctes, toutes deux corrigées : la clé
# étrangère d'un enfant de table métier recevait l'id du COMPTE créateur au lieu
# de celui du produit (point 99), et un bloc 'seed' ne savait pas rattacher un
# enfant à son parent (point 100) — la vitrine se serait ouverte sur un
# catalogue dont rien n'était commandable.
entity Variant
    finish: String
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
# La variante appartient à son produit. Cette relation ne désigne AUCUN
# propriétaire : c'est un lien de catalogue, et sa colonne porte l'id du
# produit — pas celui du vendeur qui l'a créée (point 99).
relation Product hasMany Variant
# Ce que la ligne porte : c'est cette relation qui permet au SERVEUR de lire
# le prix au catalogue. Elle vise la VARIANTE et non le produit, puisque c'est
# la variante qui porte le prix et le stock.
relation Variant hasMany OrderLine

actor Customer selfRegister
actor ShopManager

rule Product.name required
rule Product.Read public
rule Variant.Read public
rule Variant.price min 0
# Ce plancher-ci ARME la vérification de disponibilité du décompte plus bas
# (point 86) : sans lui, la boutique vendrait des paires qu'elle n'a pas.
rule Variant.stock min 0
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
rule OrderLine.subTotal derivedFrom Variant.price by quantity

# Le total de la commande est la SOMME de ses lignes, recalculée par le serveur à
# chaque ligne ajoutée, modifiée ou supprimée (point 82). Sommer un sous-total
# que le client écrirait serait la même faille en une addition de plus : monl le
# refuse à la compilation.
rule Order.totalAmount sumOf OrderLine.subTotal

# BRIQUE 14 (point 86) : le stock suit les commandes. 'decrements' ne savait
# retirer qu'une CONSTANTE ('by 3') — il retire désormais CE QUE LE CLIENT A
# DEMANDÉ. Et il refuse de descendre sous le plancher déclaré plus haut par
# 'rule Variant.stock min 0' : sans ce garde-fou, la boutique afficherait -3
# paires disponibles après avoir encaissé les huit qu'elle n'avait pas. Le
# plancher n'est pas câblé dans le compilateur — il est DÉCLARÉ dans la spec,
# et c'est sa présence qui arme la vérification.
rule OrderLine.Create decrements Variant.stock by quantity

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
    Read Variant
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
    Create Variant
    Update Variant
    Delete Variant
    Update Order.status

# Catalogue de démonstration : 6 produits avec images réelles. Le prix et le
# stock ne vivent plus ici — ils sont portés par les variantes ci-dessous.
seed Product
    name: "Chaise Ligne", category: "Assises", description: "Chêne massif et cannage tressé main.", imageUrl: "https://picsum.photos/seed/chaise/700/560"
    name: "Lampe Arc", category: "Luminaires", description: "Laiton brossé, abat-jour orientable.", imageUrl: "https://picsum.photos/seed/lampe/700/560"
    name: "Table Onde", category: "Tables", description: "Édition limitée, plateau en frêne ondé.", imageUrl: "https://picsum.photos/seed/table/700/560"
    name: "Étagère Grid", category: "Rangements", description: "Structure acier modulaire.", imageUrl: "https://picsum.photos/seed/etagere/700/560"
    name: "Fauteuil Coque", category: "Assises", description: "Assise moulée, piètement compas.", imageUrl: "https://picsum.photos/seed/fauteuil/700/560"
    name: "Vase Galet", category: "Objets", description: "Grès émaillé, pièce unique tournée main.", imageUrl: "https://picsum.photos/seed/vase/700/560"

# BRIQUE 21 (point 100) : chaque bloc rattache ses lignes à UN produit, désigné
# par son nom. Un rang aurait été illisible et se serait décalé à la première
# insertion ; monl refuse à la compilation une désignation qui ne correspond à
# rien, ou qui correspond à deux lignes. Les blocs 'seed Variant' viennent
# APRÈS 'seed Product' — les données sont insérées dans l'ordre déclaré, et le
# compilateur refuse l'ordre inverse plutôt que de le corriger en silence.
#
# Stock varié à dessein, comme avant : une finition épuisée (Table Onde en
# noyer), une en stock faible (Fauteuil Coque), pour que la vitrine montre les
# deux cas dès l'ouverture.
seed Variant for Product.name "Chaise Ligne"
    finish: "Chêne naturel", price: 249.90, stock: 12
    finish: "Noyer fumé", price: 289.00, stock: 5

seed Variant for Product.name "Lampe Arc"
    finish: "Laiton brossé", price: 189.00, stock: 4

seed Variant for Product.name "Table Onde"
    finish: "Frêne ondé", price: 1200.00, stock: 2
    finish: "Noyer massif", price: 1450.00, stock: 0

seed Variant for Product.name "Étagère Grid"
    finish: "Acier noir", price: 340.00, stock: 8
    finish: "Acier blanc", price: 340.00, stock: 6

seed Variant for Product.name "Fauteuil Coque"
    finish: "Velours ocre", price: 520.00, stock: 3

seed Variant for Product.name "Vase Galet"
    finish: "Grès émaillé", price: 68.00, stock: 20

landing
    brief: "AtelierBoutique édite du mobilier et des objets design en séries limitées. Parcourez notre catalogue et commandez en ligne."
