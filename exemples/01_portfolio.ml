app StudioNova

# ─────────────────────────────────────────────────────────────────────
# PORTFOLIO COMPLET — studio de design fictif.
# Vitrine publique (galerie de projets) + zone d'administration + formulaire
# de contact. Les données de démonstration ci-dessous (bloc 'seed') font que
# le site s'affiche REMPLI dès la première ouverture, avec de vraies images.
# ─────────────────────────────────────────────────────────────────────

# BRIQUE 13 (point 83) : les fichiers fournis par l'humain, VÉRIFIÉS PRÉSENTS à
# la compilation. Ce dossier vit hors de frontend/, qui est renommé à chaque
# construction par 'monl frontend'. Ces trois lignes se posent aussi à la
# commande : 'monl assets add logo.svg --logo' (point 84).
assets
    dir: "assets"
    logo: "studionova.svg"
    favicon: "favicon.svg"

entity Project
    title: String
    description: Text
    # DEUX images sur la même entité, et c'est délibéré — c'est la distinction
    # que la brique 13 introduit, montrée côte à côte :
    #   'cover' est un fichier LOCAL du projet. Type 'Image' : le compilateur
    #   refuse de compiler s'il manque, parce qu'une image cassée ne se voit
    #   qu'à l'œil, en ligne.
    #   'imageUrl' est une adresse DISTANTE. Elle reste 'String' : monl ne fait
    #   aucun appel réseau, il ne pourrait rien affirmer d'une URL — mieux vaut
    #   ne rien promettre que promettre à faux.
    cover: Image
    imageUrl: String
    category: String
    year: Integer

entity Message
    author: String
    email: Email
    content: Text

actor Admin
actor Visitor selfRegister

rule Project.title required
rule Project.Read public
rule Message.Create public

# Les visiteurs consultent la galerie sans compte ; l'admin gère les projets.
workflow BrowsePortfolio for Visitor
    Read Project

workflow ContactStudio for Visitor
    Create Message

workflow ManagePortfolio for Admin
    Create Project
    Update Project
    Delete Project
    Read Message

# Données de démonstration : 6 projets réels avec images (picsum.photos,
# libres et stables par 'seed'). Le site s'ouvre déjà peuplé.
seed Project
    title: "Refonte Aurora", cover: "assets/aurora.svg", category: "Identité", year: 2024, description: "Direction artistique et système de design complet pour une marque de cosmétiques.", imageUrl: "https://picsum.photos/seed/aurora/800/600"
    title: "App Meridian", cover: "assets/meridian.svg", category: "Produit", year: 2024, description: "Application mobile de suivi d'habitudes, du concept aux écrans finaux.", imageUrl: "https://picsum.photos/seed/meridian/800/600"
    title: "Identité Volta", cover: "assets/volta.svg", category: "Identité", year: 2023, description: "Logo, charte et déclinaisons pour un studio d'architecture.", imageUrl: "https://picsum.photos/seed/volta/800/600"
    title: "Site Horizon", cover: "assets/horizon.svg", category: "Web", year: 2023, description: "Site vitrine éditorial pour un festival de musique indépendante.", imageUrl: "https://picsum.photos/seed/horizon/800/600"
    title: "Packaging Sève", cover: "assets/seve.svg", category: "Print", year: 2022, description: "Gamme d'emballages pour une marque de thés biologiques.", imageUrl: "https://picsum.photos/seed/seve/800/600"
    title: "Campagne Lumen", cover: "assets/lumen.svg", category: "Web", year: 2022, description: "Direction visuelle et déclinaisons d'une campagne de lancement.", imageUrl: "https://picsum.photos/seed/lumen/800/600"

landing
    brief: "StudioNova est un studio de design indépendant : identité, produit et direction artistique. Découvrez nos projets récents."
