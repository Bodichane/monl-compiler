"""Each entity's contract: fields, roles, what the server fills."""

from ..ast_validator.fields import FieldsMixin
from ..ir import PAYMENT_REF_COLUMN, PAYMENT_STATUS_COLUMN
from . import field_roles
from . import fields as contract_fields


def _specs_of_entities(entities, fk_placements, readable, plans):
    """Each entity's contract: fields, roles, what the server fills."""
    # POINT 79: a 'derivedFrom' field is CALCULATED by the server, hence absent
    # from request bodies — exactly like a 'generated' field. The contract had
    # to say so: without it, it announced `total` among the fields to send, and
    # an interface AI faithful to the contract would have built a price form
    # the server ignores. It is the point 76 defect, reproduced on the brick
    # that had just fixed it — the lesson "declare what the backend REALLY
    # does" also holds when a brick removes something, not only when it adds a
    # column.
    #
    # POINT 82: same requirement for 'sumOf'. The point 76 defect has already
    # reproduced twice (points 79 and 81): declare it here from the start
    # rather than wait for an interface AI to build a "total" field the server
    # recomputes. A cart total is the case where the gap shows fastest — it
    # changes with every line added.
    #
    # POINT 89: fourth member of the same family. The point 76 defect
    # reproduced on each of the three previous ones; this one arrives declared.
    #
    # POINT 102: fifth member of the same family, declared from the start too.
    # Without it the contract would announce an "order number" among the fields
    # to enter, and an interface AI faithful to the contract would draw a form
    # the server ignores.
    entity_specs = {}
    for ent, fields in entities.items():
        field_list = []
        entity_model = plans.entity_models[ent]
        for fname, ftype in fields.items():
            policy = entity_model.fields[fname]
            populated_by_the_server = policy.server_generated
            field = {
                "name": fname,
                "type": ftype,
                # POINT 91: what the SERVER requires, not what the spec
                # declares. The contract reflected `rule X.y required` — yet
                # the generated Pydantic schemas make EVERY input field
                # mandatory, without exception (point 85: "required stays an
                # assertion, the schemas already make every field mandatory").
                # A frontend faithful to the contract therefore omitted the
                # undeclared fields and got a 422. Seen for real: adding
                # `email` and `address` to a customer profile broke the form of
                # a running site, while the contract announced them as
                # optional.
                "required": not populated_by_the_server and not policy.upload_rule,
                # hidden: never present in read responses
                "hidden_in_reads": policy.hidden_in_reads,
                # generated, derivedFrom or sumOf: NOT to be sent, the server
                # fills it itself (and would ignore it in the request body)
                "server_generated": populated_by_the_server,
                # categorized: reading returns a label, not the number
                "categorized_in_reads": policy.categorized_in_reads,
                "postpayment_only": policy.postpayment_only,
            }
            # BRICK B3: only the spec's declarations appear. The absence of
            # these keys means "not filterable/sortable"; that keeps the
            # contract of historical specs byte-identical.
            if fname in plans.filterable_fields.get(ent, ()):
                _render_filterable(field, fname, ftype, policy)
            if fname in plans.sortable_fields.get(ent, ()):
                field["sortable"] = True
            if policy.upload_rule:
                # BRICK B1: the field is a dedicated multipart input, not a
                # JSON value and not an Image asset. The contract exposes the
                # limit, the types, the exact field name and the two routes
                # added below; the frontend AI has nothing to guess.
                field["upload"] = {
                    "field_name": fname,
                    "max_bytes": policy.upload_rule.max_bytes,
                    "accepted_types": list(policy.upload_rule.accepted_types),
                    "storage": "server_disk_reference",
                    "note": ("bytes received at runtime; the client's file name and "
                             "Content-Type are ignored, the type is established "
                             "by byte signature; private read according to the "
                             "row's ACL, as a byte-for-byte download"),
                }
            # BRICK 19 (point 96): the allowed values. Without them, the AI
            # draws a TEXT field and the user makes up a status that gets a 422
            # — while the list fits in a dropdown menu. Same reason as the
            # bounds below: the contract describes what the backend REFUSES as
            # much as what it accepts.
            choice = policy.allowed_values
            if choice:
                field["allowed_values"] = list(choice)
            # POINT 85: the 'min'/'max' bounds give a 422 before any INSERT.
            # The contract MUST announce them: an interface that ignores them
            # lets the user fill in a form only to be refused at the end, when
            # it could have said so right away. Same reason as for
            # `server_generated` (point 79) — the contract describes what the
            # backend REALLY does, including what it REFUSES.
            _ask_bounds(field, policy)
            field.update(_non_blank_constraint(ftype, policy))
            if policy.constraints.unique:
                field["unique"] = True
                field["unique_note"] = ("unique value enforced by the database: a "
                                        "duplicate creation or update answers "
                                        "409, not 422 — tell the user rather "
                                        "than replaying the request.")
            _note_field_computed(field, policy, ent)
            field_list.append(field)
        # POINT 88: a monl foreign key references one of TWO things, and the
        # contract said only one. Those the Create route fills from the token
        # carry an ACCOUNT identifier (`_monl_users.id`); the others carry the
        # business table's `id`. `schema.sql` even writes two different
        # `REFERENCES` — the contract, however, announced "references:
        # Customer" in both cases.
        #
        # What it cost: an interface following the contract joins
        # `order.customer_id` to `customer.id`, whereas the right join is
        # `customer.customer_id`. A join that HALF works — only as long as the
        # account id and the profile id coincide, that is, on the first
        # records, that is, during testing.
        fks = _links_of_entity(ent, fk_placements, plans)
        roles = field_roles._assign_field_roles(field_list)
        for f in field_list:
            f["role"] = roles.get(f["name"])
        # POINT 76: the two tracking columns of the 'payable' brick are present
        # in every read response (the generator does a SELECT *) but were
        # declared NOWHERE in the contract. An interface AI following it to the
        # letter therefore could not know they exist, and could not display a
        # payment's state: the payment button could be drawn, its result could
        # not.
        #
        # Added AFTER role assignment, on purpose: passed to
        # _assign_field_roles, they would have taken two of the three "meta"
        # slots (point 35) and been displayed as any secondary information,
        # pushing out real spec fields. They therefore have no role — what to
        # do with them is spelled out in the brief, not deduced from a layout
        # role.
        if ent in plans.payable_by_entity:
            # Each column carries ITS OWN explanation: describing them in one
            # shared sentence made `payment_ref`, which holds a session
            # reference, announce "'en_attente' / 'payee'" — seen when
            # rereading the produced brief, not the code.
            tracking = (
                (PAYMENT_STATUS_COLUMN,
                 "payment state, written by the server alone: 'en_attente' "
                 "while nothing is charged, 'payee' once the provider's "
                 "webhook is received — this field says whether it is paid"),
                (PAYMENT_REF_COLUMN,
                 "the session reference at the provider, written by the "
                 "server alone; useful for accounting reconciliation, of no "
                 "interest to the visitor. It may be filled AS SOON AS the "
                 "session opens, before any charge: so it is not a payment "
                 "indicator, payment_status is what says whether it is "
                 "paid"),
            )
            for column, explanation in tracking:
                field_list.append({
                    "name": column,
                    "type": "String",
                    "required": False,
                    "hidden_in_reads": False,
                    # Never supplied by the client: the same prohibition as
                    # 'generated'.
                    "server_generated": True,
                    "categorized_in_reads": False,
                    "payment_tracking": True,
                    "note": explanation,
                    "role": None,
                })
        entity_specs[ent] = {
            "fields": field_list, "foreign_keys": fks,
            "client_foreign_keys": contract_fields._client_supplied_fks(plans, ent),
            "archetype": field_roles._archetype(
                roles, ent in readable,
                bool(plans.access_policies.get((ent, "Read"), None)
                     and plans.access_policies[(ent, "Read")].public)),
        }
    return entity_specs


