"""The contract's fingerprint — EIGHT sets, and a dictionary.

THE DELTA BLIND SPOT, eight times (points 88 to 116): a brick that adds a
promise to the contract must ask whether this function SEES it. Six times
the answer was no, and six times `monl update` would have answered "no
interface change", leaving a whole screen to write."""

import hashlib
import json


def _contract_signature(contract):
    routes = {f"{r['method']} {r['path']}" for r in contract["routes"]}
    fields = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
              for f in spec["fields"]}
    field_types = {f"{e}.{f['name']}": f["type"]
                   for e, spec in contract["entities"].items()
                   for f in spec["fields"]}
    access, prerequisites, locks = _ensembles_des_routes(contract)
    # POINT 89: a field is not only present or absent — it is ENTERABLE or not,
    # and that changes the interface just as much. Setting 'rule Order.total
    # derivedFrom …' on a field that already existed renames nothing: the delta
    # answered "no change" while the price form became a field the server
    # ignores. The same blind spot as point 88, on the other half of the
    # contract.
    read_single = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
                     for f in spec["fields"] if f.get("server_generated")}
    contents = _contents_editorial(contract)
    contents.update(_contents_of_fields(contract))
    contents.update(_contents_of_rules(contract))
    links = _links_of_the_signature(contract)
    sections_required = _sections_required(contract)
    return (routes, fields, access, read_single, prerequisites, locks,
            contents, links, field_types, sections_required)


def _ensembles_des_routes(contract):
    """Actors, prerequisites and payment locks carried by the routes."""
    # POINT 88: WHO may call a route is part of the interface. The delta only
    # compared method+path: opening the order book to the administrator created
    # no new route — only one more actor on existing routes — and 'monl update'
    # answered "no interface change, the existing frontend stays valid". It was
    # true and misleading: nothing was broken, but a whole screen was missing,
    # and the delta report exists precisely to say what remains to write.
    access = {f"{r['method']} {r['path']} → {actor}"
             for r in contract["routes"]
             for actor in r.get("allowed_actors") or []}
    # POINT 90: third form of the same blind spot. A route can gain a
    # PREREQUISITE without changing path, actors or fields — and the frontend
    # must still be rewritten: here, create the profile before the checkout
    # flow, or get a 409 on the last screen. Comparing routes was not enough,
    # nor comparing actors (point 88) or read-only fields (point 89). It is the
    # third time: the delta must compare EVERYTHING the contract promises, not
    # only what has a new name.
    prerequisites = {f"{r['method']} {r['path']} → requires a {r['requires_own']}"
                  for r in contract["routes"] if r.get("requires_own")}
    # POINT 91: fourth time. Setting 'payable' freezes writes on the charged
    # record AND on its lines: the routes change neither path, nor actors, nor
    # fields, but an "Edit" button drawn without knowing it leads to a 409. A
    # lock carried by a route that just appeared is excluded from the report —
    # already stated by "route added", the same anti-duplication trade-off as
    # in points 88 to 90.
    locks = {f"{r['method']} {r['path']} → frozen once {r['payment_locked']} is paid"
               for r in contract["routes"] if r.get("payment_locked")}
    return access, prerequisites, locks


def _contents_editorial(contract):
    """Sections, footer links, FAQ and account identifier: digests by key."""
    # POINT 94: fifth time, and the first that does not concern data. The delta
    # looked ONLY at the API — adding an editorial section or a FAQ question
    # touches no route, no field, and 'monl update' answered "no interface
    # change" while a whole block remained to write on the home page. The blind
    # spot had existed for `section` since point 55; the FAQ would have fallen
    # into it on the day it was born.
    #
    # A DICTIONARY and not a set, unlike the six others: the text matters as
    # much as the title. Comparing titles alone is exactly the point 89 error —
    # rewriting "Delivery and returns" from top to bottom renames nothing, and
    # yet the page must be re-rendered.
    contents = {f"section “{s['title']}”": hashlib.sha256(
                    "\n".join(s["body"]).encode("utf-8")).hexdigest()
                for s in contract.get("sections") or []}
    # BRICK 30: TENTH time, and the question asked before writing the brick.
    # Declaring a footer link creates no route, renames no field, touches no
    # actor — and the footer must be rewritten, or face a "declared link absent
    # from the site" refusal. The ADDRESS enters the digest, not only the
    # label: fixing a typo in a URL renames nothing either (lesson of points 89
    # and 96).
    contents.update({f"link “{link['label']}”": hashlib.sha256(
                         link["url"].encode("utf-8")).hexdigest()
                     for link in contract.get("links") or []})
    contents.update({f"question “{q['question']}”": hashlib.sha256(
                         "\n".join(q["answer"]).encode("utf-8")).hexdigest()
                     for q in contract.get("faq") or []})
    # POINT 95: the point 94 question, asked BEFORE writing the brick this
    # time. Declaring 'identifier: email' creates no route and renames no field
    # — the '/register' body keeps the same keys — but the registration screen
    # changes: label, input type, error message. Without this, the delta would
    # have said "no interface change" while a form started answering 422
    # without explaining why.
    formes = (contract.get("api", {}).get("auth", {}).get("register", {})
              .get("identifier_forms") or [])
    if formes:
        contents[f"account identifier ({', '.join(formes)})"] = "forme"
    return contents


