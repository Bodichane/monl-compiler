"""Building blocks of FRONTEND_PROMPT.md: routes, entities, editorial content.

Split from brief.py (file ceiling). Each function returns text the brief
pastes as is; the brief's order and wording are decided in brief.py."""

from . import field_roles

ROLE_LABELS = {"title": "TITLE — identifies it at a glance",
               "media": "MEDIA — the record's image",
               "description": "DESCRIPTION — the long text",
               "price": "PRICE",
               "stock": "AVAILABILITY — show it near the price, not as a footnote",
               "category": "CATEGORY — good for a filter",
               "meta": "meta — secondary information"}


def lignes_de_routes(contract):
    """One line per route: method, path, access, body and note."""
    routes_lines = []
    for r in contract["routes"]:
        if not r["auth_required"]:
            auth = "public"
        elif r["allowed_actors"]:
            auth = f"JWT ({', '.join(r['allowed_actors'])})"
        else:
            # Point 74: the payment webhook is authenticated, but not by a JWT
            # — by a signature from the provider. Announcing "JWT ()" would
            # suggest a route open to any logged-in account.
            auth = "provider signature, not a JWT"

        # The expected body appeared NOWHERE in the brief: the AI had to deduce
        # it from the list of fields, without ever seeing the attachment
        # columns (a comment's article_id). It could not guess them, and the
        # server answered 422 (point 57).
        corps = (f" — body: `{{{', '.join(r['request_fields'])}}}`"
                 if r.get("request_fields") else "")
        if r.get("upload"):
            upload = r["upload"]
            corps = (f" — multipart/form-data, file field `{upload['field_name']}`, "
                     f"{upload['max_bytes']} bytes maximum, types: "
                     f"{', '.join(upload['accepted_types'])}")
        # Point 74: the route notes existed in the JSON contract but did NOT
        # reach the brief — and the brief is what the AI reads. The shape of
        # the paginated response had always been missing from it, and the
        # payment steps would have been missing just the same.
        note = f" — {r['note']}" if r.get("note") else ""
        routes_lines.append(f"- `{r['method']} {r['path']}` — {r['action']} "
                            f"{r['entity']} — {auth}{corps}{note}")
    return routes_lines


def _marques_du_champ(f):
    """What the AI must know about one field, in reading order."""
    marks = []
    if f.get("role"):
        marks.append(ROLE_LABELS[f["role"]])
    if f["required"]:
        marks.append("required")
    if f["hidden_in_reads"]:
        marks.append("never returned on read")
    if f["server_generated"]:
        marks.append("server-generated — DO NOT send")
    if f.get("postpayment_only"):
        marks.append("editable only through the after-payment route")
    if f.get("upload"):
        upload = f["upload"]
        marks.append(
            f"Multipart upload via POST/GET on the field `{upload['field_name']}`, "
            f"{upload['max_bytes']} bytes maximum; types: "
            f"{', '.join(upload['accepted_types'])}. Do not send it as JSON.")
    if f["categorized_in_reads"]:
        marks.append("read as a category label")
    # BRICK 19 (point 96): the AI reads the brief, not the JSON.
    # Writing the list there is the difference between a dropdown menu
    # and a text field that gets a 422 on the value the user makes up.
    if f.get("allowed_values"):
        marks.append("DROPDOWN MENU, fixed values (422 otherwise): "
                     + ", ".join(f"“{v}”" for v in f["allowed_values"]))
    # Point 76: say what the field is for, not only that it exists.
    # Without the possible values, the AI has to guess what to compare
    # to know whether it is settled — and will guess 'paid'.
    if f.get("note"):
        marks.append(f["note"])
    return marks


def _liaisons(spec):
    """The link columns present in responses, with how to join them."""
    # POINT 88: the link columns come out in the responses (SELECT *) but
    # appeared ONLY in the JSON. Yet it is here that the easiest join to
    # get wrong is at stake — the one that attaches a record to its holder
    # — and an administration page does little else.
    liaisons = ""
    if spec["foreign_keys"]:
        lignes_liens = [
            f"  - `{li['column']}` → "
            + (f"ACCOUNT identifier. Find the {li['references']} record "
               f"whose `{li['column']}` holds the SAME value — not the one whose "
               f"`id` holds it." if li["references_account"]
               else f"`id` of a {li['references']} record.")
            for li in spec["foreign_keys"]
        ]
        liaisons = ("\nLink columns present in responses:\n"
                    + "\n".join(lignes_liens))
    return liaisons


