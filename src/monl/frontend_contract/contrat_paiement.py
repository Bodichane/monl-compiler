"""Encaissement : les deux routes, la devise, le prestataire, l'après-paiement.

La DEVISE fait partie de l'interface : sans elle, une boutique de Cotonou
affiche des euros sur des francs CFA. Le PRESTATAIRE aussi — « Payer par
carte » et « Payer par Mobile Money » ne se dessinent pas pareil."""

from ..ir import PAYMENT_STATUS_COLUMN
from . import champs


def _paiement_du_contrat(plans, routes):
    """Encaissement : les deux routes, la devise, le prestataire, et ce qui
    reste modifiable APRÈS règlement (point 113)."""
    # BRIQUE PAIEMENT (point 74). Ces deux routes ne sortent PAS de
    # route_map — elles ne naissent pas d'un workflow mais d'une règle
    # `payable` — et le contrat les ignorait donc. Conséquence concrète :
    # l'IA d'interface ne pouvait pas dessiner le bouton de règlement, et
    # se le serait de toute façon interdit, puisque le contrat lui défend
    # d'appeler un chemin absent de `routes`. Une brique que le contrat ne
    # décrit pas est une brique sans interface.
    payables = plans.payable_by_entity
    # BRIQUE 2a : la DEVISE fait partie de l'interface. Sans elle, l'IA écrit
    # « € » parce que c'est ce qu'elle a vu partout ailleurs, et une boutique
    # de Cotonou affiche des euros sur des francs CFA. L'exposant voyage avec
    # le code : c'est lui qui dit s'il faut diviser `montant_centimes` par cent
    # (euro) ou pas du tout (franc CFA).
    devise = plans.payment_currency or {"code": "EUR", "exponent": 2}
    # BRIQUE 2b : le prestataire fait partie de l'interface. « Payer par
    # carte » et « Payer par Mobile Money » ne se dessinent pas pareil, et
    # l'IA écrirait « carte bancaire » par défaut faute de le savoir.
    prestataire = plans.payment_provider or "stripe"
    for entite, champ in sorted(payables.items()):
        # POINT 87 : sous propriété transitive, « appartient » se lit à travers
        # l'intermédiaire, et un enregistrement dont l'intermédiaire a disparu
        # répond 404. L'interface doit connaître les deux, sinon elle traite un
        # 404 comme une erreur technique là où c'est une réponse métier.
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
                  # Le nom `montant_centimes` est conservé (point 95 : le
                  # renommer casserait le bouton « Payer » de tout projet
                  # existant), mais il ne veut PAS dire « centimes » partout :
                  # c'est l'unité mineure de la devise. Le dire est la seule
                  # façon d'empêcher une interface de diviser par cent un
                  # montant en francs CFA.
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
                  # Point 76 : boucler la boucle. Savoir ouvrir un règlement
                  # ne dit pas comment en montrer l'issue ; c'est le champ de
                  # suivi qui la porte, et il n'est PAS à jour au retour du
                  # prestataire (c'est son webhook qui l'écrit, plus tard).
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

    # BRIQUE writableAfterPayment. Cette route est générée hors de route_map,
    # comme celles de paiement ci-dessus : elle doit donc rejoindre le contrat
    # explicitement. Sinon les champs sont bien marqués `postpayment_only`,
    # mais l'interface n'a aucun chemin autorisé pour les modifier.
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
