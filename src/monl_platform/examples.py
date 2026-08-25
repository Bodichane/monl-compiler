"""Les spécifications d'exemple servies par la plateforme.

Pourquoi elles vivent ICI, et pas dans `exemples/` du dépôt. Le paquet
installé ne contient que du Python : un `wheel` n'emporte ni `exemples/*.ml`
ni aucun fichier de données, donc une plateforme installée par `pip` servirait
un catalogue vide. C'est exactement le défaut qui a fait disparaître
`app.py` du dépôt — quelque chose d'absent qui ne lève aucune erreur. Les
specs sont donc du code, et le test les COMPILE réellement : ce qui compte
n'est pas qu'elles ressemblent aux exemples du dépôt, c'est qu'aucune ne
puisse pourrir en silence.

Chacune est courte à dessein : elle enseigne une famille de règles, elle ne
démontre pas tout. `exemples/` reste la référence complète, commentée.

Aucune ne déclare d'`assets` : la plateforme n'offre aucun moyen de
téléverser un fichier, et une spec qui en déclare est refusée à la
compilation (brique 13). Une vitrine en ligne montre donc ses images par
`String`, jamais par `Image`.
"""

from __future__ import annotations

from typing import Any

VITRINE = """app AtelierVitrine

# Le cas le plus simple : un catalogue que tout le monde lit, que seul
# l'atelier modifie. `public` retire l'authentification de la LECTURE, et
# d'elle seule — créer, modifier et supprimer restent réservés à l'Admin.

entity Realisation
    titre: String
    resume: Text
    categorie: String
    imageUrl: String

actor Admin

rule Realisation.titre required
rule Realisation.Read public

workflow Gerer for Admin
    Create Realisation
    Read Realisation
    Update Realisation
    Delete Realisation

# Le bloc `seed` remplit la base au premier démarrage, et une seule fois :
# une vitrine vide ne se juge pas.
seed Realisation
    titre: "Comptoir Nord", categorie: "Agencement", resume: "Chene massif et laiton brosse.", imageUrl: ""
    titre: "Bibliotheque Faille", categorie: "Rangements", resume: "Modules asymetriques sur mesure.", imageUrl: ""
    titre: "Table Onde", categorie: "Tables", resume: "Plateau en frene ondee, edition limitee.", imageUrl: ""

landing
    brief: "L'Atelier Vitrine presente les realisations d'un menuisier : mobilier sur mesure et agencement d'interieur."
    section "L'atelier": "Nous dessinons et fabriquons dans le meme lieu. Chaque piece est unique."
"""

RENDEZ_VOUS = """app CarnetRendezVous

# La propriete : chacun ne voit QUE ses propres demandes. `ownedBy` filtre la
# lecture autant que l'ecriture — liste comprise, ce qui est le piege
# classique d'un controle d'acces fait a la main.

entity Client
    nom: String
    telephone: String

entity Demande
    motif: Text
    creneau: String
    statut: String
    deposeeLe: DateTime

actor Praticien
actor Visiteur selfRegister

relation Visiteur hasMany Client
relation Visiteur hasMany Demande

# Sans forme imposee, deux ecritures d'un meme numero font deux comptes.
capability auth
    identifier: phone
    phone_prefix: "+229"

rule Client.nom required
rule Client.Read ownedBy Visiteur
rule Client.Update ownedBy Visiteur

rule Demande.Read ownedBy Visiteur
rule Demande.Update ownedBy Visiteur
rule Demande.Delete ownedBy Visiteur
rule Demande.Read sharedBy Praticien
rule Demande.Update sharedBy Praticien

# On ne prend pas rendez-vous sans fiche : une demande qu'on ne peut
# rattacher a personne n'est pas honorable.
rule Demande.Create requiresOwn Client

# Le statut est une valeur PARMI UNE LISTE : sans cela le client se declare
# « honoree » lui-meme. La date est ecrite par le serveur.
rule Demande.statut oneOf "deposee", "confirmee", "honoree", "annulee"
rule Demande.deposeeLe timestamp

workflow Prendre for Visiteur
    Create Client
    Read Client
    Update Client
    Create Demande
    Read Demande
    Update Demande
    Delete Demande

workflow Tenir for Praticien
    Read Demande
    Update Demande

landing
    brief: "Le Carnet de rendez-vous permet a chacun de deposer une demande et d'en suivre l'etat."
    question "Comment annuler ?": "Ouvrez la demande depuis votre espace et passez son statut a annulee."
"""

