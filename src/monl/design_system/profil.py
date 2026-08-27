"""Ce que la spec dit du site, déduit sans rien inventer.

`_guarantees` tire la matière de la section `trust` du CONTRAT, jamais de
l'imagination (point 143)."""

import re
import unicodedata

from ..ui_patterns import select_ui_patterns


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "section"

def _all_text(contract: dict) -> str:
    values = [contract.get("app") or "", contract.get("brief") or ""]
    for section in contract.get("sections") or []:
        values.extend((section.get("title") or "", section.get("body") or ""))
    for question in contract.get("faq") or []:
        values.extend((question.get("question") or "", question.get("answer") or ""))
    return " ".join(values).lower()

def _entity_media(entity: dict) -> list[tuple[str, str]]:
    return [
        (field.get("name", "media"), field.get("type", "String"))
        for field in entity.get("fields") or []
        if field.get("role") == "media"
    ]

def infer_design_profile(contract: dict) -> dict:
    """Déduit une direction initiale à partir de signaux du contrat.

    Les signaux sont structurels (routes, archétypes, contenu), pas des noms
    magiques d'entités. La direction peut ensuite être remplacée par le
    cahier visuel écrit par l'auteur.
    """
    skills = set(contract.get("design_skills") or [])
    entities = contract.get("entities") or {}
    routes = contract.get("routes") or []
    text = _all_text(contract)
    archetypes = {item.get("archetype") for item in entities.values()}
    actions = {route.get("action") for route in routes}
    # Un service réservable peut porter un prix et donc ressembler à une
    # boutique au niveau de l'archétype. Le signal métier explicite de
    # réservation doit toutefois primer : l'interface attendue est un
    # parcours de disponibilité et de prise de rendez-vous, pas un panier.
    scheduling_signal = any(word in text for word in (
        "rendez-vous", "réserver", "réservation", "appointment", "booking",
        "créneau", "disponibilité",
    ))

    if scheduling_signal:
        kind = "service"
        pattern = "Promesse claire + offres + disponibilité + prise de contact"
    elif "monl-commerce" in skills or "shop" in archetypes or "Pay" in actions:
        kind = "commerce"
        pattern = "Hero produit + catalogue guidé + réassurance + conversion"
    elif "monl-operations" in skills:
        kind = "operations"
        pattern = "Vue d'ensemble + files de travail + détail contextuel"
    elif contract.get("sections") or contract.get("faq") or "gallery" in archetypes:
        kind = "editorial"
        pattern = "Hero narratif + preuves de confiance + récit structuré + appel final"
    elif any(word in text for word in ("rendez-vous", "appointment", "réserver", "service")):
        kind = "service"
        pattern = "Promesse claire + offres + disponibilité + prise de contact"
    else:
        kind = "generic"
        pattern = "Entrée claire + contenu principal + preuve + action suivante"

    media_entities = [
        {"entity": name, "fields": [field for field, _type in _entity_media(spec)]}
        for name, spec in entities.items()
        if _entity_media(spec)
    ]
    pages = ["Accueil / entrée principale"]
    if kind == "commerce":
        pages.extend(["Catalogue", "Fiche détaillée", "Panier ou récapitulatif"])
    elif kind == "service":
        pages.append("Prestations, disponibilité et réservation")
    if "monl-operations" in skills:
        pages.append("Espace de travail par rôle")
    if contract.get("sections"):
        pages.append("Sections éditoriales sur l'accueil, avec prolongement si nécessaire")
    if contract.get("faq"):
        pages.append("FAQ structurée")
    pages.append("Compte, authentification et états d'erreur utiles")

    profile = {
        "kind": kind,
        "pattern": pattern,
        "pages": pages,
        "media_entities": media_entities,
    }
    profile["ui_patterns"] = select_ui_patterns(contract, kind)
    return profile

def _guarantees(contract: dict) -> list[str]:
    """Ce que le backend garantit VRAIMENT, en phrases utilisables telles quelles.

    La section de réassurance est le premier endroit où une IA invente : un
    avis, un logo, « 10 000 clients satisfaits ». Lui interdire d'inventer
    sans rien lui donner ne produit pas une section honnête, il produit une
    section vide — c'est-à-dire le défaut qu'on répare. Ces phrases sont
    dérivées du contrat, donc vérifiables une par une sur le serveur généré.
    """
    faits = []
    routes = contract.get("routes") or []
    entities = contract.get("entities") or {}
    champs = [champ for spec in entities.values()
              for champ in (spec.get("fields") or [])]

    if any("/paiement" in (r.get("path") or "") for r in routes):
        faits.append(
            "Le paiement passe par un prestataire ; le site ne voit jamais un "
            "numéro de carte, et le montant est relu en base au moment de "
            "l'encaissement.")
    if any(c.get("server_generated") for c in champs):
        faits.append(
            "Les montants et les références sont calculés par le serveur : ils "
            "ne peuvent pas être modifiés depuis le navigateur.")
    if any(c.get("postpayment_only") for c in champs):
        faits.append(
            "Une commande réglée est figée : plus personne ne peut en changer "
            "le contenu ni le total.")
    if any(c.get("numbered_as") for c in champs):
        faits.append(
            "Chaque enregistrement reçoit un numéro lisible, attribué une "
            "seule fois et jamais réattribué.")
    if any(r.get("auth_required") for r in routes):
        faits.append(
            "Les données de chaque compte restent séparées : la lecture et la "
            "modification sont contrôlées côté serveur, pas cachées côté page.")
    if contract.get("self_register_actors"):
        faits.append(
            "L'inscription est ouverte aux seuls rôles prévus par la "
            "spécification ; on ne s'attribue pas un rôle privilégié.")
    return faits
