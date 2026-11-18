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
        "purpose": "make the offer and the main action understood from the first screen",
        "variants": {
            "split-editorial": "short copy on the left, dominant local media on the right, main CTA and secondary link",
            "centered-conversion": "centered promise, short proof under the heading, main CTA then a trust signal",
            "workspace-entry": "task-oriented heading, summary of the current state and a work action immediately available",
        },
        "must_have": ["identity", "promise", "main action", "useful state or proof"],
        "avoid": "a decorative hero with no action and no real information",
        "marker": 'data-monl-section="hero"',
    },
    "catalogue": {
        "purpose": "make a collection browsable without sacrificing the important detail",
        "variants": {
            "featured-rail": "a featured horizontal selection followed by a link to the full collection",
            "filter-grid": "visible filters, card grid, price/availability near the action",
            "dense-list": "compact list with search, status, useful meta and inspection on click",
        },
        "must_have": ["real data", "search or classification if available", "empty state", "local loading"],
        "avoid": "a grid of identical cards that hides the hierarchy or invents data",
        "marker": 'data-monl-section="catalogue"',
    },
    "editorial": {
        "purpose": "turn the content supplied by the author into a reading rhythm",
        "variants": {
            "split-story": "structured text on one side, image or local material on the other",
            "proof-bento": "blocks of varied sizes for values, figures, method or know-how",
            "longform-rail": "controlled reading column, side markers and narrative progression",
        },
        "must_have": ["exact title", "spec content", "breathing room", "continuity toward the next action"],
        "avoid": "hiding the editorial content behind a menu or flattening it into one paragraph",
        "marker": 'data-monl-section="editorial"',
    },
    "trust": {
        "purpose": "reduce hesitation without fabricating proof",
        "variants": {
            "value-grid": "three to four explicit commitments with a short explanation",
            "process-steps": "numbered steps of the service or the order, tied to real states",
            "evidence-strip": "indicators drawn from the contract or the content, never fake logos or fake reviews",
        },
        "must_have": ["real proof or verifiable commitment", "understandable labels", "proximity to the action concerned"],
        "avoid": "testimonials, statistics, logos or guarantees invented by the frontend",
        "marker": 'data-monl-section="trust"',
    },
    "faq": {
        "purpose": "answer objections as distinct questions",
        "variants": {
            "accordion": "separate questions, one answer visible at a time, accessible keyboard opening",
            "two-column": "short questions on the left and answers aligned on the right on a large screen",
            "definition-list": "compact list of questions/answers with no mandatory animation",
        },
        "must_have": ["one entry per spec question", "answer not rewritten", "accessible open/closed state"],
        "avoid": "pasting every answer into one block of text or adding fictional ones",
        "marker": 'data-monl-section="faq"',
    },
    "contact": {
        "purpose": "offer a clear way out toward contact or the next action",
        "variants": {
            "form-aside": "short form on one side, contact details and availability on the other",
            "contact-card": "very readable contact card, explicit phone/email actions",
            "closing-form": "form placed after the proof and the content, with state feedback near the button",
        },
        "must_have": ["real channel", "precise labels", "visible validation and error", "feedback after sending"],
        "avoid": "a form that promises sending without a route or loses the entered data on error",
        "marker": 'data-monl-section="contact"',
    },
    "booking": {
        "purpose": "move from discovery to a real booking without inventing a calendar",
        "variants": {
            "booking-flow": "chosen service, readable date and slot, short form, confirmation and errors near the action",
        },
        "must_have": ["real offers", "contract fields only", "explicit availability state", "visible confirmation or error"],
        "avoid": "a fictional calendar, invented availability or a form without a creation route",
        "marker": 'data-monl-section="booking"',
    },
    "closing-cta": {
        "purpose": "end the page with an action consistent with the promise",
        "variants": {
            "quiet-band": "restrained band, reminder of the promise and a single CTA",
            "image-overlap": "local media partly overlapping a conversion block",
            "next-step": "explicit next step after a browsing or work flow",
        },
        "must_have": ["a single priority action", "value reminder", "non-competing navigation alternative"],
        "avoid": "repeating several competing buttons or adding a promise absent from the brief",
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
        "mode express", "express mode", "images portent", "images carry",
        "page dense",
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
            f"### {pattern['name']} — variant `{pattern['variant']}`\n"
            f"_{pattern['purpose']}._\n"
            f"- Structure: {pattern['variants'][pattern['variant']]}\n"
            f"- To guarantee: {required}\n"
            f"- To avoid: {pattern['avoid']}\n"
            f"- Marker: `{pattern['marker']}`"
        )
    if not chunks:
        return ""
    return (
        "## Monl composition patterns\n\n"
        "These are local page structures, compatible with self-contained "
        "HTML/CSS/JS. Adapt them to the brief and the contract; do not copy a "
        "generic look or invent missing content.\n\n"
        + "\n\n".join(chunks)
        + "\n\n"
    )
