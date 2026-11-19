"""The routes announced to the frontend.

Same grouping as the real FastAPI generation — `_compute_route_map` is the
single, shared source (see generator/core.py). A test matches the contract
against the decorators actually written in app.py."""

from . import contract_notes, fields


def _routes_of_contract(entity_specs, plans, route_map):
    """The routes — CRUD from the SAME grouping as FastAPI generation
    (`_compute_route_map`, never parallel logic), then the upload routes,
    which come from no workflow."""
    # Routes — same grouping keys as the real FastAPI generation (route_map and
    # public are computed above, for the archetypes).
    routes = []
    for (act_type, target), plan in route_map.items():
        base = plan.base_target
        low = base.lower()
        access = plans.access_policies[(base, act_type)]
        is_public = access.public
        actors = sorted(access.actors)
        if act_type == "Create":
            # POINT 90: without this note, an interface AI builds a checkout
            # flow that hits a 409 on the very last screen — the only place
            # where the user has already filled in everything. The constraint
            # must show BEFORE, not be discovered at the end.
            required = plans.required_profiles.get(base)
            note_create = (
                f"PREREQUISITE: the caller must already own a {required}. Otherwise "
                f"this route answers 409 and creates nothing. Check on load "
                f"(GET /{required.lower()} returns theirs) and offer to create "
                f"the profile BEFORE the form, not after."
                if required else None)
            # POINT 91: creation is locked TOO — but only by a settled PARENT,
            # never by the entity itself: nothing prevents opening one more
            # order, it is ADDING a line to it that would raise the already
            # charged total. Hence `inclure_soi=False`. The contract kept quiet
            # about it while the backend already refused: a faithful AI drew a
            # "+ Add an item" on a paid order (checked on
            # `exemples/02_boutique.ml`).
            lock_parent = contract_notes._lock_payment(plans, base, include_soi=False)
            message = plans.message_rules_by_trigger.get(base)
            routes.append(fields._route("POST", f"/{low}", act_type, base, is_public, actors,
                                 request_fields=fields._creatable_fields(entity_specs.get(base)),
                                 note=contract_notes._join(note_create,
                                               contract_notes._note_lock(lock_parent, creation=True),
                                               contract_notes._note_message(message))))
            if required:
                routes[-1]["requires_own"] = required
            if lock_parent:
                routes[-1]["payment_locked"] = lock_parent
        elif act_type == "Read":
            # ADDED (brick 23, point 106): a supervisor role (declared through
            # 'sharedBy' on the same reference as 'accessibleBy') pierces the
            # column check. Without this note, an interface AI would apply the
            # party filter to the moderator themselves and carve out an empty
            # view — while the backend shows them everything.
            _sup_lecture = sorted(access.supervisors)
            _note_lecture = contract_notes._note_supervisors(_sup_lecture, "lecture")
            list_query = fields._list_query_contract(plans, base)
            routes.append(fields._route(
                "GET", f"/{low}", "List", base, is_public, actors,
                note=contract_notes._join(
                    "Parameters: limit (max 200), offset. Response: "
                    "{status, total, limit, offset, data: [...]}.",
                    contract_notes._note_list_query(list_query), _note_lecture)))
            if list_query:
                routes[-1]["list_query"] = list_query
            routes.append(fields._route("GET", f"/{low}/{{id}}", "Read", base, is_public, actors,
                                 note=_note_lecture))
            if _sup_lecture:
                routes[-1]["supervisors"] = _sup_lecture
                routes[-2]["supervisors"] = _sup_lecture
        elif act_type == "Update":
            routes.append(_route_of_modification(
                entity_specs, plans, base, low, act_type, is_public, actors))
        elif act_type == "Delete":
            lock = contract_notes._lock_payment(plans, base)
            # ADDED (brick 23, point 106): see the Read block — a deletion
            # supervisor sees/deletes every record.
            _sup_delete = sorted(access.supervisors)
            routes.append(fields._route("DELETE", f"/{low}/{{id}}", act_type, base, is_public,
                                 actors,
                                 note=contract_notes._join(contract_notes._note_lock(lock),
                                               contract_notes._note_supervisors(_sup_delete, "suppression"))))
            if _sup_delete:
                routes[-1]["supervisors"] = _sup_delete
            if lock:
                routes[-1]["payment_locked"] = lock
        elif act_type == "Execute":
            tag = plan.tags[0]
            routes.append(fields._route("POST", f"/workflow/{tag.lower()}/{target.lower()}",
                                 "Execute", target, is_public, actors))

    routes.extend(_routes_of_upload(plans))
    return routes


