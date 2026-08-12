app CodexShop

# Spécification générée par le dialogue guidé monl (déterministe, sans IA).
# Brief du projet : Boutique en ligne de test pour valider le pipeline monl avec Codex comme agent frontend.

entity Product
    name: String
    price: Money
    description: Text
    imageUrl: String
    stock: Integer
    category: String

entity Order
    total: Money
    status: String
    reference: String
    fulfillmentStatus: String
    trackingNumber: String
    creeLe: DateTime

entity Customer
    displayName: String
    email: Email
    address: Text
    postalCode: String
    city: String
    country: String

entity LigneOrder
    quantite: Integer
    sousTotal: Money

relation Customer hasMany Order
relation Customer hasOne Customer
relation Order hasMany LigneOrder
relation Product hasMany LigneOrder

actor Admin
actor Customer selfRegister

capability auth
    identifier: email

rule Product.name required
rule Customer.displayName required
rule Customer.email required
rule Customer.address required
rule Customer.postalCode required
rule Customer.city required
rule Customer.country required
rule LigneOrder.quantite required
rule Product.price min 1
rule Product.Read public
rule Order.Read ownedBy Customer
rule Order.Update ownedBy Customer
rule Customer.Read ownedBy Customer
rule Customer.Update ownedBy Customer
rule LigneOrder.Read ownedBy Order
rule LigneOrder.Update ownedBy Order

# POINT 89 : la date d'arrivée, écrite par le serveur à la
# création et jamais ensuite. Elle disparaît des corps de
# requête : une date qu'on se donne à soi-même n'atteste de
# rien, et un carnet de Order où chacun choisit ses dates
# ne dit plus dans quel ordre honorer.
rule Order.creeLe timestamp

# POINT 79 : le montant est CALCULÉ PAR LE SERVEUR — prix au
# catalogue (Product.price) multiplié par la quantité. Le
# champ LigneOrder.sousTotal disparaît donc des corps de requête,
# à la création comme à la modification. Sans ce calcul,
# l'acheteur fixerait lui-même ce qu'il règle : il devient
# propriétaire de ce qu'il crée, donc le payeur.
rule LigneOrder.sousTotal derivedFrom Product.price by quantite

# POINT 82 : le total du panier est la SOMME de ses lignes,
# recalculée par le serveur à chaque ligne ajoutée, modifiée
# ou supprimée. Sommer un sous-total que le navigateur
# écrirait serait la faille du point 77 en une addition de
# plus : le compilateur le refuse.
rule Order.total sumOf LigneOrder.sousTotal

# POINT 85 : ce plancher n'est pas décoratif — c'est lui qui
# arme la vérification de disponibilité ci-dessous. Sans lui,
# le décompte passerait sous zéro et le stock mentirait.
rule Product.stock min 0

# POINT 86 : le stock suit les commandes, et retire CE QUE LE
# CLIENT A DEMANDÉ — pas une constante. Commander plus que le
# stock disponible répond 409, sans rien décompter.
rule LigneOrder.Create decrements Product.stock by quantite

# Encaissement : le champ nommé porte le MONTANT, donc
# l'entité à encaisser. Deux routes en découlent —
# POST /entite/{id}/paiement (aucun corps : le montant est
# relu en base) et POST /paiement/webhook, dont la
# signature est vérifiée. Sans STRIPE_SECRET_KEY, elles
# répondent 503 ; le reste de l'application fonctionne.
rule Order.total payable

# Une commande sans fiche client complète ne peut pas être expédiée. Le
# backend vérifie donc l'existence de la fiche AVANT de créer la commande.
rule Order.Create requiresOwn Customer

# Ces listes deviennent des choix validés par l'API, pas du texte libre où
# une faute de frappe créerait une nouvelle catégorie ou un nouvel état.
rule Product.category oneOf "Carnets", "Stylos", "Encres"
rule Order.status oneOf "À confirmer", "Annulée"
rule Order.status "Annulée" releases LigneOrder
rule Order.fulfillmentStatus oneOf "À préparer", "En préparation", "Expédiée", "Livrée"
rule Order.reference numbered "CMD-{YYYY}-{NNNN}"
rule Order.fulfillmentStatus writableAfterPayment Admin
rule Order.trackingNumber writableAfterPayment Admin


workflow ManageProduct for Admin
    Create Product
    Read Product
    Update Product
    Delete Product

