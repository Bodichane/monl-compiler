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
        pattern = "Clear promise + offers + availability + getting in touch"
    elif "monl-commerce" in skills or "shop" in archetypes or "Pay" in actions:
        kind = "commerce"
        pattern = "Product hero + guided catalog + reassurance + conversion"
    elif "monl-operations" in skills:
        kind = "operations"
        pattern = "Overview + work queues + contextual detail"
    elif contract.get("sections") or contract.get("faq") or "gallery" in archetypes:
        kind = "editorial"
        pattern = "Narrative hero + trust proofs + structured story + final call"
    elif any(word in text for word in ("rendez-vous", "appointment", "réserver", "service")):
        kind = "service"
        pattern = "Clear promise + offers + availability + getting in touch"
    else:
        kind = "generic"
        pattern = "Clear entry + main content + proof + next action"

    media_entities = [
        {"entity": name, "fields": [field for field, _type in _entity_media(spec)]}
        for name, spec in entities.items()
        if _entity_media(spec)
    ]
    pages = ["Home / main entry"]
    if kind == "commerce":
        pages.extend(["Catalog", "Detail page", "Cart or summary"])
    elif kind == "service":
        pages.append("Services, availability and booking")
    if "monl-operations" in skills:
        pages.append("Workspace per role")
    if contract.get("sections"):
        pages.append("Editorial sections on the home page, continued elsewhere if needed")
    if contract.get("faq"):
        pages.append("Structured FAQ")
    pages.append("Account, authentication and useful error states")

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
    routes = contract.get("routes") or []
    entities = contract.get("entities") or {}
    champs = [champ for spec in entities.values()
              for champ in (spec.get("fields") or [])]

    def champ(cle):
        return any(c.get(cle) for c in champs)

    # Une table plutôt qu'une suite de `if` : l'ordre des phrases est celui
    # des lignes, et ajouter une garantie n'ajoute pas de branche.
    garanties = (
        (any("/paiement" in (r.get("path") or "") for r in routes),
         "Payment goes through a provider; the site never sees a card "
         "number, and the amount is reread from the database at the "
         "moment of charging."),
        (champ("server_generated"),
         "Amounts and references are calculated by the server: they "
         "cannot be changed from the browser."),
        (champ("postpayment_only"),
         "A paid order is frozen: nobody can change its content or its "
         "total any more."),
        (champ("numbered_as"),
         "Each record receives a readable number, assigned once and "
         "never reassigned."),
        (any(r.get("auth_required") for r in routes),
         "Each account's data stays separate: reading and modification are "
         "controlled server-side, not hidden on the page."),
        (bool(contract.get("self_register_actors")),
         "Registration is open only to the roles the specification "
         "provides for; nobody can grant themselves a privileged role."),
    )
    return [phrase for vrai, phrase in garanties if vrai]
