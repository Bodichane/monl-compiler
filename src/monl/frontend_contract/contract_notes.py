"""What the contract TELLS the interface AI, in so many words.

A brick the contract does not describe is a brick without an interface:
these notes are therefore product, not commentary. `_verrou_paiement` calls
the generator's `_payment_locked_parents` and recomputes NOTHING (point 91)
— two truths would eventually diverge."""

from ..ir import CompilationPlans

_LABELS_IDENTIFIER = {"email": "an email address",
                         "phone": "a phone number"}

def _label_identifier(formes):
    """What the 'username' field must REALLY contain (point 95)."""
    formes = [f for f in (formes or [])
              if f in _LABELS_IDENTIFIER]
    if not formes:
        return "str"
    return "str — " + " or ".join(_LABELS_IDENTIFIER[f] for f in formes)

def _note_identifier(formes, phone_prefix=None):
    """Without this note, the AI labels it "username" and leaves a free text
    field: the user types a nickname, gets a 422, and the screen does not tell
    them why (point 95)."""
    formes = [f for f in (formes or []) if f in _LABELS_IDENTIFIER]
    if not formes:
        return None
    what = " or ".join(_LABELS_IDENTIFIER[f] for f in formes)
    input_ = ("type=\"email\"" if formes == ["email"]
              else "type=\"tel\"" if formes == ["phone"]
              else "a text field accepting both")
    prefix_note = (
        f" For phone numbers, the declared calling code is `{phone_prefix}`: "
        "also accept the national notation and say so next to the field."
        if phone_prefix and "phone" in formes else ""
    )
    return (f"IDENTIFIER: the `username` field must contain {what} — 422 "
            f"otherwise. Label it accordingly on sign-up AND on sign-in "
            f"(use {input_}), never \"username\". "
            f"The server puts the value in canonical form (address in lower "
            f"case, number reduced to its digits): two spellings of the same "
            f"address are the SAME account, and sign-in accepts either "
            f"one.{prefix_note}")

def _note_release(rule):
    """What the interface must know about a releasing value (point 98)."""
    if not rule:
        return None
    return (f"RELEASE: setting `{rule['field']}` to “{rule['value']}” returns "
            f"what the linked {rule['releases']} had deducted (the stock, "
            f"typically). It happens only on the TRANSITION: setting it a "
            f"second time returns nothing more. And it is a ONE-WAY trip — any "
            f"other value is then refused with 409, since nothing guarantees "
            f"that what was returned is still available. Do not offer to "
            f"reactivate: offer to create a new one.")

def _lock_payment(plans: CompilationPlans, entity, include_soi=True):
    """Entity whose payment FREEZES writes on 'entite' — itself if it is
    payable, otherwise the parent whose total it feeds (point 91).

    `inclure_soi=False` for CREATION: a payable entity does not lock itself at
    creation (it does not exist yet), only an already settled parent refuses
    one more line.

    Single source shared with the generator: `_payment_locked_parents` is what
    really produces the guards in app.py. Recomputing the chain here would
    make two truths, one of which would end up false."""
    if include_soi and entity in plans.payable_by_entity:
        return entity
    locks = plans.payment_locked_parents.get(entity, ())
    return locks[0]["entity"] if locks else None

def _note_lock(lock, creation=False):
    if not lock:
        return None
    action = ("this route refuses to attach one more record to it"
              if creation else "this route answers 409 and writes nothing")
    return (f"LOCK: as soon as the {lock} is paid (payment_status is "
            f"'payee'), {action} — 409. Hide or "
            f"disable the action on a paid record rather than letting the "
            f"user discover it refused — a charged amount can no longer be "
            f"changed, it is refunded through the provider.")

def _note_message(rule):
    """Contract note for a notification triggered by Create."""
    if not rule:
        return None
    return (
        "NOTIFICATION: after this creation commits successfully, an "
        f"asynchronous attempt sends the subject “{rule['subject']}” to the "
        "account's address. Show that a message attempt was started, without "
        "promising delivery: an SMTP failure does not cancel the write and is "
        "logged server-side.")

def _join(*notes):
    kept = [n for n in notes if n]
    return " ".join(kept) if kept else None

def _note_supervisors(supers, action_name):
    """ADDED (brick 23, point 106): the supervisor role (declared through
    'sharedBy' on an action governed by 'accessibleBy') pierces the column
    check. Contract note: the interface AI must give this role sight/control
    of EVERYTHING, and the other roles only their own parts."""
    if not supers:
        return None
    roles = ", ".join(supers)
    return (f"SUPERVISION ({action_name}): the role {roles} accesses ALL "
            f"records, with no party restriction. The other roles allowed "
            f"here only see/modify the records they are one of the parties "
            f"of.")

def _note_list_query(query):
    """Short text passed to the frontend AI with the JSON contract."""
    if not query:
        return None
    notes = []
    if query.get("filters"):
        filters = []
        for item in query["filters"]:
            values = item["allowed_values"]
            suffix = (" among " + ", ".join(repr(v) for v in values)
                       if values is not None else " an exact value of the field's type")
            filters.append(f"parameter {item['parameter']}{suffix}")
        notes.append("Exact FILTERING, only on the declared fields: "
                     + "; ".join(filters))
    if query.get("sort"):
        sort = query["sort"]
        notes.append("SORT: parameter sort among "
                     + ", ".join(sort["fields"])
                     + ", with direction=asc or direction=desc. No other "
                     "field, operator or query language is accepted.")
    return " ".join(notes)