def _contents_of_fields(contract):
    """Releases, value lists, non-blank text and uploads, field by field."""
    contents = {}
    # POINT 96: sixth time. Setting `oneOf` on an existing field renames
    # nothing — but a text field becomes a MENU, and the list of values can
    # change without the field moving ("shipped" added to the order book). The
    # digest therefore carries the values, not only their presence: comparing
    # names alone would be the point 89 error, for the third time.
    #
    # POINT 98: seventh time. Setting `releases` creates no route and changes
    # no field — but a "reactivate" button becomes a 409, and a screen must
    # explain that cancellation gives the stock back. The delta says so.
    for r in contract["routes"]:
        lib = r.get("releases_on")
        if lib:
            contents[f"release on {r['method']} {r['path']}"] = hashlib.sha256(
                f"{lib['field']}\n{lib['value']}\n{lib['releases']}".encode()
            ).hexdigest()
    for entity, spec in sorted((contract.get("entities") or {}).items()):
        for field in spec.get("fields") or []:
            contents.update(_non_blank_signature(entity, field))
            if field.get("allowed_values"):
                contents[f"choices of {entity}.{field['name']}"] = hashlib.sha256(
                    "\n".join(field["allowed_values"]).encode("utf-8")).hexdigest()
            # BRICK B1: an Upload constrains a frontend input even if the field
            # already existed. The signature carries the contract's bytes
            # (multipart name, limit and MIME), not an uploaded value. A change
            # of max/types therefore does trigger the delta; a spec without
            # Upload adds no entry and keeps its signature.
            if field.get("upload"):
                contents[f"upload of {entity}.{field['name']}"] = hashlib.sha256(
                    json.dumps(field["upload"], sort_keys=True,
                               ensure_ascii=False).encode("utf-8")).hexdigest()
    return contents


