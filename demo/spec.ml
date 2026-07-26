app AtelierVelo

# Spécification générée par le dialogue guidé monl (déterministe, sans IA).
# Brief du projet : Une boutique d'accessoires vélo, réparation et pièces détachées.

entity Product
    name: String
    price: Money
    description: Text
    imageUrl: String
    category: String
    stock: Integer

entity Order
    total: Money
    status: String
    note: Text

entity Customer
    displayName: String

relation Customer hasMany Order

actor Admin
actor Customer selfRegister

rule Product.name required
rule Order.total required
rule Customer.displayName required
rule Product.Read public
rule Order.Update ownedBy Customer
rule Order.Delete ownedBy Customer

workflow ManageProduct for Admin
    Create Product
    Read Product
    Update Product
    Delete Product

workflow ManageOrder for Customer
    Create Order
    Read Order
    Update Order
    Delete Order

workflow ManageCustomer for Customer
    Create Customer
    Read Customer
    Update Customer
    Delete Customer

workflow BrowseAdmin for Admin
    Read Order

workflow BrowseCustomer for Customer
    Read Product

seed Product
    name: "Casque urbain Vent", price: 74.0, description: "Coque in-mold, aération 18 canaux, taille réglable 54-60 cm.", imageUrl: "diagrammes/casque.svg", category: "Sécurité", stock: 12
    name: "Éclairage Nuit 600", price: 45.0, description: "Phare avant 600 lumens, autonomie 12 h, fixation sans outil.", imageUrl: "diagrammes/eclairage.svg", category: "Sécurité", stock: 26
    name: "Chaîne 11 vitesses", price: 32.5, description: "116 maillons, traitement anticorrosion, attache rapide fournie.", imageUrl: "diagrammes/chaine.svg", category: "Transmission", stock: 40
    name: "Plateau 50 dents", price: 58.0, description: "Aluminium usiné, entraxe 110 mm, compatible double plateau.", imageUrl: "diagrammes/plateau.svg", category: "Transmission", stock: 7
    name: "Pneu Pavé 700x32", price: 39.9, description: "Gomme renforcée, bande antiperforation, flancs réfléchissants.", imageUrl: "diagrammes/pneu.svg", category: "Roues", stock: 34
    name: "Sacoche Atelier 14 L", price: 89.0, description: "Toile enduite, fixation porte-bagages, poche à outils intérieure.", imageUrl: "diagrammes/sacoche.svg", category: "Bagagerie", stock: 9
    name: "Kit outils Multi-8", price: 24.0, description: "Huit embouts, corps acier, étui coton — l'essentiel en poche.", imageUrl: "diagrammes/outils.svg", category: "Atelier", stock: 55
    name: "Révision complète", price: 95.0, description: "Prestation atelier : transmission, freins, roues, réglages, 48 h.", imageUrl: "diagrammes/revision.svg", category: "Atelier", stock: 20

# Identité visuelle IMPOSÉE par la spec (et non devinée par le compilateur) :
# le thème 'atelier' est celui du catalogue d'un réparateur — papier
# quadrillé, trait fin, accent haute visibilité. Épinglé ici, il devient
# contraignant : le smoke test vérifie que le frontend l'applique vraiment.
ui Product
    theme: atelier

landing
    brief: "Une boutique d'accessoires vélo, réparation et pièces détachées."
