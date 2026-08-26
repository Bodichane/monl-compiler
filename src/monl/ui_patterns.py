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
    "booking": {
        "purpose": "faire passer de la découverte à une réservation réelle sans inventer un calendrier",
        "variants": {
            "booking-flow": "service choisi, date et créneau lisibles, formulaire court, confirmation et erreurs proches de l'action",
        },
        "must_have": ["offres réelles", "champs du contrat uniquement", "état de disponibilité explicite", "confirmation ou erreur visible"],
        "avoid": "un calendrier fictif, une disponibilité inventée ou un formulaire sans route de création",
        "marker": 'data-monl-section="booking"',
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
            "booking": "booking-flow",
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
            "booking": "booking-flow",
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
            "booking": "booking-flow",
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
            "booking": "booking-flow",
            "closing-cta": "quiet-band",
        }
    return choices.get(name, choices["hero"])


def select_ui_patterns(contract: dict, kind: str) -> list[dict]:
    """Sélectionne les patterns sans inventer de contenu métier."""
    entities = contract.get("entities") or {}
    archetypes = {entity.get("archetype") for entity in entities.values()}
    routes = contract.get("routes") or []
    booking_route = any(
        route.get("action") in {"Create", "Update"}
        and any(word in (f"{route.get('entity', '')} {route.get('path', '')}").lower()
                for word in ("booking", "appointment", "reservation", "rendez-vous"))
        for route in routes
    )
    selected = ["hero"]
    # Une prestation tarifée peut être classée `shop` par l'archétype des
    # champs, mais son parcours est la disponibilité/réservation, pas un
    # catalogue et un panier. C'est le PARCOURS RÉELLEMENT OFFERT qui tranche,
    # jamais le `kind` : `kind != "service"` faisait perdre son catalogue à
    # `projets/KoraMaison` — une boutique (Customer/Order/OrderLine/Product)
    # que l'inférence classe `service`, et qui n'a aucune route de réservation
    # pour recevoir `booking` à la place.
    if kind == "commerce" or ("shop" in archetypes and not booking_route):
        selected.append("catalogue")
    # LE PLANCHER (point 119). Un site dont la MATIÈRE n'apparaît sur aucun
    # écran obligatoire est une coquille, quel que soit son nombre de
    # sections : `exemples/05_classement.ml` exigeait `hero` et
    # `closing-cta`, et rien du tout pour le classement lui-même — le sujet
    # du site n'était requis nulle part. Toute application qui expose des
    # entités doit donc porter une section de collection, sauf quand une
    # autre section joue déjà ce rôle : `booking` pour une réservation,
    # `workspace` pour un poste de travail (ajouté par design_system).
    if "catalogue" not in selected and entities and not booking_route \
            and kind != "operations":
        selected.append("catalogue")
    brief = (contract.get("brief") or "").lower()
    express_editorial = any(signal in brief for signal in (
        "mode express", "images portent", "page dense",
    ))
    if contract.get("sections") or express_editorial:
        selected.append("editorial")
    # `trust` était réservé au commerce et au service. Or la matière d'une
    # section de réassurance ne vient pas du secteur : elle vient du CONTRAT,
    # qui sait ce que le backend garantit vraiment — compte obligatoire,
    # montant calculé côté serveur, stock décompté, commande figée après
    # paiement. Ces phrases-là sont vraies pour toute application monl, et ce
    # sont les seules autorisées : la section reste interdite d'inventer un
    # avis, un logo ou un chiffre.
    selected.append("trust")
    if contract.get("faq"):
        selected.append("faq")
    if booking_route:
        selected.append("booking")
    contact_route = any(
        route.get("action") in {"Create", "Update"}
        and any(word in (f"{route.get('entity', '')} {route.get('path', '')}").lower()
                for word in ("message", "contact"))
        for route in routes
    )
    if contact_route:
        selected.append("contact")
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