def _contents_of_rules(contract):
    """Business rules the routes and fields do not show."""
    contents = {}
    # POINT 116: ninth and tenth time. `publicWhen` and `oncePer` live in
    # `business_rules`, which the signature did not read: setting 'rule
    # Article.Read publicWhen status "published"' creates no route, renames no
    # field and changes no actor — `monl update` answered "no interface change"
    # while a "draft" state, a list filter and a moderation screen had to be
    # drawn. `oncePer` is the same blind spot on the write side: the "vote"
    # button gains a 409 nobody announced. The VALUE enters the digest, not
    # only the presence of the rule: going from "published" to "validated"
    # renames nothing either (lesson of points 89 and 96).
    rules_metier = contract.get("business_rules") or {}
    for reference, condition in sorted((rules_metier.get("public_when") or {}).items()):
        contents[f"conditional publication of {reference}"] = hashlib.sha256(
            f"{condition.get('field')}\n{condition.get('value')}".encode()).hexdigest()
    for rule in rules_metier.get("once_per") or []:
        contents[f"uniqueness of {rule['trigger_entity']}"] = hashlib.sha256(
            "\n".join(rule["parents"]).encode("utf-8")).hexdigest()
    # BRICK 2a: twelfth time, and the question asked BEFORE writing the brick.
    # Going from EUR to XOF creates no route, renames no field and changes no
    # actor — but ALL displayed prices change symbol, and the division by a
    # hundred an interface does for the euro becomes wrong. A frontend written
    # before the change therefore shows euros on CFA francs, or a hundredth of
    # the amount. The EXPONENT enters the digest as much as the code: two
    # currencies can share a symbol and not their decimals, and comparing only
    # the code would be the point 89 error.
    payment = rules_metier.get("payment")
    if payment:
        # The PROVIDER enters the same digest (brick 2b): going from Stripe to
        # FedaPay changes neither route nor field, but the payment screen stops
        # talking about bank cards and starts talking about mobile money
        # operators.
        contents["devise d'encaissement"] = hashlib.sha256(
            f"{payment.get('provider')}\n{payment.get('currency')}\n"
            f"{payment.get('minor_unit_exponent')}".encode()).hexdigest()
    # BRICK B2: a message adds no route, but it changes the journey after a
    # creation and the text the interface must display. The delta covers the
    # trigger, the announced recipient and the full content; comparing only the
    # presence of the rule would let a change of subject or body slip through.
    for message in rules_metier.get("messages") or []:
        reference = message["trigger"]
        contents[f"outgoing message of {reference}"] = hashlib.sha256(
            json.dumps(message, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    # BRICK B3: a filter or a sort adds frontend work even if the routes and
    # fields carry the same names. The digest carries the whitelist, the finite
    # values and both sort directions; a change to this capability must
    # therefore trigger the contract delta.
    for route in contract.get("routes") or []:
        query = route.get("list_query")
        if query:
            contents[f"list capabilities of {route['method']} {route['path']}"] = hashlib.sha256(
                json.dumps(query, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
    # BRICK B4: lockout and the session/TOTP parameters change screens without
    # necessarily adding a business field. The signature carries the full
    # configuration, including durations and the rotation/replay guarantees. A
    # spec without B4 adds no entry.
    auth_features = (contract.get("api", {}).get("auth", {}).get("features") or {})
    if auth_features:
        contents["authentification B4"] = hashlib.sha256(
            json.dumps(auth_features, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    return contents


def _links_of_the_signature(contract):
    """What each foreign key contains, and who fills it."""
    # POINT 99: eighth set, and the question asked BEFORE writing the code for
    # only the second time. A foreign key does not live in `fields` — so the
    # delta could say nothing when it changes NATURE. Yet it changes in two
    # ways, and both rewrite a screen:
    #
    # - what it CONTAINS: an account id or the id of a business row. The
    #   contract has said so since point 88, precisely because a join made on
    #   the wrong one of the two HALF works;
    # - who FILLS it: the server from the token, or the client. Going from the
    #   first to the second adds a mandatory field to the creation form — a
    #   product menu on "new variant" — without renaming anything. Without this
    #   line, `monl update` answered "no interface change" and the POST got a
    #   422.
    links = set()
    for entity, spec in sorted((contract.get("entities") or {}).items()):
        designees = set(spec.get("client_foreign_keys") or [])
        for link in spec.get("foreign_keys") or []:
            porte = ("an account identifier" if link.get("references_account")
                     else f"the id of a {link['references']}")
            par = "to be sent by the client" if link["column"] in designees \
                else "filled by the server"
            links.add(f"{entity}.{link['column']} → {porte}, {par}")
    return links


def _sections_required(contract):
    """The required sections and the substance rule of each."""
    # POINT 119: NINTH time, and the question asked before writing the brick
    # this time. The section floor and the substance required of each create no
    # route, rename no field and touch no actor — but a site compliant
    # yesterday becomes non-compliant, and `monl run --check` refuses it.
    # Without this entry, `monl update` would answer "no interface change" just
    # before the site stops starting: the worst of both worlds. The digest
    # carries the RULE and not only the section name — raising `trust`'s text
    # threshold also forces a rewrite, exactly as in point 89.
    from ..design_system import _section_substance, infer_design_profile
    profile = infer_design_profile(contract)
    sections_required = {
        marker.partition("=")[2].strip('"'): hashlib.sha256(
            json.dumps(rule, sort_keys=True).encode("utf-8")).hexdigest()
        for marker, rule in _section_substance(contract, profile).items()
    }
    return sections_required


def _non_blank_signature(entity, field):
    if field.get("non_blank"):
        return {f"non-blank text of {entity}.{field['name']}": "strip"}
    return {}