def _route_of_modification(entity_specs, plans, base, low, act_type, is_public, actors):
    """The PUT route and its notes. Extracted from `_routes_du_contrat`
    (complexity ceiling); same route, same keys, same order."""
    # ADDED (point 81): the Pydantic schema is UNIQUE per entity, so
    # these foreign keys must be sent (otherwise 422) -- but monl's
    # Update route does not write them: an attachment is fixed at
    # creation. Without this note, the contract suggested that an
    # interface could move a line from one cart to another, which the
    # backend accepts (200) without changing anything. Same requirement
    # as points 76 and 79: the contract describes what the backend
    # DOES.
    links = list(entity_specs.get(base, {}).get("client_foreign_keys", []))
    note_links = None
    if links:
        accord = ("must appear in the body (one schema per entity) but are "
                  "NOT modified" if len(links) > 1 else
                  "must appear in the body (one schema per entity) but is "
                  "NOT modified")
        note_links = (
            f"{', '.join(links)} {accord}: an attachment is set on creation. "
            f"Do not offer to change it — send back the current value.")
    # POINT 91: fourth form of the blind spot of points 88 to 90. A
    # route changes neither path, nor actors, nor fields, and yet gains
    # a refusal: as soon as payment is made, it answers 409. Without
    # this note, an interface faithful to the contract draws an "Edit"
    # button on a paid order — and the user discovers the refusal after
    # filling in the form.
    lock = contract_notes._lock_payment(plans, base)
    # POINT 98: the value that RELEASES, and the one-way trip. Without
    # this note, an interface offers "back to preparation" on a
    # cancelled order and discovers a 409 on click.
    release = (plans.release_rules_by_entity.get(base) or [None])[0]
    route = fields._route("PUT", f"/{low}/{{id}}", act_type, base, is_public, actors,
                         note=contract_notes._join(note_links, contract_notes._note_lock(lock),
                                       contract_notes._note_release(release)),
                         request_fields=fields._creatable_fields(entity_specs.get(base)))
    if lock:
        route["payment_locked"] = lock
    if release:
        route["releases_on"] = {
            "field": release["field"], "value": release["value"],
            "releases": release["releases"], "terminal": True}
    return route


def _routes_of_upload(plans):
    """The upload routes, which come from no workflow. Extracted from
    `_routes_du_contrat` (complexity ceiling); same routes, same order."""
    routes = []
    # BRICK B1: these routes are not JSON CRUD. They are produced by an Upload
    # declaration and must therefore be described separately in the contract:
    # multipart name, explicit limit, types really recognized, POST upload and
    # private GET read.
    for upload in plans.upload_fields:
        entity = upload["entity"]
        field = upload["field"]
        path = f"/{entity.lower()}/{{id}}/{field}"
        for action, method, contract_action, note in (
                ("Update", "POST", "Upload", (
                    f"multipart/form-data required, file field '{field}'. "
                    f"Exact limit: {upload['max_bytes']} bytes. Types accepted "
                    f"by byte signature: {', '.join(upload['accepted_types'])}. "
                    "The file name and Content-Type declared by the client "
                    "are ignored; the upload replaces the previous file after "
                    "validation.")),
                ("Read", "GET", "Download", (
                    "byte-for-byte download response with Content-Type "
                    "application/octet-stream and nosniff; the row's ACL "
                    "applies to the file too, a known path is not enough.")),
        ):
            access = plans.access_policies[(entity, action)]
            route = fields._route(method, path, contract_action, entity, False,
                           sorted(access.actors), note=note)
            route["upload"] = {
                "field_name": field,
                "max_bytes": upload["max_bytes"],
                "accepted_types": list(upload["accepted_types"]),
                "storage": "server_disk_reference",
            }
            routes.append(route)
    return routes