def _non_blank_constraint(type_, policy):
    if (type_ in FieldsMixin.BOUNDS_TEXT and policy.constraints.required
            and not policy.server_generated):
        return {"non_blank": True}
    return {}


# The three functions below are extracted from `_specs_des_entites`
# (complexity ceiling): same keys, same values, same insertion order.
def _render_filterable(field, fname, ftype, policy):
    """Marks a field as an exact-match list filter."""
    values_filter = (list(policy.allowed_values)
                       if policy.allowed_values else None)
    if ftype == "Boolean":
        values_filter = ["true", "false"]
    field["filterable"] = True
    field["filter"] = {
        "parameter": fname,
        "kind": "exact",
        "allowed_values": values_filter,
    }


def _note_field_computed(field, policy, ent):
    """What the server computes for this field, and how to display it."""
    derive = policy.derived_rule
    somme = policy.aggregate_rule
    number = policy.numbering_rule
    if derive:
        field["derived_from"] = (f"{derive.source_entity}."
                                 f"{derive.source_field}")
        field["derived_factor"] = derive.factor
        field["note"] = (
            f"calculated by the server: {derive.source_entity}."
            f"{derive.source_field} × {derive.factor}. Do not "
            f"send it, and do not calculate it in the browser to "
            f"show it before creation — reread the value returned by "
            f"the server, it is the one that will be charged.")
    if somme:
        field["summed_from"] = (f"{somme.source_entity}."
                                f"{somme.source_field}")
        field["note"] = (
            f"total recalculated by the server: sum of the attached "
            f"{somme.source_entity}.{somme.source_field}. "
            f"Do not send it. It changes with each {somme.source_entity} "
            f"added, modified or deleted: reread the "
            f"{ent} after each line write rather than keeping a "
            f"total in the browser, which would drift.")
    if policy.timestamped:
        field["created_at"] = True
        field["note"] = (
            "creation instant, written by the server in ISO 8601 UTC "
            "(e.g. '2026-07-31T04:18:22.310+00:00'), and never changed afterwards. "
            "Do not send it: neither on creation nor on update. "
            "It sorts as text — comparing the strings is enough, "
            "no need to convert them to order a list. "
            "MAY BE EMPTY on records created before the rule was "
            "added: show a dash, never today's date — that date "
            "was not lost, it never existed.")
    if number:
        field["numbered_as"] = number.format
        field["note"] = (
            f"readable number assigned by the server on creation, on the "
            f"template “{number.format}”, and never changed afterwards. "
            f"Do not send it: neither on creation nor on update. "
            f"It is the reference a human reads and dictates — SHOW it "
            f"wherever the record is identified (list, detail, order "
            f"confirmation), preferably before the technical `id`, "
            f"and make it copyable. "
            + ("It sorts as text, the sequence part being padded "
               "with zeros. " if "{N" in number.format else "")
            + "MAY BE EMPTY on records created before the rule was "
              "added: show a dash, never an invented number.")


