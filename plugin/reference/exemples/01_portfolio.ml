app StudioNova

# ─────────────────────────────────────────────────────────────────────
# COMPLETE PORTFOLIO — fictional design studio.
# Public showcase (project gallery) + administration area + contact form.
# The
# demo data below ('seed' block) makes the site show up FILLED from the
# first
# opening, with real images.
# ─────────────────────────────────────────────────────────────────────

# BRICK 13 (point 83): the files supplied by the human, CHECKED PRESENT at
# compile time. This folder lives outside frontend/, which is renamed on every
# build by 'monl frontend'. These three lines can also be set from the command
# line: 'monl assets add logo.svg --logo' (point 84).
assets
    dir: "assets"
    logo: "studionova.svg"
    favicon: "favicon.svg"

entity Project
    title: String
    description: Text
    # TWO images on the same entity, and on purpose — it is the distinction
    # brick 13 introduces, shown side by side:
    #   'cover' is a LOCAL file of the project. Type 'Image': the compiler
    #   refuses to compile if it is missing, because a broken image is only
    #   noticed by eye, once live.
    #   'imageUrl' is a REMOTE address. It stays 'String': monl makes no
    #   network call, it could assert nothing about a URL — better to promise
    #   nothing than to promise falsely.
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

# Visitors browse the gallery without an account; the admin manages the
# projects.
workflow BrowsePortfolio for Visitor
    Read Project

workflow ContactStudio for Visitor
    Create Message

workflow ManagePortfolio for Admin
    Create Project
    Update Project
    Delete Project
    Read Message

# Demo data: 6 real projects with images (picsum.photos, free and stable
# by
# 'seed'). The site opens already populated.
seed Project
    title: "Refonte Aurora", cover: "assets/aurora.svg", category: "Identité", year: 2024, description: "Direction artistique et système de design complet pour une marque de cosmétiques.", imageUrl: "https://picsum.photos/seed/aurora/800/600"
    title: "App Meridian", cover: "assets/meridian.svg", category: "Produit", year: 2024, description: "Application mobile de suivi d'habitudes, du concept aux écrans finaux.", imageUrl: "https://picsum.photos/seed/meridian/800/600"
    title: "Identité Volta", cover: "assets/volta.svg", category: "Identité", year: 2023, description: "Logo, charte et déclinaisons pour un studio d'architecture.", imageUrl: "https://picsum.photos/seed/volta/800/600"
    title: "Site Horizon", cover: "assets/horizon.svg", category: "Web", year: 2023, description: "Site vitrine éditorial pour un festival de musique indépendante.", imageUrl: "https://picsum.photos/seed/horizon/800/600"
    title: "Packaging Sève", cover: "assets/seve.svg", category: "Print", year: 2022, description: "Gamme d'emballages pour une marque de thés biologiques.", imageUrl: "https://picsum.photos/seed/seve/800/600"
    title: "Campagne Lumen", cover: "assets/lumen.svg", category: "Web", year: 2022, description: "Direction visuelle et déclinaisons d'une campagne de lancement.", imageUrl: "https://picsum.photos/seed/lumen/800/600"

landing
    brief: "StudioNova est un studio de design indépendant : identité, produit et direction artistique. Découvrez nos projets récents."
