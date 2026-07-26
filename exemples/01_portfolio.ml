app StudioNova

# ─────────────────────────────────────────────────────────────────────
# PORTFOLIO COMPLET — studio de design fictif.
# Vitrine publique (galerie de projets) + zone d'administration + formulaire
# de contact. Les données de démonstration ci-dessous (bloc 'seed') font que
# le site s'affiche REMPLI dès la première ouverture, avec de vraies images.
# ─────────────────────────────────────────────────────────────────────

entity Project
    title: String
    description: Text
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
    title: "Refonte Aurora", category: "Identité", year: 2024, description: "Direction artistique et système de design complet pour une marque de cosmétiques.", imageUrl: "https://picsum.photos/seed/aurora/800/600"
    title: "App Meridian", category: "Produit", year: 2024, description: "Application mobile de suivi d'habitudes, du concept aux écrans finaux.", imageUrl: "https://picsum.photos/seed/meridian/800/600"
    title: "Identité Volta", category: "Identité", year: 2023, description: "Logo, charte et déclinaisons pour un studio d'architecture.", imageUrl: "https://picsum.photos/seed/volta/800/600"
    title: "Site Horizon", category: "Web", year: 2023, description: "Site vitrine éditorial pour un festival de musique indépendante.", imageUrl: "https://picsum.photos/seed/horizon/800/600"
    title: "Packaging Sève", category: "Print", year: 2022, description: "Gamme d'emballages pour une marque de thés biologiques.", imageUrl: "https://picsum.photos/seed/seve/800/600"
    title: "Campagne Lumen", category: "Web", year: 2022, description: "Direction visuelle et déclinaisons d'une campagne de lancement.", imageUrl: "https://picsum.photos/seed/lumen/800/600"

landing
    brief: "StudioNova est un studio de design indépendant : identité, produit et direction artistique. Découvrez nos projets récents."
