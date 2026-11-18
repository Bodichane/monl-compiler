"""Payment: the two routes, the currency, the provider, post-payment.

The CURRENCY is part of the interface: without it, a shop in Cotonou shows
euros on CFA francs. The PROVIDER too — "Pay by card" and "Pay by Mobile
Money" are not drawn the same way."""

from ..ir import PAYMENT_STATUS_COLUMN
from . import champs


def _paiement_du_contrat(plans, routes):
    """Payment: the two routes, the currency, the provider, and what stays
    editable AFTER payment (point 113)."""
    # PAYMENT BRICK (point 74). These two routes do NOT come out of route_map —
    # they are born not from a workflow but from a `payable` rule — and the
    # contract therefore ignored them. Concrete consequence: the interface AI
    # could not draw the payment button, and would have forbidden itself to
    # anyway, since the contract forbids it to call a path absent from
    # `routes`. A brick the contract does not describe is a brick without an
    # interface.
    payables = plans.payable_by_entity
    # BRICK 2a: the CURRENCY is part of the interface. Without it, the AI
    # writes "€" because that is what it has seen everywhere else, and a shop
    # in Cotonou shows euros on CFA francs. The exponent travels with the code:
    # it is what says whether `montant_centimes` must be divided by a hundred
    # (euro) or not at all (CFA franc).
    devise = plans.payment_currency or {"code": "EUR", "exponent": 2}
    # BRICK 2b: the provider is part of the interface. "Pay by card" and "Pay
    # by Mobile Money" are not drawn the same way, and the AI would write "bank
    # card" by default for lack of knowing.
    prestataire = plans.payment_provider or "stripe"
    for entite, champ in sorted(payables.items()):
        # POINT 87: under transitive ownership, "belongs" is read through the
        # intermediate, and a record whose intermediate has disappeared answers
        # 404. The interface must know both, otherwise it treats a 404 as a
        # technical error where it is a business answer.
        chaine = plans.transitive_ownership.get(entite)
        premier = chaine["chain"][0] if chaine else None
        via = (f"This {entite} belongs to whoever owns its "
               f"{premier}: this chain (of depth "
               f"{len(chaine['chain'])} link(s)) is what the 403 checks, and "
               f"a {entite} whose {premier} no longer exists answers "
               f"404. " if premier else "")
        routes.append(champs._route(
            "POST", f"/{entite.lower()}/{{id}}/paiement", "Pay", entite,
            False, sorted(plans.actors),
            note=(via + "Opens a payment session for this record. "
                  "NO body: the amount is read from the database in "
                  f"`{champ}`, never received from the client. Response: {{status, url, "
                  "session_id, montant_centimes, devise, montant} — redirect "
                  "the browser to `url`. "
                  # The name `montant_centimes` is kept (point 95: renaming it
                  # would break the "Pay" button of every existing project),
                  # but it does NOT mean "cents" everywhere: it is the
                  # currency's minor unit. Saying so is the only way to stop an
                  # interface from dividing an amount in CFA francs by a
                  # hundred.
                  + (f"Payment goes through **{prestataire}**: "
                     + ("the payer chooses their MOBILE MONEY operator "
                        "(MTN MoMo, Moov, Wave) on the provider's page — "
                        "do not write \"credit card\". "
                        if prestataire == "fedapay"
                        else "the payer pays by card on the provider's "
                             "page. "))
                  + f"Amounts are in **{devise['code']}**: show "
                  f"`montant` as is with this code, and NEVER divide "
                  f"`montant_centimes` by a hundred without checking the exponent — "
                  + ("this currency has no minor unit, both fields "
                     "hold the same value. " if devise["exponent"] == 0
                     else f"here the exponent is {devise['exponent']}. ")
                  + "403 if the record belongs to "
                  "someone else, 409 if it is already paid, 503 if the "
                  "server has no payment key configured. "
                  # Point 76: closing the loop. Knowing how to open a payment
                  # does not say how to show its outcome; the tracking field
                  # carries it, and it is NOT up to date on return from the
                  # provider (its webhook writes it, later).
                  f"The outcome is read in the {entite}'s "
                  f"`{PAYMENT_STATUS_COLUMN}` ('en_attente' / 'payee'): do not "
                  "announce it paid when the user comes back, the provider's "
                  "webhook may not have arrived yet.")))
    if payables:
        routes.append(champs._route(
            "POST", "/paiement/webhook", "Webhook", "Paiement", False, [],
            note=("Called by the payment PROVIDER, never by the frontend: "
                  "it requires a signature only the provider can produce. "
                  "Listed here so the route list stays exhaustive, not to "
                  "be called.")))

    # writableAfterPayment BRICK. This route is generated outside route_map,
    # like the payment ones above: it must therefore join the contract
    # explicitly. Otherwise the fields are marked `postpayment_only`, but the
    # interface has no allowed path to change them.
    postpayment = plans.postpayment_writable_by_entity
    for entite, config in sorted(postpayment.items()):
        fields = list(config["fields"])
        routes.append(champs._route(
            "PUT", f"/{entite.lower()}/{{id}}/apres-paiement",
            "UpdateAfterPayment", entite, False, [config["actor"]],
            request_fields=fields,
            note=("Write reserved to the supervisor role after payment: "
                  f"lets it fill {', '.join(f'`{f}`' for f in fields)}. "
                  "Every field is optional in the body; send only those "
                  "that change. 404 if the record does not exist, 403 for "
                  "any other role.")))
    return devise, payables, prestataire
