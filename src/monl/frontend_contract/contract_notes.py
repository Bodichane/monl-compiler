"""What the contract TELLS the interface AI, in so many words.

A brick the contract does not describe is a brick without an interface:
these notes are therefore product, not commentary. `_verrou_paiement` calls
the generator's `_payment_locked_parents` and recomputes NOTHING (point 91)
— two truths would eventually diverge."""

from ..ir import CompilationPlans

_LIBELLES_IDENTIFIANT = {"email": "an email address",
                         "phone": "a phone number"}

def _libelle_identifiant(formes):
    """What the 'username' field must REALLY contain (point 95)."""
    formes = [f for f in (formes or [])
              if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return "str"
    return "str — " + " or ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)

def _note_identifiant(formes, phone_prefix=None):
    """Without this note, the AI labels it "username" and leaves a free text
    field: the user types a nickname, gets a 422, and the screen does not tell
    them why (point 95)."""
    formes = [f for f in (formes or []) if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return None
    quoi = " or ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)
    saisie = ("type=\"email\"" if formes == ["email"]
              else "type=\"tel\"" if formes == ["phone"]
              else "a text field accepting both")
    prefix_note = (
        f" For phone numbers, the declared calling code is `{phone_prefix}`: "
        "also accept the national notation and say so next to the field."
        if phone_prefix and "phone" in formes else ""
    )
    return (f"IDENTIFIER: the `username` field must contain {quoi} — 422 "
            f"otherwise. Label it accordingly on sign-up AND on sign-in "
            f"(use {saisie}), never \"username\". "
            f"The server puts the value in canonical form (address in lower "
            f"case, number reduced to its digits): two spellings of the same "
            f"address are the SAME account, and sign-in accepts either "
            f"one.{prefix_note}")

def _note_liberation(regle):
    """What the interface must know about a releasing value (point 98)."""
    if not regle:
        return None
    return (f"RELEASE: setting `{regle['field']}` to “{regle['value']}” returns "
            f"what the linked {regle['releases']} had deducted (the stock, "
            f"typically). It happens only on the TRANSITION: setting it a "
            f"second time returns nothing more. And it is a ONE-WAY trip — any "
            f"other value is then refused with 409, since nothing guarantees "
            f"that what was returned is still available. Do not offer to "
            f"reactivate: offer to create a new one.")

def _verrou_paiement(plans: CompilationPlans, entite, inclure_soi=True):
    """Entity whose payment FREEZES writes on 'entite' — itself if it is
    payable, otherwise the parent whose total it feeds (point 91).

    `inclure_soi=False` for CREATION: a payable entity does not lock itself at
    creation (it does not exist yet), only an already settled parent refuses
    one more line.

    Single source shared with the generator: `_payment_locked_parents` is what
    really produces the guards in app.py. Recomputing the chain here would
    make two truths, one of which would end up false."""
    if inclure_soi and entite in plans.payable_by_entity:
        return entite
    verrous = plans.payment_locked_parents.get(entite, ())
    return verrous[0]["entity"] if verrous else None

def _note_verrou(verrou, creation=False):
    if not verrou:
        return None
    action = ("this route refuses to attach one more record to it"
              if creation else "this route answers 409 and writes nothing")
    return (f"LOCK: as soon as the {verrou} is paid (payment_status is "
            f"'payee'), {action} — 409. Hide or "
            f"disable the action on a paid record rather than letting the "
            f"user discover it refused — a charged amount can no longer be "
            f"changed, it is refunded through the provider.")

def _note_message(regle):
    """Contract note for a notification triggered by Create."""
    if not regle:
        return None
    return (
        "NOTIFICATION: after this creation commits successfully, an "
        f"asynchronous attempt sends the subject “{regle['subject']}” to the "
        "account's address. Show that a message attempt was started, without "
        "promising delivery: an SMTP failure does not cancel the write and is "
        "logged server-side.")

def _joindre(*notes):
    retenues = [n for n in notes if n]
    return " ".join(retenues) if retenues else None

def _note_superviseurs(supers, action_nom):
    """ADDED (brick 23, point 106): the supervisor role (declared through
    'sharedBy' on an action governed by 'accessibleBy') pierces the column
    check. Contract note: the interface AI must give this role sight/control
    of EVERYTHING, and the other roles only their own parts."""
    if not supers:
        return None
    roles = ", ".join(supers)
    return (f"SUPERVISION ({action_nom}): the role {roles} accesses ALL "
            f"records, with no party restriction. The other roles allowed "
            f"here only see/modify the records they are one of the parties "
            f"of.")

def _note_list_query(query):
    """Short text passed to the frontend AI with the JSON contract."""
    if not query:
        return None
    notes = []
    if query.get("filters"):
        filtres = []
        for item in query["filters"]:
            valeurs = item["allowed_values"]
            suffixe = (" among " + ", ".join(repr(v) for v in valeurs)
                       if valeurs is not None else " an exact value of the field's type")
            filtres.append(f"parameter {item['parameter']}{suffixe}")
        notes.append("Exact FILTERING, only on the declared fields: "
                     + "; ".join(filtres))
    if query.get("sort"):
        tri = query["sort"]
        notes.append("SORT: parameter sort among "
                     + ", ".join(tri["fields"])
                     + ", with direction=asc or direction=desc. No other "
                     "field, operator or query language is accepted.")
    return " ".join(notes)
