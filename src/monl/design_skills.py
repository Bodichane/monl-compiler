"""Compétences de composition injectées dans le brief frontend.

Elles prescrivent une profondeur vérifiable, jamais une identité visuelle.
Les dossiers ``skills/`` portent leur version utilisable par les agents ; ce
module en garde le noyau déterministe destiné aux artefacts compilés.
"""

SKILL_PROFILES = {
    "monl-design-system": {
        "purpose": "direction visuelle explicite avant l'écriture du frontend",
        "requirements": [
            "lire DESIGN_SYSTEM.md, DESIGN_SPEC.md et ASSET_MANIFEST.json avant de coder",
            "choisir un pattern de page et une hiérarchie avant les détails décoratifs",
            "traiter les anti-patterns, le contraste, le clavier, le mobile et le mouvement réduit comme des critères de livraison",
            "rendre les assets locaux réellement présents et référencés, jamais des placeholders distants",
        ],
    },
    "monl-showcase": {
        "purpose": "socle de qualité démonstration, dense et professionnel",
        "requirements": [
            "cartographier chaque parcours principal vers une entrée d'interface claire",
            "prévoir chargement, vide, succès, validation, refus et indisponibilité",
            "adapter la composition au mobile, au clavier et aux mouvements réduits",
            "présenter les opérations métier avec des contrôles humains, jamais du JSON brut",
            "utiliser des données réelles de l'API et une hiérarchie visuelle propre au brief",
        ],
    },
    "monl-commerce": {
        "purpose": "parcours commercial complet, du catalogue à la livraison",
        "requirements": [
            "montrer prix et disponibilité au point de décision",
            "rendre catalogue, panier ou récapitulatif, commande et historique cohérents",
            "traiter paiement en attente, échec et service indisponible sans inventer le succès",
            "séparer clairement l'expérience acheteur des contrôles vendeur ou administrateur",
            "exposer le suivi après paiement quand le contrat fournit cette route",
        ],
    },
    "monl-operations": {
        "purpose": "espace opérationnel organisé autour des décisions et files de travail",
        "requirements": [
            "fournir une vue d'ensemble issue des vraies données",
            "regrouper les outils par objectif et par rôle plutôt que par table de base de données",
            "proposer recherche, filtre ou segmentation quand les champs le permettent",
            "relier listes denses, inspection détaillée et actions contextualisées",
            "rendre propriété, modération et actions privilégiées immédiatement compréhensibles",
        ],
    },
}


def select_design_skills(entities, routes):
    """Sélectionne les compétences par signaux structurels, sans lire le brief."""
    selected = ["monl-showcase"]
    actions = {route["action"] for route in routes}
    # Ne jamais classifier par le NOM d'une entité : « Product » sans prix
    # n'est pas plus commercial que « Article ». Seuls des comportements ou
    # rôles de champs réellement dérivés de la spec peuvent sélectionner un
    # skill spécialisé.
    commerce = bool(actions & {"Pay", "UpdateAfterPayment"})
    if commerce:
        selected.append("monl-commerce")

    operational_actions = {"Update", "Delete", "Report", "Moderate", "Approve"}
    privileged_routes = sum(bool(route.get("allowed_actors")) for route in routes)
    operations = (len(entities) >= 3 or privileged_routes >= 5 or
                  bool(actions & operational_actions))
    if operations:
        selected.append("monl-operations")
    return selected


def render_skill_block(names):
    """Rend le noyau des skills dans le prompt autonome du projet."""
    # La profondeur métier dépend du contrat ; la lecture d'un design system
    # préparé avant le code, elle, est commune à toute interface Monl.
    names = list(names)
    if "monl-design-system" not in names:
        names.insert(0, "monl-design-system")
    chunks = []
    for name in names:
        profile = SKILL_PROFILES[name]
        rules = "\n".join(f"  - {rule}" for rule in profile["requirements"])
        chunks.append(f"### ${name}\n_{profile['purpose']}._\n{rules}")
    return (
        "## Design skills sélectionnés par Monl\n\n"
        "Ces compétences fixent le niveau de profondeur et de finition, pas "
        "la palette ni la typographie. Les appliquer ensemble ; la direction "
        "artistique reste celle du brief de l'auteur.\n\n" + "\n\n".join(chunks) + "\n\n"
    )