BOUTIQUE = """app PetiteBoutique

# La chaine marchande entiere. Le point a retenir : AUCUN montant n'est
# ecrit par le client. Le sous-total est calcule depuis le prix du catalogue
# (`derivedFrom`), le total est la somme des lignes (`sumOf`), et c'est ce
# total-la qu'on encaisse.

entity Produit
    nom: String
    description: Text
    prix: Money
    stock: Integer

entity Commande
    reference: String
    total: Money
    statut: String
    passeeLe: DateTime

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister
actor Vendeur

rule Produit.nom required
rule Produit.Read public
rule Produit.prix min 0
rule Produit.stock min 0

# Une ligne appartient a qui possede sa commande : la propriete traverse un
# cran (`ownedBy Commande`, et non `ownedBy Client`).
rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Commande
rule Ligne.Delete ownedBy Commande

rule Ligne.quantite required
rule Ligne.quantite min 1
rule Ligne.sousTotal derivedFrom Produit.prix by quantite
rule Commande.total sumOf Ligne.sousTotal

# `min 0` sur le stock ARME la verification : sans lui, on vend douze paires
# a cinquante clients. C'est la seule facon declarative de distinguer un
# stock d'un compteur qui a le droit de passer sous zero.
rule Ligne.Create decrements Produit.stock by quantite

rule Commande.total payable
rule Commande.passeeLe timestamp
rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"
rule Commande.statut oneOf "panier", "reglee", "expediee", "annulee"
rule Commande.statut "annulee" releases Ligne
rule Commande.statut writableAfterPayment Vendeur

workflow Acheter for Client
    Read Produit
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne

workflow Tenir for Vendeur
    Create Produit
    Read Produit
    Update Produit
    Delete Produit
    Update Commande.statut

seed Produit
    nom: "Carnet cousu", prix: 14.00, stock: 40, description: "96 pages, papier ivoire 100g."
    nom: "Stylo plume Ecole", prix: 29.50, stock: 12, description: "Plume acier, corps resine."
    nom: "Encre Bleu Nuit", prix: 9.90, stock: 60, description: "Flacon 30 ml."

landing
    brief: "La Petite Boutique vend de la papeterie : carnets, stylos et encres."
"""

COMMUNAUTE = """app FilCommun

# Un fil ou l'on publie sous pseudonyme. Trois idees : le pseudo est GENERE
# par le serveur (personne ne choisit son identite), un compte n'aime qu'une
# fois par message, et un message masque cesse d'etre lisible par son URL.

entity Membre
    pseudo: String
    reputation: Integer

entity Message
    contenu: Text
    auteur: String
    statut: String
    jaimes: Integer
    publieLe: DateTime

entity Jaime
    note: String

entity Signalement
    motif: String

relation Membre hasMany Message
relation Membre hasMany Jaime
relation Message hasMany Jaime
relation Membre hasMany Signalement

actor Membre selfRegister
actor Moderateur

# `generated` retire le champ du corps de requete : le serveur y ecrit un
# pseudonyme stable par compte. Un champ libre ne garantit aucune identite.
rule Message.auteur generated
rule Message.contenu required
rule Message.statut oneOf "publie", "masque"

# Lecture publique SOUS CONDITION : la liste est filtree et le detail repond
# 404 tant que le statut ne vaut pas « publie ». Le moderateur, lui, voit
# tout — sans quoi il ne pourrait plus rouvrir ce qu'il vient de masquer.
rule Message.Read publicWhen statut "publie"
rule Message.Read sharedBy Moderateur
rule Message.Update sharedBy Moderateur
rule Message.Delete sharedBy Moderateur
rule Message.publieLe timestamp

# Le compteur devient un libelle a la lecture : on montre une tendance, pas
# un nombre exact.
rule Message.jaimes categorized: "discret" below 10, "suivi" below 100, "viral" otherwise

# L'unicite tient a un index composite, jamais a une verification applicative
# — c'est lui qui protege aussi deux requetes simultanees.
rule Jaime.Create oncePer Membre, Message
rule Jaime.Create increments Message.jaimes by 1
rule Signalement.Create decrements Membre.reputation by 10

workflow Rejoindre for Membre
    Create Membre

workflow Publier for Membre
    Create Message
    Read Message

workflow Reagir for Membre
    Create Jaime
    Create Signalement

workflow Moderer for Moderateur
    Read Message
    Update Message
    Delete Message

landing
    brief: "Le Fil Commun est un fil de discussion ou l'on publie sous pseudonyme."
"""

EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "vitrine",
        "name": "Vitrine publique",
        "summary": "Un catalogue que tout le monde lit, que seul l'atelier modifie.",
        "teaches": ["public", "seed", "landing"],
        "result": {"entities": 1, "routes": 5, "files": 12},
        "spec": VITRINE,
    },
    {
        "id": "rendez-vous",
        "name": "Carnet de rendez-vous",
        "summary": "Chacun ne voit que ses propres demandes ; le praticien les voit toutes.",
        "teaches": ["ownedBy", "sharedBy", "requiresOwn", "oneOf", "timestamp",
                    "capability auth"],
        "result": {"entities": 2, "routes": 9, "files": 12},
        "spec": RENDEZ_VOUS,
    },
    {
        "id": "boutique",
        "name": "Boutique et paiement",
        "summary": "Panier, stock décompté et encaissement — aucun montant écrit par le client.",
        "teaches": ["derivedFrom", "sumOf", "decrements", "min", "payable",
                    "numbered", "releases", "writableAfterPayment"],
        "result": {"entities": 3, "routes": 17, "files": 12},
        "spec": BOUTIQUE,
    },
    {
        "id": "communaute",
        "name": "Fil communautaire",
        "summary": "Publication sous pseudonyme, un j'aime par compte, modération réelle.",
        "teaches": ["generated", "publicWhen", "oncePer", "increments",
                    "categorized", "decrements"],
        "result": {"entities": 4, "routes": 8, "files": 12},
        "spec": COMMUNAUTE,
    },
]

BY_ID = {example["id"]: example for example in EXAMPLES}


def catalogue() -> list[dict[str, Any]]:
    """Les exemples SANS leur spec : de quoi peupler une galerie."""
    return [
        {key: value for key, value in example.items() if key != "spec"}
        for example in EXAMPLES
    ]


def spec_of(example_id: str) -> str:
    """La spec d'un exemple, ou KeyError si l'identifiant est inconnu."""
    return BY_ID[example_id]["spec"]