workflow ManageOrder for Customer
    Create Order
    Read Order
    Update Order

workflow ManageCustomer for Customer
    Create Customer
    Read Customer
    Update Customer

workflow ManageLigneOrder for Customer
    Create LigneOrder
    Read LigneOrder
    Update LigneOrder

workflow BrowseAdmin for Admin
    Read Order
    Read LigneOrder
    Read Customer

workflow BrowseCustomer for Customer
    Read Product

seed Product
    name: "Carnet Lin Ivoire", price: 24.0, description: "Reliure en lin naturel, 160 pages lignées sur papier ivoire 100 g et ouverture parfaitement à plat.", imageUrl: "assets/carnet-lin.webp", stock: 18, category: "Carnets"
    name: "Carnet Pointillé A6", price: 14.0, description: "Un format de poche précis, 128 pages pointillées et deux rubans pour garder plusieurs idées en cours.", imageUrl: "assets/carnet-pointille-a6.webp", stock: 26, category: "Carnets"
    name: "Cahier Atelier A4", price: 29.0, description: "Grand cahier cousu de 96 pages vierges, pensé pour les croquis, plans et notes qui demandent de l'espace.", imageUrl: "assets/cahier-atelier-a4.webp", stock: 12, category: "Carnets"
    name: "Journal Cinq Ans", price: 32.0, description: "Une page par date et cinq lignes par année pour voir les habitudes, projets et saisons se transformer.", imageUrl: "assets/journal-cinq-ans.webp", stock: 11, category: "Carnets"
    name: "Stylo Plume Noyer", price: 42.0, description: "Corps tourné en noyer, attributs en laiton satiné et plume acier moyenne pour une écriture souple au quotidien.", imageUrl: "assets/stylo-noyer.webp", stock: 9, category: "Stylos"
    name: "Stylo Bille Laiton", price: 22.0, description: "Un corps équilibré en laiton brossé qui se patine avec l'usage, compatible avec les recharges G2.", imageUrl: "assets/stylo-bille-laiton.webp", stock: 15, category: "Stylos"
    name: "Porte-Mine Architecte", price: 18.0, description: "Mine 0,7 mm, mécanisme précis et prise hexagonale pour annoter, dessiner et mesurer sans glisser.", imageUrl: "assets/porte-mine-architecte.webp", stock: 23, category: "Stylos"
    name: "Roller Bleu Profond", price: 28.0, description: "La fluidité d'une plume dans un corps compact, avec une recharge bleu profond à séchage rapide.", imageUrl: "assets/roller-bleu-profond.webp", stock: 17, category: "Stylos"
    name: "Encre Bleu Nuit", price: 16.5, description: "Flacon de 50 ml, bleu dense aux nuances discrètes, séchage rapide et formule sans acide.", imageUrl: "assets/encre-bleu-nuit.webp", stock: 34, category: "Encres"
    name: "Encre Sépia", price: 16.5, description: "Une teinte brune chaleureuse inspirée des archives, adaptée à la correspondance comme au dessin.", imageUrl: "assets/encre-sepia.webp", stock: 21, category: "Encres"
    name: "Encre Vert Herbier", price: 16.5, description: "Vert profond légèrement grisé, lisible sur papier ivoire et suffisamment nuancé pour la calligraphie.", imageUrl: "assets/encre-vert-herbier.webp", stock: 19, category: "Encres"
    name: "Encre Bordeaux", price: 16.5, description: "Rouge sombre et feutré pour les titres, signatures et annotations qui doivent rester élégantes.", imageUrl: "assets/encre-bordeaux.webp", stock: 16, category: "Encres"

landing
    brief: "Boutique de papeterie contemporaine consacrée au geste d'écrire : carnets tactiles, stylos durables et encres profondes ; identité éditoriale dense, bleu encre, ivoire, noyer et laiton ; photographies de produits cohérentes, nombreux blocs de conseil et catalogue généreux."
    section "À propos de la boutique": "Chaque référence est testée sur un vrai bureau : qualité du papier, équilibre en main, réparabilité et cohérence des matières."
    section "Livraison et retours": "Préparation sous 48 heures, livraison suivie en 2 à 4 jours ouvrés et retours gratuits sous 30 jours."
    section "Questions fréquentes": "Conseils sur le papier plume, les recharges standard, l'entretien des instruments et le suivi des commandes."
