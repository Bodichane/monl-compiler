"""Catalogue de patterns de composition pour les frontends Monl.

Ce catalogue est inspiré des registres de références UI, mais il ne contient
ni code React, ni Tailwind, ni dépendance externe. Il décrit des structures que
DeepSeek peut traduire en HTML/CSS/JS autonome et que le contrat Monl peut
ensuite contrôler.
"""

from __future__ import annotations

from collections.abc import Iterable

PATTERN_LIBRARY = {
    "hero": {
        "purpose": "faire comprendre l'offre et l'action principale dès le premier écran",
        "variants": {
            "split-editorial": "copie courte à gauche, média local dominant à droite, CTA principal et lien secondaire",
            "centered-conversion": "promesse centrée, preuve courte sous le titre, CTA principal puis signal de confiance",
            "workspace-entry": "titre orienté tâche, résumé de l'état courant et action de travail immédiatement disponible",
        },
        "must_have": ["identité", "promesse", "action principale", "état ou preuve utile"],
        "avoid": "un hero décoratif sans action ni information réelle",
        "marker": 'data-monl-section="hero"',
    },
    "catalogue": {
        "purpose": "rendre une collection parcourable sans sacrifier le détail important",
        "variants": {
            "featured-rail": "une sélection horizontale mise en avant suivie d'un lien vers la collection complète",
            "filter-grid": "filtres visibles, grille de cartes, prix/disponibilité près de l'action",
            "dense-list": "liste compacte avec recherche, statut, méta utile et inspection au clic",
        },
        "must_have": ["données réelles", "recherche ou classification si disponible", "état vide", "chargement local"],
        "avoid": "une grille de cartes identiques qui masque la hiérarchie ou invente des données",
        "marker": 'data-monl-section="catalogue"',
    },
    "editorial": {
        "purpose": "transformer le contenu fourni par l'auteur en rythme de lecture",
        "variants": {
            "split-story": "texte structuré d'un côté, image ou matière locale de l'autre",
            "proof-bento": "blocs de tailles variées pour valeurs, chiffres, méthode ou savoir-faire",
            "longform-rail": "colonne de lecture maîtrisée, repères latéraux et progression narrative",
        },
        "must_have": ["titre exact", "contenu de la spec", "respiration", "continuité vers l'action suivante"],
        "avoid": "cacher le contenu éditorial derrière un menu ou l'aplatir en un paragraphe",
        "marker": 'data-monl-section="editorial"',
    },
    "trust": {
        "purpose": "réduire l'hésitation sans fabriquer de preuve",
        "variants": {
            "value-grid": "trois à quatre engagements explicites avec une explication courte",
            "process-steps": "étapes numérotées du service ou de la commande, reliées à des états réels",
            "evidence-strip": "indicateurs issus du contrat ou du contenu, jamais de faux logos ou faux avis",
        },
        "must_have": ["preuve réelle ou engagement vérifiable", "libellés compréhensibles", "proximité avec l'action concernée"],
        "avoid": "témoignages, statistiques, logos ou garanties inventés par le frontend",
        "marker": 'data-monl-section="trust"',
    },
    "faq": {
        "purpose": "répondre aux objections sous forme de questions distinctes",
        "variants": {
            "accordion": "questions séparées, une réponse visible à la fois, ouverture clavier accessible",
            "two-column": "questions courtes à gauche et réponses alignées à droite sur grand écran",
            "definition-list": "liste compacte de questions/réponses sans animation obligatoire",
        },
        "must_have": ["une entrée par question de la spec", "réponse non réécrite", "état ouvert/fermé accessible"],
        "avoid": "coller toutes les réponses dans un bloc de texte ou en ajouter de fictives",
        "marker": 'data-monl-section="faq"',
    },
    "contact": {
        "purpose": "offrir une sortie claire vers le contact ou la prochaine action",
        "variants": {
            "form-aside": "formulaire court d'un côté, coordonnées et disponibilité de l'autre",
            "contact-card": "carte de contact très lisible, actions téléphone/email explicites",
            "closing-form": "formulaire placé après la preuve et le contenu, avec retour d'état proche du bouton",
        },
        "must_have": ["canal réel", "libellés précis", "validation et erreur visibles", "retour après envoi"],
        "avoid": "un formulaire qui promet un envoi sans route ou qui perd les données saisies en cas d'erreur",
        "marker": 'data-monl-section="contact"',
    },
    "closing-cta": {
        "purpose": "terminer la page avec une action cohérente avec la promesse",
        "variants": {
            "quiet-band": "bandeau sobre, rappel de la promesse et un seul CTA",
            "image-overlap": "média local partiellement superposé à un bloc de conversion",
            "next-step": "prochaine étape explicite après un parcours de consultation ou de travail",
        },
        "must_have": ["une seule action prioritaire", "rappel de valeur", "alternative de navigation non concurrente"],
        "avoid": "répéter plusieurs boutons concurrents ou ajouter une promesse non présente dans le brief",
        "marker": 'data-monl-section="closing-cta"',
    },
}


