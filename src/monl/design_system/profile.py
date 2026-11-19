"""What the spec says about the site, deduced without inventing anything.

`_guarantees` draws the material of the `trust` section from the
CONTRACT, never from imagination (point 143)."""

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

# The next two functions are extracted from `infer_design_profile`
# (complexity ceiling): same lists, same order.
def _entities_media(entities):
    """The entities carrying media fields, with those fields."""
    return [
        {"entity": name, "fields": [field for field, _type in _entity_media(spec)]}
        for name, spec in entities.items()
        if _entity_media(spec)
    ]


def _pages_of_profile(contract, kind, skills):
    """The pages a site of this kind is expected to render, in order."""
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
    return pages


def infer_design_profile(contract: dict) -> dict:
    """Deduces an initial direction from signals in the contract.

    The signals are structural (routes, archetypes, content), not magic
    entity names. The direction can then be replaced by the visual brief
    written by the author."""
    skills = set(contract.get("design_skills") or [])
    entities = contract.get("entities") or {}
    routes = contract.get("routes") or []
    text = _all_text(contract)
    archetypes = {item.get("archetype") for item in entities.values()}
    actions = {route.get("action") for route in routes}
    # A bookable service can carry a price and thus look like a shop at the
    # archetype level. The explicit business signal of booking must
    # nevertheless take precedence: the expected interface is an availability
    # and appointment flow, not a cart.
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

    media_entities = _entities_media(entities)
    pages = _pages_of_profile(contract, kind, skills)

    profile = {
        "kind": kind,
        "pattern": pattern,
        "pages": pages,
        "media_entities": media_entities,
    }
    profile["ui_patterns"] = select_ui_patterns(contract, kind)
    return profile

def _guarantees(contract: dict) -> list[str]:
    """What the backend REALLY guarantees, in sentences usable as is.

    The trust section is the first place where an AI invents: a review, a
    logo, "10,000 satisfied customers". Forbidding it to invent without giving
    it anything does not produce an honest section, it produces an empty one
    — that is, the defect being fixed. These sentences are derived from the
    contract, hence verifiable one by one on the generated server."""
    routes = contract.get("routes") or []
    entities = contract.get("entities") or {}
    fields = [field for spec in entities.values()
              for field in (spec.get("fields") or [])]

    def field(key):
        return any(c.get(key) for c in fields)

    # A table rather than a series of `if`s: the order of the sentences is the
    # order of the rows, and adding a guarantee adds no branch.
    guarantees = (
        (any("/paiement" in (r.get("path") or "") for r in routes),
         "Payment goes through a provider; the site never sees a card "
         "number, and the amount is reread from the database at the "
         "moment of charging."),
        (field("server_generated"),
         "Amounts and references are calculated by the server: they "
         "cannot be changed from the browser."),
        (field("postpayment_only"),
         "A paid order is frozen: nobody can change its content or its "
         "total any more."),
        (field("numbered_as"),
         "Each record receives a readable number, assigned once and "
         "never reassigned."),
        (any(r.get("auth_required") for r in routes),
         "Each account's data stays separate: reading and modification are "
         "controlled server-side, not hidden on the page."),
        (bool(contract.get("self_register_actors")),
         "Registration is open only to the roles the specification "
         "provides for; nobody can grant themselves a privileged role."),
    )
    return [phrase for true, phrase in guarantees if true]