def _links_of_entity(ent, fk_placements, plans):
    """The entity's foreign keys, and what each one really contains."""
    identity_cols = plans.identity_foreign_keys.get(ent, frozenset())
    fks = []
    for p in fk_placements.get(ent, []):
        link = {"column": p["fk_column"], "references": p["owner_entity"],
                "unique": p["unique"]}
        if p["fk_column"] in identity_cols:
            link["references_account"] = True
            # The business profile is found through the column of the SAME
            # NAME, which carries the same account identifier — not through
            # its `id`.
            link["note"] = (
                f"contains an ACCOUNT identifier (the holder's), "
                f"not the `id` of a {p['owner_entity']} record. To "
                f"find the record: look for the {p['owner_entity']} whose "
                f"`{p['fk_column']}` has this same value — never the one "
                f"whose `id` has it, the match would be accidental.")
        else:
            link["references_account"] = False
            link["note"] = (f"contains the `id` of a "
                            f"{p['owner_entity']} record.")
        fks.append(link)
    return fks


def _ask_bounds(field, policy):
    """`min_length`/`max_length` for text, `min_value`/`max_value` for numbers."""
    for name, bound in (("min", policy.constraints.minimum),
                       ("max", policy.constraints.maximum)):
        if bound:
            field[f"{name}_{'length' if bound.portee == 'longueur' else 'value'}"] = \
                bound.valeur