def lignes_d_entites(contract):
    """One block per entity: suggested form, anatomy, fields, links."""
    entities_lines = []
    for ent, spec in contract["entities"].items():
        flags = []
        for f in spec["fields"]:
            marks = _marques_du_champ(f)
            suffix = f" ({'; '.join(marks)})" if marks else ""
            flags.append(f"  - `{f['name']}: {f['type']}`{suffix}")
        forme = field_roles.ARCHETYPE_GUIDANCE[spec["archetype"]]
        anatomie = field_roles.ARCHETYPE_ANATOMY[spec["archetype"]]
        attendus = "\n".join(f"  - {a}" for a in anatomie["attendus"])
        liaisons = _liaisons(spec)
        entities_lines.append(
            f"### {ent}\n_Suggested form: {forme}._\n"
            f"_Close to: {anatomie['voisins']}._\n"
            f"What a visitor expects to find there:\n{attendus}\n"
            + "\n".join(flags) + liaisons)
    return entities_lines


def bloc_sections(contract):
    """The editorial sections, to publish as is."""
    # Editorial content (point 55). Written out in full that this text must be
    # RENDERED as is: it is content, not a style instruction, and nothing else
    # in the contract provides any.
    sections_block = ""
    if contract.get("sections"):
        corps = "\n\n".join(f"### {s['title']}\n{s['body']}"
                            for s in contract["sections"])
        sections_block = (
            "\n## Editorial content to publish as is\n"
            "These texts are supplied by the project's author: they must "
            "appear in the interface, each in its own section, with the given "
            "title and its own element carrying "
            "`data-monl-section=\"<slug>\"`. Do not rewrite them, do not "
            "invent them elsewhere — no API route serves them, they exist "
            "only here. If the editorial pattern is present, the editorial "
            "block carries these elements inside it: do not then create a "
            "second block repeating the same title or text. "
            "Each section must appear only once.\n\n"
            # Point 59: without this sentence, these texts ended up behind a
            # menu link, on a separate page. A visitor who opens only the home
            # page never saw them — for an "about", that misses its reason to
            # exist.
            "**On the home page, not only behind a link.** Each section must "
            "be readable as one scrolls the home page. A long text may appear "
            "there in a short version and continue on its own page, but it "
            "must never be absent from it.\n\n"
            + corps + "\n")
    return sections_block


def bloc_faq(contract):
    """The FAQ, stated as a list."""
    # POINT 94: the FAQ, stated as a LIST. Rendered in the same section as the
    # sections, it became a block of prose again — exactly the defect seen on
    # SneakerLab, where four questions fit in a single string and came out
    # stuck together in one paragraph. The interface was faithful: it was the
    # contract that could not say "questions/answers".
    faq_block = ""
    if contract.get("faq"):
        couples = "\n\n".join(f"**{q['question']}**\n{q['answer']}"
                              for q in contract["faq"])
        faq_block = (
            "\n## Frequently asked questions — a LIST, not running text\n"
            "Each pair below is a question and its answer, in the order the "
            "author chose. Render them as DISTINCT entries that can be spotted "
            "at a glance — accordion, definition list, or a bold question "
            "followed by its answer. Never as a single paragraph: an FAQ whose "
            "questions run together cannot be read, and the format carries the "
            "information as much as the text.\n\n"
            "Do not rewrite these texts, do not add any, do not reorder "
            "them.\n\n"
            + couples + "\n")
    return faq_block


def bloc_paiement(contract):
    """The non-negotiable payment line, when a Pay route exists."""
    # POINT 74: the route's note already says it, but it is here that the AI
    # reads what is not negotiable. Payment is the only frontend journey where
    # an interface mistake costs money — it deserves its own line, not just a
    # mention in the inventory of routes.
    paiement = [r for r in contract["routes"] if r["action"] == "Pay"]
    paiement_block = ""
    if paiement:
        chemins = ", ".join(f"`{r['path']}`" for r in paiement)
        paiement_block = (
            f"\n- Payment: {chemins} is called **with no body at all** — the "
            "amount comes from the database, not from you. Then redirect the "
            "browser to the returned `url`. NEVER call "
            "`POST /paiement/webhook`: it is the provider's route, it requires "
            "a signature and will refuse any request from the browser.")
    return paiement_block
