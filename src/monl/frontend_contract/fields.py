"""What a route accepts, and what the client is allowed to write.

Every field filled by the SERVER leaves `request_fields` through
`server_generated` (points 76 and 79): the contract describes what the
backend really does, not only what the spec declares."""

from ..ir import CompilationPlans


def _route(method, path, action, entity, is_public, actors, request_fields=None, note=None):
    r = {"method": method, "path": path, "action": action, "entity": entity,
         "auth_required": not is_public, "allowed_actors": actors}
    if request_fields is not None:
        r["request_fields"] = request_fields
    if note:
        r["note"] = note
    return r

def _list_query_contract(plans: CompilationPlans, entity):
    """Explicit contract of the list capabilities declared for an entity."""
    model = plans.entity_models[entity]
    filters = []
    for field in plans.filterable_fields.get(entity, ()):
        policy = model.fields[field]
        values = list(policy.allowed_values) if policy.allowed_values else None
        if policy.type == "Boolean":
            values = ["true", "false"]
        filters.append({
            "field": field,
            "parameter": field,
            "kind": "exact",
            "allowed_values": values,
        })
    sort_fields = list(plans.sortable_fields.get(entity, ()))
    result = {}
    if filters:
        result["filters"] = filters
    if sort_fields:
        result["sort"] = {
            "parameter": "sort",
            "direction_parameter": "direction",
            "fields": sort_fields,
            "directions": ["asc", "desc"],
        }
    return result

def _client_supplied_fks(plans: CompilationPlans, entity):
    """Foreign key columns the CLIENT must send at creation.

    Reproduces EXACTLY what generator/schemas.py writes into the Pydantic
    schema — and relies on its methods, never on parallel logic. The contract
    used to ignore them: it announced `POST /comment` with only the `content`
    field while the backend also required `article_id`, and every frontend
    faithful to the contract got a 422 (point 57).

    Two distinct origins, same consequence for the client:
      - a counter's target (`increments`/`decrements`): "I like THIS post" is
        the caller's choice, not a deduced property;
      - parents other than the owner: the owner is filled from the JWT, the
        rest must be stated (a comment and ITS article)."""
    # Same source as the schemas and the routes (point 117): each counter's
    # plan carries the targeted key. The contract used to recompute it on the
    # side, keeping only the "owner" relation — hence `variant_id` missing from
    # `POST /orderline` (issue #82, point 195). A target can also be an
    # ordinary client FK: `dict.fromkeys` keeps the order without duplicates.
    columns = [plan.target_fk
                for plan in plans.reputation_rules_by_trigger.get(entity, ())]
    columns.extend(plans.client_foreign_keys.get(entity, ()))
    return list(dict.fromkeys(columns))

def _creatable_fields(entity_spec):
    if not entity_spec:
        return []
    return ([f["name"] for f in entity_spec["fields"]
             if not f["server_generated"] and not f.get("postpayment_only")
             and not f.get("upload")]
            + list(entity_spec.get("client_foreign_keys", [])))

def _assets_contract(assets):
    """The contract's 'assets' section: where the human's files are, and which
    ones are declared. `served_at` gives the real URL, not the disk path —
    that is the one the browser will request."""
    folder = assets.get("dir") or "assets"
    contract = {
        "dir": folder,
        "served_at": f"/site/{folder}/",
        "note": (f"Files supplied by the human (photos, logo). Reference them with a "
                 f"RELATIVE path from the page: '{folder}/…'. Never modify or move "
                 f"them: they are not produced by the AI, and this folder lives OUTSIDE "
                 f"frontend/ to survive a frontend rebuild."),
    }
    for key in ("logo", "favicon"):
        if assets.get(key):
            contract[key] = f"{folder}/{assets[key]}"
    if "logo" in contract:
        contract["logo_note"] = ("A real logo is supplied: use it in the header rather "
                                "than a text wordmark.")
    return contract
