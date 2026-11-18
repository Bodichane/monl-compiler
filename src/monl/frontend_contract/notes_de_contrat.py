"""Ce que le contrat DIT à l'IA d'interface, en toutes lettres.

Une brique que le contrat ne décrit pas est une brique sans interface : ces
notes sont donc du produit, pas du commentaire. `_verrou_paiement` appelle
`_payment_locked_parents` du générateur et ne recalcule RIEN (point 91) —
deux vérités finiraient par diverger."""

from ..ir import CompilationPlans

_LIBELLES_IDENTIFIANT = {"email": "an email address",
                         "phone": "a phone number"}

def _libelle_identifiant(formes):
    """Ce que le champ 'username' doit RÉELLEMENT contenir (point 95)."""
    formes = [f for f in (formes or [])
              if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return "str"
    return "str — " + " or ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)

def _note_identifiant(formes, phone_prefix=None):
    """Sans cette note, l'IA étiquette « nom d'utilisateur » et laisse un champ
    texte libre : l'utilisateur saisit un pseudo, récolte un 422, et l'écran ne
    lui dit pas pourquoi (point 95)."""
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
    """Ce que l'interface doit savoir d'une valeur qui libère (point 98)."""
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
    """Entité dont l'encaissement FIGE les écritures sur 'entite' — elle-même si
    elle est payable, sinon le parent dont elle alimente le total (point 91).

    `inclure_soi=False` pour la CRÉATION : une entité payable ne se verrouille
    pas elle-même à la création (elle n'existe pas encore), seul un parent déjà
    réglé refuse une ligne de plus.

    Source unique partagée avec le générateur : `_payment_locked_parents` est ce
    qui produit réellement les gardes dans app.py. Recalculer la chaîne ici en
    ferait deux vérités, dont l'une finirait fausse."""
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
    """Note de contrat pour une notification déclenchée par Create."""
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
    """AJOUT (brique 23, point 106) : le rôle superviseur (declare via
    'sharedBy' sur une action regie par 'accessibleBy') transperce le controle
    par colonnes. Note de contrat : l'IA d'interface doit donner à ce rôle la
    vision/maîtrise de TOUT, et aux autres rôles seulement leurs parties."""
    if not supers:
        return None
    roles = ", ".join(supers)
    return (f"SUPERVISION ({action_nom}): the role {roles} accesses ALL "
            f"records, with no party restriction. The other roles allowed "
            f"here only see/modify the records they are one of the parties "
            f"of.")

def _note_list_query(query):
    """Texte court transmis à l'IA frontend avec le contrat JSON."""
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