def _variant(name: str, kind: str) -> str:
    if kind == "commerce":
        choices = {
            "hero": "split-editorial",
            "catalogue": "filter-grid",
            "editorial": "split-story",
            "trust": "process-steps",
            "faq": "accordion",
            "contact": "form-aside",
            "closing-cta": "image-overlap",
        }
    elif kind == "operations":
        choices = {
            "hero": "workspace-entry",
            "catalogue": "dense-list",
            "editorial": "proof-bento",
            "trust": "evidence-strip",
            "faq": "definition-list",
            "contact": "contact-card",
            "closing-cta": "next-step",
        }
    elif kind == "service":
        choices = {
            "hero": "centered-conversion",
            "catalogue": "featured-rail",
            "editorial": "split-story",
            "trust": "value-grid",
            "faq": "accordion",
            "contact": "form-aside",
            "closing-cta": "quiet-band",
        }
    else:
        choices = {
            "hero": "split-editorial",
            "catalogue": "featured-rail",
            "editorial": "longform-rail",
            "trust": "value-grid",
            "faq": "definition-list",
            "contact": "contact-card",
            "closing-cta": "quiet-band",
        }
    return choices.get(name, choices["hero"])


def select_ui_patterns(contract: dict, kind: str) -> list[dict]:
    """Sélectionne les patterns sans inventer de contenu métier."""
    entities = contract.get("entities") or {}
    archetypes = {entity.get("archetype") for entity in entities.values()}
    selected = ["hero"]
    if "shop" in archetypes or kind == "commerce":
        selected.append("catalogue")
    if contract.get("sections"):
        selected.append("editorial")
    if kind in {"commerce", "service"} or contract.get("sections"):
        selected.append("trust")
    if contract.get("faq"):
        selected.append("faq")
    if kind == "service" or any(
        route.get("action") in {"Contact", "CreateMessage"}
        for route in contract.get("routes") or []
    ):
        selected.append("contact")
    if contract.get("brief"):
        selected.append("closing-cta")
    return [
        {
            "name": name,
            "variant": _variant(name, kind),
            **PATTERN_LIBRARY[name],
        }
        for name in dict.fromkeys(selected)
    ]


def render_pattern_block(patterns: Iterable[dict]) -> str:
    """Rend le catalogue sélectionné dans le document lu par l'IA."""
    chunks = []
    for pattern in patterns:
        required = ", ".join(pattern["must_have"])
        chunks.append(
            f"### {pattern['name']} — variante `{pattern['variant']}`\n"
            f"_{pattern['purpose']}._\n"
            f"- Structure : {pattern['variants'][pattern['variant']]}\n"
            f"- À garantir : {required}\n"
            f"- À éviter : {pattern['avoid']}\n"
            f"- Marqueur : `{pattern['marker']}`"
        )
    if not chunks:
        return ""
    return (
        "## Patterns de composition Monl\n\n"
        "Ce sont des structures de page locales, compatibles avec HTML/CSS/JS "
        "autonome. Les adapter au brief et au contrat ; ne pas copier une "
        "apparence générique ni inventer le contenu absent.\n\n"
        + "\n\n".join(chunks)
        + "\n\n"
    )
