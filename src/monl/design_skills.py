"""Composition skills injected into the frontend brief.

They prescribe a verifiable depth, never a visual identity. The
``plugin/skills/`` folders carry their version usable by agents; this
module keeps the deterministic core meant for the compiled artifacts."""

SKILL_PROFILES = {
    "monl-design-system": {
        "purpose": "explicit visual direction before writing the frontend",
        "requirements": [
            "read docs/DESIGN_SYSTEM.md, docs/DESIGN_SPEC.md and docs/ASSET_MANIFEST.json before coding",
            "choose a page pattern and a hierarchy before decorative details",
            "treat anti-patterns, contrast, keyboard, mobile and reduced motion as delivery criteria",
            "make local assets actually present and referenced, never remote placeholders",
        ],
    },
    "monl-showcase": {
        "purpose": "demo-quality foundation, dense and professional",
        "requirements": [
            "map each main flow to a clear interface entry",
            "plan for loading, empty, success, validation, refusal and unavailability",
            "adapt the composition to mobile, keyboard and reduced motion",
            "present business operations with human controls, never raw JSON",
            "use real API data and a visual hierarchy specific to the brief",
        ],
    },
    "monl-commerce": {
        "purpose": "complete commercial flow, from catalog to delivery",
        "requirements": [
            "show price and availability at the point of decision",
            "make catalog, cart or summary, order and history consistent",
            "handle pending payment, failure and unavailable service without inventing success",
            "clearly separate the buyer experience from seller or administrator controls",
            "expose after-payment tracking when the contract provides that route",
        ],
    },
    "monl-operations": {
        "purpose": "operational space organized around decisions and work queues",
        "requirements": [
            "provide an overview drawn from the real data",
            "group tools by goal and by role rather than by database table",
            "offer search, filter or segmentation when the fields allow it",
            "connect dense lists, detailed inspection and contextual actions",
            "make ownership, moderation and privileged actions immediately understandable",
        ],
    },
}


def select_design_skills(entities, routes):
    """Selects the skills by structural signals, without reading the brief."""
    selected = ["monl-showcase"]
    actions = {route["action"] for route in routes}
    # Never classify by an entity's NAME: "Product" without a price is no more
    # commercial than "Article". Only behaviors or field roles really derived
    # from the spec can select a specialized skill.
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
    """Renders the core of the skills into the project's standalone prompt."""
    # Business depth depends on the contract; reading a design system prepared
    # before the code, however, is common to every Monl interface.
    names = list(names)
    if "monl-design-system" not in names:
        names.insert(0, "monl-design-system")
    chunks = []
    for name in names:
        profile = SKILL_PROFILES[name]
        rules = "\n".join(f"  - {rule}" for rule in profile["requirements"])
        chunks.append(f"### ${name}\n_{profile['purpose']}._\n{rules}")
    return (
        "## Design skills selected by Monl\n\n"
        "These skills set the level of depth and finish, not the palette or "
        "the typography. Apply them together; the art direction remains the "
        "one in the author's brief.\n\n" + "\n\n".join(chunks) + "\n\n"
    )
